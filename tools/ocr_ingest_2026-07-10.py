#!/usr/bin/env python3
"""OCR driver for the Neha3 batch (drive_dump_2026-07-10).

Renders each scanned/legacy-font PDF to 300-DPI PNGs and OCRs every page with
tesseract `mar+san+eng` (these editions are trilingual: Marathi verse + English
translation + Marathi commentary). Concatenates page text into an extracted.md
per book, with conservative cleanup so the output needs no later hand-cleaning.

Hard-won environment notes (see RFC-009 Step 3):
  - Locale MUST be UTF-8, or sed/tesseract choke on Devanagari bytes.
  - tesseract/leptonica FAIL when the current working directory contains
    non-ASCII (Devanagari) chars — so we always run from an ASCII cwd and pass
    absolute paths. PNGs are rendered into an ASCII temp dir.

Resumable: a book whose extracted.md already exists is skipped.
Local + free: no API calls, no paid OCR.
"""
from __future__ import annotations
import os, re, sys, shutil, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path("/Users/neharepal/gurudev-corpus")
STAGING = REPO / "00_raw" / "drive_dump_2026-07-10"
OUT_DIR = STAGING / "_extracted"
DPI = 300
LANGS = "mar+san+eng"
WORKERS = 8

ENV = {**os.environ, "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}

# (pdf filename in STAGING, output slug)
BOOKS = [
    ("काकांची प्रवचने भाग ४.pdf", "kakanchi-pravachane-4"),
    ("काकांची प्रवचन भाग ५.pdf", "kakanchi-pravachane-5"),
    ("तुकाराम वचनामृत अर्थासहित.pdf", "tukaram-vachanamrut"),
    ("एकनाथ वचनामृत अर्थासहित.pdf", "eknath-vachanamrut"),
    ("रामदास वचनामृत अर्थासहित.pdf", "ramdas-vachanamrut"),
    ("संत वचनामृत अर्थासहित.pdf", "sant-vachanamrut"),
    ("ज्ञानेश्वर वचनामृत अर्थासहित .pdf", "jnaneshwar-vachanamrut"),
    ("एकनाथी भागवत वचनामृत.pdf", "eknathi-bhagvat-vachanamrut"),
    ("स्वानंदाचा गाभा संपूर्ण .pdf", "swanandacha-gabha"),
    ("ध्यानोपकारणी गीता अर्थासहित.pdf", "dhyanopakarani-gita"),
]

_PAGENUM = re.compile(r"^[\s]*[०-९0-9]{1,4}[\s]*$")          # bare page number line
_DEVA = re.compile(r"[ऀ-ॿ]")


def clean_page(text: str) -> str:
    """Conservative per-page cleanup. Preserves verse line structure."""
    out = []
    for line in text.splitlines():
        s = line.rstrip()
        if _PAGENUM.match(s):          # drop standalone page numbers (not ॥verse॥ marks)
            continue
        out.append(s)
    joined = "\n".join(out)
    # de-hyphenate English line-break hyphens (Latin letter + '-' at EOL → join)
    joined = re.sub(r"([A-Za-z])-\n([A-Za-z])", r"\1\2", joined)
    # collapse 3+ blank lines → one blank line
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def ocr_page(png: Path) -> str:
    # Pipe the image via STDIN, not by path: leptonica's C fopen fails intermittently
    # on this box ("failed to open locally") regardless of locale/cwd. Reading the image
    # from stdin bypasses that path entirely. Decode stdout leniently, discard stderr.
    r = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", LANGS],
        input=png.read_bytes(),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=ENV,
    )
    return r.stdout.decode("utf-8", errors="replace")


def process_book(pdf_name: str, slug: str) -> None:
    pdf = STAGING / pdf_name
    out = OUT_DIR / f"{slug}.extracted.md"
    if out.exists():
        print(f"[skip] {slug} (already extracted)", flush=True)
        return
    if not pdf.exists():
        print(f"[MISS] {slug}: {pdf_name} not found", flush=True)
        return
    print(f"[start] {slug} — rendering {DPI}dpi …", flush=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"ocr_{slug}_", dir="/tmp"))  # ASCII cwd/dir
    try:
        subprocess.run(
            ["pdftoppm", "-r", str(DPI), "-png", str(pdf), str(tmp / "pg")],
            check=True, env=ENV, capture_output=True,
        )
        pages = sorted(tmp.glob("pg-*.png"))
        print(f"[ocr] {slug} — {len(pages)} pages, {WORKERS} workers …", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            texts = list(ex.map(ocr_page, pages))
        body = "\n\n".join(clean_page(t) for t in texts if t.strip())
        chars = len(body)
        deva = len(_DEVA.findall(body))
        ratio = deva / max(chars, 1)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        print(f"[done] {slug} — {len(pages)}p, {chars} chars, {ratio:.0%} devanagari → {out.name}", flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    os.chdir("/tmp")  # ASCII cwd — critical for leptonica
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for pdf_name, slug in BOOKS:
        if only and only != slug:
            continue
        process_book(pdf_name, slug)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
