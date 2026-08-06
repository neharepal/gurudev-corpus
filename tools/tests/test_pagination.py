import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pagination import paginate, page_for_paragraph_index, is_chapter_start, PAGE_SIZE

def _p(n, chapter):
    return {"n": n, "chapter": chapter, "body": f"para {n}"}

def test_chapter_change_forces_new_page():
    pages = paginate([_p(1, "A"), _p(2, "A"), _p(3, "B")])
    assert [len(pg) for pg in pages] == [2, 1]
    assert [pg[0]["chapter"] for pg in pages] == ["A", "B"]

def test_long_chapter_splits_by_page_size():
    pages = paginate([_p(i, "A") for i in range(1, PAGE_SIZE * 2 + 2)])  # 9 paras
    assert [len(pg) for pg in pages] == [PAGE_SIZE, PAGE_SIZE, 1]

def test_every_paragraph_in_exactly_one_page_in_order():
    paras = [_p(1, "A"), _p(2, "B"), _p(3, "B"), _p(4, "B"), _p(5, "B"), _p(6, "B")]
    flat = [pa for pg in paginate(paras) for pa in pg]
    assert flat == paras

def test_page_for_paragraph_index():
    paras = [_p(1, "A"), _p(2, "A"), _p(3, "B"), _p(4, "B")]  # pages [A,A],[B,B]
    assert page_for_paragraph_index(paras, 0) == 1
    assert page_for_paragraph_index(paras, 1) == 1
    assert page_for_paragraph_index(paras, 2) == 2
    assert page_for_paragraph_index(paras, 99) == 2   # clamp past end

def test_is_chapter_start():
    paras = [_p(1, "A"), _p(2, "A"), _p(3, "B"), _p(4, "B")]
    pages = paginate(paras)
    assert is_chapter_start(pages, 1) is True
    assert is_chapter_start(pages, 2) is True

def test_continuation_page_is_not_chapter_start():
    pages = paginate([_p(i, "A") for i in range(1, PAGE_SIZE + 3)])  # [4],[2] same chapter
    assert is_chapter_start(pages, 1) is True
    assert is_chapter_start(pages, 2) is False

def test_empty():
    assert paginate([]) == []
    assert page_for_paragraph_index([], 0) == 1


# --- Sub-heading pass-through (2026-08-03) ---
# `is_subheading=True` paragraphs (####-emitted headings that ride inline
# with body prose) must NOT count toward PAGE_SIZE, otherwise a chapter
# opener with clustered `#### N. Title` heads would push real body prose
# off the first page. Chapter change still forces a new page.

def _sub(n, chapter):
    return {"n": n, "chapter": chapter, "body": f"heading {n}", "is_subheading": True}


def test_subheadings_do_not_consume_page_size():
    # 5 sub-headings + 4 body paras — all fit on ONE page (subheadings free)
    paras = [_sub(1, "A"), _sub(2, "A"), _sub(3, "A"), _sub(4, "A"), _sub(5, "A"),
             _p(6, "A"), _p(7, "A"), _p(8, "A"), _p(9, "A")]
    pages = paginate(paras)
    assert len(pages) == 1
    assert len(pages[0]) == 9


def test_body_paragraphs_still_wrap_at_page_size():
    # Sub-headings inline with a run of body paras: body paras still cap the
    # page. 1 subheading + PAGE_SIZE body + 1 body → 2 pages (page 1 has the
    # sub-heading and PAGE_SIZE body paras; page 2 has the final body).
    paras = [_sub(1, "A")] + [_p(i, "A") for i in range(2, PAGE_SIZE + 3)]
    pages = paginate(paras)
    assert [len(pg) for pg in pages] == [PAGE_SIZE + 1, 1]


def test_chapter_change_still_forces_page_break_even_with_subheadings():
    paras = [_p(1, "A"), _sub(2, "A"), _p(3, "B"), _sub(4, "B")]
    pages = paginate(paras)
    assert [len(pg) for pg in pages] == [2, 2]
    assert pages[0][0]["chapter"] == "A"
    assert pages[1][0]["chapter"] == "B"


# --- Char-density pagination (2026-08-06) -----------------------------------
# VERSE_FORMAT_SLUGS books opt in via `target_chars` to pack pages by body
# character count instead of a fixed PAGE_SIZE. Prose books still get the
# legacy 4-paragraph pages — that path MUST be bit-exact unchanged.


def _pl(n, chapter, body):
    return {"n": n, "chapter": chapter, "body": body}


