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


# ── follow-up relaxation: has_history skips the cite-harder retry ─────────

def test_has_history_short_circuits_retry_even_when_under_cited():
    """Follow-ups may legitimately answer with zero citations (case-b
    translate/summarize/elaborate) — the reader has the prior turn's
    citations. Forcing a retry causes the model to graft translations onto
    unrelated retrieved passages (observed 2026-07-18). Under has_history,
    enforce_qa MUST return `first` without invoking regenerate."""
    first = {"framing": _LONG, "citations": []}
    def regen(): raise AssertionError("should not regenerate for follow-ups")
    out = g.enforce_qa(first, passages_supplied=8, regenerate=regen,
                        has_history=True)
    assert out is first


def test_has_history_default_false_preserves_existing_behavior():
    """The default (has_history not passed) keeps the pre-existing
    enforce-and-retry semantics — no behavior drift for initial turns."""
    first = {"framing": _LONG, "citations": []}
    retry = {"framing": _LONG, "citations": [{"quote": {"body": "q"}}]}
    calls = {"n": 0}
    def regen():
        calls["n"] += 1
        return retry
    out = g.enforce_qa(first, passages_supplied=8, regenerate=regen)
    assert out is retry and calls["n"] == 1


def test_has_history_with_already_cited_still_no_op():
    """Sanity: when a follow-up DOES emit citations (case-a, more material),
    has_history=True is still a no-op — same result as base path."""
    first = {"framing": _LONG, "citations": [{"quote": {"body": "q"}}]}
    def regen(): raise AssertionError("should not regenerate")
    out = g.enforce_qa(first, passages_supplied=8, regenerate=regen,
                        has_history=True)
    assert out is first
