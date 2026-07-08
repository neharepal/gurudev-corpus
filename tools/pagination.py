"""Reading-page pagination for the corpus reader.

A page holds up to PAGE_SIZE paragraphs, BUT a change of `chapter` always starts
a new page (each book chapter opens on a fresh reader page). Pure and
dependency-free so read_work + the two deep-link page mappers agree on page
numbers. Spec: docs/superpowers/specs/2026-07-03-reading-mode-book-layout-design.md
"""
from __future__ import annotations
from typing import Any, Dict, List

PAGE_SIZE = 4


def paginate(paragraphs: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    pages: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_chapter: Any = None
    for para in paragraphs:
        chapter = para.get("chapter", "")
        if current and (chapter != current_chapter or len(current) >= PAGE_SIZE):
            pages.append(current)
            current = []
        if not current:
            current_chapter = chapter
        current.append(para)
    if current:
        pages.append(current)
    return pages


def page_for_paragraph_index(paragraphs: List[Dict[str, Any]], idx: int) -> int:
    if idx < 0:
        idx = 0
    pages = paginate(paragraphs)
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
