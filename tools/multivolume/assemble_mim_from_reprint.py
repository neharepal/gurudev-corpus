#!/usr/bin/env python3
"""MiM canonical assembler — from the digital reprint PDF (Apr 2025).

Consumes the reprint PDF's text layer directly via pdfplumber (no OCR) and
produces the same schema as `assemble_mim.py`:
  ##  Part markers  +  standalone `## Chapter I. …`
  ### Chapter markers within parts
  #### N. Title  — numbered sub-item shoulder-note titles
  #### (i) Title — preface roman sub-items (only under item 14)
  #### I / II / III  — preface roman-numeral section markers

Font structure (probed 2026-08-03):
  * Body font = GLNHBO+TimesNewRomanPSMT, size 12
  * Heading font = RRSHSQ+TimesNewRomanPS-BoldMT, various sizes
      - size 24 → PART marker (e.g. "PART I")
      - size 15 → PART subtitle / book title running-head
      - size 14 → chapter title text
      - size 13 → "CHAPTER II" line (except Chapter I which is size 12)
      - size 12 bold → numbered sub-item titles, preface roman markers,
                       preface (i)-(v) sub-items
  * Diacritic sub-characters appear at size 11 mixed inside size-12 words.

Strategy — font+regex hybrid:
  1. Line-group words by top-coord (tol=3).
  2. Drop running-head lines (regex list).
  3. Block-group lines by vertical gap (>22 units = new paragraph).
  4. Classify blocks: PART / CHAPTER / numbered heading / roman marker /
     (i) sub-item / body — emit structural markers from TOC, body verbatim.

Body prose is emitted verbatim; typos are preserved and logged to the
anomalies file.

Output: `_surya_ocr_job/staging/mim-canonical-reprint.candidate.md`.
Anomalies: `_surya_ocr_job/staging/mim-reprint-anomalies.txt`.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

PDF_PATH = Path(
    "/Users/neharepal/gurudev-corpus/00_raw/fwdindianmysticism/Indian Mysticism in Maharashtra.pdf"
)
OUT = Path("_surya_ocr_job/staging/mim-canonical-reprint.candidate.md")
ANOMALIES = Path("_surya_ocr_job/staging/mim-reprint-anomalies.txt")

# ---------------------------------------------------------------------------
# TOC — from `assemble_mim.py` (hand-verified against IA scan
# dli.ministry.14639). Keys use spaces so we can match parsed heading text.
# ---------------------------------------------------------------------------
TOC: dict[str, tuple[int, str]] = {
    "PART I":       (2, "Part I"),
    "PART II":      (2, "Part II"),
    "PART III":     (2, "Part III"),
    "PART IV":      (2, "Part IV"),
    "PART V":       (2, "Part V"),
    "CHAPTER I":    (2, "Chapter I. Introduction: The Development of Indian Mysticism up to the Age of Jñāneśvara"),
    "CHAPTER II":   (3, "Chapter II. Jñānadeva: Biographical Introduction"),
    "CHAPTER III":  (3, "Chapter III. The Jñāneśvarī"),
    "CHAPTER IV":   (3, "Chapter IV. The Amṛtānubhava"),
    "CHAPTER V":    (3, "Chapter V. The Abhaṅgas of Nivṛtti, Jñānadeva, Sopāna, Muktābāi, and Chāṅgadeva"),
    "CHAPTER VI":   (3, "Chapter VI. General Review of the Period"),
    "CHAPTER VII":  (3, "Chapter VII. Biographical Introduction"),
    "CHAPTER VIII": (3, "Chapter VIII. The Abhaṅgas of Nāmadeva and Contemporary Saints"),
    "CHAPTER IX":   (3, "Chapter IX. General Review"),
    "CHAPTER X":    (3, "Chapter X. Biographical Introduction: Bhānudāsa, Janārdana Swāmī, and Ekanātha"),
    "CHAPTER XI":   (3, "Chapter XI. The Abhaṅgas of Bhānudāsa, Janārdana Swāmī, and Ekanātha"),
    "CHAPTER XII":  (3, "Chapter XII. Introduction: The Bhāgavata of Ekanātha"),
    "CHAPTER XIII": (3, "Chapter XIII. General Review"),
    "CHAPTER XIV":  (3, "Chapter XIV. Biographical Introduction: Tukārāma"),
    "CHAPTER XV":   (3, "Chapter XV. Tukārāma's Mystical Career"),
    "CHAPTER XVI":  (3, "Chapter XVI. Tukārāma's Mystical Teaching"),
    "CHAPTER XVII": (3, "Chapter XVII. General Review"),
    "CHAPTER XVIII":(3, "Chapter XVIII. Biographical Introduction"),
    "CHAPTER XIX":  (3, "Chapter XIX. The Dāsabodha"),
    "CHAPTER XX":   (3, "Chapter XX. General Review and Conclusion"),
}

# ---------------------------------------------------------------------------
# Ranges (0-indexed PDF pages)
# ---------------------------------------------------------------------------
PREFACE_PAGES = range(0, 38)   # 0..37 preface
TOC_PAGES     = range(38, 53)  # 38..52 printed contents (skip)
BODY_START    = 53              # 53..end body


# ---------------------------------------------------------------------------
# Line / block grouping
# ---------------------------------------------------------------------------
LINE_TOL   = 3.0    # words within 3 units share a line
BLOCK_GAP  = 22.0   # gap > 22 units → new block (paragraph)


@dataclass
class Line:
    top: float
    x_start: float
    text: str
    words: list  # list of pdfplumber word dicts
    max_size: float
    bold_frac: float  # fraction of words in the Bold font

    @classmethod
    def from_words(cls, ws: list) -> "Line":
        text = " ".join(w["text"] for w in ws)
        # `size` isn't in extra_attrs, so pdfplumber's word dicts lack it;
        # use a proxy: word height ≈ font size.
        heights = [round((w["bottom"] - w["top"]), 1) for w in ws]
        max_size = max(heights) if heights else 0.0
        n_bold = sum(1 for w in ws if "Bold" in w["fontname"])
        return cls(
            top=min(w["top"] for w in ws),
            x_start=min(w["x0"] for w in ws),
            text=text,
            words=ws,
            max_size=max_size,
            bold_frac=n_bold / len(ws),
        )


def group_words_into_lines(words: list) -> list[Line]:
    if not words:
        return []
    sorted_ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    out: list[list] = [[sorted_ws[0]]]
    for w in sorted_ws[1:]:
        if abs(w["top"] - out[-1][-1]["top"]) <= LINE_TOL:
            out[-1].append(w)
        else:
            out.append([w])
    # Sort words within each line by x0
    lines = []
    for ws in out:
        ws.sort(key=lambda w: w["x0"])
        lines.append(Line.from_words(ws))
    return lines


def group_lines_into_blocks(lines: list[Line]) -> list[list[Line]]:
    """Group lines into blocks by vertical gap. Also break a block whenever
    it transitions from a bold heading line to a regular body line — the
    typeset gap between a shoulder-note heading and its body paragraph is
    typically ~20 units (below our BLOCK_GAP=22), so without this split the
    heading would fuse with the body and lose its `####` marker."""
    if not lines:
        return []
    blocks: list[list[Line]] = [[lines[0]]]
    for ln in lines[1:]:
        prev = blocks[-1][-1]
        gap = ln.top - prev.top
        # Bold ↔ non-bold transition (heading↔body) always starts a new
        # block — the typeset gap can be as small as ~20 units, below
        # BLOCK_GAP=22, so bare gap detection is not enough.
        transition = (
            (prev.bold_frac >= 0.8 and ln.bold_frac < 0.5) or  # heading → body
            (prev.bold_frac < 0.5 and ln.bold_frac >= 0.8)     # body → heading
        )
        if gap > BLOCK_GAP or transition:
            blocks.append([ln])
        else:
            blocks[-1].append(ln)
    return blocks


# ---------------------------------------------------------------------------
# Running-head detection
# ---------------------------------------------------------------------------
_RUN_HEAD_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\d{1,4}$"),  # bare page number
    re.compile(r"^PREFACE(?:\s+[IVXL]+)?$", re.IGNORECASE),
    re.compile(r"^[IVXL]+\s+PREFACE$", re.IGNORECASE),
    re.compile(r"^CONTENTS(?:\s+[IVXL]+)?$", re.IGNORECASE),
    re.compile(r"^[IVXL]+\s+CONTENTS$", re.IGNORECASE),
    # Chapter I first page book-title running head:
    re.compile(r"^Indian\s+Mysticism\s*:?\s*Mysticism\s+in\s+Mah[ãā]r[ãā]shtra\.?$"),
    re.compile(r"^\(CHAP\.\s+[IVXL]+\)$"),
]

# Chapter-body running heads look like: `THE JNANESVARI 180`,
# `180 THE JNANESVARI`, `MYSTICISM IN MAHARASHTRA 558 (CHAP. XX)`.
# Distinguishing features: contain a page number OR end with `(CHAP. X)`.
# We DO NOT treat plain `CHAPTER II` or `PART II` as running heads — those
# are structural section markers we need to emit.
_RUN_HEAD_KEYWORDS = (
    "MYSTICISM IN MAHARASHTRA",
    "THE JNANESVARI",
    "THE AMRITANUBHAVA",
    "THE BHAGAVATA",  # possible for later chapters
    "THE DASABODHA",  # possible for Ch XIX
)


def is_running_head(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    for pat in _RUN_HEAD_PATTERNS:
        if pat.fullmatch(t):
            return True
    # Chapter body running head — must include an all-caps book/chapter
    # slug AND either a bare page number or a `(CHAP. X)` tail.
    up = t.upper()
    for kw in _RUN_HEAD_KEYWORDS:
        if kw in up:
            has_pgnum = bool(re.search(r"\b\d{1,4}\b", t))
            has_chaptail = bool(re.search(r"\(CHAP\.\s+[IVXL]+\)", t))
            if has_pgnum or has_chaptail:
                return True
            # Bare `MYSTICISM IN MAHARASHTRA` alone is also a running head
            if up == kw:
                return True
    return False


# ---------------------------------------------------------------------------
# Heading classification
# ---------------------------------------------------------------------------
_CHAPTER_HEAD_RE = re.compile(r"^CHAPTER\s+([IVXL]+)\.?$")
_PART_HEAD_RE    = re.compile(r"^PART\s+([IVXL]+)\.?$")
_NUMBERED_RE     = re.compile(r"^(\d+)\s*\.\s*(.*)$", re.DOTALL)
_ROMAN_ONLY_RE   = re.compile(r"^[IVXL]+$")
_SUBROMAN_RE     = re.compile(r"^\(([ivxlcdm]+)\)\s*(.*)$", re.DOTALL)

# Known typos in the reprint's heading text — corrected per Neha 2026-08-03.
# Applied word-by-word during heading emit; body prose is NEVER mutated.
HEADING_TYPO_FIX: dict[str, str] = {
    "Vison": "Vision",
    "Sanctury": "Sanctuary",
    "Comparision": "Comparison",
}

# Preface roman-section boundaries (Neha-verified). Reprint prints I, II, III
# as bold roman-only lines; IV is replaced by a `* * * *` divider before
# section 15 — we synthesize the missing `IV` marker here so the reader has
# all four sections in the drawer. Map: first-numbered-heading N → roman.
PREFACE_ROMAN_BOUNDARIES: dict[int, str] = {
    1: "I",
    2: "II",
    11: "III",
    15: "IV",
}


def fix_heading_typos(text: str) -> str:
    """Replace known reprint heading typos, whole-word only."""
    def sub(m: re.Match) -> str:
        w = m.group(0)
        return HEADING_TYPO_FIX.get(w, w)
    return re.sub(r"\b\w+\b", sub, text)


def block_text(block: list[Line]) -> str:
    return " ".join(ln.text for ln in block)


def block_dominant_size(block: list[Line]) -> float:
    """Approximate — we no longer track `size` per word. Use the max line
    height across the block (word height ≈ font size)."""
    return max((ln.max_size for ln in block), default=0.0)


def block_bold_frac(block: list[Line]) -> float:
    total = sum(len(ln.words) for ln in block)
    if total == 0:
        return 0.0
    bolds = sum(1 for ln in block for w in ln.words if "Bold" in w["fontname"])
    return bolds / total


def block_is_bold_heading(block: list[Line]) -> bool:
    """A block is a heading candidate if >=80% of its words are bold."""
    return block_bold_frac(block) >= 0.8


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------
def main() -> int:
    if not PDF_PATH.exists():
        print(f"ERR: PDF not found at {PDF_PATH}", file=sys.stderr)
        return 1

    body_lines: list[str] = []
    anomalies: list[str] = []
    inserted: dict[str, bool] = {k: False for k in TOC}
    saw_preface_heading = False
    preface_started = False
    # Track which preface roman markers we've already emitted so we know
    # when to synthesize a missing one (only IV is missing in the reprint,
    # but the mechanism is general).
    emitted_preface_romans: set[str] = set()

    def emit(s: str = ""):
        body_lines.append(s)

    def emit_heading(prefix_hashes: str, text: str):
        emit("")
        emit(f"{prefix_hashes} {text}")
        emit("")

    def flag(msg: str):
        anomalies.append(msg)

    with pdfplumber.open(PDF_PATH) as pdf:
        total_pages = len(pdf.pages)
        for pn in range(total_pages):
            # Skip the printed Contents pages
            if pn in TOC_PAGES:
                continue

            page = pdf.pages[pn]
            try:
                # NOTE: we intentionally omit `size` from extra_attrs. When
                # `size` is included, pdfplumber refuses to merge adjacent
                # glyphs that share a base word but differ in point-size
                # (e.g. body `Mahārāshtra` where the `ā` subscripts render
                # at size 11 while the surrounding letters are size 12).
                # Dropping size restores clean word merging so we get
                # `Mahārāshtra` rather than `Mah ā r ā shtra` in body prose.
                words = page.extract_words(extra_attrs=["fontname"])
            except Exception as e:  # pragma: no cover
                flag(f"p{pn}: pdfplumber word-extract failed: {e}")
                continue

            if not words:
                if pn >= BODY_START:
                    flag(f"p{pn}: no words extracted (blank page?)")
                continue

            # Drop rendering artifacts positioned outside the page's normal
            # text area (stray diacritics rendered at x > page width, etc).
            pw = page.width
            words = [w for w in words if -5 <= w["x0"] <= pw + 5]

            lines = group_words_into_lines(words)
            # Drop running-head lines
            kept: list[Line] = []
            for ln in lines:
                if is_running_head(ln.text):
                    continue
                # Additional heuristic — very tiny font (<=10) at extreme
                # positions is likely a running head we missed. Drop.
                if ln.max_size <= 10.5 and (ln.top < 30 or ln.top > page.height - 20):
                    continue
                kept.append(ln)

            if not kept:
                if pn >= BODY_START:
                    flag(f"p{pn}: only headers (no body text after filter)")
                continue

            blocks = group_lines_into_blocks(kept)

            # Emit `## Preface` once at the top of preface
            if pn in PREFACE_PAGES and not preface_started:
                emit_heading("##", "Preface")
                preface_started = True

            skip_next = False
            for i, block in enumerate(blocks):
                if skip_next:
                    skip_next = False
                    continue

                text = block_text(block).strip()
                if not text:
                    continue

                is_heading = block_is_bold_heading(block)
                dom_size = block_dominant_size(block)

                # ---- PART marker (bold size ~24, text starts with "PART") ----
                if is_heading and dom_size >= 20:
                    m = _PART_HEAD_RE.match(text.split(" ", 2)[0] + " " + text.split(" ", 2)[1] if len(text.split(" ")) >= 2 else text)
                    # Better: strict PART regex on the first two tokens joined
                    tokens = text.split()
                    if len(tokens) >= 2 and tokens[0].upper() == "PART":
                        roman = tokens[1].rstrip(".")
                        key = f"PART {roman.upper()}"
                        if key in TOC and not inserted[key]:
                            level, canonical = TOC[key]
                            emit_heading("#" * level, canonical)
                            inserted[key] = True
                            # If next block is the Part subtitle (bold size 15),
                            # skip it — we render from TOC.
                            if i + 1 < len(blocks):
                                nxt = blocks[i + 1]
                                if block_is_bold_heading(nxt) and block_dominant_size(nxt) >= 14:
                                    skip_next = True
                            continue
                        elif key in TOC:
                            flag(f"p{pn}: duplicate PART marker {key}")
                            continue

                # ---- CHAPTER header (bold size 12-14, first tokens "CHAPTER X") ----
                if is_heading:
                    tokens = text.split()
                    if len(tokens) >= 2 and tokens[0].upper() == "CHAPTER":
                        roman = tokens[1].rstrip(".")
                        key = f"CHAPTER {roman.upper()}"
                        # Anomaly: printed "CHAPTER IX" on p329 where TOC has X
                        if pn == 329 and key == "CHAPTER IX":
                            flag(f"p329: printed 'CHAPTER IX' but per Part-III opening this is Chapter X (per your note)")
                            key = "CHAPTER X"
                        if key in TOC and not inserted[key]:
                            level, canonical = TOC[key]
                            emit_heading("#" * level, canonical)
                            inserted[key] = True
                            # If this block contains only the "CHAPTER X" line
                            # (no title text after), the title block usually
                            # follows — skip that (rendered from TOC).
                            trailing = " ".join(tokens[2:]).strip()
                            if not trailing and i + 1 < len(blocks):
                                nxt = blocks[i + 1]
                                if block_is_bold_heading(nxt) and block_dominant_size(nxt) >= 13:
                                    skip_next = True
                            continue
                        elif key in TOC:
                            # Already inserted — probably re-detected on a
                            # continuation page. Silently skip.
                            continue

                # ---- Preface roman-numeral section marker (I/II/III alone) ----
                if is_heading and _ROMAN_ONLY_RE.fullmatch(text) and pn in PREFACE_PAGES:
                    marker = text.strip()
                    emit_heading("####", marker)
                    emitted_preface_romans.add(marker)
                    continue

                # ---- Preface (i) / (ii) sub-item ----
                if is_heading and pn in PREFACE_PAGES:
                    m = _SUBROMAN_RE.match(text)
                    if m:
                        rn, rest = m.group(1), m.group(2).strip()
                        rest = rest.rstrip(".").strip()
                        emit_heading("####", f"({rn}) {rest}")
                        continue

                # ---- Numbered heading (`1. Title` — bold, size 12/13) ----
                if is_heading:
                    m = _NUMBERED_RE.match(text)
                    if m and int(m.group(1)) <= 200:
                        n = int(m.group(1))
                        title = m.group(2).strip().rstrip(".").strip()
                        # Fix known reprint heading typos (whole-word only).
                        title = fix_heading_typos(title)
                        # Skip if the "title" is empty (defensive).
                        if title:
                            # In the preface: if this numbered section is
                            # the first one under a roman group AND that
                            # roman marker never appeared (reprint dropped
                            # the `IV` header, replaced with `* * * *`),
                            # synthesize the missing roman before emitting.
                            if pn in PREFACE_PAGES and n in PREFACE_ROMAN_BOUNDARIES:
                                expected = PREFACE_ROMAN_BOUNDARIES[n]
                                if expected not in emitted_preface_romans:
                                    emit_heading("####", expected)
                                    emitted_preface_romans.add(expected)
                            emit_heading("####", f"{n}. {title}")
                            continue

                # ---- Body paragraph ----
                emit("")
                emit(text)
                emit("")

    # Post-loop: flag any TOC entries we never emitted
    missed = [k for k, ok in inserted.items() if not ok]
    for k in missed:
        anomalies.append(f"MISSED TOC entry (never emitted): {k}")

    # Known reprint anomalies
    anomalies.insert(0, "== MiM reprint (Adobe Acrobat 10.0.0, Apr 2025) known anomalies ==")
    anomalies.insert(1, "* Preface has only 3 roman sections (I, II, III) — no IV — despite user spec.")
    anomalies.insert(2, "* p5 typo: '3. The Vison of the Self' (should be 'Vision').")
    anomalies.insert(3, "* p12 typo: '8. The Sanctury and the Statues.' (should be 'Sanctuary').")
    anomalies.insert(4, "* p2 typo: '2. ... a Comparision' (should be 'Comparison').")
    anomalies.insert(5, "* p25 heading missing space: '14.The Criterion...' (unified as-printed).")
    anomalies.insert(6, "* p31 heading missing space: '(v)The Intuitional Aspect.' (as-printed).")
    anomalies.insert(7, "* p32 heading missing space: '15.Relation to the University of Bombay.' (as-printed).")
    anomalies.insert(8, "* p329 prints 'CHAPTER IX' at the head of Part III — corrected to Chapter X per Neha's note.")
    anomalies.insert(9, "* Chapter IV title printed as 'The Amritānubhava' (i-form); TOC canonical uses 'Amṛtānubhava'.")
    anomalies.insert(10, "* Chapter V title printed as 'Abhangas of Nivritti, Jñānadeva, Sopāna, Muktābai, and Changādeva' (ASCII a in place of ā/ṛ); TOC canonical uses full diacritics.")
    anomalies.insert(11, "")

    # Frontmatter
    frontmatter = """---
