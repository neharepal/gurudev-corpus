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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import intent
import retrieve
from llm_client import ChatClient, MissingApiKeyError, pick_model
from prompts import (
    _passage_label,
    build_pravachan_user_message,
    build_reading_user_message,
    build_user_message,
    get_system_prompt,
)
from streaming import sse, sse_heartbeat

import datetime
import json
import math
import re
import yaml

PORT = int(os.environ.get("GURUDEV_BACKEND_PORT", "8765"))

# Path to the issue-report queue file.
# Written once at module load so tests can monkeypatch `server.ISSUE_QUEUE_PATH`.
ISSUE_QUEUE_PATH: Path = REPO / "logs" / "issue_reports.jsonl"


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

# Page size for reading mode — must match the constant used in read_work().
_PAGE_SIZE = 4


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

    Uses the same _PAGE_SIZE and paragraph-filtering logic as read_work() so
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

    return (target_idx // _PAGE_SIZE) + 1


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


class ReportRequest(BaseModel):
    question: str
    mode: str
    citations: Optional[List[ReportCitation]] = None
    note: Optional[str] = None
    # Correction fields (garble Phase 2 — flag-and-queue).
    # All optional so plain issue reports remain backward-compatible.
    kind: Optional[str] = None        # "correction" | "issue" (default None = "issue")
    slug: Optional[str] = None        # work slug
    page: Optional[int] = None        # 1-based page number
    paragraph: Optional[int] = None   # paragraph n value
    original: Optional[str] = None    # verbatim text as rendered
    corrected: Optional[str] = None   # user's corrected text
    lang: Optional[str] = None        # "en" | "mr"


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


STATE = _State()


def _embed_query(question: str) -> np.ndarray:
    """Match the embed convention from tune_sweep.embed_with()."""
    name = STATE.model_name
    q = question
    if "e5" in name.lower():
        q = "query: " + q
    vec = STATE.model.encode([q], normalize_embeddings=True, convert_to_numpy=True)
    return vec[0].astype(np.float32)


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
    subset_texts = (
        [retrieve.load_chunk_text(sub_metas[i], int(keep_idx[i])) for i in range(len(sub_metas))]
        if keep_idx is not None
        else None
    )

    qvec = _embed_query(question)
    scores = sub_emb @ qvec
    query_intent = intent.classify_intent(question)
    scores = retrieve.apply_intent_tier_weights(scores, sub_metas, query_intent)
    cand_n = min(candidates, len(scores))
    fused = retrieve.fused_candidate_scores(question, scores, sub_metas, texts=subset_texts)
    cand_idx = np.argpartition(-fused, cand_n - 1)[:cand_n]
    cand_idx = cand_idx[np.argsort(-fused[cand_idx])]
    cand_scores = scores[cand_idx]
    reranked = retrieve.mmr_rerank(
        qvec, cand_idx, cand_scores, sub_emb, sub_metas,
        top_k=top_k,
        mmr_lambda=mmr_lambda,
        max_per_source=max_per_source,
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


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


app = FastAPI(title="Gurudev Sangrah backend", version="0.1.0")

# Allow the local Next.js dev server to call us cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


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

    STATE.client = ChatClient()
    print("[startup] ready", file=sys.stderr)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "model": STATE.model_name,
        "chunks": len(STATE.metas),
    }


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
    """Append a flagged-answer report to the issue queue.

    Accepts: { question, mode, citations?, note?, kind?, slug?, page?,
               paragraph?, original?, corrected?, lang? }
    Returns: { ok: true }

    Each report is one JSON line in ISSUE_QUEUE_PATH (logs/issue_reports.jsonl).
    ISSUE_QUEUE_PATH is a module-level constant so tests can monkeypatch it.

    Applying corrections or re-embedding garbled passages is a separate
    maintenance step (garble Phase 2) — this endpoint only queues the flag.
    """
    ISSUE_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    record: Dict[str, Any] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "question": req.question,
        "mode": req.mode,
        "citations": [c.model_dump() for c in (req.citations or [])],
        "note": req.note or "",
    }
    # Correction fields — only included when the caller sends them.
    if req.kind is not None:
        record["kind"] = req.kind
    if req.slug is not None:
        record["slug"] = req.slug
    if req.page is not None:
        record["page"] = req.page
    if req.paragraph is not None:
        record["paragraph"] = req.paragraph
    if req.original is not None:
        record["original"] = req.original
    if req.corrected is not None:
        record["corrected"] = req.corrected
    if req.lang is not None:
        record["lang"] = req.lang
    with open(ISSUE_QUEUE_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"ok": True}


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

    # Resolve language
    available_langs: List[str] = work_meta.get("languages", ["en"])
    if lang is None:
        lang = available_langs[0]
    elif lang not in available_langs:
        raise HTTPException(
            status_code=404,
            detail=f"Language {lang!r} not available for {slug!r}. Available: {available_langs}",
        )

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

    PAGE_SIZE = _PAGE_SIZE
    total_pages = math.ceil(total / PAGE_SIZE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_paras = all_paragraphs[start:end]

    chapter = page_paras[0]["chapter"] if page_paras else ""

    title: str = work_meta.get("title") or slug.replace("-", " ").title()
    author_display = _author_display_name(work_meta.get("author", ""))

    return {
        "workSlug": slug,
        "workTitle": title,
        "author": author_display,
        "chapter": chapter,
        "totalPages": total_pages,
        "paragraphs": [{"n": p["n"], "body": p["body"]} for p in page_paras],
    }


def _prepare_request(req: AskRequest):
    """Validate the request and run retrieval. Returns (mode, user_msg, system_prompt,
    chunks, mode_retrieval_meta) or raises HTTPException."""
    mode = req.mode
    if mode not in ("qa", "pravachan", "reading"):
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode!r}")
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="`question` is required")

    top_k = {"qa": 8, "pravachan": 15, "reading": 5}[mode]
    candidates = 30
    mmr_lambda = 0.7

    metadata_filter: Optional[Dict[str, Any]] = None
    if req.work and mode in ("reading", "qa"):
        metadata_filter = {"work_id": req.work}
    # Citation breadth: unscoped Q&A retrieves at most ONE chunk per work, so
    # the model is handed one strong passage from each of the top distinct
    # works and its citations span the corpus instead of clustering in a single
    # book. Work-scoped Q&A (mode=="qa" + work set) must NOT keep that breadth
    # cap — the filter already restricts to one work, so we allow top_k chunks
    # from it. Reading is also scoped to one work (cap = top_k). Pravachan
    # keeps 2 to allow a couple of passages from a rich source.
    if metadata_filter and "work_id" in metadata_filter:
        max_per_source = top_k
    elif mode == "qa":
        max_per_source = 1
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

    system_prompt = get_system_prompt(mode)
    return mode, user_msg, system_prompt, chunks, retrieval_s