def test_char_density_packs_until_target():
    # 10 paragraphs of 200 chars each = 2000 total. target=1500, min=3.
    # After 8 paras: 1600 chars ≥ 1500 → break. 2 remain on page 2.
    paras = [_pl(i, "A", "x" * 200) for i in range(1, 11)]
    pages = paginate(paras, target_chars=1500)
    assert [len(pg) for pg in pages] == [8, 2]


def test_char_density_respects_min_per_page():
    # A single 5000-char paragraph followed by two short ones: the long
    # para alone exceeds target immediately, but min_per_page=3 forbids
    # breaking after 1 body. Must pull in the next 2 before closing.
    paras = [_pl(1, "A", "x" * 5000), _pl(2, "A", "short"), _pl(3, "A", "short")]
    pages = paginate(paras, target_chars=1500, min_per_page=3)
    assert len(pages) == 1
    assert len(pages[0]) == 3


def test_char_density_respects_max_per_page():
    # 100 tiny paragraphs — never hits target chars. max_per_page=10 forces
    # a break at 10 rows regardless.
    paras = [_pl(i, "A", "hey!") for i in range(1, 101)]
    pages = paginate(paras, target_chars=1500, max_per_page=10)
    assert [len(pg) for pg in pages] == [10] * 10


def test_char_density_chapter_change_still_breaks_page():
    paras = [_pl(1, "A", "x" * 300), _pl(2, "B", "x" * 300)]
    pages = paginate(paras, target_chars=1500)
    assert [len(pg) for pg in pages] == [1, 1]
    assert pages[0][0]["chapter"] == "A"
    assert pages[1][0]["chapter"] == "B"


def test_char_density_headings_do_not_count_toward_chars_or_cap():
    heading = {"n": 1, "chapter": "A", "body": "H", "is_heading": True}
    paras = [heading] + [_pl(i, "A", "x" * 500) for i in range(2, 5)]  # 3 bodies × 500 = 1500
    pages = paginate(paras, target_chars=1500, min_per_page=3)
    assert len(pages) == 1
    assert len(pages[0]) == 4


def test_page_for_paragraph_index_char_density():
    paras = [_pl(i, "A", "x" * 200) for i in range(1, 11)]
    assert page_for_paragraph_index(paras, 0, target_chars=1500) == 1
    assert page_for_paragraph_index(paras, 7, target_chars=1500) == 1
    assert page_for_paragraph_index(paras, 8, target_chars=1500) == 2
    assert page_for_paragraph_index(paras, 9, target_chars=1500) == 2


def test_target_none_is_bit_exact_legacy_page_size():
    # Regression: target_chars=None must produce IDENTICAL pages to omitting
    # the parameter. Guards the fixed-count path.
    paras = [_p(i, "A") for i in range(1, PAGE_SIZE * 3 + 2)]
    assert paginate(paras) == paginate(paras, target_chars=None)


def test_default_call_unchanged_for_prose_workflow():
    # Legacy 4-per-page, no target — the split prose books have relied on
    # since RFC-020. Belt-and-suspenders for kakanchi-pravachane.
    paras = [_p(i, "A") for i in range(1, 10)]
    pages = paginate(paras)
    assert [len(pg) for pg in pages] == [PAGE_SIZE, PAGE_SIZE, 1]


# --- One-entry-per-page pagination (2026-08-06) -----------------------------
# `reflections` (Gurudev Ranade's diary) needs each `### <date>` entry on its
# own page. `##` part markers immediately followed by `###` share a page with
# the child (part header + first entry = one natural unit).


def _h(n, chapter, level=3, body=None):
    return {
        "n": n, "chapter": chapter,
        "body": body or f"heading {n}",
        "is_heading": True, "heading_level": level,
    }


def _b(n, chapter, body=None):
    return {"n": n, "chapter": chapter, "body": body or f"body {n}"}


def test_one_entry_per_page_each_h3_starts_new_page():
    # 3 date entries, each with a body paragraph → 3 pages.
    paras = [
        _h(1, "Feb 21", level=3), _b(2, "Feb 21"),
        _h(3, "Feb 22", level=3), _b(4, "Feb 22"),
        _h(5, "Feb 23", level=3), _b(6, "Feb 23"),
    ]
    pages = paginate(paras, one_entry_per_page=True)
    assert len(pages) == 3
    assert [pg[0]["body"] for pg in pages] == ["heading 1", "heading 3", "heading 5"]


def test_one_entry_per_page_multi_body_stays_on_same_page():
    # A single date entry with 10 body paragraphs must stay on ONE page,
    # not split at PAGE_SIZE — the mode has NO length cap between headings.
    paras = [_h(1, "Feb 21", level=3)] + [_b(i, "Feb 21") for i in range(2, 12)]
    pages = paginate(paras, one_entry_per_page=True)
    assert len(pages) == 1
    assert len(pages[0]) == 11


