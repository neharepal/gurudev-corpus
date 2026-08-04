#!/usr/bin/env python3
"""MiM-specific canonical assembler.

Consumes Surya OCR output and produces a structured canonical text.md for
Mysticism in Maharashtra (Ranade, 1933). Uses the hand-verified TOC from the
IA scan (`dli.ministry.14639`) for chapter titles, so OCR errors in headings
(diacritics, hyphenation) can never bleed into the `##`/`###` markers.

Strategy — STRUCTURAL MARKERS ONLY. Body prose from Surya is emitted
verbatim; we never mutate Ranade's text. What we DO add:
  1. `##` / `###` / `####` markers from the Contents pages, positioned in
     reading order.
  2. `####` sub-item markers interleaved before body paragraphs whose first
     token is the matching `N.`.
  3. `####` preface roman-numeral markers (I / II / III / IV).

The book's two-column marginalia layout (short section titles printed in
the left margin next to numbered body paragraphs) causes Surya to
interleave shoulder-note words into body prose line by line. Multiple
post-fix heuristics were tried and reverted 2026-08-03 — see the research
notes / RFC-023 that supersedes this assembler. Until a proper column-
aware OCR pipeline lands, body prose from the preface + chapter openers
will contain merged shoulder-note fragments; the reader should surface
them as-is rather than heuristically strip.

Output: `_surya_ocr_job/staging/mim-canonical.candidate.md`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RESULTS = Path("_surya_ocr_job/out_raw/mysticism-in-maharashtra/mysticism-in-maharashtra/results.json")
OUT = Path("_surya_ocr_job/staging/mim-canonical.candidate.md")

# Hand-verified TOC from IA scan `dli.ministry.14639`. Roman numeral →
# (level, canonical title).
TOC: dict[str, tuple[int, str]] = {
    "PART I":     (2, "Part I"),
    "PART II":    (2, "Part II"),
    "PART III":   (2, "Part III"),
    "PART IV":    (2, "Part IV"),
    "PART V":     (2, "Part V"),
    "CHAPTER I":   (2, "Chapter I. Introduction: The Development of Indian Mysticism up to the Age of Jñāneśvara"),
    "CHAPTER II":  (3, "Chapter II. Jñānadeva: Biographical Introduction"),
    "CHAPTER III": (3, "Chapter III. The Jñāneśvarī"),
    "CHAPTER IV":  (3, "Chapter IV. The Amṛtānubhava"),
    "CHAPTER V":   (3, "Chapter V. The Abhaṅgas of Nivṛtti, Jñānadeva, Sopāna, Muktābāi, and Chāṅgadeva"),
    "CHAPTER VI":  (3, "Chapter VI. General Review of the Period"),
    "CHAPTER VII": (3, "Chapter VII. Biographical Introduction"),
    "CHAPTER VIII":(3, "Chapter VIII. The Abhaṅgas of Nāmadeva and Contemporary Saints"),
    "CHAPTER IX":  (3, "Chapter IX. General Review"),
    "CHAPTER X":   (3, "Chapter X. Biographical Introduction: Bhānudāsa, Janārdana Swāmī, and Ekanātha"),
    "CHAPTER XI":  (3, "Chapter XI. The Abhaṅgas of Bhānudāsa, Janārdana Swāmī, and Ekanātha"),
    "CHAPTER XII": (3, "Chapter XII. Introduction: The Bhāgavata of Ekanātha"),
    "CHAPTER XIII":(3, "Chapter XIII. General Review"),
    "CHAPTER XIV": (3, "Chapter XIV. Biographical Introduction: Tukārāma"),
    "CHAPTER XV":  (3, "Chapter XV. Tukārāma's Mystical Career"),
    "CHAPTER XVI": (3, "Chapter XVI. Tukārāma's Mystical Teaching"),
    "CHAPTER XVII":(3, "Chapter XVII. General Review"),
    "CHAPTER XVIII":(3,"Chapter XVIII. Biographical Introduction"),
    "CHAPTER XIX": (3, "Chapter XIX. The Dāsabodha"),
    "CHAPTER XX":  (3, "Chapter XX. General Review and Conclusion"),
}

PREFACE_START_PDF_PAGE = 7
TOC_START_PDF_PAGE = 42
BODY_START_PDF_PAGE = 53

_DROP_LABELS = {"PageHeader", "PageFooter", "Footnote"}
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_KEY_RE = re.compile(r"^\s*(PART|CHAPTER)\s+([IVXL]+)\s*\.?\s*$", re.IGNORECASE)
_HEADING_START_RE = re.compile(r"^\s*(PART|CHAPTER)\s+([IVXL]+)(\.|\s|$)", re.IGNORECASE)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    s = _BR_RE.sub("\n", html)
    s = _TAG_RE.sub("", s)
    s = (
        s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
        .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    )
    return "\n".join(line.rstrip() for line in s.splitlines()).strip()


def normalize_heading_key(text: str) -> str | None:
    m = _HEADING_START_RE.match(text)
    if not m:
        return None
    kind, roman = m.group(1).upper(), m.group(2).upper()
    key = f"{kind} {roman}"
    return key if key in TOC else None


_ITEM_RE = re.compile(r"(\d+)\.\s+(.+?)\s*\(\s*p\.\s*(\d+)\s*\)")
_SUBDIV_RE = re.compile(r"\(([IVXL]+)\)\s+([A-Z][a-zA-Z ]+)\.\s*[—–-]\s*")


def parse_toc_items(pages) -> dict[str, list[tuple[int, str, int]]]:
    out: dict[str, list[tuple[int, str, int]]] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush():
        nonlocal buffer
        if current and buffer:
            joined = " ".join(buffer)
            joined = re.sub(r"-\s+", "", joined)
            joined = re.sub(r"\s+", " ", joined)
            out.setdefault(current, [])
            for m in _ITEM_RE.finditer(joined):
                n = int(m.group(1))
                title = m.group(2).strip().rstrip(";").strip()
                title = _SUBDIV_RE.sub("", title).strip()
                out[current].append((n, title, int(m.group(3))))
        buffer = []

    for page in pages:
        pp = page.get("page", 0)
        if pp < TOC_START_PDF_PAGE or pp >= BODY_START_PDF_PAGE:
            continue
        blocks = sorted(
            (b for b in page.get("blocks", []) if isinstance(b, dict)),
            key=lambda b: b.get("reading_order", 10**9),
        )
        for b in blocks:
            if b.get("label") in _DROP_LABELS:
                continue
            text = html_to_text(b.get("html", "")).strip()
            if not text:
                continue
            if b.get("label") == "SectionHeader":
                key = normalize_heading_key(text)
                if key and key.startswith("CHAPTER"):
                    flush()
                    current = key
                    continue
            if current:
                buffer.append(text)
    flush()
    return out


def main() -> int:
    if not RESULTS.exists():
        print(f"ERR: {RESULTS} not found — MiM OCR hasn't finished.", file=sys.stderr)
        return 1
    with open(RESULTS, encoding="utf-8") as f:
        raw_json = json.load(f)
    pages = raw_json["mysticism-in-maharashtra"]
    pages_sorted = sorted(pages, key=lambda p: p.get("page", 0))

    items_by_chapter = parse_toc_items(pages_sorted)

    body_lines: list[str] = []
    inserted: dict[str, bool] = {k: False for k in TOC}
    swallow_next_heading_for: str | None = None
    pending_items: dict[int, str] = {}
    _NUM_PARA_RE = re.compile(r"^\s*(\d+)\.\s")

    for page in pages_sorted:
        pdf_page = page.get("page", 0)
        if TOC_START_PDF_PAGE <= pdf_page < BODY_START_PDF_PAGE:
            continue
        if pdf_page < PREFACE_START_PDF_PAGE:
            continue

        blocks = sorted(
            (b for b in page.get("blocks", []) if isinstance(b, dict)),
            key=lambda b: b.get("reading_order", 10**9),
        )
        for b in blocks:
            if b.get("skipped") or b.get("error"):
                continue
            if b.get("label") in _DROP_LABELS:
                continue
            text = html_to_text(b.get("html") or "")
            if not text:
                continue

            if swallow_next_heading_for and b.get("label") == "SectionHeader":
                if not _HEADING_START_RE.match(text):
                    body_lines.append("")
                    body_lines.append(text)
                    body_lines.append("")
                items = items_by_chapter.get(swallow_next_heading_for, [])
                pending_items = {n: title for n, title, _pg in items}
                swallow_next_heading_for = None
                continue
            swallow_next_heading_for = None

            if b.get("label") == "SectionHeader" and re.match(r"^\s*PREFACE\.?\s*$", text, re.IGNORECASE):
                body_lines.append("")
                body_lines.append("## Preface")
                body_lines.append("")
                continue

            if b.get("label") == "SectionHeader" and pdf_page < BODY_START_PDF_PAGE:
                m = re.match(r"^\s*[:\.]?\s*([IVXL]+)\s*\.?\s*$", text)
                if m:
                    body_lines.append("")
                    body_lines.append(f"#### {m.group(1)}")
                    body_lines.append("")
                    continue

            if b.get("label") == "SectionHeader":
                key = normalize_heading_key(text)
                if key and not inserted[key]:
                    for n in sorted(pending_items):
                        body_lines.append("")
                        body_lines.append(f"#### {n}. {pending_items[n]}")
                        body_lines.append("")
                    pending_items = {}
                    level, canonical = TOC[key]
                    prefix = "#" * level
                    body_lines.append("")
                    body_lines.append(f"{prefix} {canonical}")
                    body_lines.append("")
                    inserted[key] = True
                    swallow_next_heading_for = key
                    continue

            m = _NUM_PARA_RE.match(text)
            if m:
                n = int(m.group(1))
                if n in pending_items:
                    title = pending_items.pop(n)
                    body_lines.append("")
                    body_lines.append(f"#### {n}. {title}")
                    body_lines.append("")
                    text = text[m.end():].lstrip()
            body_lines.append(text)
            body_lines.append("")

    for n in sorted(pending_items):
        body_lines.append("")
        body_lines.append(f"#### {n}. {pending_items[n]}")
        body_lines.append("")

    body = "\n".join(body_lines).strip() + "\n"

    frontmatter = """---
work_id: mysticism-in-maharashtra
author: gurudev_ranade
work_type: book
language: en
title_en: "Mysticism in Maharashtra"
sources:
  - Surya OCR of IA scan dli.ministry.14639 (Ranade, 1933)
extracted_via: "Surya OCR 2 (surya-2 model) + tools/multivolume/assemble_mim.py"
extracted_on: 2026-08-03
---
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(frontmatter + "\n" + body)

    n_parts = sum(1 for k, ok in inserted.items() if ok and k.startswith("PART"))
    n_chapters = sum(1 for k, ok in inserted.items() if ok and k.startswith("CHAPTER"))
    n_items = sum(len(v) for v in items_by_chapter.values())
    missed = [k for k, ok in inserted.items() if not ok]
    print(f"MiM candidate written: {OUT}")
    print(f"  size: {OUT.stat().st_size / 1024:.1f} KB")
    print(f"  ## Part markers inserted: {n_parts} / 5")
    print(f"  ##/### Chapter markers inserted: {n_chapters} / 20")
    print(f"  #### sub-item markers: {n_items} (from TOC parse)")
    if missed:
        print(f"  MISSED chapters (need manual check): {missed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
