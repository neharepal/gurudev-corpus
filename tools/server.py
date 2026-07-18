#!/usr/bin/env python3
"""
FastAPI backend for Gurudev Sangrah.

Loads the BGE-M3 embedding model + corpus embeddings once at startup, then
handles POST /ask requests by:
  1. embedding the question,
  2. running MMR retrieval (per ADR-008, ADR-009),
  3. calling the Anthropic API via structured tool-use (per ADR-011), and
  4. returning the validated pydantic response as JSON.

Run:
    ANTHROPIC_API_KEY=... /Users/neharepal/opt/anaconda3/bin/python tools/server.py

Env vars:
    ANTHROPIC_API_KEY   required; per ADR-003 the v1 API key gate
    GURUDEV_BACKEND_PORT optional; default 8765

The chat-app Next.js route (`/api/ask`) calls this backend over HTTP; see
`tools/SERVER_README.md` for the dev workflow.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from gate import InviteAndCapMiddleware
import logging_config  # noqa: E402  # side-effect module

# Wire structured logging early so uvicorn access logs use the same handler.
logging_config.configure()
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import grounding
import intent
import query_translation
import query_understanding
from pagination import paginate, page_for_paragraph_index, is_chapter_start
import retrieve
from llm_client import ChatClient, MissingApiKeyError, pick_model
from prompts import (
    _passage_label,
    build_pravachan_user_message,
    build_reading_user_message,
    build_user_message,
    get_system_prompt,
    get_citation_extraction_prompt,
)
from streaming import sse, sse_heartbeat

import datetime
import json
import re
import uuid
import yaml

PORT = int(os.environ.get("GURUDEV_BACKEND_PORT", "8765"))

# Path to the RFC-004 flag queue file.
# Written once at module load so tests can monkeypatch `server.FLAG_QUEUE_PATH`.
FLAG_QUEUE_PATH: Path = REPO / "03_catalog" / "flag_queue.yaml"


# ---------------------------------------------------------------------------
# Reading-mode helpers
# ---------------------------------------------------------------------------

def _author_display_name(author_id: str) -> str:
    """Convert a catalog author id to a display name.

    gurudev_ranade → 'Shri Gurudev'  (per product spec)
    everything_else → title-case the id with underscores as spaces.
    """
    if author_id == "gurudev_ranade":
        return "Shri Gurudev"
    return author_id.replace("_", " ").title()


def _strip_inline_md(s: str) -> str:
    """Remove markdown emphasis markers from reading text, keeping the words.

    The source markdown uses **bold** / *italic* / `code`; rendered raw they show
    literal asterisks (e.g. "**Preliminary**"). Reading mode wants clean prose, so
    strip the delimiters. Asterisks/backticks only — underscores are left alone
    (they appear in transliteration and ids).
    """
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)   # **bold**
    s = re.sub(r"\*(.+?)\*", r"\1", s)        # *italic*
    return s.replace("`", "")


def _parse_work_text(text_path: Path) -> List[Dict[str, Any]]:
    """Parse a text.md file into a list of paragraph records.

    Each record: {"n": int, "body": str, "chapter": str,
                  "char_start": int, "char_end": int}

    `char_start` and `char_end` are absolute byte offsets into the original
    full `text.md` string (including the front-matter bytes that are stripped
    before parsing). They use the same coordinate system as the chunk
    meta `char_start` / `char_end` produced by the chunker, so callers can
    map a chunk offset directly to the paragraph that contains it.

    Algorithm:
    1. Strip YAML front matter (between the first two '---' fences).
       Record the byte length of the stripped prefix so offsets can be
       added back to produce absolute positions.
    2. Find blocks by iterating blank-line boundaries via re.finditer so
       each block's start position within the post-front-matter body is
       known.
    3. Track the current section heading (any line starting with # ... ##).
    4. Paragraph = a block that is NOT a heading AND has len(stripped) >= 80.
    5. Number paragraphs from 1 across the whole work.
    """
    full_text = text_path.read_text(encoding="utf-8")

    # Strip YAML front matter: content between the very first --- and the
    # closing ---. The front matter always starts at byte 0.
    fm_len = 0  # number of chars consumed by front matter (added back to offsets)
    raw = full_text
    if raw.startswith("---"):
        end = raw.find("\n---\n", 3)
        if end != -1:
            fm_len = end + 4  # length of "---...---\n"
            raw = raw[fm_len:]  # body after front matter

    # Find block boundaries using re.finditer so we track each block's
    # start position within `raw` (and therefore absolute position in `full_text`).
    # Strategy: iterate over the runs of non-blank content separated by \n{2,}.
    # re.split loses positions; instead find all separator spans and infer blocks.
    current_heading: str = ""
    n = 0
    results: List[Dict[str, Any]] = []

    # Build a list of (block_text, raw_start, raw_end) for every inter-separator chunk.
    # raw_start/raw_end are offsets within `raw` (before fm_len is added back).
    block_spans: List[tuple] = []
    pos = 0
    for sep_match in re.finditer(r"\n{2,}", raw):
        block_text = raw[pos:sep_match.start()]
        block_spans.append((block_text, pos, sep_match.start()))
        pos = sep_match.end()
    # Remainder after the last separator (or the whole string if no separators)
    if pos <= len(raw):
        block_spans.append((raw[pos:], pos, len(raw)))

    for (block_raw, raw_start, raw_end) in block_spans:
        block = block_raw.strip()
        if not block:
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.*)", block)
        if heading_match:
            current_heading = _strip_inline_md(heading_match.group(2).strip())
            continue
        # A block that is ONLY a bold line is a section heading (the source uses
        # **Heading** instead of ## in places), e.g. "**Preliminary**".
        bold_only = re.match(r"^\*\*(.+?)\*\*[.:]?$", block)
        if bold_only:
            current_heading = bold_only.group(1).strip()
            continue
        # Skip short/decorative blocks
        if len(block) < 80:
            continue
        n += 1
        # Absolute offsets: raw_start/raw_end are within the post-front-matter
        # body; add fm_len to get absolute offsets in full_text (same coordinate
        # system as chunk meta char_start / char_end).
        results.append({
            "n": n,
            "body": _strip_inline_md(block),
            "chapter": current_heading,
            "char_start": fm_len + raw_start,
            "char_end": fm_len + raw_end,
        })
    return results


# In-process cache of parsed works. Key: (path, lang). Cleared on reload.
_reading_cache: Dict[tuple, List[Dict[str, Any]]] = {}

# Roots under which canonical/aggregated works live. The per-author/per-kind
# layout varies (books/, letters/, lectures/, …), so rather than hardcode every
# (author, kind) pair we glob `<root>/<author>/<kind>/<slug>` as a general
# fallback. This covers works absent from catalog.yaml whose kind isn't `books`
# (e.g. kakasaheb_tulpule/lectures, nimbargi_maharaj/books) — see RUNBOOK R1.
_WORK_ROOTS = ("01_canonical", "02_aggregated")


def _glob_work_dir(slug: str) -> Optional[Path]:
    """Find a work directory named `slug` anywhere under the corpus roots.

    General fallback for works not in catalog.yaml and not under a hardcoded
    candidate dir. Returns the first matching directory that contains at least
    one `<lang>/text.md`, or None.
    """
    for root in _WORK_ROOTS:
        for d in (REPO / root).glob(f"*/*/{slug}"):
            if d.is_dir() and any(
                sub.is_dir() and (sub / "text.md").exists() for sub in d.iterdir()
            ):
                return d
    return None


def _resolve_text_path(slug: str, lang: Optional[str]) -> Optional[Path]:
    """Return the resolved text.md path for (slug, lang), or None if not found.

    This mirrors the lookup logic in read_work() so reading_page_for_offset
    can locate the same file without duplicating catalog loading in hot paths.
    """
    import yaml as _yaml
    catalog_path = REPO / "03_catalog" / "catalog.yaml"
    work_meta = None
    try:
        with open(catalog_path, encoding="utf-8") as f:
            catalog = _yaml.safe_load(f)
        for w in (catalog.get("works") or []):
            if w.get("id") == slug:
                work_meta = w
                break
    except Exception:
        pass

    if work_meta is None:
        candidate_dirs = [
            REPO / "01_canonical" / "gurudev_ranade" / "books" / slug,
            REPO / "01_canonical" / "bhausaheb_maharaj" / "letters" / slug,
            REPO / "01_canonical" / "kakasaheb_tulpule" / "books" / slug,
            REPO / "01_canonical" / "other_authors" / "books" / slug,
            REPO / "02_aggregated" / "biography" / "about_gurudev_ranade" / slug,
        ]
        work_dir = None
        for d in candidate_dirs:
            if d.exists():
                work_dir = d
                break
        if work_dir is None:
            # General fallback: glob the corpus roots for the slug (covers
            # non-`books` kinds and authors not in the hardcoded list).
            work_dir = _glob_work_dir(slug)
        if work_dir is None:
            return None
        langs_on_disk = sorted(
            d.name for d in work_dir.iterdir()
            if d.is_dir() and (d / "text.md").exists()
        )
        resolved_lang = lang if lang and lang in langs_on_disk else (langs_on_disk[0] if langs_on_disk else None)
        if resolved_lang is None:
            return None
        return work_dir / resolved_lang / "text.md"

    available_langs: List[str] = work_meta.get("languages", ["en"])
    resolved_lang = lang if lang and lang in available_langs else available_langs[0]
    work_path_str: str = work_meta.get("path", "")
    if not work_path_str:
        return None
    text_path = REPO / work_path_str.rstrip("/") / resolved_lang / "text.md"
    return text_path if text_path.exists() else None


def reading_page_for_offset(slug: str, lang: Optional[str], char_offset: int) -> Optional[int]:
    """Return the 1-based reading page that contains `char_offset` in (slug, lang).

    `char_offset` must be in the same coordinate system as chunk meta
    `char_start` / `char_end` (absolute offset into the full text.md including
    front matter).  Returns None if the work cannot be resolved or has no
    qualifying paragraphs.

    Uses the same pagination logic as read_work() so
    the page number matches what the reader shows.
    """
    text_path = _resolve_text_path(slug, lang)
    if text_path is None:
        return None

    cache_key = (str(text_path), lang)
    if cache_key not in _reading_cache:
        try:
            _reading_cache[cache_key] = _parse_work_text(text_path)
        except Exception:
            return None
    all_paragraphs = _reading_cache[cache_key]
    if not all_paragraphs:
        return None

    # Find the paragraph whose [char_start, char_end) contains char_offset,
    # or the first paragraph that starts at or after char_offset.
    # Paragraphs are in document order; use a linear scan (fast enough for
    # typical works with hundreds of paragraphs).
    target_idx: Optional[int] = None
    for i, para in enumerate(all_paragraphs):
        if para["char_start"] <= char_offset < para["char_end"]:
            target_idx = i
            break
        if para["char_start"] > char_offset and target_idx is None:
            target_idx = i
            break

    if target_idx is None:
        # char_offset is past the last paragraph — return the last page.
        target_idx = len(all_paragraphs) - 1

    return page_for_paragraph_index(all_paragraphs, target_idx)


def _norm_for_match(s: str) -> str:
    """Normalise text for substring matching across the chunk/reader boundary.

    The verbatim quote `body` and the reader's paragraph text both derive from
    the same `text.md`, but go through slightly different cleaning (chunk garble
    scrub vs `_strip_inline_md`) and carry different whitespace. Collapsing all
    runs of whitespace to a single space and stripping markdown emphasis makes a
    prefix of the quote reliably matchable against the paragraph that contains
    it — independent of the (unreliable) `char_start` offset.
    """
    return re.sub(r"\s+", " ", _strip_inline_md(s)).strip()


def reading_page_for_body(text_path: Path, body: str) -> Optional[int]:
    """Return the 1-based reading page whose paragraph contains `body`.

    Anchors on the verbatim quote TEXT rather than the chunk's `char_start`
    offset. The chunker's `char_start` is a synthetic counter (stripped,
    `\\n\\n`-rejoined paragraphs) that drifts from true `text.md` offsets and
    accumulates error with depth (see docs/RUNBOOK.md R1), so offset-based page
    lookup lands on the wrong page. Searching the parsed paragraphs for the
    quote's leading text is drift-proof: it finds the paragraph the devotee is
    actually looking for.

    Returns None if the text can't be parsed or no paragraph matches.
    """
    if not body:
        return None
    cache_key = (str(text_path), None)
    if cache_key not in _reading_cache:
        try:
            _reading_cache[cache_key] = _parse_work_text(text_path)
        except Exception:
            return None
    paragraphs = _reading_cache[cache_key]
    if not paragraphs:
        return None

    needle = _norm_for_match(body)
    if not needle:
        return None
    # A quote always STARTS inside a single paragraph (even if it later spans
    # boundaries), so a prefix of the quote is contained in that paragraph.
    # Try a generous prefix first, then shorter ones, to tolerate minor
    # cleaning differences near the tail of the window.
    # Try windows taken from progressively LATER in the quote, not only the
    # prefix. A quote may begin with a verse / dohā / bold line that
    # _parse_work_text treats as a section heading and excludes from
    # `paragraphs` (common in pravachan works) — a later window (the prose
    # commentary) still anchors it to the right page. Prefix-first (start=0)
    # preserves the fast common case and its exact prior behaviour.
    for start in (0, 30, 60, 100, 150):
        for win in (60, 40, 24):
            key = needle[start:start + win]
            if len(key) < 12:
                continue
            for i, para in enumerate(paragraphs):
                if key in _norm_for_match(para["body"]):
                    return page_for_paragraph_index(paragraphs, i)
    return None


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    mode: str  # "qa" | "pravachan" | "reading"
    question: str
    lang: Optional[str] = None  # "en" | "mr"; informational, not used for routing
    # Reading-mode scoping.
    work: Optional[str] = None
    passage: Optional[str] = None
    passage_title: Optional[str] = None
    # Reserved for the threaded-follow-up refactor; not used by the single-turn
    # pipeline today. Included so the wire shape doesn't need to change later.
    history: Optional[List[Dict[str, Any]]] = None


class ReportCitation(BaseModel):
    workTitle: str
    location: str
    # RFC-004: quote body included for issue context so reviewers can see what
    # was actually cited. Optional for backward-compat (plain location-only
    # reports from old clients or correction flows still work).
    body: Optional[str] = None


class ReportRequest(BaseModel):
    question: str
    mode: str
    citations: Optional[List[ReportCitation]] = None
    note: Optional[str] = None
    # RFC-004 flag category (radio selection from the UI).
    category: Optional[str] = None
    # RFC-004: full answer text (framing/synthesis joined) so reviewers can
    # see exactly what the model said without re-running the query. Optional
    # for backward-compat.
    answer_text: Optional[str] = None
    # Correction fields (garble Phase 2 — flag-and-queue).
    # All optional so plain issue reports remain backward-compatible.
    kind: Optional[str] = None        # "correction" | "issue" (default None = "issue")
    slug: Optional[str] = None        # work slug
    page: Optional[int] = None        # 1-based page number
    paragraph: Optional[int] = None   # paragraph n value
    original: Optional[str] = None    # verbatim text as rendered
    corrected: Optional[str] = None   # user's corrected text
    lang: Optional[str] = None        # "en" | "mr"
    name: Optional[str] = None        # contributor name (corrections; no login)


# ---------------------------------------------------------------------------
# Lifespan state (loaded once at startup)
# ---------------------------------------------------------------------------


class _State:
    embeddings: np.ndarray
    metas: List[dict]
    manifest: Dict[str, Any]
    model: Any  # sentence_transformers.SentenceTransformer
    model_name: str
    client: ChatClient
    # RFC-017 (Phase 2 small-to-big chunking): parent_id -> {"text": ..., ...}.
    # Empty dict until Task 9's re-embed produces 04_processed/parents.jsonl —
    # NOT yet consumed by `_retrieve` (see expand_children_to_parents docstring).
    parents_by_id: Dict[str, Any]


STATE = _State()


def _embed_query(question: str) -> np.ndarray:
    """Match the embed convention from tune_sweep.embed_with()."""
    name = STATE.model_name
    q = question
    if "e5" in name.lower():
        q = "query: " + q
    vec = STATE.model.encode([q], normalize_embeddings=True, convert_to_numpy=True)
    return vec[0].astype(np.float32)


def _rerank_candidates(question, candidates, reranker_obj, *, top_k):
    """Reorder [(idx, text), ...] by cross-encoder relevance; keep top_k.

    Fail-safe: if the reranker is unavailable or returns the wrong count,
    keep the input order (already MMR-ranked) and just truncate to top_k.
    """
    if not reranker_obj.available() or not candidates:
        return candidates[:top_k]
    texts = [t for _, t in candidates]
    scores = reranker_obj.rerank(question, texts)
    if len(scores) != len(candidates):
        return candidates[:top_k]
    order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    return [candidates[i] for i in order[:top_k]]


def _extra_query_strings(question):
    """Rewrite + HyDE strings to fold into retrieval, per env flags. [] if off."""
    extras = []
    if os.environ.get("ENABLE_QUERY_REWRITE") == "1":
        rw = query_understanding.rewrite_query(question)
        if rw:
            extras.append(rw)
    if os.environ.get("ENABLE_HYDE") == "1":
        hy = query_understanding.hypothetical_doc(question)
        if hy:
            extras.append(hy)
    return extras


def _retrieve(
    question: str,
    *,
    top_k: int,
    candidates: int,
    mmr_lambda: float,
    max_per_source: int,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if metadata_filter:
        mask = np.ones(len(STATE.metas), dtype=bool)
        for k, v in metadata_filter.items():
            mask &= np.array([m.get(k) == v for m in STATE.metas], dtype=bool)
        if not mask.any():
            return []
        keep_idx = np.where(mask)[0]
        sub_emb = STATE.embeddings[keep_idx]
        sub_metas = [STATE.metas[i] for i in keep_idx]
    else:
        keep_idx = None
        sub_emb = STATE.embeddings
        sub_metas = STATE.metas

    # Pre-load subset texts with correct absolute indices so BM25 gets the right document.
    # On the unfiltered path texts=None is fine (index covers the full corpus with identity mapping).
    if keep_idx is not None:
        # Load the full corpus texts ONCE (cached) and subset by absolute index.
        # The old per-chunk load_chunk_text re-scanned chunks.jsonl for every
        # chunk (O(n^2) — ~22s for a 552-chunk work); this is O(1) per chunk.
        _all_texts = retrieve.get_all_chunk_texts(STATE.metas)
        subset_texts = [_all_texts[int(keep_idx[i])] for i in range(len(sub_metas))]
    else:
        subset_texts = None

    qvec = _embed_query(question)
    # Dual-retrieval union (ADR-017): keep each query variant's dense scores as a
    # SEPARATE ranking and RRF-fuse the rankings, rather than MAX-combining into
    # one score array. Under MAX the highest-absolute-cosine variant dominated, so
    # a passage that was rank-1 for the Marathi translation but modest in absolute
    # cosine got diluted out of the top-k. RRF gives each variant's rank-1 full
    # credit.
    #   EN/romanized → Marathi: Devanagari passages compete at monolingual strength.
    #   Devanagari → EN: Gurudev's ~60%-English scholarly works compete likewise.
    # Fail-safe: a variant that doesn't translate is simply absent from the list.
    dense_variants = [sub_emb @ qvec]
    q_dev = query_translation.translate_query(question)
    if q_dev:
        dense_variants.append(sub_emb @ _embed_query(q_dev))
    q_en = query_translation.translate_to_english(question)
    if q_en:
        dense_variants.append(sub_emb @ _embed_query(q_en))
    _extras = _extra_query_strings(question)
    for _e in _extras:
        dense_variants.append(sub_emb @ _embed_query(_e))
    query_intent = intent.classify_intent(question)
    # Tier-weight EACH variant, then fuse. (Tier deltas are additive per chunk, so
    # `scores` — the per-passage max, kept only for the cos_score readout — is
    # identical whether the weight is applied before or after the max.)
    dense_variants = [
        retrieve.apply_intent_tier_weights(d, sub_metas, query_intent)
        for d in dense_variants
    ]
    scores = dense_variants[0] if len(dense_variants) == 1 else np.maximum.reduce(dense_variants)
    cand_n = min(candidates, len(scores))
    # GAP 2 fix: pass translated queries to BM25 so cross-lingual results get a
    # lexical RRF component.  q_dev (Marathi) helps EN queries find Marathi athvani;
    # q_en (English) helps MR queries find English canonical works.
    _bm25_extras = [q for q in ([q_dev, q_en] + _extras) if q]
    fused = retrieve.fused_candidate_scores(
        question, dense_variants[0], sub_metas, texts=subset_texts,
        bm25_queries=_bm25_extras or None,
        extra_dense=dense_variants[1:] or None,
    )
    fused = retrieve.apply_quality_weights(
        fused, sub_metas, enabled=os.environ.get("ENABLE_JUNK_WEIGHT") == "1"
    )
    cand_idx = np.argpartition(-fused, cand_n - 1)[:cand_n]
    cand_idx = cand_idx[np.argsort(-fused[cand_idx])]
    # Use the FUSED (dense+lexical) relevance for MMR ranking + the per-work cap,
    # not raw dense — otherwise a lexically-surfaced chunk (e.g. the idol-worship
    # passage) gets into the pool but loses its work's slot to a higher-dense
    # sibling. MMR's diversity term still uses the embeddings.
    cand_scores = fused[cand_idx]
    import reranker as _reranker_mod
    rerank_on = os.environ.get("ENABLE_RERANK") == "1"
    if rerank_on:
        widen = int(os.environ.get("RERANK_CANDIDATES", str(retrieve.INITIAL_CANDIDATES)))
        pool = cand_idx[:widen]
        # MMR first only to drop near-duplicate OCR chunks, generous cap.
        deduped = retrieve.mmr_rerank(
            qvec, pool, fused[pool], sub_emb, sub_metas,
            top_k=len(pool), mmr_lambda=mmr_lambda, max_per_source=max_per_source,
        )
        cand_pairs = []
        for idx, _mmr in deduped:
            oidx = int(keep_idx[idx]) if keep_idx is not None else int(idx)
            cand_pairs.append((idx, retrieve.load_chunk_text(sub_metas[idx], oidx)))
        top = _rerank_candidates(question, cand_pairs, _reranker_mod.get_reranker(), top_k=top_k)
        reranked = [(idx, 0.0) for idx, _txt in top]  # score slot unused downstream
    else:
        reranked = retrieve.mmr_rerank(
            qvec, cand_idx, cand_scores, sub_emb, sub_metas,
            top_k=top_k, mmr_lambda=mmr_lambda, max_per_source=max_per_source,
        )
    if os.environ.get("ENABLE_SMALL_TO_BIG", "1") != "0" and STATE.parents_by_id:
        # RFC-017 Task 6: group ranked children into distinct parents; the answer
        # model reads the parent (context) while `cite_text` on the meta is the
        # child's precise span for splice. Default ON when parents.jsonl loaded
        # (child index) — set ENABLE_SMALL_TO_BIG=0 to force the flat fallback
        # for the old pre-Phase-2 index, per RFC-017 handover.
        #
        # `max_per_work` restores the pre-Phase-2 breadth guarantee: a single
        # source work (biography, compilation, large canonical) can't grab
        # more than N distinct parent sections in the top-k, so Gurudev's own
        # smaller works get room to surface alongside a big biography. Only
        # applies when the caller HASN'T already restricted to a single work
        # via metadata_filter — in the scoped case (Amar Sandesh Sudha etc.)
        # we want all top-k parents from that one work.
        _max_per_work = None if metadata_filter else 1
        return small_to_big_results(
            reranked, sub_metas, keep_idx, STATE.parents_by_id,
            dense_scores=scores,
            max_per_parent=max_per_source, top_k=top_k,
            max_per_work=_max_per_work,
        )
    out: List[Dict[str, Any]] = []
    for idx, mmr_score in reranked:
        meta = sub_metas[idx]
        original_idx = int(keep_idx[idx]) if keep_idx is not None else int(idx)
        text = retrieve.load_chunk_text(meta, original_idx)
        out.append({
            "meta": meta,
            "text": text,
            "cos_score": float(scores[idx]),
            "mmr_score": float(mmr_score),
        })
    return out


def expand_children_to_parents(ranked_idxs, metas, parents_by_id, *, max_per_parent, top_k):
    """Group ranked child rows into their distinct parents (child-rank order).

    Returns [{parent_id, parent_text, children:[{...}]}] — the parent is the
    context the answer model reads; children are the precise anchors to quote.

    RFC-017 Task 6: called via `small_to_big_results` from `_retrieve` when
    `ENABLE_SMALL_TO_BIG=1`.
    """
    groups, order = {}, []
    for idx in ranked_idxs:
        m = metas[idx]
        pid = m.get("parent_id")
        if pid is None:
            continue
        if pid not in groups:
            if len(order) >= top_k:
                continue
            groups[pid] = {"parent_id": pid,
                           "parent_text": (parents_by_id.get(pid) or {}).get("text", ""),
                           "children": []}
            order.append(pid)
        g = groups[pid]
        if len(g["children"]) < max_per_parent:
            g["children"].append({"child_idx": int(idx),
                                  "text": m.get("cite_text") or m.get("text", "")})
    return [groups[p] for p in order]


_ARTHASAHIT_WORK_IDS = frozenset({
    "tukaram-vachanamrut", "eknath-vachanamrut", "ramdas-vachanamrut",
    "sant-vachanamrut", "jnaneshwar-vachanamrut", "eknathi-bhagvat-vachanamrut",
    "dhyanopakarani-gita",
})


def small_to_big_results(reranked, sub_metas, keep_idx, parents_by_id, *,
                          dense_scores, max_per_parent, top_k,
                          max_per_work: Optional[int] = None):
    """RFC-017 wiring: turn ranked child rows into per-parent output rows.

    Each row's `text` is the PARENT section (context handed to the answer model)
    and `meta` merges the parent's meta with `cite_text` copied from the top-
    matched child so `splice_qa_citations` quotes the precise child span. When
    the top child was retrieval-only (no `cite_text`, e.g. an arthasahit
    uncertain split), the meta is marked `retrieval_only=True` so splice drops
    that citation rather than quoting a parent that may contain the sadhak's
    meaning. Preserves the `{meta, text, cos_score, mmr_score}` shape flat
    retrieval emits, so downstream code (build_user_message, splice,
    _enrich_citation_readpage) stays untouched.

    `max_per_work` caps distinct parent sections per source work_id — restores
    the pre-Phase-2 breadth guarantee that a single work (biography,
    compilation, etc.) can't dominate the top-k. Under unscoped Q&A this is
    typically 1; under scoped Q&A (metadata_filter set) leave as None so all
    top-k parents can come from the one requested work.
    """
    groups: Dict[str, Any] = {}
    order: List[str] = []
    work_counts: Dict[str, int] = {}
    for idx, mmr_score in reranked:
        m = sub_metas[idx]
        pid = m.get("parent_id")
        if pid is None:
            continue
        if pid not in groups:
            if len(order) >= top_k:
                continue
            parent = parents_by_id.get(pid) or {}
            wid = parent.get("work_id") or m.get("work_id") or ""
            # Enforce the per-work cap BEFORE registering the new parent, so
            # a work that already hit its allowance can't claim another slot.
            if max_per_work is not None and wid:
                if work_counts.get(wid, 0) >= max_per_work:
                    continue
            groups[pid] = {
                "parent": parent,
                "children": [],
                "mmr_score": float(mmr_score),
                "cos_score": float(dense_scores[idx]),
            }
            order.append(pid)
            if wid:
                work_counts[wid] = work_counts.get(wid, 0) + 1
        g = groups[pid]
        if len(g["children"]) < max_per_parent:
            g["children"].append(m)
    out: List[Dict[str, Any]] = []
    for pid in order:
        g = groups[pid]
        parent = g["parent"]
        top_child = g["children"][0] if g["children"] else {}
        cite = top_child.get("cite_text")
        meta = dict(parent)
        meta["parent_id"] = pid
        is_arthasahit = parent.get("work_id") in _ARTHASAHIT_WORK_IDS
        if cite:
            meta["cite_text"] = cite
            # Only arthasahit citations must be capped to cite_text — for prose,
            # splice reads from the parent so the LLM can quote 2–4 sentences of
            # context (RFC-017 refinement post-live-eval).
            if is_arthasahit:
                meta["restrict_to_cite"] = True
        elif is_arthasahit:
            # Arthasahit child with no cite_text = the verse/meaning split was
            # uncertain; never cite it (would risk quoting the sadhak's meaning).
            meta["retrieval_only"] = True
        # Non-arthasahit child without cite_text is unusual (regular chunker
        # sets cite_text on every child) but not fatal — splice will fall
        # through to chunk["text"] (the parent).
        out.append({
            "meta": meta,
            "text": parent.get("text", ""),
            "cos_score": g["cos_score"],
            "mmr_score": g["mmr_score"],
        })
    return out


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


app = FastAPI(title="Gurudev Sangrah backend", version="0.1.0")

# CORS: comma-separated list from FRONTEND_ORIGIN env; defaults to the local
# Next.js dev server so `make dev` still works. In production
# (RFC-016 §3), set FRONTEND_ORIGIN=https://<your-vercel-domain> — no other
# origin can drive the paid backend. Multiple deploys (prod + preview) can be
# comma-separated.
_cors_origins = [
    o.strip()
    for o in os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# RFC-016 §3 light gate: invite-code header check + hard daily cap on /ask.
# Both are no-ops when their env vars are unset, so `make dev` isn't affected.
# Middlewares run outermost-first: CORS handles preflight before the gate ever
# sees the request (preflights carry no auth headers by design).
app.add_middleware(InviteAndCapMiddleware)


PARENTS_PATH = REPO / "04_processed" / "parents.jsonl"


def _load_parents_by_id() -> Dict[str, Any]:
    """Load `04_processed/parents.jsonl` (RFC-017) into a parent_id -> row dict.

    Returns {} if the file doesn't exist yet (it won't until Task 9's re-embed
    produces parent/child chunks) or is unreadable — this must never block
    startup or corpus reload on today's flat-chunk corpus.
    """
    if not PARENTS_PATH.exists():
        return {}
    out: Dict[str, Any] = {}
    try:
        with PARENTS_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                pid = row.get("id") or row.get("parent_id")
                if pid:
                    out[pid] = row
    except Exception as e:
        print(f"[startup] WARNING: failed to load {PARENTS_PATH}: {e}", file=sys.stderr)
        return {}
    return out


def _load_corpus_into_state() -> Dict[str, Any]:
    """(Re)load embeddings + metadata + manifest from disk into STATE.

    Shared by startup and POST /admin/reload, so a re-embed (tools/embedder.py)
    can be picked up live without a full restart. The embedding MODEL is left
    untouched — it is corpus-independent and stays warm across reloads. If the
    manifest's embedding model itself changed, a full restart is still required;
    the returned dict flags that via `model_changed`.
    """
    t = time.time()
    embeddings, metas, manifest = retrieve.load_corpus()
    prev_model = getattr(STATE, "model_name", None)
    new_model = manifest.get("model", "BAAI/bge-m3")
    # Swap references in. These assignments are individually atomic; reload is
    # intended for a quiet admin moment after ingestion, not under load.
    STATE.embeddings = embeddings
    STATE.metas = metas
    STATE.manifest = manifest
    STATE.model_name = new_model
    # RFC-017: parents.jsonl doesn't exist until Task 9's re-embed; guarded to
    # {} so this is a no-op on today's corpus. Not yet read by `_retrieve`.
    STATE.parents_by_id = _load_parents_by_id()
    # Works catalog: one row per distinct work_id, powers query_understanding's
    # substring/LLM detection of "the query is about a specific book". Built
    # once at load time; ~100 rows, trivial memory.
    works: Dict[str, Dict[str, Any]] = {}
    for m in metas:
        wid = m.get("work_id")
        if wid and wid not in works:
            works[wid] = {
                "work_id": wid,
                "title": m.get("title"),
                "title_en": m.get("title_en"),
                "title_translit": m.get("title_translit"),
            }
    STATE.works_catalog = list(works.values())
    return {
        "chunks": len(metas),
        "dim": int(embeddings.shape[1]),
        "model": new_model,
        "model_changed": prev_model is not None and prev_model != new_model,
        "load_seconds": round(time.time() - t, 2),
    }


@app.on_event("startup")
def _load_everything() -> None:
    # Fail fast if the API key is missing — the server has nothing to do without it.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingApiKeyError(
            "ANTHROPIC_API_KEY is not set. Per ADR-003, the chat backend uses "
            "the Anthropic API. Export ANTHROPIC_API_KEY before starting the server."
        )

    print("[startup] loading corpus...", file=sys.stderr)
    info = _load_corpus_into_state()
    print(
        f"[startup] {info['chunks']} chunks (dim={info['dim']}) "
        f"in {info['load_seconds']}s",
        file=sys.stderr,
    )

    print(f"[startup] loading embedding model: {STATE.model_name}", file=sys.stderr)
    t = time.time()
    from sentence_transformers import SentenceTransformer
    STATE.model = SentenceTransformer(STATE.model_name, trust_remote_code=True)
    print(f"[startup] model ready in {time.time() - t:.1f}s", file=sys.stderr)

    # Warm-up embed: the first encode() call does lazy tokenizer/forward-pass
    # init that otherwise lands on the first real user query (~10s of cold
    # latency). Pay it here at startup instead.
    t = time.time()
    _embed_query("warm up the embedding model")
    print(f"[startup] embed warm-up in {time.time() - t:.1f}s", file=sys.stderr)

    # Build the BM25 lexical index now (it's otherwise built lazily on the FIRST
    # query — a ~12-15s cold-start that lands on whoever asks first). Pay it here.
    t = time.time()
    retrieve._get_or_build_bm25_index(STATE.metas)
    print(f"[startup] BM25 index build in {time.time() - t:.1f}s", file=sys.stderr)

    STATE.client = ChatClient()
    print("[startup] ready", file=sys.stderr)


@app.get("/health")
def health() -> Dict[str, Any]:
    """LB-style health probe (RFC-016 §4 + scale-ready seam).

    Returns 200 with `status`:
      - "warming"  — startup hasn't finished (model/BM25 still loading)
      - "ready"    — serving traffic
      - "degraded" — running but a subsystem is off (e.g. parents.jsonl absent,
                     small-to-big disabled but flag was on)

    Callable without the invite header; middleware allowlists /health. Load
    balancers should require "ready" before routing traffic.
    """
    embeddings = getattr(STATE, "embeddings", None)
    metas = getattr(STATE, "metas", None) or []
    model_ready = getattr(STATE, "model", None) is not None
    parents_ready = bool(getattr(STATE, "parents_by_id", None))

    if embeddings is None or not model_ready or not metas:
        status = "warming"
    elif not parents_ready and os.environ.get("ENABLE_SMALL_TO_BIG", "1") != "0":
        # Flag says small-to-big should be on, but no parents.jsonl loaded.
        status = "degraded"
    else:
        status = "ready"

    # Include the gate/cap counter so a future admin dashboard can render it.
    gate_status: Dict[str, Any] = {}
    for m in getattr(app, "user_middleware", []) or []:
        cls = getattr(m, "cls", None)
        if cls is InviteAndCapMiddleware:
            # Middleware is instantiated by starlette; find the live instance.
            # (No supported public API — pull from app.middleware_stack lazily.)
            stack = getattr(app, "middleware_stack", None)
            gate_status = _resolve_gate_status(stack)
            break

    return {
        "status": status,
        "model": getattr(STATE, "model_name", None),
        "chunks": len(metas),
        "parents_loaded": len(getattr(STATE, "parents_by_id", None) or {}),
        "gate": gate_status,
    }


def _resolve_gate_status(node) -> Dict[str, Any]:
    """Walk starlette's middleware chain to find the live InviteAndCapMiddleware
    instance and return its status() dict. Silent no-op if the chain isn't
    built yet (during initial reload) or the instance can't be found."""
    while node is not None:
        if isinstance(node, InviteAndCapMiddleware):
            try:
                return node.status()
            except Exception:
                return {}
        node = getattr(node, "app", None)
    return {}


