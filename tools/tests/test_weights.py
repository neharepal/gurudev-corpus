import numpy as np
import retrieve


def _metas():
    return [
        {"kind": "canonical", "author": "gurudev_ranade"},   # 0: canonical primary
        {"kind": "canonical", "author": "other_authors"},    # 1: canonical other
        {"kind": "biography"},                                # 2: recollections
        {"kind": "reference"},                                # 3: reference
    ]


def test_doctrinal_weights_prefer_canonical_demote_reference():
    scores = np.zeros(4, dtype=np.float32)
    out = retrieve.apply_intent_tier_weights(scores, _metas(), "doctrinal")
    # canonical primary = +0.10 + 0.04 ; canonical other = +0.10 ;
    # recollections = +0.04 ; reference = -0.12
    assert out[0] == np.float32(0.14)
    assert out[1] == np.float32(0.10)
    assert out[2] == np.float32(0.04)
    assert out[3] == np.float32(-0.12)
    # ordering: primary > other > recollections > reference
    assert out[0] > out[1] > out[2] > out[3]


def test_narrative_weights_prefer_recollections():
    scores = np.zeros(4, dtype=np.float32)
    out = retrieve.apply_intent_tier_weights(scores, _metas(), "narrative")
    assert out[2] == np.float32(0.10)          # recollections boosted
    assert out[0] == np.float32(0.04)          # canonical primary: 0 + primary bonus
    assert out[2] > out[0]                     # recollection beats canonical


def test_unknown_intent_used_for_unrecognised_label():
    scores = np.zeros(4, dtype=np.float32)
    out = retrieve.apply_intent_tier_weights(scores, _metas(), "banana")
    # falls back to the "unknown" row: canonical +0.05, recollections 0, reference -0.08
    assert out[1] == np.float32(0.05)
    assert out[3] == np.float32(-0.08)


def test_non_mutating():
    scores = np.zeros(4, dtype=np.float32)
    snapshot = scores.copy()
    retrieve.apply_intent_tier_weights(scores, _metas(), "doctrinal")
    assert np.array_equal(scores, snapshot)
