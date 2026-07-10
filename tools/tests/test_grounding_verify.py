import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grounding as g

def _chunk(text): return {"text": text, "meta": {"title": "W", "work_id": "w"}}

def test_clean_quote_passes():
    src = "Bhakti consists in love to God, and through the love of God, in the love of man."
    cits = [{"quote": {"passage": "A", "body": "love to God, and through the love of God"}}]
    flags = g.verify_citations(cits, {"A": _chunk(src)})
    assert flags == []

def test_body_absent_from_source_is_flagged():
    src = "A passage about the Upanishads and self-knowledge."
    cits = [{"quote": {"passage": "A", "body": "he built Carlyle Cottage in 1917"}}]
    flags = g.verify_citations(cits, {"A": _chunk(src)})
    assert len(flags) == 1 and flags[0]["passage"] == "A"

def test_unknown_passage_is_flagged():
    cits = [{"quote": {"passage": "Z", "body": "anything"}}]
    flags = g.verify_citations(cits, {"A": _chunk("...")})
    assert len(flags) == 1 and flags[0]["reason"] == "no source chunk"

def test_empty_body_skipped():
    cits = [{"quote": {"passage": "A", "body": ""}}]
    assert g.verify_citations(cits, {"A": _chunk("text")}) == []

def test_fuzzy_close_quote_passes():
    # A quote that differs only by a couple of chars from source should still match
    # (partial_ratio >= 85). Requires rapidfuzz; if absent this asserts exact-only
    # behavior instead, which is acceptable degradation.
    src = "Bhakti consists in love to God, and through the love of God, in the love of man."
    body = "love to God, and through the love of Gd, in the love of man"  # 'Gd' typo
    cits = [{"quote": {"passage": "A", "body": body}}]
    flags = g.verify_citations(cits, {"A": _chunk(src)})
    if g._partial_ratio is not None:
        assert flags == []          # fuzzy match tolerates the typo
    else:
        assert len(flags) == 1      # exact-only degradation flags it