@app.post("/admin/reload")
def admin_reload() -> Dict[str, Any]:
    """Re-read the on-disk embeddings index into memory — no full restart.

    Run this after re-embedding (tools/embedder.py) so newly ingested works
    become retrievable in the live server. Returns before/after chunk counts.
    If the manifest's embedding model changed, `model_changed` is true and a
    full restart is still needed to load the new model.

    Note: the server binds 0.0.0.0, so this route is reachable on the LAN. It is
    not destructive (it only re-reads local files), but if that exposure matters
    in your deployment, front it with auth or bind to localhost.
    """
    _reading_cache.clear()
    retrieve._BM25_CACHE.clear()
    retrieve._TEXTS_CACHE.clear()
    global _works_cache
    _works_cache = None
    before = len(getattr(STATE, "metas", []) or [])
    info = _load_corpus_into_state()
    info["chunks_before"] = before
    print(f"[reload] {before} -> {info['chunks']} chunks", file=sys.stderr)
    if info["model_changed"]:
        print(
            "[reload] WARNING: manifest embedding model changed "
            f"to {info['model']!r}; a full restart is required to load it.",
            file=sys.stderr,
        )
    return {"ok": True, **info}


# In-process cache for the /works list. Populated lazily on the first request;
# cleared alongside _reading_cache in /admin/reload so a new ingestion is
# visible without a restart.
_works_cache: Optional[List[Dict[str, Any]]] = None