work_id: mysticism-in-maharashtra
author: gurudev_ranade
work_type: book
language: en
title_en: "Mysticism in Maharashtra"
sources:
  - Digital reprint (Adobe Acrobat 10.0.0, 2025) — text layer extracted via pdfplumber
extracted_via: "tools/multivolume/assemble_mim_from_reprint.py"
extracted_on: 2026-08-03
---
"""

    body = "\n".join(body_lines).strip() + "\n"
    # Collapse triple-or-more blank lines into a single blank
    body = re.sub(r"\n{3,}", "\n\n", body)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(frontmatter + "\n" + body)

    ANOMALIES.parent.mkdir(parents=True, exist_ok=True)
    with open(ANOMALIES, "w", encoding="utf-8") as f:
        f.write("\n".join(anomalies) + "\n")

    # Report
    n_parts    = sum(1 for k, ok in inserted.items() if ok and k.startswith("PART"))
    n_chapters = sum(1 for k, ok in inserted.items() if ok and k.startswith("CHAPTER"))
    print(f"MiM (reprint) candidate written: {OUT}")
    print(f"  size:                {OUT.stat().st_size / 1024:.1f} KB")
    print(f"  ## Part markers:     {n_parts} / 5")
    print(f"  chapter markers:     {n_chapters} / 20")
    print(f"  anomalies flagged:   {len(anomalies)}  → {ANOMALIES}")
    if missed:
        print(f"  MISSED:              {missed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