def test_one_entry_per_page_h2_pairs_with_next_h3():
    # H2 "PART I" immediately followed by H3 "first date" packs on one page.
    paras = [
        _h(1, "PART I", level=2),
        _h(2, "Feb 21", level=3),
        _b(3, "Feb 21"),
        _h(4, "Feb 22", level=3),
        _b(5, "Feb 22"),
    ]
    pages = paginate(paras, one_entry_per_page=True)
    assert len(pages) == 2
    # Page 1: H2 + H3 + body
    assert [p.get("heading_level") for p in pages[0]] == [2, 3, None]
    # Page 2: H3 + body
    assert [p.get("heading_level") for p in pages[1]] == [3, None]


def test_one_entry_per_page_h2_mid_stream_breaks_page():
    # H2 mid-stream (start of Part II) MUST close the previous entry.
    paras = [
        _h(1, "PART I", level=2), _h(2, "Feb 21", level=3), _b(3, "Feb 21"),
        _h(4, "PART II", level=2), _h(5, "May 10", level=3), _b(6, "May 10"),
    ]
    pages = paginate(paras, one_entry_per_page=True)
    assert len(pages) == 2
    assert [p["body"] for p in pages[0]] == ["heading 1", "heading 2", "body 3"]
    assert [p["body"] for p in pages[1]] == ["heading 4", "heading 5", "body 6"]


def test_one_entry_per_page_exclusive_with_target_chars():
    # The two modes are mutually exclusive — combining them raises.
    import pytest as _pt
    with _pt.raises(ValueError):
        paginate([_b(1, "A")], target_chars=1500, one_entry_per_page=True)


def test_one_entry_per_page_reflections_shape():
    # Simulates reflections: 3 parts, 67 dates, mostly 1-body entries.
    # Neha's target: exactly 67 pages (each date = 1 page; part headings
    # ride on the first date of their part).
    paras = []
    n = 1
    # Part I: 30 dates
    paras.append(_h(n, "PART I", level=2)); n += 1
    for i in range(30):
        paras.append(_h(n, f"P1-day-{i}", level=3)); n += 1
        paras.append(_b(n, f"P1-day-{i}")); n += 1
    # Part II: 20 dates
    paras.append(_h(n, "PART II", level=2)); n += 1
    for i in range(20):
        paras.append(_h(n, f"P2-day-{i}", level=3)); n += 1
        paras.append(_b(n, f"P2-day-{i}")); n += 1
    # Part III: 17 dates
    paras.append(_h(n, "PART III", level=2)); n += 1
    for i in range(17):
        paras.append(_h(n, f"P3-day-{i}", level=3)); n += 1
        paras.append(_b(n, f"P3-day-{i}")); n += 1
    pages = paginate(paras, one_entry_per_page=True)
    assert len(pages) == 67, f"expected 67 pages (30+20+17), got {len(pages)}"


def test_one_entry_per_page_subheadings_ride_along():
    # is_subheading rows (####+ items) also aren't headings — they should
    # ride onto the current entry's page without breaking.
    paras = [
        _h(1, "Feb 21", level=3),
        {"n": 2, "chapter": "Feb 21", "body": "sub", "is_subheading": True},
        _b(3, "Feb 21"),
        _h(4, "Feb 22", level=3),
        _b(5, "Feb 22"),
    ]
    pages = paginate(paras, one_entry_per_page=True)
    assert len(pages) == 2
    assert len(pages[0]) == 3


def test_one_entry_per_page_bit_exact_default_when_off():
    # Regression: passing one_entry_per_page=False (or omitting) must give
    # identical results to the legacy default path for a prose input.
    paras = [_p(i, "A") for i in range(1, 10)]
    assert paginate(paras) == paginate(paras, one_entry_per_page=False)


def test_page_for_paragraph_index_one_entry_per_page():
    # Verify index → page mapping works under the new mode.
    paras = [
        _h(1, "Feb 21", level=3), _b(2, "Feb 21"),
        _h(3, "Feb 22", level=3), _b(4, "Feb 22"), _b(5, "Feb 22"),
        _h(6, "Feb 23", level=3), _b(7, "Feb 23"),
    ]
    assert page_for_paragraph_index(paras, 0, one_entry_per_page=True) == 1
    assert page_for_paragraph_index(paras, 1, one_entry_per_page=True) == 1
    assert page_for_paragraph_index(paras, 2, one_entry_per_page=True) == 2
    assert page_for_paragraph_index(paras, 4, one_entry_per_page=True) == 2
    assert page_for_paragraph_index(paras, 5, one_entry_per_page=True) == 3