def _humanize_slug(slug: str) -> str:
    """Convert a work slug to a display title when meta.yaml has no title."""
    return slug.replace("-", " ").title()


def _scan_readable_works() -> List[Dict[str, Any]]:
    """Walk 01_canonical and return metadata for every work with a text.md.

    Canonical structure:
        01_canonical/<author_id>/<work_type>/<work_id>/<lang>/text.md
    A work is readable iff at least one <lang>/text.md exists.
    Title and author are read from <work_id>/meta.yaml if present;
    the author display name is formatted via _author_display_name().
    Returns a list of dicts sorted by title (case-insensitive).
    """
    canonical_root = REPO / "01_canonical"
    results: List[Dict[str, Any]] = []
    # Guard: canonical_root must exist (it always does in the corpus, but
    # be defensive so the endpoint doesn't 500 in a stripped test env).
    if not canonical_root.exists():
        return results

    for author_dir in sorted(canonical_root.iterdir()):
        if not author_dir.is_dir():
            continue
        author_id = author_dir.name
        for work_type_dir in sorted(author_dir.iterdir()):
            if not work_type_dir.is_dir():
                continue
            for work_dir in sorted(work_type_dir.iterdir()):
                if not work_dir.is_dir():
                    continue
                # Collect language subdirectories that have a text.md.
                langs = sorted(
                    d.name for d in work_dir.iterdir()
                    if d.is_dir() and (d / "text.md").exists()
                )
                if not langs:
                    continue
                work_id = work_dir.name
                # Try to read meta.yaml for proper title and author override.
                meta_path = work_dir / "meta.yaml"
                title: str = _humanize_slug(work_id)
                meta_author_id = author_id
                if meta_path.exists():
                    try:
                        with open(meta_path, encoding="utf-8") as fh:
                            meta = yaml.safe_load(fh) or {}
                        # Prefer title_en if set, else title.
                        raw_title = (meta.get("title_en") or "").strip() or (meta.get("title") or "").strip()
                        if raw_title:
                            title = raw_title
                        # meta.yaml may override the author (rare but possible).
                        if meta.get("author"):
                            meta_author_id = meta["author"]
                    except Exception:
                        pass
                results.append({
                    "slug": work_id,
                    "title": title,
                    "author": _author_display_name(meta_author_id),
                    "languages": langs,
                })

    results.sort(key=lambda w: w["title"].lower())
    return results


