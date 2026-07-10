import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grounding as g

_LONG = "x" * 250

def test_retries_when_under_cited_and_takes_cited_retry():
    first = {"framing": _LONG, "citations": []}
    retry = {"framing": _LONG, "citations": [{"quote": {"body": "q"}}]}
    calls = {"n": 0}
    def regen():
        calls["n"] += 1
        return retry
    out = g.enforce_qa(first, passages_supplied=8, regenerate=regen)
    assert out is retry and calls["n"] == 1

def test_no_retry_when_already_cited():
    first = {"framing": _LONG, "citations": [{"quote": {"body": "q"}}]}
    def regen(): raise AssertionError("should not regenerate")
    out = g.enforce_qa(first, passages_supplied=8, regenerate=regen)
    assert out is first

def test_keeps_first_when_retry_still_uncited():
    first = {"framing": _LONG, "citations": []}
    retry = {"framing": _LONG, "citations": []}
    out = g.enforce_qa(first, passages_supplied=8, regenerate=lambda: retry)
    assert out is first  # no improvement -> keep original, don't loop

def test_regen_exception_is_safe():
    first = {"framing": _LONG, "citations": []}
    def regen(): raise RuntimeError("api down")
    out = g.enforce_qa(first, passages_supplied=8, regenerate=regen)
    assert out is first
