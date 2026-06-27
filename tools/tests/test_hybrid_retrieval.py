"""Unit tests for BM25 + RRF hybrid retrieval — corpus-free."""
import numpy as np
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import retrieve


# ─── tokenizer ─────────────────────────────────────────────────────────────

def test_tokenize_basic():
    tokens = retrieve._tokenize_bm25("Bhakti does not consist in love")
    # "Bhakti", "consist", "love" should be present (stopwords like "does","not","in" dropped)
    assert "bhakti" in tokens
    assert "love" in tokens


def test_tokenize_hyphen_expands():
    tokens = retrieve._tokenize_bm25("idol-worship is a practice")
    # hyphenated form AND sub-parts should all appear
    assert "idol" in tokens
    assert "worship" in tokens
    assert "idol-worship" in tokens


def test_tokenize_devanagari_kept():
    tokens = retrieve._tokenize_bm25("भक्ति म्हणजे देवावर प्रेम")
    # Devanagari tokens must survive
    assert any("ऀ" <= ch <= "ॿ" for tok in tokens for ch in tok)


# ─── BM25Index ──────────────────────────────────────────────────────────────

TEXTS = [
    "idol worship is a formal practice of bhakti",   # 0 — has "idol", "worship"
    "bhakti consists in love to god",                # 1 — no "idol"
    "god is everywhere and worship is universal",    # 2 — has "worship" but not "idol"
]


def test_bm25_present_ranks_higher_than_absent():
    idx = retrieve.BM25Index.build(TEXTS)
    scores = idx.score(retrieve._tokenize_bm25("idol worship"))
    # chunk 0 has both terms; chunk 1 has neither "idol" nor "worship" in exact form
    assert scores[0] > scores[1]


def test_bm25_rarer_term_idf_contribution():
    # "idol" appears only in chunk 0 (rare) → should contribute strongly
    texts = [
        "idol worship formal practice",   # 0 — idol appears
        "worship worship worship",        # 1 — worship appears 3× but not idol
        "nothing relevant here at all",   # 2 — neither
    ]
    idx = retrieve.BM25Index.build(texts)
    idol_scores = idx.score(retrieve._tokenize_bm25("idol"))
    # chunk 0 has idol; chunk 1 does not; chunk 2 does not
    assert idol_scores[0] > idol_scores[1]
    assert idol_scores[0] > idol_scores[2]


def test_bm25_hyphenated_query_matches_chunk():
    texts = [
        "idol-worship is condemned by bhakti saints",  # 0 — contains hyphenated form
        "love of god surpasses rituals",               # 1 — no idol
    ]
    idx = retrieve.BM25Index.build(texts)
    scores = idx.score(retrieve._tokenize_bm25("idol-worship"))
    assert scores[0] > scores[1]


def test_bm25_zero_for_no_overlap():
    idx = retrieve.BM25Index.build(TEXTS)
    scores = idx.score(retrieve._tokenize_bm25("xyz_nonexistent_term"))
    assert np.all(scores == 0.0)


# ─── lexical_scores convenience wrapper ─────────────────────────────────────

def test_lexical_scores_returns_array_length_matches_texts():
    texts = ["bhakti and love", "idol worship practice"]
    scores = retrieve.lexical_scores("idol worship", texts)
    assert len(scores) == 2


def test_lexical_scores_empty_query_returns_zeros():
    texts = ["bhakti and love", "idol worship practice"]
    scores = retrieve.lexical_scores("", texts)
    assert np.all(scores == 0.0)


# ─── RRF fusion ─────────────────────────────────────────────────────────────

def _make_dense(n):
    """Dense scores: chunk 0 is best."""
    arr = np.zeros(n, dtype=np.float32)
    for i in range(n):
        arr[i] = 1.0 - i * 0.05
    return arr


def test_rrf_strong_both_ranks_first():
    # chunk 0: dense rank 1, lexical rank 1 → should be #1 after fusion
    # chunk 1: dense rank 2, lexical rank 2 → should be #2
    dense = np.array([0.9, 0.8, 0.7], dtype=np.float32)
    lex   = np.array([5.0, 3.0, 0.0], dtype=np.float32)  # chunk 2 has no lex
    fused = retrieve.rrf_fuse(dense, lex, k=60)
    assert fused[0] > fused[1] > fused[2]


def test_rrf_mid_dense_top_lexical_beats_top_dense_absent_lexical():
    # chunk 0: dense rank 1 (best), no lexical score
    # chunk 1: dense rank 5 (moderate), lexical rank 1 (best)
    n = 10
    dense = np.zeros(n, dtype=np.float32)
    lex   = np.zeros(n, dtype=np.float32)
    for i in range(n):
        dense[i] = 1.0 - i * 0.05
    # chunk 1 gets strong lexical
    lex[1] = 8.0
    fused = retrieve.rrf_fuse(dense, lex, k=60)
    # chunk 1 (mid dense, top lex) must beat chunk 0 (top dense, zero lex)
    assert fused[1] > fused[0], f"fused[1]={fused[1]:.4f} should beat fused[0]={fused[0]:.4f}"


def test_rrf_empty_lexical_preserves_dense_order():
    """With no lexical signal, RRF should maintain dense ranking order."""
    dense = np.array([0.9, 0.8, 0.7, 0.6], dtype=np.float32)
    lex   = np.zeros(4, dtype=np.float32)
    fused = retrieve.rrf_fuse(dense, lex, k=60)
    # dense order = 0 > 1 > 2 > 3 → fused order must be the same
    assert fused[0] > fused[1] > fused[2] > fused[3]