@app.get("/works")
def list_works() -> Dict[str, Any]:
    """Return all canonical works that have at least one readable text.md.

    Response: { "works": [ { "slug", "title", "author", "languages" }, ... ] }
    Sorted by title (case-insensitive). Result is cached in-process;
    /admin/reload clears the cache so newly ingested works appear.
    """
    global _works_cache
    if _works_cache is None:
        _works_cache = _scan_readable_works()
    return {"works": _works_cache}


@app.post("/report")
def report_issue(req: ReportRequest) -> Dict[str, Any]:
    """Append a flagged-answer report to the RFC-004 YAML flag queue.

    Accepts: { question, mode, citations?, note?, category?,
               kind?, slug?, page?, paragraph?, original?, corrected?, lang? }
    Returns: { ok: true }

    Each report is one mapping appended to FLAG_QUEUE_PATH
    (03_catalog/flag_queue.yaml).  FLAG_QUEUE_PATH is a module-level constant
    so tests can monkeypatch it.

    Both plain issue reports and F18 in-reader corrections write to this
    same queue; the `kind` field distinguishes them ("issue" vs "correction").
    """
    FLAG_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Serialize citations, keeping body when present so reviewers see the quoted text.
    serialized_citations = [
        {k: v for k, v in c.model_dump().items() if v is not None}
        for c in (req.citations or [])
    ]
    entry: Dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "flagged_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "pending",
        "kind": req.kind or "issue",
        "question": req.question,
        "mode": req.mode,
        "citations": serialized_citations,
        "category": req.category or "",
        "note": req.note or "",
        "lang": req.lang or "",
    }
    # Persist the full answer text for reviewer context (RFC-004).
    if req.answer_text is not None:
        entry["answer_text"] = req.answer_text
    # Correction-specific fields — only included when the caller sends them.
    if req.slug is not None:
        entry["slug"] = req.slug
    if req.page is not None:
        entry["page"] = req.page
    if req.paragraph is not None:
        entry["paragraph"] = req.paragraph
    if req.original is not None:
        entry["original"] = req.original
    if req.corrected is not None:
        entry["corrected"] = req.corrected
    # Contributor name — who suggested this (no login), for the review queue.
    if req.name:
        entry["name"] = req.name

    # Append to the YAML list safely:
    # read existing content → parse as list (or default to []) → append → dump.
    existing: List[Dict[str, Any]] = []
    if FLAG_QUEUE_PATH.exists():
        try:
            raw = yaml.safe_load(FLAG_QUEUE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                existing = raw
        except Exception:
            existing = []
    existing.append(entry)
    FLAG_QUEUE_PATH.write_text(
        yaml.dump(existing, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin flag-queue helpers
# ---------------------------------------------------------------------------

def _load_flag_queue() -> List[Dict[str, Any]]:
    """Load all entries from FLAG_QUEUE_PATH, backfilling ids for legacy entries."""
    if not FLAG_QUEUE_PATH.exists():
        return []
    try:
        raw = yaml.safe_load(FLAG_QUEUE_PATH.read_text(encoding="utf-8"))
        entries: List[Dict[str, Any]] = raw if isinstance(raw, list) else []
    except Exception:
        entries = []
    # Backfill stable ids for legacy entries that predate the id field.
    changed = False
    for i, e in enumerate(entries):
        if not e.get("id"):
            ts = e.get("flagged_at", "unknown")
            e["id"] = f"{ts}-{i}"
            changed = True
    if changed:
        _save_flag_queue(entries)
    return entries


def _save_flag_queue(entries: List[Dict[str, Any]]) -> None:
    """Atomically rewrite FLAG_QUEUE_PATH."""
    FLAG_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = FLAG_QUEUE_PATH.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.dump(entries, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    tmp.replace(FLAG_QUEUE_PATH)


def _append_flags(flags: List[Dict[str, Any]], req: "AskRequest") -> None:
    """Append auto-verify flags (from grounding.verify_citations) to the flag queue.

    Reuses the same FLAG_QUEUE_PATH read/append/write path as /report and the
    F18 correction flow, so these show up in the same review queue. Each flag
    record from grounding.verify_citations has passage/workTitle/score/reason;
    `source: "auto-verify"` distinguishes these from user-submitted reports.
    No-op when `flags` is empty (never touches the file for the common case).
    """
    if not flags:
        return
    entries = _load_flag_queue()
    for f in flags:
        entries.append({
            "id": uuid.uuid4().hex[:12],
            "flagged_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": "pending",
            "kind": "issue",
            "source": "auto-verify",
            "question": req.question,
            "mode": req.mode,
            "passage": f.get("passage", ""),
            "workTitle": f.get("workTitle", ""),
            "score": f.get("score"),
            "note": f.get("reason", ""),
        })
    _save_flag_queue(entries)


# ---------------------------------------------------------------------------
# Admin dashboard routes
# ---------------------------------------------------------------------------

_ADMIN_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Flag Queue — Gurudev Corpus</title>
<style>
  :root {
    --bg: #fdf6e3; --card: #fffdf5; --border: #d6c89a;
    --txt: #3b2e0f; --muted: #7a6940; --accent: #5a4a1c;
    --green: #2d6a2d; --red: #8b1a1a; --gray: #666;
    --diff-add: #e6ffe6; --diff-add-txt: #1a4d1a;
    --diff-del: #ffe6e6; --diff-del-txt: #6b0000;
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 20px; background: var(--bg); color: var(--txt);
         font-family: Georgia, 'Times New Roman', serif; font-size: 15px; }
  h1 { font-size: 1.5rem; color: var(--accent); margin: 0 0 4px; }
  .subtitle { color: var(--muted); font-size: 0.85rem; margin-bottom: 20px; }
  .filters { margin-bottom: 16px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  .filters label { font-size: 0.85rem; color: var(--muted); }
  .filters select { font-size: 0.85rem; padding: 4px 8px; border: 1px solid var(--border);
                    border-radius: 4px; background: var(--card); color: var(--txt); }
  #count { color: var(--muted); font-size: 0.85rem; margin-left: auto; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
          padding: 14px 16px; margin-bottom: 12px; }
  .card-header { display: flex; gap: 10px; align-items: flex-start; flex-wrap: wrap; }
  .badge { display: inline-block; font-size: 0.72rem; font-family: monospace; font-weight: bold;
           padding: 2px 7px; border-radius: 3px; text-transform: uppercase; white-space: nowrap; }
  .badge-correction { background: #fff3cd; color: #7a5000; border: 1px solid #d4a820; }
  .badge-issue      { background: #e8ecff; color: #1a2a80; border: 1px solid #5060c0; }
  .badge-pending    { background: #f0f0f0; color: #555; border: 1px solid #bbb; }
  .badge-approved   { background: #d4edda; color: #155724; border: 1px solid #6db87a; }
  .badge-rejected   { background: #f8d7da; color: #721c24; border: 1px solid #e07a80; }
  .meta { color: var(--muted); font-size: 0.8rem; font-family: monospace; }
  .slug { color: var(--accent); font-weight: bold; font-size: 0.9rem; }
  .diff-block { margin: 10px 0; border: 1px solid var(--border); border-radius: 4px;
                overflow: hidden; font-family: monospace; font-size: 0.82rem; }
  .diff-del { background: var(--diff-del); color: var(--diff-del-txt); padding: 6px 10px;
              white-space: pre-wrap; word-break: break-word; }
  .diff-add { background: var(--diff-add); color: var(--diff-add-txt); padding: 6px 10px;
              white-space: pre-wrap; word-break: break-word; }
  .diff-label { font-size: 0.7rem; color: var(--muted); padding: 2px 10px;
                background: #f5f0e0; border-bottom: 1px solid var(--border); }
  .note-block { font-size: 0.85rem; color: var(--txt); margin: 8px 0; line-height: 1.5; }
  .note-label { font-weight: bold; color: var(--accent); }
  .actions { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  button { padding: 5px 14px; border-radius: 4px; border: none; cursor: pointer;
           font-size: 0.85rem; font-family: inherit; font-weight: bold; transition: opacity 0.15s; }
  button:hover { opacity: 0.82; }
  .btn-approve { background: var(--green); color: #fff; }
  .btn-reject  { background: var(--red); color: #fff; }
  .btn-reset   { background: #888; color: #fff; }
  .msg { font-size: 0.8rem; color: var(--muted); margin-left: 6px; }
  .err { color: var(--red); }
  #toast { position: fixed; top: 14px; right: 18px; background: #333; color: #fff;
           padding: 8px 18px; border-radius: 5px; font-size: 0.85rem;
           opacity: 0; transition: opacity 0.3s; pointer-events: none; z-index: 1000; }
  #toast.show { opacity: 1; }
  .empty { color: var(--muted); font-style: italic; padding: 30px 0; text-align: center; }
  .at { font-size: 0.75rem; color: var(--gray); font-family: monospace; }
</style>
</head>
<body>
<h1>Flag Queue</h1>
<div class="subtitle">Gurudev Corpus — maintainer review dashboard</div>
<div class="filters">
  <label>Kind: <select id="fKind">
    <option value="">All</option>
    <option value="correction">Correction</option>
    <option value="issue">Issue</option>
  </select></label>
  <label>Status: <select id="fStatus">
    <option value="">All</option>
    <option value="pending">Pending</option>
    <option value="approved">Approved</option>
    <option value="rejected">Rejected</option>
  </select></label>
  <span id="count"></span>
</div>
<div id="list"><p class="empty">Loading…</p></div>
<div id="toast"></div>
<script>
let ALL = [];

function escHtml(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function showToast(msg, isErr) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.background = isErr ? '#8b1a1a' : '#2d6a2d';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

function statusBadge(s) {
  s = s || 'pending';
  return `<span class="badge badge-${s}">${s}</span>`;
}

function kindBadge(k) {
  return `<span class="badge badge-${k}">${k}</span>`;
}

function renderDiff(original, corrected) {
  return `<div class="diff-block">
    <div class="diff-label">BEFORE</div>
    <div class="diff-del">${escHtml(original)}</div>
    <div class="diff-label">AFTER</div>
    <div class="diff-add">${escHtml(corrected)}</div>
  </div>`;
}

function renderEntry(e) {
  const kind = e.kind || 'issue';
  const status = e.status || 'pending';
  let body = '';
  if (kind === 'correction') {
    const slug = e.slug || '';
    const pg = e.page != null ? `p.${e.page}` : '';
    const para = e.paragraph != null ? `¶${e.paragraph}` : '';
    const lang = e.lang ? ` [${e.lang}]` : '';
    body += `<div style="margin:6px 0"><span class="slug">${escHtml(slug)}</span>`;
    if (pg || para) body += ` <span class="meta">${pg} ${para}</span>`;
    body += `<span class="meta">${escHtml(lang)}</span></div>`;
    if (e.original != null || e.corrected != null) {
      body += renderDiff(e.original || '', e.corrected || '');
    }
  } else {
    if (e.category) body += `<div class="note-block"><span class="note-label">Category:</span> ${escHtml(e.category)}</div>`;
    if (e.note) body += `<div class="note-block"><span class="note-label">Note:</span> ${escHtml(e.note)}</div>`;
    if (e.question) body += `<div class="note-block"><span class="note-label">Question:</span> ${escHtml(e.question)}</div>`;
    if (e.answer_text) body += `<div class="note-block"><span class="note-label">Answer:</span> <span style="white-space:pre-wrap">${escHtml(e.answer_text)}</span></div>`;
    if (e.citations && e.citations.length) {
      body += `<div class="note-block"><span class="note-label">Citations:</span></div>`;
      for (const c of e.citations) {
        body += `<div class="diff-block" style="margin:4px 0 8px 0">`;
        body += `<div class="diff-label">${escHtml(c.workTitle)} · ${escHtml(c.location)}</div>`;
        if (c.body) body += `<div class="diff-add" style="background:var(--card)">${escHtml(c.body)}</div>`;
        body += `</div>`;
      }
    }
  }
  const flaggedAt = e.flagged_at ? `<span class="at" title="${escHtml(e.flagged_at)}">${e.flagged_at.slice(0,19).replace('T',' ')} UTC</span>` : '';
  const by = e.name ? `✍ ${escHtml(e.name)}` : '';
  const entryId = escHtml(e.id || '');
  return `<div class="card" id="entry-${entryId}" data-kind="${kind}" data-status="${status}">
  <div class="card-header">
    ${kindBadge(kind)}
    ${statusBadge(status)}
    <span class="meta" style="margin-left:auto">${by ? by + ' · ' : ''}${flaggedAt}</span>
  </div>
  ${body}
  <div class="actions" id="actions-${entryId}">
    <button class="btn-approve" onclick="setStatus('${entryId}','approved')">Approve</button>
    <button class="btn-reject"  onclick="setStatus('${entryId}','rejected')">Reject</button>
    <button class="btn-reset"   onclick="setStatus('${entryId}','pending')">Reset</button>
    <span class="msg" id="msg-${entryId}"></span>
  </div>
</div>`;
}

async function setStatus(id, status) {
  const msgEl = document.getElementById('msg-' + id);
  msgEl.textContent = 'Saving…'; msgEl.className = 'msg';
  try {
    const resp = await fetch('/admin/flags/' + encodeURIComponent(id) + '/status', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({status}),
    });
    if (!resp.ok) { throw new Error(await resp.text()); }
    const entry = ALL.find(e => e.id === id);
    if (entry) entry.status = status;
    const card = document.getElementById('entry-' + id);
    if (card) {
      card.dataset.status = status;
      card.querySelector('.badge-pending, .badge-approved, .badge-rejected').outerHTML =
        `<span class="badge badge-${status}">${status}</span>`;
    }
    msgEl.textContent = 'Saved'; msgEl.className = 'msg';
    showToast('Status set to ' + status);
    applyFilters();
  } catch(err) {
    msgEl.textContent = 'Error: ' + err.message; msgEl.className = 'msg err';
    showToast('Failed: ' + err.message, true);
  }
}

function applyFilters() {
  const fKind = document.getElementById('fKind').value;
  const fStatus = document.getElementById('fStatus').value;
  let visible = 0;
  const cards = document.querySelectorAll('.card');
  cards.forEach(c => {
    const ok = (!fKind || c.dataset.kind === fKind) &&
               (!fStatus || c.dataset.status === fStatus);
    c.style.display = ok ? '' : 'none';
    if (ok) visible++;
  });
  document.getElementById('count').textContent = `Showing ${visible} of ${ALL.length}`;
}

async function load() {
  try {
    const resp = await fetch('/admin/flags.json');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    ALL = await resp.json();
    const list = document.getElementById('list');
    if (!ALL.length) { list.innerHTML = '<p class="empty">No flagged entries yet.</p>'; return; }
    // newest first
    const sorted = [...ALL].sort((a,b) => (b.flagged_at||'').localeCompare(a.flagged_at||''));
    list.innerHTML = sorted.map(renderEntry).join('');
    applyFilters();
  } catch(err) {
    document.getElementById('list').innerHTML = `<p class="empty err">Failed to load: ${err.message}</p>`;
  }
}

document.getElementById('fKind').addEventListener('change', applyFilters);
document.getElementById('fStatus').addEventListener('change', applyFilters);
load();
</script>
</body>
</html>
"""


@app.get("/admin/flags")
def admin_flags_dashboard():
    """Serve the maintainer flag-review dashboard (self-contained HTML)."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=_ADMIN_DASHBOARD_HTML, status_code=200)


_ADMIN_ACTIVITY_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Activity — Gurudev Sangrah</title>
<style>
  :root { --bg:#f5f1e6; --card:#fffdf6; --border:#c4b895; --txt:#2d2410;
          --muted:#665741; --accent:#8b5a2b; --ok:#4b6b34; --warn:#8b5a1a;
          --err:#8b3a3a; }
  * { box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: var(--bg);
         color: var(--txt); margin: 0; padding: 26px 22px; }
  h1 { font-family: Georgia, serif; margin: 0 0 4px; font-size: 1.4rem; }
  .subtitle { color: var(--muted); margin-bottom: 18px; font-size: 0.85rem; }
  .filters { margin: 8px 0 20px; display: flex; gap: 14px; flex-wrap: wrap;
             align-items: center; font-size: 0.9rem; }
  .filters input, .filters select { padding: 4px 8px; border: 1px solid var(--border);
              border-radius: 3px; background: var(--card); font: inherit; }
  #count { color: var(--muted); font-size: 0.85rem; }
  table { width: 100%; border-collapse: collapse; background: var(--card);
          border: 1px solid var(--border); border-radius: 4px; overflow: hidden;
          font-size: 0.85rem; }
  th, td { padding: 6px 10px; text-align: left; vertical-align: top;
           border-bottom: 1px solid #eae0c2; }
  th { background: #f0e8cf; font-weight: 600; color: var(--muted);
       font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }
  tr:last-child td { border-bottom: none; }
  td.name { color: var(--accent); font-weight: 600; }
  td.time { color: var(--muted); font-family: monospace; font-size: 0.75rem;
            white-space: nowrap; }
  td.q { max-width: 480px; overflow: hidden; text-overflow: ellipsis;
         white-space: nowrap; }
  td.q:hover { white-space: normal; word-break: break-word; }
  td.ms { text-align: right; font-family: monospace; font-size: 0.78rem;
          color: var(--muted); }
  td.status { font-family: monospace; font-size: 0.75rem; }
  .st-2, .st-1 { color: var(--ok); }
  .st-4 { color: var(--warn); }
  .st-5 { color: var(--err); }
  .pill { display: inline-block; padding: 1px 6px; border-radius: 8px;
          background: #eae0c2; font-size: 0.7rem; color: var(--muted); }
  .empty { color: var(--muted); font-style: italic; padding: 30px 0;
           text-align: center; }
  .row-toggle { cursor: pointer; color: var(--accent); user-select: none;
                font-family: monospace; font-size: 0.9rem; }
  .row-detail { display: none; background: #f9f2dc; }
  .row-detail.open { display: table-row; }
  .row-detail-cell { padding: 12px 20px; border-bottom: 1px solid #d4c69a; }
  .ans-framing { font-family: Georgia, serif; line-height: 1.5;
                 margin: 4px 0 12px; color: var(--txt); }
  .ans-cite { border-left: 3px solid var(--accent); margin: 8px 0;
              padding: 6px 12px; background: #fffdf6; }
  .ans-cite-body { font-family: Georgia, serif; font-style: italic;
                   line-height: 1.5; color: var(--txt); font-size: 0.92rem; }
  .ans-cite-attr { font-size: 0.78rem; color: var(--muted); margin-top: 4px; }
  .ans-synth { font-family: Georgia, serif; line-height: 1.5;
               margin: 12px 0 4px; color: var(--txt); }
  .ans-label { font-size: 0.7rem; text-transform: uppercase;
               letter-spacing: 0.05em; color: var(--muted);
               margin: 12px 0 4px; font-weight: 600; }
  .retrieved-list { font-family: monospace; font-size: 0.72rem;
                    color: var(--muted); line-height: 1.5; }
  .retrieved-item { padding: 2px 0; }
  .retrieved-item .wid { color: var(--accent); }
</style></head><body>
<h1>Activity Log</h1>
<div class="subtitle">Gurudev Corpus — who is using the app, in real time</div>
<div class="filters">
  <label>Name: <input id="fName" placeholder="filter by name…"></label>
  <label>Path: <select id="fPath">
    <option value="">All</option>
    <option value="/ask">/ask</option>
    <option value="/report">/report</option>
  </select></label>
  <span id="count"></span>
  <a href="#" id="pauseBtn" style="color:var(--accent); text-decoration:none; cursor:pointer">⏸ Pause auto-refresh</a>
  <span style="margin-left:auto"><a href="/admin/flags" style="color:var(--accent)">Flag Queue →</a></span>
</div>
<table>
  <thead><tr>
    <th></th><th>Time (PT)</th><th>Name</th><th>Path</th><th>Question</th>
    <th>Mode</th><th>Lang</th><th style="text-align:right">ms</th><th>Status</th>
  </tr></thead>
  <tbody id="rows"><tr><td colspan="9" class="empty">Loading…</td></tr></tbody>
</table>
<script>
let ALL = [];
// Set of `ts` strings for rows the user has expanded. Stable across the 15s
// auto-refresh so a details pane doesn't snap shut mid-read (was: the render
// replaced tbody innerHTML wholesale, losing every .open class + resetting
// every ▾ triangle back to ▸).
const OPEN = new Set();
// Pause auto-refresh while the user is actively interacting — prevents any
// jitter/collapse even if we ever regress the OPEN-state preservation.
let PAUSED = false;
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
// Stable per-row key. Timestamp is unique enough within a session (microsecond
// precision on the server) and survives the auto-refresh cycle unchanged.
function rowKey(e) { return e.ts || ''; }
function render() {
  const fn = (document.getElementById('fName').value || '').toLowerCase();
  const fp = document.getElementById('fPath').value;
  const rows = document.getElementById('rows');
  const filtered = ALL.filter(e =>
    (!fn || (e.name || '').toLowerCase().includes(fn)) &&
    (!fp || e.path === fp)
  );
  document.getElementById('count').textContent =
    `Showing ${filtered.length} of ${ALL.length}`;
  if (!filtered.length) {
    rows.innerHTML = '<tr><td colspan="9" class="empty">No entries.</td></tr>';
    return;
  }
  rows.innerHTML = filtered.map((e) => {
    const key = rowKey(e);
    const isOpen = OPEN.has(key);
    const st = e.status || 0;
    const stCls = 'st-' + Math.floor(st / 100);
    let t = '';
    if (e.ts) {
      try {
        t = new Date(e.ts).toLocaleString('en-US', {
          timeZone: 'America/Los_Angeles',
          year: 'numeric', month: '2-digit', day: '2-digit',
          hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
        }).replace(',', '');
      } catch (_) { t = e.ts.slice(0,19).replace('T',' '); }
    }
    const tCell = `<span title="${esc(e.ts || '')}">${esc(t)}</span>`;
    const q = e.question || '';
    const noteBadge = e.category
      ? ` <span class="pill">${esc(e.category)}</span>` : '';
    const expandable = e.answer || (e.retrieved && e.retrieved.length);
    const glyph = isOpen ? '▾' : '▸';
    const toggle = expandable
      ? `<span class="row-toggle" onclick="toggleDetail('${esc(key)}')" data-key="${esc(key)}">${glyph}</span>`
      : '';
    const detailClass = isOpen ? 'row-detail open' : 'row-detail';
    return `<tr>
      <td>${toggle}</td>
      <td class="time">${tCell}</td>
      <td class="name">${esc(e.name || '—')}</td>
      <td><code>${esc(e.path || '')}</code></td>
      <td class="q">${esc(q)}${noteBadge}</td>
      <td>${esc(e.mode || '')}</td>
      <td>${esc(e.lang || '')}</td>
      <td class="ms">${esc(e.ms || '')}</td>
      <td class="status ${stCls}">${esc(st)}</td>
    </tr>` + (expandable
      ? `<tr class="${detailClass}" data-key="${esc(key)}">
           <td colspan="9" class="row-detail-cell">${renderDetail(e)}</td>
         </tr>` : '');
  }).join('');
}

function renderDetail(e) {
  let html = '';
  const ans = e.answer;
  if (ans) {
    // Framing: string OR array of paragraphs (RFC-014 QA structure).
    const framing = ans.framingParagraphs || (ans.framing ? [ans.framing] : []);
    if (Array.isArray(framing) && framing.length) {
      html += '<div class="ans-label">Framing</div>';
      for (const p of framing) {
        if (typeof p === 'string' && p.trim()) {
          html += `<div class="ans-framing">${esc(p)}</div>`;
        }
      }
    }
    // Citations: quote.body + workTitle + author.
    const cits = ans.citations || [];
    if (cits.length) {
      html += `<div class="ans-label">Citations (${cits.length})</div>`;
      for (const c of cits) {
        const q = c.quote || {};
        const body = q.body || '';
        const wt = q.workTitle || '';
        const au = q.author || '';
        const loc = q.location || '';
        const attrib = [wt, loc].filter(Boolean).join(', ') + (au ? ' · ' + au : '');
        html += `<div class="ans-cite">
          <div class="ans-cite-body">${esc(body)}</div>
          <div class="ans-cite-attr">— ${esc(attrib)}</div>
        </div>`;
      }
    }
    // Synthesis (closing paragraph).
    if (ans.synthesis) {
      html += '<div class="ans-label">Synthesis</div>';
      html += `<div class="ans-synth">${esc(ans.synthesis)}</div>`;
    }
    // References (works drawn on but not quoted).
    const refs = ans.references || [];
    if (refs.length) {
      html += `<div class="ans-label">References (${refs.length})</div>`;
      html += '<div class="retrieved-list">';
      for (const r of refs) {
        html += `<div class="retrieved-item">${esc(r.workTitle || '')}${r.author ? ' · ' + esc(r.author) : ''}</div>`;
      }
      html += '</div>';
    }
  }
  // Retrieved chunks — what actually got surfaced BEFORE the LLM saw it.
  // Critical for "why did it cite that passage?" debugging.
  const ret = e.retrieved || [];
  if (ret.length) {
    html += `<div class="ans-label">Retrieved passages (top ${ret.length})</div>`;
    html += '<div class="retrieved-list">';
    for (const r of ret) {
      html += `<div class="retrieved-item">
        <span class="wid">${esc(r.work_id)}</span> ${esc(r.title)}
        · cos=${r.cos_score} mmr=${r.mmr_score}
        <div style="padding-left:14px">${esc((r.cite_text||'').slice(0,220))}</div>
      </div>`;
    }
    html += '</div>';
  }
  return html || '<em style="color:var(--muted)">no answer captured</em>';
}

function toggleDetail(key) {
  if (OPEN.has(key)) OPEN.delete(key); else OPEN.add(key);
  // Toggle in-place without a re-render — cheaper, and it keeps scroll
  // position exactly where the reader was.
  const rows = document.getElementById('rows');
  const detail = rows.querySelector(`tr.row-detail[data-key="${CSS.escape(key)}"]`);
  const toggle = rows.querySelector(`span.row-toggle[data-key="${CSS.escape(key)}"]`);
  if (detail) detail.classList.toggle('open', OPEN.has(key));
  if (toggle) toggle.textContent = OPEN.has(key) ? '▾' : '▸';
}
async function load() {
  if (PAUSED) return;
  try {
    const r = await fetch('/admin/activity.json');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    ALL = (await r.json()).slice().reverse();  // newest first
    render();
  } catch (err) {
    document.getElementById('rows').innerHTML =
      `<tr><td colspan="9" class="empty">Failed to load: ${esc(err.message)}</td></tr>`;
  }
}
document.getElementById('fName').addEventListener('input', render);
document.getElementById('fPath').addEventListener('change', render);
// Wire the pause/resume affordance so a maintainer reading a long answer
// can freeze the refresh cycle if they want to.
const pauseBtn = document.getElementById('pauseBtn');
if (pauseBtn) {
  pauseBtn.addEventListener('click', () => {
    PAUSED = !PAUSED;
    pauseBtn.textContent = PAUSED ? '▶ Resume auto-refresh' : '⏸ Pause auto-refresh';
    pauseBtn.style.color = PAUSED ? 'var(--warn)' : 'var(--accent)';
  });
}
load();
setInterval(load, 15000);  // refresh every 15 s
</script></body></html>
"""


@app.get("/admin/activity")
def admin_activity_dashboard():
    """Serve the activity log dashboard (self-contained HTML). Refreshes every
    15 s so the maintainer sees new requests without reload."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=_ADMIN_ACTIVITY_HTML, status_code=200)


@app.get("/admin/activity.json")
def admin_activity_json() -> List[Dict[str, Any]]:
    """Return recent access-log entries (last 500) as JSON. Powers the
    /admin/activity page. Silent [] if the log isn't wired up yet."""
    for m in getattr(app, "user_middleware", []) or []:
        if getattr(m, "cls", None) is InviteAndCapMiddleware:
            stack = getattr(app, "middleware_stack", None)
            node = stack
            while node is not None:
                if isinstance(node, InviteAndCapMiddleware):
                    log = getattr(node, "access_log", None)
                    if log is not None:
                        return log.tail(500)
                    break
                node = getattr(node, "app", None)
    return []


@app.get("/admin/flags.json")
def admin_flags_json() -> List[Dict[str, Any]]:
    """Return all flag-queue entries as JSON, with ids and statuses backfilled."""
    return _load_flag_queue()


class FlagStatusUpdate(BaseModel):
    status: str  # "approved" | "rejected" | "pending"


@app.post("/admin/flags/{flag_id}/status")
def admin_flag_set_status(flag_id: str, body: FlagStatusUpdate) -> Dict[str, Any]:
    """Set the status of a flag-queue entry by id.

    Accepts: { "status": "approved" | "rejected" | "pending" }
    Returns: { "ok": true, "id": <id>, "status": <new_status> }
    """
    allowed = {"approved", "rejected", "pending"}
    if body.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status {body.status!r}. Must be one of: {sorted(allowed)}",
        )
    entries = _load_flag_queue()
    for e in entries:
        if e.get("id") == flag_id:
            e["status"] = body.status
            _save_flag_queue(entries)
            return {"ok": True, "id": flag_id, "status": body.status}
    raise HTTPException(status_code=404, detail=f"No flag entry with id={flag_id!r}")


@app.get("/read/{slug}")
def read_work(slug: str, lang: Optional[str] = None, page: int = 1) -> Dict[str, Any]:
    """Return one page of real corpus text for the given work slug.

    Query params:
      lang  — optional; defaults to the work's first language in the catalog.
      page  — 1-based page number (default 1); 4 paragraphs per page.

    Returns a ReadingPage JSON object:
      {workSlug, workTitle, author, chapter, totalPages, paragraphs: [{n, body}]}

    404 if the slug is not in the catalog or the text.md file is missing.
    """
    # Load catalog
    catalog_path = REPO / "03_catalog" / "catalog.yaml"
    with open(catalog_path, encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    work_meta = None
    for w in catalog.get("works", []):
        if w.get("id") == slug:
            work_meta = w
            break

    # Fallback: if not in catalog, try to locate the text.md by scanning the
    # canonical directory. This handles pathway-to-god-in-hindi-literature
    # which exists on disk but is absent from catalog.yaml.
    if work_meta is None:
        # Try common canonical path patterns
        candidate_dirs = [
            REPO / "01_canonical" / "gurudev_ranade" / "books" / slug,
            REPO / "01_canonical" / "bhausaheb_maharaj" / "letters" / slug,
            REPO / "01_canonical" / "kakasaheb_tulpule" / "books" / slug,
            REPO / "01_canonical" / "other_authors" / "books" / slug,
            REPO / "02_aggregated" / "biography" / "about_gurudev_ranade" / slug,
        ]
        work_dir = None
        for d in candidate_dirs:
            if d.exists():
                work_dir = d
                break
        if work_dir is None:
            # General fallback: glob the corpus roots for the slug (covers
            # non-`books` kinds and authors not in the hardcoded list), so a
            # cited canonical work always opens instead of 404-ing. RUNBOOK R1.
            work_dir = _glob_work_dir(slug)
        if work_dir is None:
            raise HTTPException(status_code=404, detail=f"Work not found: {slug!r}")
        # Infer author from path
        parts = work_dir.parts
        author_id = "gurudev_ranade"
        for i, part in enumerate(parts):
            if part in ("01_canonical", "02_aggregated"):
                # Next part is the author
                if i + 1 < len(parts):
                    candidate = parts[i + 1]
                    if candidate not in ("biography",):
                        author_id = candidate
                break
        # Infer languages from subdirectory names
        langs_on_disk = sorted(
            d.name for d in work_dir.iterdir()
            if d.is_dir() and (d / "text.md").exists()
        )
        work_meta = {
            "id": slug,
            "title": slug.replace("-", " ").title(),
            "author": author_id,
            "languages": langs_on_disk or ["en"],
            "path": str(work_dir.relative_to(REPO)) + "/",
        }

    # Resolve language. Fall back to the work's primary language rather than
    # 404-ing when the requested lang is unavailable: a citation's "Read in
    # full" link carries the UI language (e.g. `en`), but most works exist only
    # in Marathi/Hindi, and the passage the reader clicked was in that language.
    # Serve what's on disk. (Mirrors _resolve_text_path.)
    available_langs: List[str] = work_meta.get("languages", ["en"])
    if lang is None or lang not in available_langs:
        lang = available_langs[0]

    # Locate text.md
    work_path_str: str = work_meta.get("path", "")
    if not work_path_str:
        raise HTTPException(status_code=404, detail=f"No path for work {slug!r}")
    text_path = REPO / work_path_str.rstrip("/") / lang / "text.md"
    if not text_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"text.md not found at {text_path.relative_to(REPO)}",
        )

    # Parse (with cache)
    cache_key = (str(text_path), lang)
    if cache_key not in _reading_cache:
        _reading_cache[cache_key] = _parse_work_text(text_path)
    all_paragraphs = _reading_cache[cache_key]

    total = len(all_paragraphs)
    if total == 0:
        raise HTTPException(status_code=404, detail="Work has no parseable paragraphs")

    pages = paginate(all_paragraphs)
    total_pages = len(pages)
    page = max(1, min(page, total_pages))
    page_paras = pages[page - 1]
    chapter = page_paras[0]["chapter"] if page_paras else ""
    chapter_start = is_chapter_start(pages, page)

    title: str = work_meta.get("title") or slug.replace("-", " ").title()
    author_display = _author_display_name(work_meta.get("author", ""))

    return {
        "workSlug": slug,
        "workTitle": title,
        "author": author_display,
        "chapter": chapter,
        "chapterStart": chapter_start,
        "totalPages": total_pages,
        "paragraphs": [{"n": p["n"], "body": p["body"]} for p in page_paras],
    }


def _prepare_request(req: AskRequest, request: Optional[Request] = None):
    """Validate the request and run retrieval. Returns (mode, user_msg, system_prompt,
    chunks, mode_retrieval_meta) or raises HTTPException.

    When `request` is provided, auto-scope decisions are written to
    `request.state.log_entry["auto_scope"]` so the /admin/activity dashboard
    can surface them (ADR-018)."""
    mode = req.mode
    if mode not in ("qa", "pravachan", "reading"):
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode!r}")
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="`question` is required")

    top_k = {"qa": 12, "pravachan": 15, "reading": 5}[mode]
    candidates = 100
    mmr_lambda = 0.7

    # Diagnostic: surface the shape of the history payload on the access log
    # so we can tell whether follow-up bodies are reaching the server.
    # Compact: turn count + max title chars + max body chars, per turn.
    if request is not None and req.history:
        try:
            summary = []
            for turn in req.history:
                cp = turn.get("cited_passages") or []
                bodies = [len((p.get("body") or "")) for p in cp]
                summary.append({
                    "n_cited": len(cp),
                    "bodies_len": bodies,
                    "any_body": any(b > 0 for b in bodies),
                })
            request.state.log_entry["history_shape"] = summary
        except (AttributeError, KeyError, TypeError):
            pass

    metadata_filter: Optional[Dict[str, Any]] = None
    auto_scope_info: Optional[Dict[str, Any]] = None
    if req.work and mode in ("reading", "qa"):
        metadata_filter = {"work_id": req.work}
    elif mode == "qa" and getattr(STATE, "works_catalog", None):
        # Auto-scope: two deterministic tiers, no LLM.
        #  1. Quoted title in the query — hard user-explicit signal.
        #  2. Unquoted title substring — natural-phrasing fallback.
        # Fires only when the sadhak hasn't already explicitly selected a
        # work in the UI. See ADR-018 (with 2026-07-18 revision).
        if os.environ.get("ENABLE_QUERY_UNDERSTANDING", "1") != "0":
            try:
                auto_scope_info = query_understanding.extract_mentioned_work(
                    question, STATE.works_catalog,
                )
                if auto_scope_info and auto_scope_info.get("work_id"):
                    metadata_filter = {"work_id": auto_scope_info["work_id"]}
                # Surface the detection outcome on the activity log so the
                # maintainer can see when auto-scope fired, to which work,
                # and via which tier (quoted / substring / ambiguous).
                if request is not None and auto_scope_info:
                    try:
                        request.state.log_entry["auto_scope"] = auto_scope_info
                    except (AttributeError, KeyError, TypeError):
                        pass
            except Exception:
                pass  # never let auto-scope break retrieval
    # Citation breadth: unscoped Q&A retrieves at most 2 chunks per work so
    # the model sees one or two strong passages from each of the top distinct
    # works and its citations span the corpus instead of clustering in a single
    # book. Work-scoped Q&A (mode=="qa" + work set) must NOT keep that breadth
    # cap — the filter already restricts to one work, so we allow top_k chunks
    # from it. Reading is also scoped to one work (cap = top_k). Pravachan
    # keeps 2 to allow a couple of passages from a rich source.
    if metadata_filter and "work_id" in metadata_filter:
        max_per_source = top_k
    elif mode == "qa":
        max_per_source = 2
    else:
        max_per_source = 2

    t0 = time.time()
    chunks = _retrieve(
        question,
        top_k=top_k,
        candidates=candidates,
        mmr_lambda=mmr_lambda,
        max_per_source=max_per_source,
        metadata_filter=metadata_filter,
    )
    retrieval_s = time.time() - t0
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No matching chunks for this query (corpus may be silent on the topic, or filter is too narrow)",
        )

    if mode == "pravachan":
        user_msg = build_pravachan_user_message(chunks, question)
    elif mode == "reading":
        title = req.passage_title or (req.work or "(current passage)")
        user_msg = build_reading_user_message(req.passage or "", chunks, question, title)
    else:
        user_msg = build_user_message(chunks, question, history=req.history)

    system_prompt = get_system_prompt(mode, lang=req.lang or "en")
    return mode, user_msg, system_prompt, chunks, retrieval_s


def _enrich_citation_readpage(
    citation: Dict[str, Any],
    label_to_chunk: Dict[str, Any],
) -> None:
    """Set readPage on a citation's quote dict, in place.

    Resolves the cited passage to its reading page by anchoring on the verbatim
    quote TEXT inside the work's `text.md` (drift-proof), located via the chunk's
    own `meta.source_path`. Falls back to the (unreliable) char_start offset only
    when the text can't be located. Only acts on canonical quotes that have a
    workId already set (i.e. after splice_quote_dict has run). Safe to call
    multiple times (idempotent). See docs/RUNBOOK.md R1.
    """
    if not isinstance(citation, dict):
        return
    quote = citation.get("quote")
    if not isinstance(quote, dict):
        return
    if quote.get("kind") != "canonical":
        return
    work_id = quote.get("workId") or ""
    if not work_id:
        return
    # Retrieve the chunk that backs this citation for its source path, language,
    # and (fallback) char_start.
    passage_label = (quote.get("passage") or "").strip()
    chunk = (label_to_chunk or {}).get(passage_label)
    if chunk is None:
        return
    meta = chunk.get("meta") or {}

    # Primary: anchor on the verbatim quote body inside the chunk's own
    # source_path text.md. This sidesteps the broken char_start entirely and
    # works even for works absent from catalog.yaml / the slug-based fallback
    # dirs (R1 defect 1a), because the chunk already carries its exact path.
    page: Optional[int] = None
    source_path = meta.get("source_path") or ""
    text_path = (REPO / source_path) if source_path else None
    body = quote.get("body") or ""
    if text_path is not None and text_path.exists() and body:
        page = reading_page_for_body(text_path, body)

    # Fallback: offset-based lookup (drifts, but better than page 1 when the
    # body can't be matched, e.g. heavy cleaning divergence).
    if page is None:
        char_start = meta.get("char_start")
        if char_start is not None:
            page = reading_page_for_offset(work_id, meta.get("language"), char_start)

    if page is not None:
        quote["readPage"] = page


def _enrich_citations_readpage(
    citations: List[Dict[str, Any]],
    label_to_chunk: Dict[str, Any],
) -> None:
    """Apply _enrich_citation_readpage to every citation in the list."""
    for c in citations:
        _enrich_citation_readpage(c, label_to_chunk)


def _citation_extraction_regen(mode, user_message, label_to_chunk, first_result, lang):
    """Enforcement retry as focused citation EXTRACTION (shared by both ask paths).

    A full "cite harder" re-gen fails for Marathi answers over English sources: the
    model won't quote English passages while writing Marathi prose, so it emits an
    uncited essay again. This instead asks ONLY for the citations — a language-neutral
    reference task ("copy the passage's own anchor words") the model does fine — then
    keeps the original framing/synthesis and merges in the extracted, spliced citations.
    """
    parsed, _ = STATE.client.ask_structured(
        mode=mode,
        system_prompt=get_citation_extraction_prompt(lang),
        user_message=user_message,
        label_to_chunk=label_to_chunk,
    )
    r = parsed.model_dump(exclude_none=True)
    merged = {**first_result, "citations": r.get("citations") or []}
    _enrich_citations_readpage(merged.get("citations") or [], label_to_chunk)
    return merged


def _enforce_and_verify_qa(result, label_to_chunk, *, regenerate,
                            has_history: bool = False):
    """Apply the grounding guard to a QA result dict. Returns (result, flags).

    No-op unless GROUNDING_MODE == 'enforce'. `regenerate` produces a second
    QA result dict (already spliced) for the enforcement retry.

    `has_history` short-circuits the retry (a follow-up may legitimately
    answer with zero citations — the user has the prior turn's citations
    already). See grounding.enforce_qa docstring.
    """
    if os.environ.get("GROUNDING_MODE") != "enforce":
        return result, []
    passages = sum(1 for _ in (label_to_chunk or {}))
    result = grounding.enforce_qa(
        result, passages_supplied=passages, regenerate=regenerate,
        has_history=has_history,
    )
    flags = grounding.verify_citations(result.get("citations") or [], label_to_chunk)
    return result, flags


def _replay_qa_as_sse(result):
    """Yield (kind, payload) events functionally compatible with the live QA stream
    from a completed result dict. Emits scalar field events, then array_item events for
    list fields, and finally a done event. Events are shaped for frontend consumption;
    the done event payload (with exclude_none) replaces the draft wholesale."""
    for name in ("kind", "classification", "question", "framing", "synthesis"):
        if name in result and result[name] is not None:
            yield "field", {"name": name, "value": result[name]}
    for name in ("framingParagraphs", "citations", "references"):
        items = result.get(name)
        if isinstance(items, list):
            for i, value in enumerate(items):
                yield "array_item", {"array": name, "index": i, "value": value}
            yield "field_close", {"name": name}
    yield "done", {"response": result, "usage": {}}


def _retrieval_event_payload(chunks: List[Dict[str, Any]], retrieval_s: float) -> Dict[str, Any]:
    """Shape for the `retrieval` SSE event (RFC-010): chunk metadata + elapsed time.
    Strips the chunk text body (too large for an SSE event) — that's only needed server-side.
    """
    return {
        "chunks": [
            {
                "workTitle": c["meta"].get("title") or c["meta"].get("work_id"),
                "kind": c["meta"].get("kind"),
                "language": c["meta"].get("language"),
                "cos": c["cos_score"],
                "mmr": c["mmr_score"],
            }
            for c in chunks
        ],
        "elapsed_s": round(retrieval_s, 3),
    }


def _summarize_retrieved_chunks(chunks) -> list:
    """Compact record of what was surfaced for the activity log — enough to
    answer 'why did it cite that passage?' later without re-running the
    query. Only work_id / cite_text / cos+mmr scores; drops full chunk text."""
    out = []
    for c in chunks or []:
        m = c.get("meta") or {}
        cite = m.get("cite_text") or ""
        if not isinstance(cite, str):
            cite = str(cite)
        out.append({
            "work_id": m.get("work_id", ""),
            "title": m.get("title", ""),
            "chunk_id": m.get("id", ""),
            "parent_id": m.get("parent_id"),
            "cite_text": cite[:500],
            "cos_score": round(float(c.get("cos_score", 0.0)), 4),
            "mmr_score": round(float(c.get("mmr_score", 0.0)), 4),
        })
    return out


def _finalize_ask_log(request: Request, *, result: dict | None,
                       retrieved: list, status: int, elapsed_ms: int) -> None:
    """Write the full-context /ask access log line (question + answer +
    retrieved chunks). Silent no-op if the gate middleware isn't wiring
    logs (dev/CI). Marks the request so the middleware skips its
    auto-write."""
    try:
        entry = getattr(request.state, "log_entry", None)
        log = getattr(request.state, "access_log", None)
        if entry is None or log is None:
            return
        entry["status"] = status
        entry["ms"] = elapsed_ms
        if retrieved:
            entry["retrieved"] = retrieved
        if result is not None:
            entry["answer"] = result
        log.append(entry)
        request.state.access_logged_by_handler = True
    except Exception:
        pass  # logging must never break the request


@app.post("/ask")
def ask(req: AskRequest, request: Request):
    """Main entry point.

    Accept: application/json  → single JSON body (existing behavior, CLI clients)
    Accept: text/event-stream → progressive SSE stream (RFC-010, chat-app)
    """
    accept = (request.headers.get("accept") or "").lower()
    wants_stream = "text/event-stream" in accept

    ask_t0 = time.time()
    mode, user_msg, system_prompt, chunks, retrieval_s = _prepare_request(req, request)
    retrieved_summary = _summarize_retrieved_chunks(chunks)

    # Map the passage labels the model sees (A, B, C, ...) back to their chunks,
    # so Q&A citations emitted by reference can be spliced to verbatim text.
    # Same enumeration order as prompts.format_chunks_for_prompt.
    label_to_chunk = {_passage_label(i): c for i, c in enumerate(chunks)}

    if not wants_stream:
        # ── Non-streaming JSON path (CLI, tune_sweep.py, anything sending Accept: application/json)
        try:
            parsed, _response = STATE.client.ask_structured(
                mode=mode,
                system_prompt=system_prompt,
                user_message=user_msg,
                label_to_chunk=label_to_chunk,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
        result = parsed.model_dump(exclude_none=True)
        # Enrich Q&A citations with the reading page so the frontend can open
        # the reader at the exact page containing the cited passage.
        if mode == "qa":
            _enrich_citations_readpage(result.get("citations") or [], label_to_chunk)

            result, _flags = _enforce_and_verify_qa(
                result, label_to_chunk,
                regenerate=lambda: _citation_extraction_regen(
                    mode, user_msg, label_to_chunk, result, req.lang or "en"),
                has_history=bool(req.history),
            )
            _append_flags(_flags, req)
        _finalize_ask_log(request, result=result, retrieved=retrieved_summary,
                          status=200, elapsed_ms=int((time.time() - ask_t0) * 1000))
        return result

    # ── Streaming SSE path (chat-app)
    def event_stream():
        # Flush past small-chunk buffering (Next dev / undici) so the first tiny
        # events — retrieval + the enforce opener — reach the browser immediately
        # instead of sitting in a buffer until later output pushes past the
        # threshold. A large SSE comment is ignored by the client parser, which
        # drops any line starting with ":" (chat-app lib/api.ts).
        yield ":" + (" " * 8192) + "\n\n"
        # First: retrieval event so the UI can show "Found N passages in Xs"
        # while the LLM is still warming up.
        yield sse("retrieval", **_retrieval_event_payload(chunks, retrieval_s))

        if mode == "qa" and os.environ.get("GROUNDING_MODE") == "enforce":
            # Instant opener: enforce buffers the whole answer (it needs the full
            # text to verify citations), which reads as a long silent wait. Emit a
            # warm 1-2 line immediately as the `framing` field so the reader sees
            # something the moment they ask; the final `done` event replaces the
            # draft wholesale, so this is cleared when the grounded answer lands.
            _opener = (
                "🙏 गुरुदेवांचे लेखन आणि भक्तांच्या आठवणींमध्ये शोधत आहे — आधारसहित उत्तर तयार होत आहे…"
                if (req.lang or "en") == "mr"
                else "🙏 Searching Gurudev's own writings and the devotees' recollections — composing a grounded, cited answer…"
            )
            yield sse("field", name="framing", value=_opener)

            # Buffered path (RFC-014): generate non-streaming, enforce/verify,
            # then replay as SSE. Trades progressive type-out for guaranteed
            # grounding; preserves the SSE event contract (no frontend change).
            try:
                parsed, _r = STATE.client.ask_structured(
                    mode=mode, system_prompt=system_prompt,
                    user_message=user_msg, label_to_chunk=label_to_chunk,
                )
                result = parsed.model_dump(exclude_none=True)
                _enrich_citations_readpage(result.get("citations") or [], label_to_chunk)
                result, _flags = _enforce_and_verify_qa(
                    result, label_to_chunk,
                    regenerate=lambda: _citation_extraction_regen(
                        mode, user_msg, label_to_chunk, result, req.lang or "en"),
                    has_history=bool(req.history),
                )
                _append_flags(_flags, req)
                _finalize_ask_log(request, result=result,
                                    retrieved=retrieved_summary, status=200,
                                    elapsed_ms=int((time.time() - ask_t0) * 1000))
                for kind, payload in _replay_qa_as_sse(result):
                    yield sse(kind, **payload)
                return
            except RuntimeError as e:
                _finalize_ask_log(request, result=None,
                                    retrieved=retrieved_summary, status=502,
                                    elapsed_ms=int((time.time() - ask_t0) * 1000))
                yield sse("error", message=str(e)); return
        # else: existing true-streaming loop unchanged

        last_event_ts = time.time()
        for kind, payload in STATE.client.ask_structured_stream(
            mode=mode,
            system_prompt=system_prompt,
            user_message=user_msg,
            label_to_chunk=label_to_chunk,
        ):
            now = time.time()
            if now - last_event_ts > 15:
                yield sse_heartbeat()
            # Enrich Q&A citations with readPage at two points:
            # 1. On each array_item event so the frontend can use it immediately.
            # 2. On the done event's reconciled citations list for consistency.
            if mode == "qa":
                if kind == "array_item" and payload.get("array") == "citations":
                    value = payload.get("value")
                    if isinstance(value, dict):
                        _enrich_citation_readpage(value, label_to_chunk)
                elif kind == "done":
                    response_dict = payload.get("response") or {}
                    _enrich_citations_readpage(
                        response_dict.get("citations") or [], label_to_chunk
                    )
                    _finalize_ask_log(request, result=response_dict,
                                        retrieved=retrieved_summary, status=200,
                                        elapsed_ms=int((time.time() - ask_t0) * 1000))
            yield sse(kind, **payload)
            last_event_ts = now

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx hint: don't buffer SSE in production.
            "X-Accel-Buffering": "no",
        },
    )


def main() -> int:
    import uvicorn
    print(f"[server] starting on http://0.0.0.0:{PORT}", file=sys.stderr)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
