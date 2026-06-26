"""Unit tests for server.reading_page_for_offset (F14 mapping).

These tests are corpus-free: a small synthetic text.md is written to a
tmp directory and server._resolve_text_path is monkeypatched to return it,
so no real corpus files are needed and the tests run offline.

Paragraph-to-page mapping: _PAGE_SIZE = 4, so
  idx 0-3  → page 1
  idx 4-7  → page 2
  idx 8-11 → page 3
  etc.

Each paragraph in the synthetic file is ≥80 chars (the filter threshold in
_parse_work_text) and separated by a blank line.  A YAML front-matter block
is prepended so the char_start / char_end offsets include the front-matter
bytes, exactly as the real chunker produces.
"""

import sys
import os
import textwrap
from pathlib import Path

import pytest

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)


# ---------------------------------------------------------------------------
# Helpers to build a synthetic text.md
# ---------------------------------------------------------------------------

# Front matter added to every synthetic file; length is fixed so we can
# predict char_start values when needed.
_FRONT_MATTER = "---\ntitle: Synthetic Test Work\nauthor: test_author\n---\n"

# Each "body paragraph" must be ≥ 80 chars (the _parse_work_text threshold).
# We pad them to exactly 80 chars for predictability.
def _make_paragraph(index: int) -> str:
    """Return a deterministic paragraph body of exactly 80 chars."""
    label = f"Paragraph {index}: "
    filler = "x" * (80 - len(label))
    return label + filler


def _build_text_md(n_paragraphs: int) -> str:
    """Build a minimal text.md with front matter + n_paragraphs paragraphs."""
    parts = [_FRONT_MATTER]
    for i in range(n_paragraphs):
        parts.append(_make_paragraph(i))
        parts.append("")  # blank line separator
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_text_path(tmp_path_factory):
    """Write a synthetic text.md with 12 paragraphs (→ 3 full pages)."""
    tmp = tmp_path_factory.mktemp("synthetic_work")
    text_path = tmp / "text.md"
    text_path.write_text(_build_text_md(12), encoding="utf-8")
    return text_path


@pytest.fixture(scope="module")
def parsed_paragraphs(synthetic_text_path):
    """Return the parsed paragraphs list for the synthetic file."""
    from server import _parse_work_text
    return _parse_work_text(synthetic_text_path)


# ---------------------------------------------------------------------------
# _parse_work_text sanity checks (corpus-free)
# ---------------------------------------------------------------------------

def test_synthetic_parse_produces_expected_count(parsed_paragraphs):
    """Exactly 12 qualifying paragraphs should be parsed."""
    assert len(parsed_paragraphs) == 12


def test_synthetic_paragraphs_numbered_from_1(parsed_paragraphs):
    for i, p in enumerate(parsed_paragraphs):
        assert p["n"] == i + 1


def test_synthetic_paragraphs_char_starts_are_ascending(parsed_paragraphs):
    starts = [p["char_start"] for p in parsed_paragraphs]
    assert starts == sorted(starts), "char_start values must be strictly ascending"


def test_synthetic_paragraphs_char_ends_after_starts(parsed_paragraphs):
    for p in parsed_paragraphs:
        assert p["char_end"] > p["char_start"]


# ---------------------------------------------------------------------------
# reading_page_for_offset — core mapping tests (monkeypatched resolver)
# ---------------------------------------------------------------------------

@pytest.fixture()
def patched_reading_page_for_offset(synthetic_text_path, monkeypatch):
    """Return a callable that calls reading_page_for_offset with the resolver
    monkeypatched to return our synthetic file regardless of slug/lang.
    """
    import server

    # Clear the in-process cache so each test starts clean.
    server._reading_cache.clear()

    # Make _resolve_text_path always return the synthetic file.
    monkeypatch.setattr(server, "_resolve_text_path", lambda slug, lang: synthetic_text_path)

    return server.reading_page_for_offset


def test_offset_zero_returns_page_1(patched_reading_page_for_offset, parsed_paragraphs):
    """An offset of 0 is before the first paragraph; should land on page 1."""
    page = patched_reading_page_for_offset("any-slug", "en", 0)
    assert page == 1, f"Expected page 1 for offset 0, got {page}"


def test_offset_inside_first_paragraph_returns_page_1(patched_reading_page_for_offset, parsed_paragraphs):
    """An offset inside paragraph 0 (idx=0) → page 1."""
    p0 = parsed_paragraphs[0]
    mid = p0["char_start"] + (p0["char_end"] - p0["char_start"]) // 2
    page = patched_reading_page_for_offset("any-slug", "en", mid)
    assert page == 1


def test_offset_at_paragraph_4_start_returns_page_2(patched_reading_page_for_offset, parsed_paragraphs):
    """Paragraph at idx=4 (5th paragraph) → page 2 (idxes 4-7 → page 2)."""
    p4 = parsed_paragraphs[4]
    page = patched_reading_page_for_offset("any-slug", "en", p4["char_start"])
    assert page == 2, f"Expected page 2 for paragraph idx=4, got {page}"


def test_offset_at_paragraph_8_start_returns_page_3(patched_reading_page_for_offset, parsed_paragraphs):
    """Paragraph at idx=8 (9th paragraph) → page 3 (idxes 8-11 → page 3)."""
    p8 = parsed_paragraphs[8]
    page = patched_reading_page_for_offset("any-slug", "en", p8["char_start"])
    assert page == 3, f"Expected page 3 for paragraph idx=8, got {page}"


def test_offset_inside_last_paragraph_returns_last_page(patched_reading_page_for_offset, parsed_paragraphs):
    """An offset inside the last paragraph (idx=11) → page 3."""
    p_last = parsed_paragraphs[-1]
    mid = p_last["char_start"] + (p_last["char_end"] - p_last["char_start"]) // 2
    page = patched_reading_page_for_offset("any-slug", "en", mid)
    # 12 paragraphs / PAGE_SIZE=4 → 3 pages; last paragraph idx=11 → page 3
    assert page == 3, f"Expected page 3 for last paragraph, got {page}"


def test_out_of_range_offset_returns_last_page(patched_reading_page_for_offset, parsed_paragraphs):
    """An offset beyond the last paragraph → last page (not None)."""
    # char_end of the last paragraph + a large number
    huge_offset = parsed_paragraphs[-1]["char_end"] + 100_000
    page = patched_reading_page_for_offset("any-slug", "en", huge_offset)
    assert page == 3, f"Expected last page (3) for out-of-range offset, got {page}"


def test_page_formula_holds_for_every_paragraph(patched_reading_page_for_offset, parsed_paragraphs):
    """For each paragraph at idx i, page = (i // PAGE_SIZE) + 1."""
    PAGE_SIZE = 4  # mirrors _PAGE_SIZE in server.py
    for i, para in enumerate(parsed_paragraphs):
        expected_page = (i // PAGE_SIZE) + 1
        # Use char_start to anchor to this paragraph exactly.
        page = patched_reading_page_for_offset("any-slug", None, para["char_start"])
        assert page == expected_page, (
            f"Paragraph idx={i}: expected page {expected_page}, got {page}"
        )


def test_unresolvable_slug_returns_none(monkeypatch):
    """If the work cannot be resolved, reading_page_for_offset returns None."""
    import server
    server._reading_cache.clear()
    monkeypatch.setattr(server, "_resolve_text_path", lambda slug, lang: None)
    result = server.reading_page_for_offset("no-such-work", "en", 0)
    assert result is None
