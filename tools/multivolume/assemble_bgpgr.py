#!/usr/bin/env python3
"""BGPGR canonical assembler.

Consumes Surya OCR output and produces a structured canonical text.md for
"The Bhagavadgita as a Philosophy of God-Realisation" (Ranade, published
posthumously by Nagpur University; 4th ed. reprint 2001 by Bharatiya
Vidya Bhavan, IA scan `acpr.the-bhagavadgita-as-a-philosophy-of-god-realisation`).

Strategy — STRUCTURAL MARKERS ONLY. Body prose from Surya is emitted
verbatim; we never mutate Ranade's text. Structural signals we add:

  1. `##` Part markers for PART I..V (canonical titles from TOC dict).
  2. `###` Chapter markers for CHAPTER I..XXI (canonical titles from TOC dict).
  3. `####` sub-section markers passed through from Surya `SectionHeader`
     blocks that appear inside chapter bodies (e.g. `Iśopaniṣad`,
     `Sāmkhya and Yoga`, `Introduction`).
  4. `##` front-matter section markers (Kulapati's Preface, Publishers'
     Note, etc.) via a curated whitelist.

Known Surya quirks handled:
  * PART III on p79 was tagged `PageHeader` (dropped), only its subtitle
    "THE LABYRINTH OF MODERN INTERPRETATIONS" survived as `SectionHeader`.
    We insert PART III when we first see that subtitle.
  * PART V on p259 came out as `PART VCONCLUSION` (space lost). We
    normalize.
  * Chapter XXI (p261) has three consecutive SectionHeaders including a
    compound "* The Sublime and the Divine … Introduction" — we emit the
    canonical chapter title from TOC and swallow the redundant repeats.

Output:
  * `_surya_ocr_job/staging/bgpgr-canonical.candidate.md`
  * `_surya_ocr_job/staging/bgpgr-anomalies.txt`
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "_surya_ocr_job/out_raw/bhagavadgita-as-pathway-to-god-realization/bhagavadgita-as-pathway-to-god-realization/results.json"
OUT = REPO / "_surya_ocr_job/staging/bgpgr-canonical.candidate.md"
ANOMALIES = REPO / "_surya_ocr_job/staging/bgpgr-anomalies.txt"

# ---------------------------------------------------------------------------
# TOC — hand-verified from the Contents pages of the IA scan.
#
# Chapter titles from the Contents; body-page chapter subtitles sometimes
# differ (e.g. body says "A MYSTICAL INTERPRETATION OF THE BHAGAVADGITĀ
# (JÑĀNEŚVARA)" whereas Contents says "A Mystical Interpretation of the
# Bhagavadgītā : Jñāneśvara"). We use the Contents form because it's
# already normalized (title-case, correct diacritics on Bhagavadgītā).
# ---------------------------------------------------------------------------
TOC: dict[str, tuple[int, str]] = {
    "PART I":       (2, "Part I. The Relation of the Bhagavadgītā to the Ancient Philosophical Systems"),
    "PART II":      (2, "Part II. Vedāntic and Mystical Interpretations of the Bhagavadgītā"),
    "PART III":     (2, "Part III. The Labyrinth of Modern Interpretations"),
    "PART IV":      (2, "Part IV. The Clue through the Labyrinth"),
    "PART V":       (2, "Part V. Conclusion"),
    "CHAPTER I":    (3, "Chapter I. The Relation of the Bhagavadgītā to the Upaniṣads"),
    "CHAPTER II":   (3, "Chapter II. The Relation of the Bhagavadgītā to Sāṁkhya and Yoga"),
    "CHAPTER III":  (3, "Chapter III. The Relation of the Bhagavadgītā to the Brahmasūtras"),
    "CHAPTER IV":   (3, "Chapter IV. Vedāntic Interpretations of the Bhagavadgītā: Śaṁkara, Rāmānuja, Madhva and Vallabha"),
    "CHAPTER V":    (3, "Chapter V. A Mystical Interpretation of the Bhagavadgītā: Jñāneśvara"),
    "CHAPTER VI":   (3, "Chapter VI. Interpolationism"),
    "CHAPTER VII":  (3, "Chapter VII. Devotionalism: Bhandarkar"),
    "CHAPTER VIII": (3, "Chapter VIII. Christianism"),
    "CHAPTER IX":   (3, "Chapter IX. Buddhism: Buddhirāja"),
    "CHAPTER X":    (3, "Chapter X. Activism: Tilak"),
    "CHAPTER XI":   (3, "Chapter XI. Detachment: Gandhi"),
    "CHAPTER XII":  (3, "Chapter XII. Other Modern Prominent Interpreters"),
    "CHAPTER XIII": (3, "Chapter XIII. Numenism: Otto"),
    "CHAPTER XIV":  (3, "Chapter XIV. Divinisation: Aurobindo"),
    "CHAPTER XV":   (3, "Chapter XV. Antinomies of Metaphysics"),
    "CHAPTER XVI":  (3, "Chapter XVI. The Categorical Imperative, Activism and its Limitations"),
    "CHAPTER XVII": (3, "Chapter XVII. Moralism, Super-Moralism and Beatificism"),
    "CHAPTER XVIII":(3, "Chapter XVIII. The Problem of God"),
    "CHAPTER XIX":  (3, "Chapter XIX. Methods of Meditation"),
    "CHAPTER XX":   (3, "Chapter XX. A Sublime Vision of God"),
    "CHAPTER XXI":  (3, "Chapter XXI. The Sublime and the Divine: A Study in Comparative Thought"),
}

# Front-matter SectionHeader whitelist — cleaned canonical titles.
# Keys are the raw Surya text (post-clean), values are (level, title).
FRONT_MATTER_TITLES: dict[str, tuple[int, str]] = {
    "KULAPATI'S PREFACE":                              (2, "Kulapati's Preface"),
    "PUBLISHERS' NOTE":                                (2, "Publishers' Note"),
    "Publishers' Note ( Fourth Edition )":             (2, "Publishers' Note (Fourth Edition)"),
    "The Bhagavadgītā as a Philosophy of God-realisation": (3, "The Bhagavadgītā as a Philosophy of God-realisation (Ranade's Originally Planned Outline)"),
    "Abbreviations":                                   (2, "Abbreviations"),
    "GENERAL INTRODUCTION":                            (2, "General Introduction"),
}

# Pages to skip entirely.
#   1-4:  bare title / blank / title / colophon
#   11-12: Contents
#   13-14: repeat half-title + blank
#   258-260: blanks around Part V transition (kept; blanks skip naturally)
# 278-328: General Index, Gita-quotation index, Documentation, Notes,
#          Errata, publisher back matter — all reference material.
SKIP_PAGES: set[int] = set(range(1, 5)) | {11, 12, 13, 14}
BACK_MATTER_START_PAGE = 278  # inclusive — skip from here to end

# Sentinel: subtitle of Part III (Surya lost the "PART III" tag itself).
PART_III_SUBTITLE = "THE LABYRINTH OF MODERN INTERPRETATIONS"

_DROP_LABELS = {"PageHeader", "PageFooter", "Footnote"}
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_START_RE = re.compile(r"^\s*(PART|CHAPTER)\s+([IVXL]+)(\.|\s|$)", re.IGNORECASE)
# Match the Surya-mangled "PART VCONCLUSION" glitch too (missing space).
_PART_V_GLITCH_RE = re.compile(r"^\s*PART\s+V\s*CONCLUSION\s*$", re.IGNORECASE)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    s = _BR_RE.sub("\n", html)
    s = _TAG_RE.sub("", s)
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return "\n".join(line.rstrip() for line in s.splitlines()).strip()


def normalize_heading_key(text: str) -> str | None:
    """Return a `TOC` key if `text` matches PART X or CHAPTER X."""
    if _PART_V_GLITCH_RE.match(text):
        return "PART V"
    m = _HEADING_START_RE.match(text)
    if not m:
        return None
    kind, roman = m.group(1).upper(), m.group(2).upper()
    key = f"{kind} {roman}"
    return key if key in TOC else None


def is_book_title_boilerplate(text: str) -> bool:
    """Heuristic: repeated half-title / running-head style titles we drop."""
    upper = text.upper()
    if not upper:
        return False
    boilerplate_markers = (
        "BHAGAVADGITA : PHILOSOPHY OF GOD",
        "BHAGAVADGĪTĀ : PHILOSOPHY OF GOD",
        "BHAGAVADGITA AS A PHILOSOPHY OF GOD",
        "BHAGAVADGĪTĀ AS A PHILOSOPHY OF GOD",
    )
    return any(m in upper for m in boilerplate_markers)


def main() -> int:
    if not RESULTS.exists():
        print(f"ERR: {RESULTS} not found — BGPGR OCR hasn't finished.", file=sys.stderr)
        return 1
    with open(RESULTS, encoding="utf-8") as f:
        raw_json = json.load(f)
    pages = raw_json["bhagavadgita-as-pathway-to-god-realization"]
    pages_sorted = sorted(pages, key=lambda p: p.get("page", 0))

    body_lines: list[str] = []
    anomalies: list[str] = []

    inserted: dict[str, bool] = {k: False for k in TOC}
    inserted_front: dict[str, bool] = {k: False for k in FRONT_MATTER_TITLES}

    swallow_next_heading_for: str | None = None
    pages_emitted = 0
    pages_seen = 0

    for page in pages_sorted:
        pdf_page = page.get("page", 0)
        pages_seen += 1
        if pdf_page in SKIP_PAGES:
            continue
        if pdf_page >= BACK_MATTER_START_PAGE:
            continue

        blocks = sorted(
            (b for b in page.get("blocks", []) if isinstance(b, dict)),
            key=lambda b: b.get("reading_order", 10**9),
        )
        page_had_content = False
        for b in blocks:
            if b.get("skipped") or b.get("error"):
                continue
            if b.get("label") in _DROP_LABELS:
                continue
            text = html_to_text(b.get("html") or "")
            if not text:
                continue

            label = b.get("label", "")

            # SectionHeader text often contains `\n` from mid-line `<br/>`s
            # (Surya wraps long titles). Normalize whitespace to single
            # spaces for headers only; body Text blocks preserve line breaks.
            if label == "SectionHeader":
                text = re.sub(r"\s+", " ", text).strip()
                if not text:
                    continue

            # ----------------------------------------------------------------
            # Swallow the next SectionHeader immediately after a PART/CHAPTER
            # marker — that's the redundant chapter/part subtitle already
            # baked into the canonical TOC title.
            # ----------------------------------------------------------------
            if swallow_next_heading_for and label == "SectionHeader":
                # Only swallow if it isn't itself a chapter/part marker.
                if not normalize_heading_key(text):
                    swallow_next_heading_for = None
                    continue
                swallow_next_heading_for = None
                # Fall through — the current block IS a new chapter/part.

            # ----------------------------------------------------------------
            # PART III synthetic insertion. Surya lost the "PART III" tag on
            # p79; only the subtitle "THE LABYRINTH OF MODERN INTERPRETATIONS"
            # survived. Insert PART III on first sight of that subtitle.
            # ----------------------------------------------------------------
            if label == "SectionHeader" and text.strip().upper() == PART_III_SUBTITLE:
                if not inserted["PART III"]:
                    _, canonical = TOC["PART III"]
                    body_lines.append("")
                    body_lines.append(f"## {canonical}")
                    body_lines.append("")
                    inserted["PART III"] = True
                    page_had_content = True
                    continue
                # Already inserted — this block is a duplicate; swallow.
                continue

            # ----------------------------------------------------------------
            # PART / CHAPTER heading (SectionHeader with recognizable roman).
            # ----------------------------------------------------------------
            if label == "SectionHeader":
                key = normalize_heading_key(text)
                if key:
                    if inserted[key]:
                        # Already emitted (duplicate print of PART V etc).
                        # Still swallow the following subtitle so we don't
                        # leak it into body.
                        swallow_next_heading_for = key
                        continue
                    level, canonical = TOC[key]
                    prefix = "#" * level
                    body_lines.append("")
                    body_lines.append(f"{prefix} {canonical}")
                    body_lines.append("")
                    inserted[key] = True
                    swallow_next_heading_for = key
                    page_had_content = True
                    continue

            # ----------------------------------------------------------------
            # Front-matter whitelist SectionHeaders.
            # ----------------------------------------------------------------
            if label == "SectionHeader" and text in FRONT_MATTER_TITLES:
                if not inserted_front[text]:
                    level, canonical = FRONT_MATTER_TITLES[text]
                    prefix = "#" * level
                    body_lines.append("")
                    body_lines.append(f"{prefix} {canonical}")
                    body_lines.append("")
                    inserted_front[text] = True
                    page_had_content = True
                    continue
                continue

            # ----------------------------------------------------------------
            # Repeated half-title / decorative running-heads → drop.
            # (Necessary because pp13, front-cover repeats, etc. still leak
            # in as SectionHeaders even though we skip pp13-14.)
            # ----------------------------------------------------------------
            if label == "SectionHeader" and is_book_title_boilerplate(text):
                continue

            # ----------------------------------------------------------------
            # Any other SectionHeader → sub-section marker (####).
            # This handles Iśopaniṣad, Sāmkhya and Yoga, Introduction,
            # Garbe, etc. inside chapter bodies.
            # ----------------------------------------------------------------
            if label == "SectionHeader":
                # Special: Ch XXI's compound "* [chapter title] Introduction"
                # SectionHeader on p261 — reduce to a plain "Introduction"
                # sub-section, matching Ch XIV / Ch XVI's convention.
                if text.lstrip().startswith("*") and text.rstrip().endswith("Introduction"):
                    body_lines.append("")
                    body_lines.append("#### Introduction")
                    body_lines.append("")
                    page_had_content = True
                    continue
                # Strip leading "* " footnote-marker or bullet
                clean_txt = re.sub(r"^[\*\•·]\s*", "", text).strip()
                if not clean_txt:
                    continue
                body_lines.append("")
                body_lines.append(f"#### {clean_txt}")
                body_lines.append("")
                page_had_content = True
                continue

            # ----------------------------------------------------------------
            # Any other block (Text, ListGroup, Table, TableOfContents…):
            # emit verbatim as a paragraph.
            # ----------------------------------------------------------------
            body_lines.append(text)
            body_lines.append("")
            page_had_content = True

        if page_had_content:
            pages_emitted += 1
        else:
            # Only flag if it's a body page (past preface) that had nothing
            # after skipping headers/footers/images.
            if 5 <= pdf_page < BACK_MATTER_START_PAGE and pdf_page not in SKIP_PAGES:
                if not any(
                    (blk.get("label") not in _DROP_LABELS and blk.get("label") != "Picture")
                    for blk in blocks
                    if isinstance(blk, dict)
                ):
                    anomalies.append(f"p{pdf_page}: no emittable content (blank / picture-only page)")

    # Check for missing headings.
    missing = [k for k, ok in inserted.items() if not ok]
    if missing:
        for k in missing:
            anomalies.insert(0, f"MISSING structural marker: {k}  ({TOC[k][1]})")

    missing_front = [k for k, ok in inserted_front.items() if not ok]
    if missing_front:
        for k in missing_front:
            anomalies.append(f"MISSING front-matter header: {k}  ({FRONT_MATTER_TITLES[k][1]})")

    # PART III synthetic-insertion note (informational).
    anomalies.append(
        "NOTE: PART III synthesized from subtitle 'THE LABYRINTH OF MODERN INTERPRETATIONS' on p79 "
        "— Surya labelled the literal 'PART III' text as PageHeader (dropped)."
    )
    # PART V synthetic normalization note.
    anomalies.append(
        "NOTE: PART V header on p259 came from Surya as 'PART VCONCLUSION' (missing space); "
        "normalized to PART V via regex."
    )

    body = "\n".join(body_lines).strip() + "\n"

    frontmatter = """---
