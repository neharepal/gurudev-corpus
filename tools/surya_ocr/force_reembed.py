#!/usr/bin/env python3
"""Force the embedder to re-encode specific works (handles the stale-vector gotcha).

WHY THIS EXISTS: tools/embedder.py carries over vectors by chunk_id ONLY — it never
compares text (build_id_to_vec keys on id; a count-match short-circuit can skip a build
entirely). So after replacing a work's text.md with the SAME chunk_ids, a normal embed
run would keep the OLD vectors. This script evicts the named works' rows from the
id→vec source (embeddings.npy + chunks_meta.jsonl, kept row-aligned), so the very next
`python tools/embedder.py` sees those ids as NEW and re-encodes them from the fresh text.

Order (from repo root), after apply_replacements.py --apply:
    python tools/chunker.py                                   # rebuild chunks.jsonl from new text
    python tools/surya_ocr/force_reembed.py --apply <ids...>  # evict old vectors for those works
    python tools/embedder.py                                  # re-encode the evicted works only

Usage:
    python tools/surya_ocr/force_reembed.py sadhakbodh gurudev-paramarthik-shikvan   # dry-run
    python tools/surya_ocr/force_reembed.py --apply sadhakbodh ...                    # do it
"""
from __future__ import annotations
import argparse, datetime, json, shutil, sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[2]
EMB = REPO / "04_processed/embeddings/embeddings.npy"
META = REPO / "04_processed/embeddings/chunks_meta.jsonl"
TODAY = datetime.date.today().isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("work_ids", nargs="+")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    metas = [json.loads(l) for l in META.read_text(encoding="utf-8").splitlines() if l.strip()]
    emb = np.load(EMB)
    if len(metas) != emb.shape[0]:
        print(f"ABORT: index misaligned ({len(metas)} metas vs {emb.shape[0]} vectors) — do not touch."); return 1

    prefixes = tuple(f"{w}--" for w in args.work_ids)
    keep, evict = [], []
    for i, m in enumerate(metas):
        (evict if str(m.get("id", "")).startswith(prefixes) else keep).append(i)

    per_work = {w: sum(1 for m in metas if str(m.get("id", "")).startswith(f"{w}--")) for w in args.work_ids}
    print(f"Index: {len(metas):,} rows. Evicting {len(evict):,} rows across {len(args.work_ids)} works:")
    for w, c in per_work.items():
        print(f"  {w:38} {c:>6} chunks" + ("" if c else "   <-- WARNING: 0 rows (already re-chunked or wrong id?)"))
    if not evict:
        print("Nothing to evict. If you already ran the chunker with a changed chunk count, the ids"
              " may differ — run this BEFORE the chunker, or use `python tools/embedder.py --restart`.")
        return 0
    if not args.apply:
        print("\nDry-run. Re-run with --apply to write the evicted index (a backup is made first).")
        return 0

    bak = EMB.parent / f"_bak-reocr-{TODAY}"
    bak.mkdir(exist_ok=True)
    shutil.copy2(EMB, bak / EMB.name)
    shutil.copy2(META, bak / META.name)
    keep = sorted(keep)
    new_emb = emb[keep]
    new_metas = [metas[i] for i in keep]
    assert new_emb.shape[0] == len(new_metas), "post-evict misalignment"
    np.save(EMB, new_emb)
    META.write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in new_metas) + "\n", encoding="utf-8")
    print(f"\nBacked up to {bak}. Index now {new_emb.shape[0]:,} rows (was {emb.shape[0]:,}).")
    print("Next: python tools/embedder.py   (re-encodes the evicted works as new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
