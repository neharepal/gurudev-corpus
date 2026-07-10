# tools/tests/test_retrieve_rerank_wiring.py
# Verifies _rerank_candidates reorders (idx, text) pairs by the reranker and
# keeps top_k; falls back to input order when the reranker is unavailable.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server

class _FakeRer:
    def __init__(self, avail, scores=None): self._a=avail; self._s=scores
    def available(self): return self._a
    def rerank(self, q, passages): return self._s or []

def test_rerank_reorders_and_truncates():
    cands = [(0, "alpha"), (1, "beta"), (2, "gamma")]
    rer = _FakeRer(True, scores=[0.1, 0.9, 0.5])  # beta best, gamma, alpha
    out = server._rerank_candidates("q", cands, rer, top_k=2)
    assert [i for i, _ in out] == [1, 2]

def test_rerank_unavailable_keeps_input_order():
    cands = [(0, "a"), (1, "b"), (2, "c")]
    rer = _FakeRer(False)
    out = server._rerank_candidates("q", cands, rer, top_k=2)
    assert [i for i, _ in out] == [0, 1]   # first top_k of the input (MMR) order