work_id: bhagavadgita-as-pathway-to-god-realization
author: gurudev_ranade
work_type: book
language: en
title_en: "The Bhagavadgita as a Philosophy of God-Realisation"
sources:
  - Surya OCR of IA scan acpr.the-bhagavadgita-as-a-philosophy-of-god-realisation (Ranade, published posthumously by Nagpur University)
extracted_via: "Surya OCR 2 (surya-2 model) + tools/multivolume/assemble_bgpgr.py"
extracted_on: 2026-08-04
---
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(frontmatter + "\n" + body)

    ANOMALIES.parent.mkdir(parents=True, exist_ok=True)
    with open(ANOMALIES, "w", encoding="utf-8") as f:
        f.write("BGPGR assembler anomalies — generated by tools/multivolume/assemble_bgpgr.py\n")
        f.write(f"Source: {RESULTS}\n")
        f.write(f"Pages seen: {pages_seen}\n")
        f.write(f"Pages skipped (Contents/half-title/back-matter): "
                f"{sorted(SKIP_PAGES) + list(range(BACK_MATTER_START_PAGE, 329))}\n")
        f.write(f"Pages emitted (with content): {pages_emitted}\n")
        f.write("\n")
        for line in anomalies:
            f.write(line + "\n")

    n_parts = sum(1 for k, ok in inserted.items() if ok and k.startswith("PART"))
    n_chapters = sum(1 for k, ok in inserted.items() if ok and k.startswith("CHAPTER"))
    n_front = sum(1 for ok in inserted_front.values() if ok)

    # Count heading markers in final output for the report.
    n_h2 = sum(1 for ln in body_lines if ln.startswith("## ") and not ln.startswith("### "))
    n_h3 = sum(1 for ln in body_lines if ln.startswith("### ") and not ln.startswith("#### "))
    n_h4 = sum(1 for ln in body_lines if ln.startswith("#### "))

    print(f"BGPGR candidate written: {OUT}")
    print(f"  size: {OUT.stat().st_size / 1024:.1f} KB")
    print(f"  ## Part markers inserted: {n_parts} / 5")
    print(f"  ### Chapter markers inserted: {n_chapters} / 21")
    print(f"  ## front-matter headers inserted: {n_front} / {len(FRONT_MATTER_TITLES)}")
    print(f"  headings in output: ## × {n_h2}   ### × {n_h3}   #### × {n_h4}")
    print(f"  pages emitted (with content): {pages_emitted}")
    print(f"  anomalies file: {ANOMALIES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
