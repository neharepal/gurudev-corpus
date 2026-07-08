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
