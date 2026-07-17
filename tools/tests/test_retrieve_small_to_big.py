"""RFC-017 Task 6 wiring: `_retrieve` under `ENABLE_SMALL_TO_BIG=1` returns
one row per distinct parent (context for the answer model) with the top-matched
child's `cite_text` on the meta (the precise anchor for splice). Off-flag path
is unchanged.

The test exercises a small helper (`small_to_big_results`) directly, then does
one integration check on `_retrieve` with the flag ON — heavier retrieval
plumbing (BM25/MMR/reranker) is monkeypatched so the assertion is about the
small-to-big transformation, not the ranker.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

def test_small_to_big_results_groups_children_into_parent_context():
    metas = [
        {"id": "w--en--0000--000", "parent_id": "w--en--0000", "kind_level": "child",
         "cite_text": "buried sentence.", "work_id": "w", "title": "W",
         "kind": "canonical", "language": "en"},
        {"id": "w--en--0000--005", "parent_id": "w--en--0000", "kind_level": "child",
         "cite_text": "another child.", "work_id": "w", "title": "W",
         "kind": "canonical", "language": "en"},
        {"id": "w--en--0001--002", "parent_id": "w--en--0001", "kind_level": "child",
         "cite_text": "d-child.", "work_id": "w", "title": "W",
         "kind": "canonical", "language": "en"},
    ]
    parents = {
        "w--en--0000": {"id": "w--en--0000", "text": "PARENT-0 TEXT",
                        "work_id": "w", "title": "W", "kind": "canonical",
                        "source_path": "01_canonical/w/en/text.md",
                        "language": "en"},
        "w--en--0001": {"id": "w--en--0001", "text": "PARENT-1 TEXT",
                        "work_id": "w", "title": "W", "kind": "canonical",
                        "source_path": "01_canonical/w/en/text.md",
                        "language": "en"},
    }
    reranked = [(0, 0.9), (1, 0.85), (2, 0.6)]
    dense = np.array([0.55, 0.50, 0.42], dtype=np.float32)

    out = server.small_to_big_results(
        reranked, metas, keep_idx=None, parents_by_id=parents,
        dense_scores=dense, max_per_parent=2, top_k=8,
    )

    assert [o["meta"]["parent_id"] for o in out] == ["w--en--0000", "w--en--0001"]
    assert out[0]["text"] == "PARENT-0 TEXT"
    assert out[0]["meta"].get("cite_text") == "buried sentence."
    # Parent's source_path is what splice / readPage anchor on.
    assert out[0]["meta"].get("source_path") == "01_canonical/w/en/text.md"
    assert out[0]["cos_score"] == pytest.approx(0.55, rel=1e-5)


def test_small_to_big_retrieval_only_child_marks_meta_uncitable():
    """An arthasahit child without cite_text (uncertain verse/meaning split)
    still contributes parent context but is marked so splice drops the
    citation — never risk quoting the sadhak's meaning as Gurudev's words."""
    metas = [{"id": "tukaram-vachanamrut--mr--0000--000",
              "parent_id": "tukaram-vachanamrut--mr--0000",
              "kind_level": "child", "work_id": "tukaram-vachanamrut",
              "title": "Tukaram Vachanamrut", "kind": "canonical",
              "language": "mr"}]
    parents = {"tukaram-vachanamrut--mr--0000": {
        "id": "tukaram-vachanamrut--mr--0000",
        "text": "verse and meaning here",
        "work_id": "tukaram-vachanamrut", "title": "Tukaram Vachanamrut",
        "kind": "canonical",
        "source_path": "01_canonical/tukaram_vachanamrut/mr/text.md",
        "language": "mr"}}

    out = server.small_to_big_results(
        [(0, 0.9)], metas, keep_idx=None, parents_by_id=parents,
        dense_scores=np.array([0.5], dtype=np.float32),
        max_per_parent=2, top_k=8,
    )
    assert len(out) == 1
    assert "cite_text" not in out[0]["meta"]
    assert out[0]["meta"].get("retrieval_only") is True


def test_small_to_big_arthasahit_child_sets_restrict_to_cite():
    """An arthasahit child WITH cite_text must be marked `restrict_to_cite=True`
    so splice reads from cite_text (verse only), never the parent that also
    contains the meaning."""
    metas = [{"id": "tukaram-vachanamrut--mr--0000--001",
              "parent_id": "tukaram-vachanamrut--mr--0000",
              "kind_level": "child", "work_id": "tukaram-vachanamrut",
              "title": "Tukaram Vachanamrut", "kind": "canonical",
              "language": "mr", "cite_text": "करीं धंदा परि आवडती पाय"}]
    parents = {"tukaram-vachanamrut--mr--0000": {
        "id": "tukaram-vachanamrut--mr--0000",
        "text": "करीं धंदा परि आवडती पाय\nअर्थ - सादाकाचा गूढ अर्थ.",
        "work_id": "tukaram-vachanamrut", "title": "Tukaram Vachanamrut",
        "kind": "canonical",
        "source_path": "01_canonical/tukaram_vachanamrut/mr/text.md",
        "language": "mr"}}
    out = server.small_to_big_results(
        [(0, 0.9)], metas, keep_idx=None, parents_by_id=parents,
        dense_scores=np.array([0.5], dtype=np.float32),
        max_per_parent=2, top_k=8,
    )
    assert out[0]["meta"].get("cite_text") == "करीं धंदा परि आवडती पाय"
    assert out[0]["meta"].get("restrict_to_cite") is True


def test_small_to_big_prose_does_not_set_restrict_to_cite():
    """Non-arthasahit (prose) small-to-big rows keep `cite_text` for reference
    but must NOT set `restrict_to_cite` — splice defaults to the parent so the
    LLM can quote 2–4 sentences of context, not just the child's one anchor."""
    metas = [{"id": "charitra-tatvajnan-tulpule--mr--0088--008",
              "parent_id": "charitra-tatvajnan-tulpule--mr--0088",
              "kind_level": "child",
              "work_id": "charitra-tatvajnan-tulpule",
              "title": "Charitra", "kind": "canonical", "language": "mr",
              "cite_text": "शेजारच्या घरावर वीज पडल्याचें ऐकून"}]
    parents = {"charitra-tatvajnan-tulpule--mr--0088": {
        "id": "charitra-tatvajnan-tulpule--mr--0088",
        "text": "PARENT with several sentences of context around the lightning.",
        "work_id": "charitra-tatvajnan-tulpule", "title": "Charitra",
        "kind": "canonical",
        "source_path": "01_canonical/charitra/mr/text.md", "language": "mr"}}
    out = server.small_to_big_results(
        [(0, 0.9)], metas, keep_idx=None, parents_by_id=parents,
        dense_scores=np.array([0.5], dtype=np.float32),
        max_per_parent=2, top_k=8,
    )
    assert out[0]["meta"].get("restrict_to_cite") is not True
    assert out[0]["meta"].get("retrieval_only") is not True


