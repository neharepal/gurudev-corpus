#!/usr/bin/env python3
"""ia_djvu_split.py — split IA DjVu XML pages with a floated shoulder-note
layout into clean body prose + separate margin notes.

Reads Internet Archive DjVu XML (from djvused / IA re-OCR pipeline) and,
for each page, separates a two-region floated-sidenote layout into:
  - body_words : the main text column, and
  - margin_words: the left shoulder-note column.

The split is done per line: for every OCR line we look for a horizontal
gap that literally crosses `page_width * split_ratio`. A full-width body
line has some word straddling that x, so it will not be split (avoiding
the trap where the first body words of a paragraph get mis-classified as
"margin" just because they happen to start on the far left).

Non-destructive: only reads XML; writes a JSON dump to the requested path.
Stdlib only (xml.etree.ElementTree, json, re, statistics).
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator

PAGE_ID_RE = re.compile(r"_(\d{4})\.djvu$")

# ----- coord + parse ---------------------------------------------------------

def _parse_coords(raw: str) -> tuple[int, int, int, int] | None:
    """Return (x_left, y_top, x_right, y_bottom) from a DjVu coords string.

    DjVu XML writes coords as (x_min, y_bottom, x_max, y_top) with y_bottom
    numerically greater than y_top in the image frame. Sorting defensively
    gives us the same tuple layout regardless of order.
    """
    try:
        parts = [int(p) for p in raw.split(",")]
    except ValueError:
        return None
    if len(parts) != 4:
        return None
    x_a, y_a, x_b, y_b = parts
    x_left, x_right = sorted((x_a, x_b))
    y_top, y_bottom = sorted((y_a, y_b))
    return x_left, y_top, x_right, y_bottom


def _looks_like_word(text: str) -> bool:
    """Drop pure-punctuation OCR artifacts (=, |, ~, ·, etc.)."""
    return any(c.isalnum() for c in text)


def parse_djvu(xml_path) -> Iterator[dict]:
    """Yield one dict per page.

    Each dict:
      {"index": int,          # IA page index parsed from usemap="..._NNNN.djvu"
       "width": int,          # page width in px
       "height": int,         # page height in px
       "words": [(x_left, y_top, x_right, y_bottom, text), ...]}
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    for obj in root.iter("OBJECT"):
        usemap = obj.get("usemap", "")
        m = PAGE_ID_RE.search(usemap)
        if not m:
            continue
        idx = int(m.group(1))
        try:
            width = int(obj.get("width", "0"))
            height = int(obj.get("height", "0"))
        except ValueError:
            width, height = 0, 0
        words: list[tuple[int, int, int, int, str]] = []
        for w in obj.iter("WORD"):
            coords = _parse_coords(w.get("coords", ""))
            if coords is None:
                continue
            text = (w.text or "").strip()
            if not text or not _looks_like_word(text):
                continue
            x0, y0, x1, y1 = coords
            words.append((x0, y0, x1, y1, text))
        yield {"index": idx, "width": width, "height": height, "words": words}


# ----- line grouping ---------------------------------------------------------

def _group_into_lines(
    words: list[tuple[int, int, int, int, str]],
    y_tolerance: int | None = None,
) -> list[list[tuple[int, int, int, int, str]]]:
    """Group words into visual lines by y-proximity.

    Sort by (y_top, x_left); walk in order; assign each word to the current
    line if its y_top is within tolerance of the running line's mean y_top,
    else open a new line. Tolerance defaults to 0.6 * median word height —
    generous enough to keep punctuation and ascenders on the same baseline,
    tight enough to keep separate print-lines apart.
    """
    if not words:
        return []
    if y_tolerance is None:
        heights = [w[3] - w[1] for w in words if w[3] > w[1]]
        med = statistics.median(heights) if heights else 60
        y_tolerance = max(12, int(med * 0.6))
    sorted_ws = sorted(words, key=lambda w: (w[1], w[0]))
    lines: list[list] = []
    for w in sorted_ws:
        if not lines:
            lines.append([w])
            continue
        cur = lines[-1]
        cur_top = statistics.mean(x[1] for x in cur)
        if abs(w[1] - cur_top) <= y_tolerance:
            cur.append(w)
        else:
            lines.append([w])
    return lines


