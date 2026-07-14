#!/usr/bin/env python3
"""Compare Surya re-OCR output against the current (tesseract) corpus text.

Run on the MAIN machine after the M4 hands back `out/<work_id>.md`. Scores each
book on the SAME metrics as the OCR audit (tools/ocr_qa.py): Devanagari share,
legacy-font mojibake, decode-garbage, header/footer leak, plus length delta as a
truncation guard. Emits a per-work verdict and writes replace_decisions.yaml,
which apply_replacements.py consumes.

Usage (from repo root):
    python tools/surya_ocr/compare.py --surya-dir _surya_ocr_job/out
    python tools/surya_ocr/compare.py --surya-dir _surya_ocr_job/out --work sadhakbodh

Verdicts:
  REPLACE   Surya clearly cleaner (less mojibake/garbage, deva% not dropped) and
            length is sane (no truncated OCR).
  REVIEW    mixed signal — human eyeballs the sample before deciding.
  KEEP      Surya no better, or shorter/worse — likely a poor SOURCE scan (needs a
            better copy, not a better engine).
"""
from __future__ import annotations
import argparse, glob, json, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from ocr_qa import MOJIBAKE, VERSE  # reuse the audit's exact definitions
from collections import Counter
import yaml

GARBLED = [
    "jivandarshan-deshpande", "kannada-sahityatil-punyasmruti", "vindication-of-indian-philosophy",
    "sadhakbodh", "javak-patre-tipane", "gurudev-paramarthik-shikvan", "sonari-pane-2000",
    "kushal-pradhyapak", "allahabad-days-mr", "kannad-parmarth-sopan", "parmartha-mandir",
    "swanandacha-gabha", "acpr-silver-jubilee-vol1", "acpr-silver-jubilee-vol2", "pawanbhumi-jamkhandi",
]


def metrics(text: str) -> dict:
    n = max(len(text), 1)
    deva = sum(0x900 <= ord(c) <= 0x97f for c in text)
    latin = sum(c.isascii() and c.isalpha() for c in text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    c = Counter(l for l in lines if 3 < len(l) <= 80 and not VERSE.match(l))
    npg = max(n // 1800, 1)
    leaks = sum(1 for l, k in c.items() if k >= max(8, int(npg * 0.20)))
    return {
        "chars": len(text),
        "deva_pct": round(100 * deva / n, 1),
        "latin_pct": round(100 * latin / n, 1),
        "repl": text.count("�"),
        "mojibake": len(MOJIBAKE.findall(text)),
        "header_leaks": leaks,
    }


def resolve_current_text_md(work_dir: Path, orig_lang: str | None) -> Path | None:
    cands = list(work_dir.glob("*/text.md"))
    if not cands:
        return None
    if orig_lang:
        for c in cands:
            if c.parent.name == orig_lang:
                return c
    return max(cands, key=lambda p: p.stat().st_size)  # the main body


def verdict(old: dict, new: dict) -> tuple[str, str]:
    # truncation guard: Surya text should be within a sane length band of the old
    ratio = new["chars"] / max(old["chars"], 1)
    if ratio < 0.55:
        return "KEEP", f"surya {ratio:.0%} of old length — truncated/poor source scan"
    cleaner = (new["mojibake"] <= old["mojibake"] and new["repl"] <= old["repl"]
               and new["header_leaks"] <= old["header_leaks"])
    deva_drop = old["deva_pct"] - new["deva_pct"]
    junk_gone = (old["mojibake"] - new["mojibake"]) + (old["repl"] - new["repl"])
    if cleaner and deva_drop <= 5 and (junk_gone > 0 or old["header_leaks"] > new["header_leaks"]):
        return "REPLACE", f"cleaner: mojibake {old['mojibake']}->{new['mojibake']}, repl {old['repl']}->{new['repl']}, leaks {old['header_leaks']}->{new['header_leaks']}"
    if not cleaner or deva_drop > 5:
        return "REVIEW", f"mixed: deva {old['deva_pct']}%->{new['deva_pct']}%, mojibake {old['mojibake']}->{new['mojibake']}, repl {old['repl']}->{new['repl']}"
    return "REVIEW", "no clear junk reduction — eyeball the sample"


def sample(text: str, span: int = 220) -> str:
    start = int(len(text) * 0.4)
    return " ".join(text[start:start + span].split())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surya-dir", default="_surya_ocr_job/out", help="folder with out/<work_id>.md")
    ap.add_argument("--work", action="append", help="limit to these work_ids (repeatable)")
    ap.add_argument("--out", default="tools/surya_ocr/replace_decisions.yaml")
    args = ap.parse_args()

    os.chdir(REPO)
    metas = {}
    for mp in glob.glob("**/meta.yaml", recursive=True):
        try:
            d = yaml.safe_load(open(mp, encoding="utf-8")) or {}
        except Exception:
            continue
        if d.get("id") in GARBLED:
            metas[d["id"]] = (Path(mp).parent, d.get("original_language"))

    todo = args.work or GARBLED
    decisions = {}
    print(f"{'work_id':38} {'verdict':8} {'old→new deva%':>16} {'moji':>10} {'repl':>10} {'len Δ':>8}")
    print("-" * 100)
    for wid in todo:
        surya_md = Path(args.surya_dir) / f"{wid}.md"
        if wid not in metas:
            print(f"{wid:38} (no meta)"); continue
        wdir, lang = metas[wid]
        cur = resolve_current_text_md(wdir, lang)
        if not surya_md.exists():
            print(f"{wid:38} {'PENDING':8} (no {surya_md})"); continue
        if not cur:
            print(f"{wid:38} (no current text.md)"); continue
        old = metrics(cur.read_text(encoding="utf-8", errors="replace"))
        new = metrics(surya_md.read_text(encoding="utf-8", errors="replace"))
        v, why = verdict(old, new)
        decisions[wid] = {
            "verdict": v, "replace": v == "REPLACE", "reason": why,
            "current_text_md": str(cur), "surya_md": str(surya_md),
            "old": old, "new": new,
        }
        dpct = f"{old['deva_pct']}→{new['deva_pct']}"
        moji = f"{old['mojibake']}→{new['mojibake']}"
        repl = f"{old['repl']}→{new['repl']}"
        dl = f"{new['chars']/max(old['chars'],1):.0%}"
        print(f"{wid:38} {v:8} {dpct:>16} {moji:>10} {repl:>10} {dl:>8}")
    # samples for REVIEW/REPLACE
    print("\n=== samples (40% into each doc) for eyeballing ===")
    for wid, d in decisions.items():
        if d["verdict"] in ("REPLACE", "REVIEW"):
            old_s = sample(Path(d["current_text_md"]).read_text(encoding="utf-8", errors="replace"))
            new_s = sample(Path(d["surya_md"]).read_text(encoding="utf-8", errors="replace"))
            print(f"\n--- {wid} [{d['verdict']}] ---")
            print(f"  TESSERACT: {old_s}")
            print(f"  SURYA    : {new_s}")

    Path(args.out).write_text(yaml.safe_dump(decisions, allow_unicode=True, sort_keys=True), encoding="utf-8")
    n_rep = sum(1 for d in decisions.values() if d["replace"])
    print(f"\nWrote {args.out}: {n_rep} REPLACE / {len(decisions)} scored.")
    print("Review it (flip any REVIEW→replace:true you approve), then: python tools/surya_ocr/apply_replacements.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
