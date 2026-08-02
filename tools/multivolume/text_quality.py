"""Phase 3 text-quality pass for multi-volume assembly (RFC-020).

Input:  raw Surya-assembled markdown at _surya_ocr_job/out/<work>-vol<N>.md
Output: cleaned markdown at <staging_dir>/<work>-vol<N>.clean.md
Also emits a per-vol JSON diff report at <staging_dir>/<work>-vol<N>.diff.json

Cleanup rules (conservative — no edit that requires judgment happens silently):

1. Strip standalone page-number lines (Devanagari or Arabic digits alone on
   a line). Length capped at 4 digits so numeric lists are safe. Reports the
   count.

2. Rejoin paragraphs cut by a page break. Rule: if paragraph P ends without
   terminal punctuation AND the immediately-following block is a stripped
   page-number line AND the next paragraph P+1 doesn't look like a chapter
   marker or verse line, merge P + P+1 with a single space. Terminal set:
   . ? ! ॥ । "  '  » । (any Devanagari or western terminator).

3. Trim back-matter. From the first line matching `^संपर्क` to EOF is dropped,
   because that anchors the publisher/contact/price block on every vol. Also
   drops surrounding underscore-separator lines (`_____`) if they precede
   the संपर्क cutoff.

4. Whitespace hygiene: strip trailing spaces on every line; collapse ≥3
   consecutive blank lines to 1 blank line.

Deliberately NOT done:
- No `!` → `॥` guesses (`!` is genuine in some sentences)
- No verse-vs-body classification (Phase-4-adjacent, not our problem here)
- No OCR error correction (would need per-word review; separate pass)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Devanagari or Arabic digits, up to 4 chars, alone on a line
_PAGE_NUM_RE = re.compile(r"^\s*[०-९0-9]{1,4}\s*$")

# Blank line
_BLANK_RE = re.compile(r"^\s*$")

# Chapter marker patterns we must NOT rejoin across
_CHAPTER_MARKER_RE = re.compile(
    r"^\s*(?:"
    r"पुष्प\s+[०-९\d]+"                          # पुष्प N (vols 1, 2)
    r"|[०-९\d]+\s*\.\s*.+"                        # N. <title> (vols 4, 5)
    r"|[०-९\d]+\s*\)\s*.+"                        # N) sub-part (vol 3)
    r"|अनुक्रमणिका"
    r"|प्रस्तावना"
    r"|परिशिष्ट.*"
    r"|महत्वाच्या नोंदी"
    r"|काकांची प्रवचने.*"
    r")\s*$"
)

# Terminal punctuation — a paragraph ending in any of these is "complete"
# (don't need to rejoin across the page break)
_TERMINAL = set(list('.?!।॥"\')」»…') + ['।।'])

# Back-matter anchor: everything from the first `संपर्क` line onward
_BACKMATTER_ANCHOR_RE = re.compile(r"^\s*संपर्क\b")

# Separator lines that precede back-matter — drop when they lead into cutoff
_SEPARATOR_LINE_RE = re.compile(r"^\s*_{3,}\s*$")


@dataclass
class VolStats:
    input_lines: int = 0
    output_lines: int = 0
    page_nums_stripped: int = 0
    paragraphs_rejoined: int = 0
    backmatter_lines_dropped: int = 0
    separator_lines_dropped: int = 0
    trailing_ws_stripped: int = 0
    blank_runs_collapsed: int = 0

    def as_dict(self) -> dict:
        return {
            "input_lines": self.input_lines,
            "output_lines": self.output_lines,
            "page_nums_stripped": self.page_nums_stripped,
            "paragraphs_rejoined": self.paragraphs_rejoined,
            "backmatter_lines_dropped": self.backmatter_lines_dropped,
            "separator_lines_dropped": self.separator_lines_dropped,
            "trailing_ws_stripped": self.trailing_ws_stripped,
            "blank_runs_collapsed": self.blank_runs_collapsed,
        }


def _looks_like_verse(line: str) -> bool:
    """A short line ending with `!` or `॥` or `।।` is likely a verse pada
    that should NOT be joined with a following paragraph.
    """
    s = line.strip()
    if not s or len(s) > 100:
        return False
    return s.endswith(("!", "॥", "।।"))


def _ends_terminally(text: str) -> bool:
    s = text.rstrip()
    if not s:
        return True
    if s.endswith("।।") or s.endswith("॥"):
        return True
    return s[-1] in _TERMINAL


def clean(md: str) -> tuple[str, VolStats]:
    lines = md.splitlines()
    stats = VolStats(input_lines=len(lines))

    # Step 1: trailing-whitespace hygiene
    hygienic = []
    for L in lines:
        r = L.rstrip()
        if r != L:
            stats.trailing_ws_stripped += 1
        hygienic.append(r)
    lines = hygienic

    # Step 2: chop back-matter — from first `संपर्क` line to EOF, plus any
    # immediately-preceding blank/separator lines that clearly belong to
    # the boundary.
    cutoff = None
    for i, L in enumerate(lines):
        if _BACKMATTER_ANCHOR_RE.match(L):
            cutoff = i
            break
    if cutoff is not None:
        # Walk back to swallow adjacent blank/separator/underscore lines
        j = cutoff
        while j > 0 and (_BLANK_RE.match(lines[j - 1]) or _SEPARATOR_LINE_RE.match(lines[j - 1])):
            if _SEPARATOR_LINE_RE.match(lines[j - 1]):
                stats.separator_lines_dropped += 1
            j -= 1
        stats.backmatter_lines_dropped = len(lines) - j
        lines = lines[:j]

    # Also drop any orphan separator lines mid-body (unlikely, but safe)
    filtered = []
    for L in lines:
        if _SEPARATOR_LINE_RE.match(L):
            stats.separator_lines_dropped += 1
            continue
        filtered.append(L)
    lines = filtered

    # Step 3: strip standalone page numbers AND rejoin sentences cut by them
    # ONLY. A rejoin fires only when the ONLY intervening content between two
    # paragraphs is a page-number line (± surrounding blank lines). Ordinary
    # paragraph breaks (blank line only) are NEVER merged — those are the
    # author's real paragraph structure.
    def is_page_num(L: str) -> bool:
        return bool(_PAGE_NUM_RE.match(L))

    def is_blank(L: str) -> bool:
        return bool(_BLANK_RE.match(L))

    result: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        L = lines[i]

        if is_page_num(L):
            # Peek: is this page-number line sandwiched between two paragraphs
            # that can be legally rejoined? If so, drop the page number AND
            # merge. Otherwise just drop the page number and preserve
            # paragraph structure.
            stats.page_nums_stripped += 1

            # Find the previous non-blank line in `result`
            prev_idx = None
            for k in range(len(result) - 1, -1, -1):
                if not is_blank(result[k]):
                    prev_idx = k
                    break

            # Skip page number + any surrounding blanks in source; find next
            # non-blank, non-page-num line
            j = i + 1
            while j < n and (is_blank(lines[j]) or is_page_num(lines[j])):
                if is_page_num(lines[j]):
                    stats.page_nums_stripped += 1
                j += 1
            next_line = lines[j] if j < n else None

            can_rejoin = (
                prev_idx is not None
                and next_line is not None
                and not _ends_terminally(result[prev_idx])
                and not _looks_like_verse(result[prev_idx])
                and not _looks_like_verse(next_line)
                and not _CHAPTER_MARKER_RE.match(next_line)
                and not _CHAPTER_MARKER_RE.match(result[prev_idx])
            )

            if can_rejoin:
                # Drop trailing blanks from result, append next_line to prev
                while result and is_blank(result[-1]):
                    result.pop()
                result[-1] = result[-1] + " " + next_line.lstrip()
                stats.paragraphs_rejoined += 1
                i = j + 1  # skip past next_line too
                continue
            else:
                # Just drop the page number, keep the paragraph break
                i += 1
                continue

        result.append(L)
        i += 1

    # Step 4: collapse ≥3 consecutive blank lines to 1
    collapsed: list[str] = []
    blank_run = 0
    for L in result:
        if is_blank(L):
            blank_run += 1
            if blank_run == 1:
                collapsed.append("")
            else:
                stats.blank_runs_collapsed += 1
        else:
            blank_run = 0
            collapsed.append(L)

    # Trim leading/trailing blank lines
    while collapsed and is_blank(collapsed[0]):
        collapsed.pop(0)
    while collapsed and is_blank(collapsed[-1]):
        collapsed.pop()

    # Step 5: drop orphan chapter markers at EOF. If the last non-blank line
    # is a chapter marker (see _CHAPTER_MARKER_RE) with no body content after
    # it, drop it. Common cause: महत्वाच्या नोंदी (Reader's Notes) heading
    # whose body was just underscore-separator note-taking lines that we
    # already stripped in Step 2.
    while collapsed:
        # Find last non-blank
        last_idx = len(collapsed) - 1
        while last_idx >= 0 and is_blank(collapsed[last_idx]):
            last_idx -= 1
        if last_idx < 0:
            break
        if _CHAPTER_MARKER_RE.match(collapsed[last_idx]):
            # Drop it + any trailing blanks
            del collapsed[last_idx:]
            while collapsed and is_blank(collapsed[-1]):
                collapsed.pop()
            stats.backmatter_lines_dropped += 1
        else:
            break

    stats.output_lines = len(collapsed)
    out = "\n".join(collapsed) + "\n"
    return out, stats


def main():
    src_dir = Path("/Users/neharepal/gurudev-corpus/_surya_ocr_job/out")
    staging = Path("/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging")
    staging.mkdir(parents=True, exist_ok=True)

    summary = {}
    for vol in (1, 2, 3, 4, 5):
        wid = f"kakanchi-pravachane-vol{vol}"
        src = src_dir / f"{wid}.md"
        cleaned, stats = clean(src.read_text(encoding="utf-8"))
        out_md = staging / f"{wid}.clean.md"
        out_md.write_text(cleaned, encoding="utf-8")
        (staging / f"{wid}.diff.json").write_text(json.dumps(stats.as_dict(), indent=2), encoding="utf-8")
        summary[wid] = stats.as_dict()

    (staging / "phase3_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print human-readable summary
    print(f"{'vol':<6} {'in':>6} {'out':>6} {'pgnum':>7} {'rejoin':>8} {'backmatter':>11} {'seps':>6} {'ws':>6} {'blanks':>8}")
    for wid, s in summary.items():
        v = wid.split("vol")[-1]
        print(f"vol {v:<4} {s['input_lines']:>6} {s['output_lines']:>6} "
              f"{s['page_nums_stripped']:>7} {s['paragraphs_rejoined']:>8} "
              f"{s['backmatter_lines_dropped']:>11} {s['separator_lines_dropped']:>6} "
              f"{s['trailing_ws_stripped']:>6} {s['blank_runs_collapsed']:>8}")


if __name__ == "__main__":
    main()
