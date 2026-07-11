#!/usr/bin/env python3
"""OCR quality gate (RFC-009 Step 4) for extracted.md files.

Automated checks for the failure modes that quietly ruin Reading Mode and retrieval:

  1. decode garbage      — U+FFFD replacement chars (OCR bytes that didn't decode)
  2. legacy-font mojibake — Shree-Lipi/Lipika symbol chars leaking through (˜ Ï ¡ Ô …)
  3. script ratio        — Devanagari share implausibly low (OCR failure or wrong -l)
  4. header/footer leak  — a short line recurring ~once per page (running title/chapter
                           banner leaking into the body, as PGHL suffered)

Usage:
  python tools/ocr_qa.py FILE.extracted.md [--pages N]
  python tools/ocr_qa.py DIR/*.extracted.md          # globbed; pages estimated per file

--pages gives the true page count (from `pdfinfo`) for the header/footer test; without it,
pages are estimated from char count (~1800 chars/page). Exit 0 if all pass, 1 if any flags.
"""
from __future__ import annotations
import argparse, re, sys
from collections import Counter
from pathlib import Path

MOJIBAKE = re.compile(r"[˜Ï¡Ô†¬»½ѽ]")          # glyphs seen in Lipika/Shree-Lipi mojibake
VERSE = re.compile(r"^[०-९\d\s।॥\-\.]+$")            # pure verse/number markers — never a header
CHARS_PER_PAGE_EST = 1800

# thresholds
REPL_FRAC_FAIL = 0.001      # >0.1% replacement chars → fail
MOJIBAKE_FRAC_FAIL = 0.0005 # >0.05% mojibake glyphs → fail
DEVA_FRAC_WARN = 0.35       # <35% Devanagari on a MR work → warn (trilingual books run ~60%)
HEADER_PAGE_FRAC = 0.20     # a line recurring on ≥20% of pages → flagged as running header


def check(path: Path, pages: int | None) -> list[str]:
    t = path.read_text(encoding="utf-8")
    n = max(len(t), 1)
    flags: list[str] = []

    repl = t.count("�")
    if repl / n > REPL_FRAC_FAIL:
        flags.append(f"FAIL decode-garbage: {repl} � chars ({100*repl/n:.2f}%)")

    moji = len(MOJIBAKE.findall(t))
    if moji / n > MOJIBAKE_FRAC_FAIL:
        flags.append(f"FAIL legacy-font-mojibake: {moji} symbol chars ({100*moji/n:.2f}%)")

    deva = sum(0x900 <= ord(c) <= 0x97f for c in t)
    latin = sum(c.isascii() and c.isalpha() for c in t)
    if deva / n < DEVA_FRAC_WARN:
        flags.append(f"WARN low-devanagari: {100*deva/n:.0f}% (latin {100*latin/n:.0f}%) — verify lang/scan")

    npg = pages or max(n // CHARS_PER_PAGE_EST, 1)
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    c = Counter(l for l in lines if 3 < len(l) <= 80 and not VERSE.match(l))
    thresh = max(8, int(npg * HEADER_PAGE_FRAC))
    leaks = [(l, k) for l, k in c.items() if k >= thresh]
    for l, k in sorted(leaks, key=lambda x: -x[1]):
        flags.append(f"FAIL header/footer-leak: {k}x (~{100*k/npg:.0f}% of {npg}p) «{l[:50]}»")

    stat = f"{path.name}: {n} chars, {100*deva/n:.0f}% deva, {100*latin/n:.0f}% latin, ~{npg}p"
    return [stat] + flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--pages", type=int, default=None)
    a = ap.parse_args()
    any_fail = False
    for fp in a.files:
        p = Path(fp)
        lines = check(p, a.pages)
        stat, flags = lines[0], lines[1:]
        verdict = "PASS" if not any(f.startswith("FAIL") for f in flags) else "FLAG"
        if verdict == "FLAG":
            any_fail = True
        print(f"[{verdict}] {stat}")
        for f in flags:
            print(f"        {f}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