def test_small_to_big_uses_keep_idx_for_metadata_filter():
    """When _retrieve applied a metadata_filter, sub_metas indices map through
    keep_idx to absolute indices — dense_scores is indexed on sub_metas."""
    sub_metas = [
        {"id": "w--en--0002--000", "parent_id": "w--en--0002", "kind_level": "child",
         "cite_text": "sub-c.", "work_id": "w", "title": "W",
         "kind": "canonical", "language": "en"},
    ]
    parents = {"w--en--0002": {"id": "w--en--0002", "text": "PARENT-2 TEXT",
                                "work_id": "w", "title": "W", "kind": "canonical",
                                "source_path": "01_canonical/w/en/text.md",
                                "language": "en"}}
    keep_idx = np.array([17], dtype=np.int64)  # arbitrary absolute idx
    out = server.small_to_big_results(
        [(0, 0.7)], sub_metas, keep_idx=keep_idx, parents_by_id=parents,
        dense_scores=np.array([0.6], dtype=np.float32),
        max_per_parent=2, top_k=8,
    )
    assert out and out[0]["meta"]["parent_id"] == "w--en--0002"


# ---------------------------------------------------------------------------
# Integration test: _retrieve under the flag returns parent-context rows
# ---------------------------------------------------------------------------

class _StubModel:
    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True):
        # Return a simple query vector; the actual dense scores come from the
        # stubbed embeddings @ vec — but we monkeypatch the ranking below so
        # the exact query vector doesn't matter beyond dtype/shape.
        return np.array([[1.0, 0.0]], dtype=np.float32)


