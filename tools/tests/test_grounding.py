import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grounding as g

_LONG = "x" * 250

def test_substantive_zero_citations_is_under_cited():
    resp = {"framing": _LONG, "citations": []}
    assert g.is_under_cited(resp, passages_supplied=8) is True

def test_has_citations_not_under_cited():
    resp = {"framing": _LONG, "citations": [{"quote": {"body": "..."}}]}
    assert g.is_under_cited(resp, passages_supplied=8) is False

def test_no_passages_supplied_not_under_cited():
    # Nothing to cite -> not a grounding failure (navigational / empty retrieval).
    resp = {"framing": _LONG, "citations": []}
    assert g.is_under_cited(resp, passages_supplied=0) is False

def test_trivial_answer_not_under_cited():
    resp = {"framing": "Not covered in the retrieved passages.", "citations": []}
    assert g.is_under_cited(resp, passages_supplied=8) is False

def test_framing_paragraphs_count_toward_length():
    resp = {"framing": "", "framingParagraphs": ["y" * 130, "z" * 130], "citations": []}
    assert g.is_under_cited(resp, passages_supplied=5) is True

def test_body_length_boundary():
    assert g.is_under_cited({"framing": "x" * 199, "citations": []}, passages_supplied=8) is False
    assert g.is_under_cited({"framing": "x" * 200, "citations": []}, passages_supplied=8) is True
