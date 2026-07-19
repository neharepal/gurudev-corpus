#!/usr/bin/env python3
"""Post-ingest verifier for RFC-017 arthasahit works.

The 7 arthasahit works (verse + sadhak-authored meaning) must ingest with a
special contract:
  - `cite_text` is the VERSE only (never the meaning, so we never mis-attribute
    the sadhak's gloss to Gurudev). The verse must not contain the marker
    word `अर्थ` (that word starts the meaning block).
  - A row with no `cite_text` key is retrieval-only — surfaces in search but
    splice drops the citation (RFC-017 uncertain-split path).

This tool checks a completed ingest end-to-end:
  1. Every arthasahit work_id has at least one child row in chunks.jsonl.
  2. Every arthasahit child either has `cite_text` (lacking `अर्थ`) OR has
     no `cite_text` key at all (retrieval-only).
  3. Every arthasahit child's `parent_id` resolves in parents.jsonl.
  4. Row alignment: embeddings.npy rows == chunks_meta.jsonl lines ==
     chunks.jsonl lines. (This is the invariant every retrieval query relies
     on — one bad row breaks the whole index.)

Exit code 0 = PASS, 1 = FAIL. Use `--work-id <id>` to scope checks 1-3 to a
single work (the row-alignment check is always corpus-wide).

Usage:
  tools/verify_arthasahit_ingest.py                    # verify all 7 works
  tools/verify_arthasahit_ingest.py --work-id tukaram-vachanamrut
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parent.parent
CHUNKS_PATH = REPO / "04_processed" / "chunks.jsonl"
PARENTS_PATH = REPO / "04_processed" / "parents.jsonl"
EMB_DIR = REPO / "04_processed" / "embeddings"
EMB_PATH = EMB_DIR / "embeddings.npy"
META_PATH = EMB_DIR / "chunks_meta.jsonl"

ARTHASAHIT_WORK_IDS = frozenset({
    "tukaram-vachanamrut", "eknath-vachanamrut", "ramdas-vachanamrut",
    "sant-vachanamrut", "jnaneshwar-vachanamrut", "eknathi-bhagvat-vachanamrut",
    "dhyanopakarani-gita",
})

ARTHA_MARKER = "अर्थ"

# In an arthasahit book, `अर्थ` marks the start of the sadhak's meaning-gloss
# section — it's a paragraph-initial heading (`अर्थ -`, `अर्थ :`, `अर्थ १`),
# NOT an inline noun/adverb use. The verifier's pattern MUST mirror the
# parser's boundary check exactly (arthasahit_parse.py:_ARTHA_RE) — otherwise
# the verifier flags cases the parser correctly kept in the verse.
#
# False positives previously caught:
#   • `अर्थात्` / `अर्थात` — Marathi/Sanskrit adverb "that is, meaning"
#     (~40 in tukaram-vachanamrut, 3000+ across the wider corpus).
#   • Inline `अर्थ` as a noun meaning "meaning / purpose / sense" —
#     "श्लोकाचा अर्थ", "बोल लावण्यात अर्थ नाही", "महावाक्याचा अर्थ",
#     "त्याचा अर्थ समजेल", etc.
# Only line-start `अर्थ` (with a non-Devanagari continuation) qualifies.
import re
_ARTHA_HEADER_RE = re.compile(r"(?m)^\s*अर्थ(?![ऀ-ॿ])")


def _has_artha_header(text: str) -> bool:
    """True if `text` contains a line-initial arthasahit meaning-gloss
    heading. Mirrors the split marker in arthasahit_parse.py so the
    verifier and the parser stay in agreement."""
    return bool(_ARTHA_HEADER_RE.search(text or ""))


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def verify_arthasahit_children(
    chunks_path: Path,
    parents_path: Path,
    *,
    only_work_id: str | None = None,
) -> tuple[list[str], dict]:
    """Return (errors, stats) for arthasahit rows in chunks.jsonl.

    stats keys: `children_by_work` (dict), `citable`, `retrieval_only`,
    `total_arthasahit_children`.
    """
    if only_work_id and only_work_id not in ARTHASAHIT_WORK_IDS:
        return (
            [f"--work-id {only_work_id!r} is not one of the 7 arthasahit works"],
            {},
        )

    scope: frozenset[str] = (
        frozenset({only_work_id}) if only_work_id else ARTHASAHIT_WORK_IDS
    )

    parent_ids: set[str] = set()
    for p in _iter_jsonl(parents_path):
        pid = p.get("id")
        if pid:
            parent_ids.add(pid)

    errors: list[str] = []
    children_by_work: dict[str, int] = {}
    citable = 0
    retrieval_only = 0
    total = 0

    for row in _iter_jsonl(chunks_path):
        wid = row.get("work_id")
        if wid not in scope:
            continue
        if row.get("kind_level") != "child":
            # chunks.jsonl is children-only by contract; a stray parent row
            # here would break the row-alignment check downstream, so surface
            # it as a hard error rather than silently skipping.
            errors.append(
                f"row {row.get('id')!r}: work_id={wid} but kind_level="
                f"{row.get('kind_level')!r} (expected 'child')"
            )
            continue
        total += 1
        children_by_work[wid] = children_by_work.get(wid, 0) + 1

        pid = row.get("parent_id")
        if not pid or pid not in parent_ids:
            errors.append(
                f"child {row.get('id')!r}: parent_id={pid!r} not found in parents.jsonl"
            )

        if "cite_text" in row:
            cite = row["cite_text"] or ""
            if _has_artha_header(cite):
                errors.append(
                    f"child {row.get('id')!r}: cite_text contains {ARTHA_MARKER!r} "
                    f"— the sadhak's meaning leaked into the citation"
                )
            elif not cite.strip():
                # Present-but-empty cite_text is worse than absent — splice
                # would render an empty quotation. Treat as an error.
                errors.append(
                    f"child {row.get('id')!r}: cite_text is present but empty"
                )
            else:
                citable += 1
        else:
            retrieval_only += 1

    for wid in scope:
        if wid not in children_by_work:
            errors.append(f"work_id {wid!r}: no child rows in chunks.jsonl")

    stats = {
        "children_by_work": children_by_work,
        "citable": citable,
        "retrieval_only": retrieval_only,
        "total_arthasahit_children": total,
    }
    return errors, stats


def verify_row_alignment(
    chunks_path: Path,
    meta_path: Path,
    emb_path: Path,
) -> tuple[list[str], dict]:
    """embeddings.npy row count == chunks_meta lines == chunks.jsonl lines.

    Uses numpy's memmap header read so we don't page the whole matrix in.
    """
    errors: list[str] = []

    def _count(path: Path) -> int:
        n = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n

    chunks_n = _count(chunks_path)
    meta_n = _count(meta_path)

    try:
        import numpy as np
        emb = np.load(emb_path, mmap_mode="r")
        emb_rows = int(emb.shape[0])
    except Exception as e:
        errors.append(f"could not read embeddings.npy: {e}")
        emb_rows = -1

    if not (chunks_n == meta_n == emb_rows):
        errors.append(
            f"row-alignment: chunks.jsonl={chunks_n:,}, "
            f"chunks_meta.jsonl={meta_n:,}, embeddings.npy={emb_rows:,} "
            "(all three must match)"
        )
    return errors, {
        "chunks_lines": chunks_n,
        "meta_lines": meta_n,
        "emb_rows": emb_rows,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--work-id", default=None,
                   help="Scope arthasahit checks (1-3) to a single work.")
    p.add_argument("--chunks", type=Path, default=CHUNKS_PATH)
    p.add_argument("--parents", type=Path, default=PARENTS_PATH)
    p.add_argument("--emb", type=Path, default=EMB_PATH)
    p.add_argument("--meta", type=Path, default=META_PATH)
    args = p.parse_args()

    for req in (args.chunks, args.parents, args.emb, args.meta):
        if not req.exists():
            print(f"FAIL: missing {req}", file=sys.stderr)
            return 1

    errors: list[str] = []

    art_errors, art_stats = verify_arthasahit_children(
        args.chunks, args.parents, only_work_id=args.work_id,
    )
    errors.extend(art_errors)

    align_errors, align_stats = verify_row_alignment(
        args.chunks, args.meta, args.emb,
    )
    errors.extend(align_errors)

    scope = f"work_id={args.work_id}" if args.work_id else "all 7 works"
    print(f"Arthasahit verification ({scope})")
    print(f"  total children:  {art_stats.get('total_arthasahit_children', 0):,}")
    print(f"  citable:         {art_stats.get('citable', 0):,}")
    print(f"  retrieval-only:  {art_stats.get('retrieval_only', 0):,}")
    for wid, n in sorted(art_stats.get("children_by_work", {}).items()):
        print(f"    {wid}: {n:,}")
    print("Row alignment:")
    print(f"  chunks.jsonl:     {align_stats.get('chunks_lines', -1):,}")
    print(f"  chunks_meta.jsonl:{align_stats.get('meta_lines', -1):,}")
    print(f"  embeddings.npy:   {align_stats.get('emb_rows', -1):,}")

    if errors:
        print(f"\nFAIL ({len(errors)} error{'s' if len(errors) != 1 else ''}):",
              file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
