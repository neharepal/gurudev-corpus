import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import reranker as rr

def test_rerank_orders_by_injected_scorer():
    # Inject a fake cross-encoder so the test needs no model download.
    r = rr.Reranker(scorer=lambda pairs: [len(p[1]) for p in pairs])
    scores = r.rerank("q", ["short", "a much longer passage"])
    assert scores[1] > scores[0]
    assert r.available() is True

def test_rerank_empty_passages():
    r = rr.Reranker(scorer=lambda pairs: [1.0 for _ in pairs])
    assert r.rerank("q", []) == []

def test_unavailable_when_load_fails():
    def boom():
        raise RuntimeError("no model")
    r = rr.Reranker(loader=boom)
    assert r.available() is False
    assert r.rerank("q", ["a", "b"]) == []   # fail-safe: empty -> caller falls back

def test_rerank_returns_empty_when_scorer_raises():
    def boom(pairs):
        raise RuntimeError("scoring failed")
    r = rr.Reranker(scorer=boom)
    assert r.rerank("q", ["a", "b"]) == []
    assert r.available() is True   # available, but scoring failed -> [] (caller falls back)

def test_get_reranker_is_singleton():
    assert rr.get_reranker() is rr.get_reranker()
