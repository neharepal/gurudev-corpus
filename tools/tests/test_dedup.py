import numpy as np
import retrieve


def test_near_duplicate_of_selected_chunk_is_skipped():
    # 3 unit vectors: 0 and 1 are near-identical (the souvenir reprint case),
    # 2 is distinct. With max_per_source high, MMR would otherwise take 0 and 1.
    embeddings = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.999, 0.0447, 0.0],   # ~0.999 cosine with vec 0
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    # normalise rows
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    metas = [
        {"work_id": "canonical-gita"},
        {"work_id": "acpr-souvenir"},
        {"work_id": "other"},
    ]
    qvec = embeddings[0]
    cand_idx = np.array([0, 1, 2])
    cand_scores = embeddings @ qvec  # 0 highest, 1 ~equal, 2 low

    out = retrieve.mmr_rerank(
        qvec, cand_idx, cand_scores, embeddings, metas,
        top_k=3, mmr_lambda=0.7, max_per_source=5, dup_threshold=0.92,
    )
    selected = [i for i, _ in out]
    assert 0 in selected           # the canonical original is kept
    assert 1 not in selected       # its near-duplicate reprint is dropped
    assert 2 in selected           # the distinct chunk survives


def test_dup_threshold_one_keeps_everything():
    embeddings = np.eye(3, dtype=np.float32)
    metas = [{"work_id": f"w{i}"} for i in range(3)]
    qvec = embeddings[0]
    cand_idx = np.array([0, 1, 2])
    cand_scores = embeddings @ qvec
    out = retrieve.mmr_rerank(
        qvec, cand_idx, cand_scores, embeddings, metas,
        top_k=3, mmr_lambda=0.7, max_per_source=5, dup_threshold=1.0,
    )
    assert len(out) == 3
