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