# --- Real-corpus regression: reflections one-entry-per-page + KP control ----
# End-to-end sanity: parse the on-disk reflections and kakanchi-pravachane
# text.md through the actual paginator. Reflections must produce 67 pages
# (one per date entry); kakanchi-pravachane must be bit-exact unchanged.


import pathlib as _pathlib
import sys as _sys

_REPO = _pathlib.Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(_REPO / "tools"))
from server import _parse_work_text as _parse  # noqa: E402
from server import (  # noqa: E402
    _pagination_target_chars as _target_for,
    _pagination_one_entry_per_page as _one_entry_for,
)
import pytest as _pytest  # noqa: E402

_REFLECTIONS_TXT = _REPO / "01_canonical" / "gurudev_ranade" / "books" / "reflections" / "en" / "text.md"
_KAKANCHI_TXT = (
    _REPO / "01_canonical" / "kakasaheb_tulpule" / "lectures" / "kakanchi-pravachane" / "mr" / "text.md"
)


@_pytest.mark.skipif(not _REFLECTIONS_TXT.exists(), reason="reflections text.md missing")
class TestReflectionsOneEntryPerPage:
    def _pages(self):
        paras = _parse(_REFLECTIONS_TXT, slug="reflections")
        return paginate(
            paras,
            target_chars=_target_for("reflections"),
            one_entry_per_page=_one_entry_for("reflections"),
        )

    def test_helpers_return_expected_flags_for_reflections(self):
        assert _target_for("reflections") is None, "one-per-entry must exclude char-density"
        assert _one_entry_for("reflections") is True

    def test_total_pages_equals_dated_entries(self):
        pages = self._pages()
        # 3 H2 (part titles) + 67 H3 (dates) in the source. Each H2 rides
        # with the H3 that follows it → 67 pages total.
        assert len(pages) == 67, (
            f"expected 67 pages (one per date entry), got {len(pages)}"
        )

    def test_page_1_starts_with_h2_then_h3(self):
        pages = self._pages()
        first = pages[0]
        # First para: H2 "REFLECTIONS – I"; second para: H3 "21st February 1912"
        assert first[0].get("is_heading") is True
        assert first[0].get("heading_level") == 2
        assert "REFLECTIONS" in first[0]["body"]
        assert first[1].get("is_heading") is True
        assert first[1].get("heading_level") == 3
        assert "21st February 1912" in first[1]["body"]
        # Followed by at least one body paragraph
        assert any(not p.get("is_heading") for p in first)

    def test_page_2_starts_with_h3_only(self):
        pages = self._pages()
        second = pages[1]
        assert second[0].get("is_heading") is True
        assert second[0].get("heading_level") == 3
        assert "22nd February 1912" in second[0]["body"]
        # No H2 on page 2
        assert not any(p.get("heading_level") == 2 for p in second)

    def test_every_page_starts_with_a_heading(self):
        # Regression: every page's first row is an is_heading row (H2 or H3).
        # If this fails, a body paragraph slipped into the leading slot.
        pages = self._pages()
        for i, pg in enumerate(pages, 1):
            assert pg[0].get("is_heading") is True, (
                f"page {i} does not start with a heading: {pg[0].get('body', '')[:40]}"
            )


@_pytest.mark.skipif(not _KAKANCHI_TXT.exists(), reason="kakanchi-pravachane text.md missing")
class TestKakanchiPravachaneBitExactUnderNewMode:
    """Regression: reflections mode changes MUST NOT touch prose books.
    Parse + paginate kakanchi-pravachane exactly as production does with
    the new call shape, and verify identical output to the plain default."""

    def test_helpers_off_for_kakanchi(self):
        assert _target_for("kakanchi-pravachane") is None
        assert _one_entry_for("kakanchi-pravachane") is False

    def test_pagination_bit_exact(self):
        paras = _parse(_KAKANCHI_TXT, slug="kakanchi-pravachane")
        pages_plain = paginate(paras)
        pages_via_helpers = paginate(
            paras,
            target_chars=_target_for("kakanchi-pravachane"),
            one_entry_per_page=_one_entry_for("kakanchi-pravachane"),
        )
        assert [len(pg) for pg in pages_plain] == [len(pg) for pg in pages_via_helpers]
        assert [[p["n"] for p in pg] for pg in pages_plain] == \
               [[p["n"] for p in pg] for pg in pages_via_helpers]