# ----- column split ---------------------------------------------------------

def split_columns(
    words: list[tuple[int, int, int, int, str]],
    page_width: int,
    split_ratio: float = 0.35,
    min_gap_px: int | None = None,
) -> tuple[list, list]:
    """Return (margin_words, body_words), split per line at `page_width*split_ratio`.

    For each OCR line we look for a gap that literally straddles the threshold
    AND is at least `min_gap_px` wide: a pair of adjacent (by x_left) words
    where the left word ends BEFORE the threshold, the right word begins AT
    OR AFTER it, and the space between them is wide enough that it's a real
    inter-column band, not a coincidentally-placed inter-word space on a
    full-width body line.

    `min_gap_px` defaults to max(85, 2.4% of page_width). Empirically on this
    600-DPI IA scan, real shoulder-note gaps run 100–220 px while normal
    inter-word gaps stay under 80 px.

    Lines with no qualifying gap:
      - all words right of threshold → body (a normal body line);
      - all words left of threshold  → margin (a pure shoulder-note line);
      - mixed (some word straddles the threshold, or the crossing gap is too
        narrow) → body (a full-width body line).

    If fewer than 5 words end up in the margin, return ([], all_words) — the
    page has no shoulder note.
    """
    if not words:
        return [], []
    threshold = page_width * split_ratio
    if min_gap_px is None:
        min_gap_px = max(85, int(page_width * 0.024))
    lines = _group_into_lines(words)
    margin: list = []
    body: list = []
    for line in lines:
        line_sorted = sorted(line, key=lambda w: w[0])
        split_idx = None
        for i in range(len(line_sorted) - 1):
            left_end = line_sorted[i][2]
            right_start = line_sorted[i + 1][0]
            gap = right_start - left_end
            if left_end < threshold <= right_start and gap >= min_gap_px:
                split_idx = i + 1
                break
        if split_idx is not None:
            margin.extend(line_sorted[:split_idx])
            body.extend(line_sorted[split_idx:])
            continue
        # No qualifying gap crossing the threshold
        if all(w[2] < threshold for w in line_sorted):
            margin.extend(line_sorted)
        else:
            body.extend(line_sorted)

    if len(margin) < 5:
        return [], words
    return margin, body


# ----- lines → structured text ---------------------------------------------

def words_to_lines(
    words: list[tuple[int, int, int, int, str]],
    y_tolerance: int | None = None,
) -> list[dict]:
    """Group words into lines and render each as text with its y-range.

    Returns [{"y0": y_top, "y1": y_bottom, "x0": x_left, "x1": x_right,
              "text": " ".join(words)}].
    """
    lines_of_words = _group_into_lines(words, y_tolerance=y_tolerance)
    out: list[dict] = []
    for ln in lines_of_words:
        ln_sorted = sorted(ln, key=lambda w: w[0])
        text = " ".join(w[4] for w in ln_sorted)
        out.append({
            "y0": min(w[1] for w in ln_sorted),
            "y1": max(w[3] for w in ln_sorted),
            "x0": min(w[0] for w in ln_sorted),
            "x1": max(w[2] for w in ln_sorted),
            "text": text,
        })
    return out


# ----- margin notes clustering ---------------------------------------------

def _cluster_notes(margin_lines: list[dict], gap_multiplier: float = 2.2) -> list[dict]:
    """Group consecutive margin lines into notes by vertical adjacency.

    Two consecutive margin lines belong to the same note iff their vertical
    gap is smaller than gap_multiplier × median line height. Each note gets
    the combined (y0, y1) range so callers can splice it back into body at
    the right place.
    """
    if not margin_lines:
        return []
    heights = [ln["y1"] - ln["y0"] for ln in margin_lines if ln["y1"] > ln["y0"]]
    med_h = statistics.median(heights) if heights else 60
    gap_thresh = med_h * gap_multiplier
    notes: list[list[dict]] = []
    for ln in margin_lines:
        if not notes:
            notes.append([ln])
            continue
        prev_last = notes[-1][-1]
        gap = ln["y0"] - prev_last["y1"]
        if gap <= gap_thresh:
            notes[-1].append(ln)
        else:
            notes.append([ln])
    out: list[dict] = []
    for note in notes:
        text = " ".join(ln["text"] for ln in note).strip()
        # trim any trailing lone-punct OCR tokens
        text = re.sub(r"(\s[=|~\-·]+)+$", "", text).strip()
        out.append({
            "text": text,
            "y0": min(ln["y0"] for ln in note),
            "y1": max(ln["y1"] for ln in note),
        })
    return out


