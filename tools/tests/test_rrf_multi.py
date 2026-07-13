"""Dual-retrieval union: rrf_fuse_multi RRF-fuses several dense rankings + lex.

Replaces the score-level MAX combine of query variants (EN + MR translations),
which let the highest-absolute-cosine variant dominate and diluted cross-lingual
matches. Each dense ranking contributes 1/(k+rank) independently.
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import retrieve


def test_single_dense_equals_rrf_fuse():
    dense = np.array([0.9, 0.5, 0.7, 0.1], dtype=np.float32)
    lex = np.array([0.0, 2.0, 0.0, 1.0], dtype=np.float32)
    a = retrieve.rrf_fuse(dense, lex, k=60)
    b = retrieve.rrf_fuse_multi([dense], lex, k=60)
    assert np.allclose(a, b)


def test_two_rankings_give_symmetric_credit():
    # A ranks 0>1>2>3 ; B ranks 3>2>1>0 (reversed). With RRF over both, chunk 0
    # (rank1 in A, rank4 in B) and chunk 3 (rank4 in A, rank1 in B) score EQUAL,
    # and both beat the middling chunks 1,2. A MAX-combine would instead be driven
    # by absolute cosine magnitudes.
    A = np.array([0.90, 0.80, 0.70, 0.10], dtype=np.float32)
    B = np.array([0.10, 0.20, 0.30, 0.90], dtype=np.float32)
    lex = np.zeros(4, dtype=np.float32)
    f = retrieve.rrf_fuse_multi([A, B], lex, k=60)
    assert np.isclose(f[0], f[3])          # symmetric
    assert np.isclose(f[1], f[2])
    assert f[0] > f[1]                       # rank-1-in-one beats always-middling


def test_marathi_only_hit_survives_the_fusion():
    # The dilution case: chunk 3 is rank-1 for the MR query but has LOW absolute
    # cosine, while chunks 0-2 have high EN cosine. Under MAX+single-RRF chunk 3
    # would be buried; under multi-RRF its MR rank-1 gives it a strong contribution.
    en = np.array([0.60, 0.58, 0.56, 0.20], dtype=np.float32)   # chunk3 last
    mr = np.array([0.30, 0.28, 0.26, 0.45], dtype=np.float32)   # chunk3 FIRST
    lex = np.zeros(4, dtype=np.float32)
    multi = retrieve.rrf_fuse_multi([en, mr], lex, k=60)
    # chunk 3 (mr rank1, en rank4) should outrank chunk 2 (en rank3, mr rank3)
    assert multi[3] > multi[2]
