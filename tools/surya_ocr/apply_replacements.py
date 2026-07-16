#!/usr/bin/env python3
"""Replace tesseract text.md with the Surya re-OCR, per replace_decisions.yaml.

Run on the MAIN machine after reviewing compare.py's output. For each work marked
`replace: true`, this backs up the old text.md, drops the Surya text in place
(same work_id), and records the change in meta.yaml. It does NOT re-embed — do that
with force_reembed.py + the embedder (see RETURN-WORKFLOW.md).

Usage (from repo root):
    python tools/surya_ocr/apply_replacements.py                 # dry-run (shows plan)
    python tools/surya_ocr/apply_replacements.py --apply         # do it
"""
from __future__ import annotations
import argparse, datetime, shutil, sys
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[2]
DECISIONS = REPO / "tools/surya_ocr/replace_decisions.yaml"
TODAY = datetime.date.today().isoformat()


def update_meta(meta_path: Path, old_m: dict, new_m: dict) -> None:
    d = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    d["text_extraction_method"] = f"surya-ocr (M4 re-OCR {TODAY})"
    note = (f"Re-OCR'd {TODAY} with Surya (Apple-Silicon) to replace garbled tesseract "
            f"output; deva {old_m['deva_pct']}%→{new_m['deva_pct']}%, "
            f"mojibake {old_m['mojibake']}→{new_m['mojibake']}, repl {old_m['repl']}→{new_m['repl']}.")
    prev = d.get("quality_notes")
    d["quality_notes"] = (str(prev) + " | " + note) if prev else note
    d.setdefault("re_ocr", []).append(
        {"date": TODAY, "engine": "surya-ocr", "reason": "tesseract garble (audit 2026-07-14)"})
    meta_path.write_text(
        yaml.safe_dump(d, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="perform the replacement (default: dry-run)")
    ap.add_argument("--decisions", default=str(DECISIONS))
    args = ap.parse_args()

    import os
    os.chdir(REPO)  # decisions store repo-relative paths
    dec = yaml.safe_load(Path(args.decisions).read_text(encoding="utf-8")) or {}
    todo = {w: d for w, d in dec.items() if d.get("replace")}
    if not todo:
        print("Nothing marked replace:true in", args.decisions); return 0

    bak_root = REPO / "04_processed" / f"_bak-reocr-{TODAY}"
    print(f"{'APPLY' if args.apply else 'DRY-RUN'} — {len(todo)} works; backups → {bak_root}\n")
    replaced = []
    for wid, d in sorted(todo.items()):
        cur = Path(d["current_text_md"]); surya = Path(d["surya_md"])
        if not surya.exists():
            print(f"  SKIP {wid}: missing {surya}"); continue
        meta_path = cur.parent.parent / "meta.yaml"
        print(f"  {wid}")
        print(f"     text.md : {cur}   ({d['old']['chars']:,} → {d['new']['chars']:,} chars)")
        print(f"     reason  : {d['reason']}")
        if args.apply:
            rel = cur.relative_to(REPO) if cur.is_absolute() else cur
            bak = bak_root / rel
            bak.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cur, bak)                 # keep the tesseract original
            shutil.copy2(surya, cur)               # drop Surya in place
            if meta_path.exists():
                update_meta(meta_path, d["old"], d["new"])
            replaced.append(wid)
    if args.apply:
        print(f"\nReplaced {len(replaced)} works. Now force-re-embed them:")
        print(f"  python tools/chunker.py")
        print(f"  python tools/surya_ocr/force_reembed.py --apply {' '.join(replaced)}")
        print(f"  python tools/embedder.py")
    else:
        print("\nDry-run only. Re-run with --apply to perform replacements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
