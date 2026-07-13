import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from childsplit import split_into_children


def test_prose_splits_into_sentences():
    txt = "Bhakti is the soul. Namasmaran is its practice. Grace descends."
    kids = split_into_children(txt, window=0)
    assert [k["text"] for k in kids] == [
        "Bhakti is the soul.", "Namasmaran is its practice.", "Grace descends."]
    assert all(k["text"] == k["embed_text"] for k in kids)  # window=0 ⇒ no window added


def test_embed_text_includes_neighbor_window():
    txt = "One. Two. Three."
    kids = split_into_children(txt, window=1)
    # middle child's embed_text carries its neighbors for signal
    mid = [k for k in kids if k["text"] == "Two."][0]
    assert "One." in mid["embed_text"] and "Three." in mid["embed_text"]


def test_devanagari_verse_splits_on_dandas():
    verse = "गुरु गोविंद दोऊ खड़े । काके लागूं पाय ॥ बलिहारी गुरु आपने ॥"
    kids = split_into_children(verse, window=0)
    assert len(kids) >= 2
    assert any("गुरु गोविंद" in k["text"] for k in kids)


def test_single_sentence_returns_one_child():
    kids = split_into_children("Only one sentence here.", window=1)
    assert len(kids) == 1
    assert kids[0]["text"] == kids[0]["embed_text"] == "Only one sentence here."
