import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arthasahit_parse import split_verse_meaning


def test_splits_at_artha_marker():
    entry = "करीं धंदा परि आवडती पाय ॥१॥\nअर्थ - या अभंगात तुकाराम म्हणतात..."
    verse, meaning = split_verse_meaning(entry)
    assert "करीं धंदा" in verse
    assert meaning is not None and "तुकाराम म्हणतात" in meaning
    assert "अर्थ" not in verse


def test_splits_at_english_gloss():
    entry = "माझिया मीपणावरी पडो पाषाण ॥१॥\n(Cursed be my egoism.)"
    verse, meaning = split_verse_meaning(entry)
    assert "पाषाण" in verse
    assert meaning is not None and "Cursed be my egoism" in meaning


def test_no_confident_boundary_returns_none_meaning():
    entry = "गुरु गोविंद दोऊ खड़े । काके लागूं पाय ॥"
    verse, meaning = split_verse_meaning(entry)
    assert verse == entry.strip()
    assert meaning is None


def test_arthat_line_is_not_a_marker():
    entry = "पहिला चरण ॥१॥\nअर्थात दुसरा चरण आहे ॥२॥"
    verse, meaning = split_verse_meaning(entry)
    assert meaning is None


def test_marker_at_start_gives_empty_verse():
    entry = "अर्थ - या अभंगात तुकाराम म्हणतात."
    verse, meaning = split_verse_meaning(entry)
    assert verse == ""
    assert meaning == "अर्थ - या अभंगात तुकाराम म्हणतात."
