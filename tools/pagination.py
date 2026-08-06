"""Reading-page pagination for the corpus reader.

Two pagination modes:

  1. **Fixed-count** (default). Up to `PAGE_SIZE` body paragraphs per page.
     A chapter change always starts a new page. `is_subheading` / `is_heading`
     rows ride along without consuming a body slot. This is the historical
     path — every prose book (kakanchi-pravachane, MiM, …) uses it.

  2. **Char-density** (opt-in via `target_chars`). Pack body paragraphs
     greedily until the running char sum reaches `target_chars` OR the row
     count would exceed `max_per_page`. Always keep at least `min_per_page`
     rows so a lone chapter-opening heading + one short verse aren't stranded
     on a page-of-one. Only used for `VERSE_FORMAT_SLUGS` books — front
     matter items like `फोन :- (०८४२२) २८३७१६` shouldn't each take a
     PAGE_SIZE=4 slot the way a 400-char prose paragraph does. Spec:
     Neha 2026-08-06 (page 1 was 4 short address lines; wanted ~1500 chars).

Pure and dependency-free so `read_work` + the two deep-link page mappers
(`reading_page_for_offset`, `reading_page_for_body`) agree on page numbers.
Spec: docs/superpowers/specs/2026-07-03-reading-mode-book-layout-design.md
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

PAGE_SIZE = 4

# Char-density defaults, only consulted when `target_chars` is passed.
# 1500 chars ≈ one printed reader page for Devanagari verse books
# (validated visually against pages 58–62 of nityanemavali). 40-cap
# prevents a run of tiny one-word padas from ballooning a page into
# an unbrowsable wall; 3-floor prevents a heading + one line taking
# a whole page when the natural block just happens to be long.
_DEFAULT_MIN_PER_PAGE = 3
_DEFAULT_MAX_PER_PAGE = 40


def paginate(
    paragraphs: List[Dict[str, Any]],
    target_chars: Optional[int] = None,
    min_per_page: int = _DEFAULT_MIN_PER_PAGE,
    max_per_page: int = _DEFAULT_MAX_PER_PAGE,
) -> List[List[Dict[str, Any]]]:
    """Split `paragraphs` into reader pages.

    - If `target_chars` is None: legacy fixed-count mode (PAGE_SIZE bodies).
    - If `target_chars` is set (e.g. 1500 for VERSE_FORMAT_SLUGS books):
      char-density mode — pack until the body char sum reaches target OR
      the row count would exceed `max_per_page`, but never break before
      `min_per_page` bodies have landed on the page. Headings/subheadings
      still ride along without counting toward either the char sum or
      the row cap (they are structural, not body).
    """
    pages: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_chapter: Any = None
    body_count = 0  # only real body paragraphs count toward the size gate
    body_chars = 0  # body text char accumulator (density mode only)

    def _should_break() -> bool:
        """Are we allowed to break now (i.e. enough body already committed)
        AND does the size/density gate say we should?"""
        if body_count < min_per_page:
            return False
        if target_chars is None:
            return body_count >= PAGE_SIZE
        if len(current) >= max_per_page:
            return True
        return body_chars >= target_chars

    for para in paragraphs:
        chapter = para.get("chapter", "")
        # `is_subheading` (####+ items) and `is_heading` (verse-format ##/###
        # synthetic paragraphs — see server.VERSE_FORMAT_SLUGS) both ride
        # inline with body prose without consuming a page slot. Otherwise a
        # chapter opener with a heading + a few short verses would push real
        # body content off the page.
        is_structural = bool(para.get("is_subheading")) or bool(para.get("is_heading"))
        if current and (chapter != current_chapter or _should_break()):
            pages.append(current)
            current = []
            body_count = 0
            body_chars = 0
        if not current:
            current_chapter = chapter
        current.append(para)
        if not is_structural:
            body_count += 1
            if target_chars is not None:
                body_chars += len(para.get("body", ""))
    if current:
        pages.append(current)
    return pages


def page_for_paragraph_index(
    paragraphs: List[Dict[str, Any]],
    idx: int,
    target_chars: Optional[int] = None,
    min_per_page: int = _DEFAULT_MIN_PER_PAGE,
    max_per_page: int = _DEFAULT_MAX_PER_PAGE,
) -> int:
    if idx < 0:
        idx = 0
    pages = paginate(paragraphs, target_chars=target_chars,
                     min_per_page=min_per_page, max_per_page=max_per_page)
    seen = 0
    for page_num, page in enumerate(pages, start=1):
        seen += len(page)
        if idx < seen:
            return page_num
    return max(1, len(pages))


def is_chapter_start(pages: List[List[Dict[str, Any]]], page_num: int) -> bool:
    if page_num <= 1:
        return True
    if page_num > len(pages):
        return False
    return pages[page_num - 1][0].get("chapter", "") != pages[page_num - 2][-1].get("chapter", "")