def _enrich_citation_readpage(
    citation: Dict[str, Any],
    label_to_chunk: Dict[str, Any],
) -> None:
    """Set readPage on a citation's quote dict, in place.

    Looks up the passage label in label_to_chunk to get char_start, then
    calls reading_page_for_offset. Only acts on canonical quotes that have a
    workId already set (i.e. after splice_quote_dict has run). Safe to call
    multiple times (idempotent).
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
    # Retrieve the chunk that backs this citation to get char_start and language.
    passage_label = (quote.get("passage") or "").strip()
    chunk = (label_to_chunk or {}).get(passage_label)
    if chunk is None:
        return
    meta = chunk.get("meta") or {}
    char_start = meta.get("char_start")
    if char_start is None:
        return
    lang = meta.get("language")
    page = reading_page_for_offset(work_id, lang, char_start)
    if page is not None:
        quote["readPage"] = page


def _enrich_citations_readpage(
    citations: List[Dict[str, Any]],
    label_to_chunk: Dict[str, Any],
) -> None:
    """Apply _enrich_citation_readpage to every citation in the list."""
    for c in citations:
        _enrich_citation_readpage(c, label_to_chunk)


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


@app.post("/ask")
def ask(req: AskRequest, request: Request):
    """Main entry point.

    Accept: application/json  → single JSON body (existing behavior, CLI clients)
    Accept: text/event-stream → progressive SSE stream (RFC-010, chat-app)
    """
    accept = (request.headers.get("accept") or "").lower()
    wants_stream = "text/event-stream" in accept

    mode, user_msg, system_prompt, chunks, retrieval_s = _prepare_request(req)

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
        return result

    # ── Streaming SSE path (chat-app)
    def event_stream():
        # First: retrieval event so the UI can show "Found N passages in Xs"
        # while the LLM is still warming up.
        yield sse("retrieval", **_retrieval_event_payload(chunks, retrieval_s))

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
