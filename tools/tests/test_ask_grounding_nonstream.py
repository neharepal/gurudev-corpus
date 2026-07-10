# tools/tests/test_ask_grounding_nonstream.py
# Exercises _enforce_and_verify_qa: the pure orchestration the handler calls.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server

_LONG = "x" * 250

def test_enforce_regenerates_when_uncited(monkeypatch):
    monkeypatch.setenv("GROUNDING_MODE", "enforce")
    first = {"framing": _LONG, "citations": []}
    retry = {"framing": _LONG, "citations": [{"quote": {"passage": "A", "body": "love to God"}}]}
    ltc = {"A": {"text": "love to God and man", "meta": {}}}
    out, flags = server._enforce_and_verify_qa(first, ltc, regenerate=lambda: retry)
    assert out is retry and flags == []

def test_off_mode_is_noop(monkeypatch):
    monkeypatch.delenv("GROUNDING_MODE", raising=False)
    first = {"framing": _LONG, "citations": []}
    out, flags = server._enforce_and_verify_qa(first, {"A": {"text": "t", "meta": {}}},
                                               regenerate=lambda: {"boom": 1})
    assert out is first and flags == []   # no enforcement, no verify when off
