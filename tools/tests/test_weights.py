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


def test_narrative_weights_boost_recollections_but_floor_canonical():
    # Narrative still lifts recollections for true stories/anecdotes, BUT a
    # canonical floor (canonical +0.05) stops Gurudev's own works from being
    # ranked BELOW souvenirs on philosophical questions that classify narrative
    # ("How did Gurudev attain God-realization?"). With the primary-author bonus:
    #   canonical primary = 0.05 + 0.04 = 0.09  (Gurudev's own works LEAD)
    #   recollections     = 0.08                (still beat non-primary canonical)
    #   canonical other   = 0.05
    #   reference         = -0.08
    scores = np.zeros(4, dtype=np.float32)
    out = retrieve.apply_intent_tier_weights(scores, _metas(), "narrative")
    assert out[2] == np.float32(0.08)          # recollections boosted
    assert out[0] == np.float32(0.09)          # canonical primary: 0.05 + bonus
    assert out[1] == np.float32(0.05)          # canonical other: floor
    assert out[3] == np.float32(-0.08)         # reference demoted
    assert out[0] > out[2] > out[1]            # Gurudev's own > recollections > other canonical


def test_unknown_intent_used_for_unrecognised_label():
    scores = np.zeros(4, dtype=np.float32)
    out = retrieve.apply_intent_tier_weights(scores, _metas(), "banana")
    # falls back to the "unknown" row. RFC-011 retuning (retrieve.py
    # TIER_WEIGHTS comment) replaced the old {canonical:+0.05, recollections:0}
    # prior — which silently demoted biography/athvani on ambiguous queries —
    # with an equal small nudge for both content tiers: canonical +0.02,
    # recollections +0.02, reference -0.08. Validated on eval_retrieval.py
    # gold set (10->11 PASS, zero doctrinal regressions).
    assert out[1] == np.float32(0.02)
    assert out[3] == np.float32(-0.08)


def test_non_mutating():
    scores = np.zeros(4, dtype=np.float32)
    snapshot = scores.copy()
    retrieve.apply_intent_tier_weights(scores, _metas(), "doctrinal")
    assert np.array_equal(scores, snapshot)