# ----- assemble body prose --------------------------------------------------

def assemble_page(margin_lines: list[dict], body_lines: list[dict]) -> dict:
    """Reconstruct one page.

    Body: consecutive body lines are joined with a single space. A paragraph
    break is inserted when the vertical gap between two lines is ≥1.8× the
    median gap AND the earlier line ended well short of the right margin
    (i.e., it looks like the end of a paragraph, not a mid-paragraph wrap).

    Notes: clustered margin lines with their y-ranges so a downstream tool
    can splice them into the body at the correct position.
    """
    notes = _cluster_notes(margin_lines)
    if not body_lines:
        return {"body": "", "notes": notes}

    gaps: list[int] = []
    for prev, cur in zip(body_lines, body_lines[1:]):
        gaps.append(max(0, cur["y0"] - prev["y1"]))
    median_gap = statistics.median(gaps) if gaps else 30
    right_max = max(ln["x1"] for ln in body_lines)
    right_short = right_max - 240  # "short line" threshold ~240px shy of right edge

    pieces: list[str] = [body_lines[0]["text"]]
    for prev, cur in zip(body_lines, body_lines[1:]):
        gap = max(0, cur["y0"] - prev["y1"])
        prev_ended_short = prev["x1"] < right_short
        if gap >= median_gap * 1.8 and prev_ended_short:
            pieces.append("\n\n" + cur["text"])
        else:
            pieces.append(" " + cur["text"])
    body = "".join(pieces).strip()
    return {"body": body, "notes": notes}


# ----- driver ---------------------------------------------------------------

def main() -> int:
    xml_path = Path("/Users/neharepal/gurudev-corpus/_surya_ocr_job/ia_reocr/mim_djvu.xml")
    out_path = Path("/Users/neharepal/gurudev-corpus/_surya_ocr_job/ia_reocr/mim_preface_split.json")

    if not xml_path.exists():
        print(f"missing: {xml_path}", file=sys.stderr)
        return 1

    target_range = range(7, 46)  # IA page indices 7..45 inclusive
    results: list[dict] = []
    per_page_summary: list[dict] = []

    for page in parse_djvu(xml_path):
        if page["index"] not in target_range:
            continue
        margin_words, body_words = split_columns(page["words"], page["width"])
        margin_lines = words_to_lines(margin_words)
        body_lines = words_to_lines(body_words)
        assembled = assemble_page(margin_lines, body_lines)

        page_out = {
            "index": page["index"],
            "width": page["width"],
            "height": page["height"],
            "body": assembled["body"],
            "notes": assembled["notes"],
        }
        results.append(page_out)
        per_page_summary.append({
            "index": page["index"],
            "n_notes": len(assembled["notes"]),
            "body_chars": len(assembled["body"]),
        })

        print(f"\n=== IA page {page['index']:04d} ({page['width']}x{page['height']}) ===")
        print(f"margin notes detected: {len(assembled['notes'])}")
        for i, note in enumerate(assembled["notes"], 1):
            print(f"  - [{i}] y=[{note['y0']}..{note['y1']}] {note['text']}")
        preview = assembled["body"][:500].replace("\n", " / ")
        print(f"body[:500]: {preview}")

    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # aggregate report
    n_pages = len(per_page_summary)
    pages_with_notes = [p for p in per_page_summary if p["n_notes"] > 0]
    empty_pages = [p["index"] for p in per_page_summary if p["body_chars"] < 50]
    avg_notes = (
        sum(p["n_notes"] for p in pages_with_notes) / len(pages_with_notes)
        if pages_with_notes else 0
    )
    print("\n=== summary ===")
    print(f"preface pages scanned: {n_pages}")
    print(f"pages with >=1 margin note: {len(pages_with_notes)}")
    print(f"avg notes per note-bearing page: {avg_notes:.2f}")
    if empty_pages:
        print(f"pages with <50 chars body (empty or wrong): {empty_pages}")
    print(f"json -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