def test_retrieve_flag_gated_small_to_big_returns_parent_groups(monkeypatch):
    metas = [
        {"id": "w--en--0000--000", "parent_id": "w--en--0000", "kind_level": "child",
         "cite_text": "the lightning-struck-house sentence.",
         "work_id": "w", "title": "W", "kind": "canonical", "language": "en",
         "source_path": "01_canonical/w/en/text.md"},
        {"id": "w--en--0000--005", "parent_id": "w--en--0000", "kind_level": "child",
         "cite_text": "sibling child.",
         "work_id": "w", "title": "W", "kind": "canonical", "language": "en",
         "source_path": "01_canonical/w/en/text.md"},
        {"id": "w--en--0001--002", "parent_id": "w--en--0001", "kind_level": "child",
         "cite_text": "distant child.",
         "work_id": "w2", "title": "W2", "kind": "canonical", "language": "en",
         "source_path": "01_canonical/w2/en/text.md"},
    ]
    parents = {
        "w--en--0000": {"id": "w--en--0000", "text": "PARENT-0 with the buried sentence.",
                         "work_id": "w", "title": "W", "kind": "canonical",
                         "source_path": "01_canonical/w/en/text.md", "language": "en"},
        "w--en--0001": {"id": "w--en--0001", "text": "PARENT-1 elsewhere.",
                         "work_id": "w2", "title": "W2", "kind": "canonical",
                         "source_path": "01_canonical/w2/en/text.md", "language": "en"},
    }
    embeddings = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]], dtype=np.float32)

    server.STATE.embeddings = embeddings
    server.STATE.metas = metas
    server.STATE.parents_by_id = parents
    server.STATE.model = _StubModel()
    server.STATE.model_name = "stub"

    monkeypatch.setattr(server.query_translation, "translate_query", lambda q: "")
    monkeypatch.setattr(server.query_translation, "translate_to_english", lambda q: "")
    monkeypatch.setattr(server.intent, "classify_intent", lambda q: "doctrinal")
    monkeypatch.setattr(server.retrieve, "apply_intent_tier_weights",
                        lambda scores, metas, intent: scores)
    monkeypatch.setattr(server.retrieve, "fused_candidate_scores",
                        lambda q, dense, metas, texts=None, bm25_queries=None,
                        extra_dense=None: dense)
    monkeypatch.setattr(server.retrieve, "apply_quality_weights",
                        lambda fused, metas, enabled: fused)
    # Rank strictly by dense score; keep the top_k.
    def _mmr(qvec, cand_idx, cand_scores, sub_emb, sub_metas,
             *, top_k, mmr_lambda, max_per_source):
        pairs = list(zip(cand_idx.tolist(), cand_scores.tolist()))
        pairs.sort(key=lambda p: -p[1])
        return [(int(i), float(s)) for i, s in pairs[:top_k]]
    monkeypatch.setattr(server.retrieve, "mmr_rerank", _mmr)
    monkeypatch.setattr(server.retrieve, "load_chunk_text",
                        lambda meta, oidx: meta.get("text") or "")
    monkeypatch.setenv("ENABLE_SMALL_TO_BIG", "1")
    monkeypatch.delenv("ENABLE_RERANK", raising=False)
    monkeypatch.delenv("ENABLE_JUNK_WEIGHT", raising=False)

    out = server._retrieve(
        "the lightning incident",
        top_k=8, candidates=10, mmr_lambda=0.7, max_per_source=2,
    )

    parent_ids = [r["meta"]["parent_id"] for r in out]
    assert parent_ids == ["w--en--0000", "w--en--0001"], parent_ids
    assert out[0]["text"] == "PARENT-0 with the buried sentence."
    assert out[0]["meta"].get("cite_text") == "the lightning-struck-house sentence."


def test_retrieve_off_flag_is_unchanged(monkeypatch):
    """Sanity: with ENABLE_SMALL_TO_BIG unset, `_retrieve` returns flat child
    rows (parent_id present on meta but no grouping / cite_text lifting)."""
    metas = [
        {"id": "w--en--0000--000", "parent_id": "w--en--0000", "kind_level": "child",
         "cite_text": "c0", "work_id": "w", "title": "W", "kind": "canonical",
         "language": "en", "source_path": "01_canonical/w/en/text.md",
         "text": "CHILD-0"},
        {"id": "w--en--0000--005", "parent_id": "w--en--0000", "kind_level": "child",
         "cite_text": "c1", "work_id": "w", "title": "W", "kind": "canonical",
         "language": "en", "source_path": "01_canonical/w/en/text.md",
         "text": "CHILD-1"},
    ]
    embeddings = np.array([[1.0, 0.0], [0.9, 0.1]], dtype=np.float32)
    server.STATE.embeddings = embeddings
    server.STATE.metas = metas
    server.STATE.parents_by_id = {}
    server.STATE.model = _StubModel()
    server.STATE.model_name = "stub"

    monkeypatch.setattr(server.query_translation, "translate_query", lambda q: "")
    monkeypatch.setattr(server.query_translation, "translate_to_english", lambda q: "")
    monkeypatch.setattr(server.intent, "classify_intent", lambda q: "doctrinal")
    monkeypatch.setattr(server.retrieve, "apply_intent_tier_weights",
                        lambda scores, metas, intent: scores)
    monkeypatch.setattr(server.retrieve, "fused_candidate_scores",
                        lambda q, dense, metas, texts=None, bm25_queries=None,
                        extra_dense=None: dense)
    monkeypatch.setattr(server.retrieve, "apply_quality_weights",
                        lambda fused, metas, enabled: fused)
    def _mmr(qvec, cand_idx, cand_scores, sub_emb, sub_metas,
             *, top_k, mmr_lambda, max_per_source):
        pairs = sorted(zip(cand_idx.tolist(), cand_scores.tolist()), key=lambda p: -p[1])
        return [(int(i), float(s)) for i, s in pairs[:top_k]]
    monkeypatch.setattr(server.retrieve, "mmr_rerank", _mmr)
    monkeypatch.setattr(server.retrieve, "load_chunk_text",
                        lambda meta, oidx: meta.get("text") or "")
    monkeypatch.delenv("ENABLE_SMALL_TO_BIG", raising=False)

    out = server._retrieve("q", top_k=8, candidates=10, mmr_lambda=0.7, max_per_source=2)
    # Flat: two rows (one per child), no grouping/lifting.
    assert [r["meta"]["id"] for r in out] == ["w--en--0000--000", "w--en--0000--005"]
    assert out[0]["text"] == "CHILD-0"
