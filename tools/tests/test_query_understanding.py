import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import query_understanding as qu

def test_rewrite_uses_injected_and_strips():
    out = qu.rewrite_query("कारलाईल कॉटेज", rewriter=lambda q: "  कारलाईल कॉटेज कुठे बांधली?  ")
    assert out == "कारलाईल कॉटेज कुठे बांधली?"

def test_rewrite_none_on_echo_or_empty():
    assert qu.rewrite_query("x", rewriter=lambda q: "x") is None
    assert qu.rewrite_query("x", rewriter=lambda q: "") is None

def test_rewrite_none_when_llm_disabled():
    assert qu.rewrite_query("anything", use_llm=False) is None

def test_hyde_uses_injected():
    out = qu.hypothetical_doc("bhakti", generator=lambda q: "Bhakti is devotion to God, love of man.")
    assert "devotion" in out

def test_hyde_failsafe_on_exception():
    def boom(q): raise RuntimeError("down")
    assert qu.hypothetical_doc("q", generator=boom) is None
