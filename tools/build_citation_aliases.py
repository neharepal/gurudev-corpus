#!/usr/bin/env python3
"""RFC-018 Phase 1 — build the citation-alias index.

For every chunk in a CONTAINER work, decide whether it verbatim-quotes a chunk
from an ORIGINAL work in our corpus (Gurudev's own writings + Bhausaheb's
letters). When a strong match is found, emit an alias row. At citation time
(RFC-018 §3, implemented separately), splice consults the index and swaps the
citation's attribution from the container to the original.

Precision-first: score >= 0.82 AND jaccard >= 0.55 — see RFC-018.

Same-language matching only.

Usage
-----
Full run:
    python3 tools/build_citation_aliases.py

Dry-run report on a subset:
    python3 tools/build_citation_aliases.py \\
        --dry-run \\
        --container sadhakbodh \\
        --container charitra-tatvajnan-tulpule \\
        --sample 50 \\
        --report /tmp/aliases-sample.md

Full run for one container, still writing to the aliases file:
    python3 tools/build_citation_aliases.py --container sadhakbodh

Outputs
-------
- 04_processed/citation_aliases.jsonl (or `--out`) — one JSON per alias.
- A summary line to stderr.
- With --report, a Markdown report suitable for eyeball review.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
import yaml

# Reuse the in-house BM25Index + tokenizer from the retrieval path so the alias
# builder sees candidates the same way the runtime retriever would.
_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))
from retrieve import BM25Index, _tokenize_bm25  # noqa: E402


REPO = _here.parent
WORK_ROLES_PATH = REPO / "03_catalog" / "work_roles.yaml"
CHUNKS_META_PATH = REPO / "04_processed" / "embeddings" / "chunks_meta.jsonl"
EMBEDDINGS_PATH = REPO / "04_processed" / "embeddings" / "embeddings.npy"
CHUNKS_JSONL_PATH = REPO / "04_processed" / "chunks.jsonl"
OUT_PATH_DEFAULT = REPO / "04_processed" / "citation_aliases.jsonl"


# Thresholds from RFC-018.
MIN_COMBINED = 0.82
MIN_JACCARD = 0.55
BM25_TOPK = 8


# ────────────────────────────────────────────────────────────────────────────
# Small utilities
# ────────────────────────────────────────────────────────────────────────────


def load_work_roles(path: Path = WORK_ROLES_PATH) -> tuple:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    originals = set(doc.get("originals") or [])
    containers = set(doc.get("containers") or [])
    if not originals or not containers:
        raise SystemExit(f"work_roles.yaml has no originals or no containers")
    return originals, containers


def load_metas(path: Path = CHUNKS_META_PATH) -> List[dict]:
    metas: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            metas.append(json.loads(line))
    return metas


def load_chunk_texts_by_id(
    path: Path = CHUNKS_JSONL_PATH, ids_wanted: set | None = None
) -> dict:
    """Return {chunk_id: cite_text}. When `ids_wanted` is provided, only rows
    with a matching id are kept (memory-friendly for subset runs)."""
    out: dict = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            cid = row.get("id")
            if ids_wanted is not None and cid not in ids_wanted:
                continue
            out[cid] = row.get("cite_text") or row.get("text") or ""
    return out


def char_ngram_set(text: str, n: int = 5) -> set:
    """Character n-gram set. Whitespace-collapsed, lowercased, no punctuation
    strip (Devanagari punctuation is meaningful)."""
    if not text:
        return set()
    s = " ".join(text.lower().split())
    if len(s) < n:
        return {s}
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    uni = len(a | b)
    return inter / uni if uni else 0.0


def l2_normalize_rows(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n = np.where(n == 0.0, 1.0, n)
    return x / n


# ────────────────────────────────────────────────────────────────────────────
# Alias search per language
# ────────────────────────────────────────────────────────────────────────────


def _summarize(text: str, n: int = 160) -> str:
    s = " ".join((text or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def search_language(
    lang: str,
    metas: List[dict],
    embeddings: np.ndarray,
    originals: set,
    containers: set,
    container_filter: set | None,
    sample: int | None,
    log_prefix: str = "",
) -> List[dict]:
    """Find alias rows for one language. Returns a list of alias dicts."""

    # Row indices for originals + containers in this language.
    orig_rows = [
        i for i, m in enumerate(metas)
        if m.get("language") == lang and m.get("work_id") in originals
    ]
    cont_rows = [
        i for i, m in enumerate(metas)
        if m.get("language") == lang and m.get("work_id") in containers
        and (container_filter is None or m.get("work_id") in container_filter)
    ]
    if not orig_rows or not cont_rows:
        print(f"{log_prefix}[{lang}] originals={len(orig_rows)} containers={len(cont_rows)} → skip",
              file=sys.stderr)
        return []

    print(f"{log_prefix}[{lang}] originals={len(orig_rows)} container-chunks={len(cont_rows)}",
          file=sys.stderr)

    # Optional sample cap for dry-runs.
    if sample and sample < len(cont_rows):
        cont_rows = cont_rows[:sample]
        print(f"{log_prefix}[{lang}] --sample capped container chunks to {len(cont_rows)}",
              file=sys.stderr)

    # Build BM25 over originals' cite_text — pull from chunks.jsonl so we
    # have the full text (chunks_meta.jsonl already has cite_text on it).
    #
    # Filter out very-short originals: they generate spurious 1.0-jaccard
    # matches on section headings / title fragments (e.g. a 2-word "Ranade's
    # Philosophy" original chunk would jaccard-match any container mention).
    MIN_TEXT_LEN = 40
    keep_orig_local = [
        i for i, i_row in enumerate(orig_rows)
        if len(metas[i_row].get("cite_text") or "") >= MIN_TEXT_LEN
    ]
    orig_rows = [orig_rows[i] for i in keep_orig_local]
    orig_texts = [metas[i].get("cite_text") or "" for i in orig_rows]
    print(f"{log_prefix}[{lang}] originals >= {MIN_TEXT_LEN} chars: {len(orig_rows)}",
          file=sys.stderr)
    print(f"{log_prefix}[{lang}] building BM25 over originals…", file=sys.stderr)
    bm25 = BM25Index.build(orig_texts)

    # Normalize the embedding rows we need. Two slices to avoid a full-corpus
    # normalize.
    print(f"{log_prefix}[{lang}] slicing + normalizing embeddings…", file=sys.stderr)
    orig_emb = l2_normalize_rows(embeddings[orig_rows].astype(np.float32))
    cont_emb = l2_normalize_rows(embeddings[cont_rows].astype(np.float32))

    # Precompute char 5-gram sets for originals.
    print(f"{log_prefix}[{lang}] precomputing char 5-gram sets for originals…", file=sys.stderr)
    orig_ngrams = [char_ngram_set(t, 5) for t in orig_texts]

    aliases: List[dict] = []
    t0 = time.time()
    progress_every = max(1, len(cont_rows) // 20)
    for ci, cont_row in enumerate(cont_rows):
        if ci and ci % progress_every == 0:
            elapsed = time.time() - t0
            rate = ci / max(elapsed, 1e-6)
            eta = (len(cont_rows) - ci) / max(rate, 1e-6)
            print(f"{log_prefix}[{lang}]   {ci}/{len(cont_rows)}  ({rate:.1f}/s, eta {eta:.0f}s)",
                  file=sys.stderr)

        cont_meta = metas[cont_row]
        cont_text = cont_meta.get("cite_text") or ""
        if len(cont_text) < 40:
            # Too short — jaccard on tiny strings is noisy; skip.
            continue

        # BM25 top-K over originals.
        qtoks = _tokenize_bm25(cont_text)
        scores = bm25.score(qtoks)
        if scores.max() == 0.0:
            continue
        top_bm25 = np.argpartition(-scores, min(BM25_TOPK, len(scores) - 1))[:BM25_TOPK]

        cont_v = cont_emb[ci]
        cont_ng = char_ngram_set(cont_text, 5)

        best = None
        for oi in top_bm25:
            oi = int(oi)
            if scores[oi] <= 0.0:
                continue
            cos = float(np.dot(cont_v, orig_emb[oi]))
            jac = jaccard(cont_ng, orig_ngrams[oi])
            combined = 0.5 * cos + 0.5 * jac
            if best is None or combined > best[3]:
                best = (oi, cos, jac, combined)

        if best is None:
            continue
        oi, cos, jac, combined = best
        if combined < MIN_COMBINED or jac < MIN_JACCARD:
            continue

        orig_meta = metas[orig_rows[oi]]
        aliases.append({
            "chunk_id": cont_meta.get("id"),
            "container": {
                "work_id": cont_meta.get("work_id"),
                "title": cont_meta.get("title") or "",
                "excerpt": _summarize(cont_text, 200),
            },
            "alias": {
                "work_id": orig_meta.get("work_id"),
                "chunk_id": orig_meta.get("id"),
                "title": orig_meta.get("title") or "",
                "author": orig_meta.get("author") or "",
                "excerpt": _summarize(orig_meta.get("cite_text") or "", 200),
                "match": {
                    "confidence": round(combined, 4),
                    "type": "lexical+semantic",
                    "jaccard": round(jac, 4),
                    "cosine": round(cos, 4),
                },
            },
        })

    print(f"{log_prefix}[{lang}] declared aliases: {len(aliases)}", file=sys.stderr)
    return aliases


# ────────────────────────────────────────────────────────────────────────────
# Report writer
# ────────────────────────────────────────────────────────────────────────────


def write_markdown_report(aliases: List[dict], out_path: Path, args) -> None:
    lines = [
        "# RFC-018 citation-alias — sample report",
        "",
        f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Total aliases in this run: **{len(aliases)}**",
        f"- Thresholds: combined >= {MIN_COMBINED}, jaccard >= {MIN_JACCARD}",
        f"- Container filter: {sorted(args.container) if args.container else 'ALL containers'}",
        f"- Sample cap per language: {args.sample if args.sample else 'no cap'}",
        f"- Dry run (nothing written to citation_aliases.jsonl): {args.dry_run}",
        "",
        "## Confidence histogram",
        "",
    ]
    if aliases:
        bins = [0.82, 0.86, 0.90, 0.94, 0.98, 1.01]
        counts = [0] * (len(bins) - 1)
        for a in aliases:
            c = a["alias"]["match"]["confidence"]
            for j in range(len(bins) - 1):
                if bins[j] <= c < bins[j + 1]:
                    counts[j] += 1
                    break
        for j in range(len(bins) - 1):
            lo, hi = bins[j], bins[j + 1]
            lines.append(f"- [{lo:.2f}, {hi:.2f}): {counts[j]}")
    else:
        lines.append("_no aliases found — check work_roles.yaml, threshold, or "
                     "sample size._")

    lines += [
        "",
        "## Sample aliases (up to 40, most confident first)",
        "",
    ]
    top = sorted(aliases,
                 key=lambda a: -a["alias"]["match"]["confidence"])[:40]
    for i, a in enumerate(top, 1):
        m = a["alias"]["match"]
        lines += [
            f"### {i}. {a['container']['work_id']}  →  {a['alias']['work_id']}",
            f"- confidence **{m['confidence']}** (jaccard {m['jaccard']}, cosine {m['cosine']})",
            f"- container chunk `{a['chunk_id']}`",
            f"- original chunk `{a['alias']['chunk_id']}` — author `{a['alias']['author']}`",
            "",
            "**Container excerpt:**",
            "",
            f"> {a['container']['excerpt']}",
            "",
            "**Original excerpt (proposed re-attribution target):**",
            "",
            f"> {a['alias']['excerpt']}",
            "",
            "---",
            "",
        ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def main() -> None:
    global MIN_COMBINED, MIN_JACCARD  # populated below from argparse
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dry-run", action="store_true",
                   help="don't write citation_aliases.jsonl; --report only")
    p.add_argument("--container", action="append", default=[],
                   help="limit to these container work_ids (repeatable). "
                        "Default: scan all containers in work_roles.yaml.")
    p.add_argument("--sample", type=int, default=None,
                   help="cap container chunks scanned per language "
                        "(for a quick eyeball; default: no cap)")
    p.add_argument("--report", type=Path, default=None,
                   help="write a Markdown report to this path")
    p.add_argument("--out", type=Path, default=OUT_PATH_DEFAULT,
                   help=f"aliases jsonl output (default: {OUT_PATH_DEFAULT})")
    p.add_argument("--languages", default="",
                   help="comma-separated language filter (default: en,mr,hi)")
    p.add_argument("--min-combined", type=float, default=MIN_COMBINED,
                   help=f"override combined-score threshold "
                        f"(default: {MIN_COMBINED}). Useful for calibration.")
    p.add_argument("--min-jaccard", type=float, default=MIN_JACCARD,
                   help=f"override jaccard threshold (default: {MIN_JACCARD})")
    p.add_argument("--top", type=int, default=0,
                   help="in dry-run reports, ALSO include this many "
                        "best-scoring near-miss candidates for calibration "
                        "even if they miss the threshold")
    args = p.parse_args()

    MIN_COMBINED = args.min_combined
    MIN_JACCARD = args.min_jaccard

    originals, containers = load_work_roles()
    container_filter = set(args.container) if args.container else None
    if container_filter:
        bogus = container_filter - containers
        if bogus:
            print(f"warning: --container ids not in containers list: {sorted(bogus)}",
                  file=sys.stderr)

    langs = [l.strip() for l in args.languages.split(",") if l.strip()] or \
        ["en", "mr", "hi"]

    print(f"[roles] originals={len(originals)}  containers={len(containers)} "
          f"(scanning: {sorted(container_filter) if container_filter else 'all'})",
          file=sys.stderr)
    print(f"[roles] languages: {langs}", file=sys.stderr)

    metas = load_metas()
    print(f"[load] chunks_meta rows: {len(metas)}", file=sys.stderr)

    embeddings = np.load(EMBEDDINGS_PATH, mmap_mode="r")
    if embeddings.shape[0] != len(metas):
        raise SystemExit(
            f"row count mismatch: chunks_meta={len(metas)}, "
            f"embeddings={embeddings.shape[0]}"
        )

    all_aliases: List[dict] = []
    for lang in langs:
        aliases = search_language(
            lang=lang,
            metas=metas,
            embeddings=embeddings,
            originals=originals,
            containers=containers,
            container_filter=container_filter,
            sample=args.sample,
            log_prefix="  ",
        )
        all_aliases.extend(aliases)

    if args.report:
        write_markdown_report(all_aliases, args.report, args)
        print(f"[report] wrote {args.report}", file=sys.stderr)

    if not args.dry_run:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as f:
            for a in all_aliases:
                f.write(json.dumps(a, ensure_ascii=False))
                f.write("\n")
        print(f"[write] wrote {len(all_aliases)} aliases to {args.out}",
              file=sys.stderr)
    else:
        print(f"[dry-run] {len(all_aliases)} aliases (not written)",
              file=sys.stderr)


if __name__ == "__main__":
    main()
