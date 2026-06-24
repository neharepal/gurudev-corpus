#!/usr/bin/env python3
"""
Retrieval probe — query the corpus and see what comes back.

Usage:
    python3 tools/retrieve.py "What are Gurudev's views on Bhakti?"
    python3 tools/retrieve.py --top-k 5 "श्री गुरुदेव नामसाधनेविषयी काय सांगतात?"
    python3 tools/retrieve.py --no-rerank "..."

The first measurable proof that the RAG pipeline works.

Loads BGE-M3 once, embeds the query, retrieves top-K by cosine similarity,
applies MMR diversity rerank + per-source cap (per RFC-003 §Deduplication layers),
prints results with metadata + text preview.

Per ADR-008: no story aggregation; dedup is at retrieval+generation time.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
EMB_PATH = REPO / "04_processed" / "embeddings" / "embeddings.npy"
META_PATH = REPO / "04_processed" / "embeddings" / "chunks_meta.jsonl"
MANIFEST_PATH = REPO / "04_processed" / "embeddings" / "manifest.json"

DEFAULT_TOP_K = 8
INITIAL_CANDIDATES = 30   # pull more for MMR + per-source cap to whittle down
MMR_LAMBDA = 0.7           # 1.0 = pure relevance, 0.0 = pure diversity
MAX_PER_SOURCE = 2         # at most N chunks per source_work_id in final result

# Primary-source boost. The cosine score for a chunk authored by a lineage
# master and classified as canonical gets this much added before MMR rerank.
# Compensates for two known disadvantages of primary material vs. secondary:
#   1. Marathi primary texts lose cross-language cosine against English queries
#      (English queries score higher against English secondary sources like
#      ACPR souvenirs that contain English excerpts of the same letters).
#   2. OCR'd Marathi from Wikimedia scans has spacing artifacts on conjunct
#      consonants that pull embeddings slightly off-target.
# Tuned so that primary material reliably enters the candidate pool even when
# a strong-matching English secondary source exists, without dominating when
# the primary content is genuinely unrelated.
PRIMARY_TIER_BOOST = 0.07

# Lineage-master author folders. Their canonical writing is the "primary" tier
# for source-preference rules in the prompt and the retrieval boost above.
PRIMARY_AUTHORS = frozenset({
    "gurudev_ranade",
    "bhausaheb_maharaj",
    "nimbargi_maharaj",
    "kakasaheb_tulpule",
    "amburao_maharaj",
})


def chunk_tier(meta: dict) -> str:
    """Authority tier of a chunk for intent-aware ranking (RFC-011).

    canonical     -> the masters' / canonical authors' own works (01_canonical)
    recollections -> athvani + biography (souvenirs, memoirs; 00_raw, 02_aggregated)
    reference     -> bibliographies / indexes (03_catalog)
    Anything unrecognised defaults to recollections (never over-promoted).
    """
    kind = meta.get("kind")
    if kind == "canonical":
        return "canonical"
    if kind == "reference":
        return "reference"
    return "recollections"


def apply_primary_tier_boost(
    scores: np.ndarray,
    metas: list[dict],
    *,
    boost: float = PRIMARY_TIER_BOOST,
) -> np.ndarray:
    """Add `boost` to scores for primary-tier canonical chunks; return a new array.

    Idempotent and non-mutating. Call AFTER computing raw cosine scores and
    BEFORE rerank. Logs nothing — callers can compare returned vs input arrays
    if they want to instrument.
    """
    if boost <= 0:
        return scores
    boosted = scores.copy()
    for i, m in enumerate(metas):
        if (
            m.get("kind") == "canonical"
            and m.get("author") in PRIMARY_AUTHORS
        ):
            boosted[i] += boost
    return boosted


def load_corpus() -> tuple[np.ndarray, list[dict], dict]:
    """Load embeddings + per-chunk metadata + manifest."""
    if not EMB_PATH.exists():
        print(f"ERROR: embeddings not built yet. Run tools/embedder.py first.", file=sys.stderr)
        print(f"       Expected at {EMB_PATH.relative_to(REPO)}", file=sys.stderr)
        sys.exit(2)
    embeddings = np.load(EMB_PATH)
    metas: list[dict] = []
    with META_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                metas.append(json.loads(line))
    manifest = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}
    if embeddings.shape[0] != len(metas):
        print(
            f"WARNING: embeddings ({embeddings.shape[0]}) and metadata ({len(metas)}) misaligned",
            file=sys.stderr,
        )
    return embeddings, metas, manifest


def embed_query(query: str, model_name: str) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    # e5 models need the "query:" instructional prefix to match how passages were
    # embedded (prefixed with "passage:"). Mismatch tanks retrieval. See ADR-009.
    if "e5" in model_name.lower():
        query = "query: " + query
    model = SentenceTransformer(model_name, trust_remote_code=True)
    vec = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)
    return vec[0].astype(np.float32)


def mmr_rerank(
    query_vec: np.ndarray,
    candidate_indices: np.ndarray,
    candidate_scores: np.ndarray,
    embeddings: np.ndarray,
    metas: list[dict],
    *,
    top_k: int,
    mmr_lambda: float,
    max_per_source: int,
) -> list[tuple[int, float]]:
    """Greedy MMR selection with per-source cap.

    Returns ordered [(chunk_index, mmr_score), ...] of length up to top_k.
    """
    selected: list[int] = []
    selected_scores: list[float] = []
    per_source: dict[str, int] = {}
    candidate_set = list(zip(candidate_indices.tolist(), candidate_scores.tolist()))

    while candidate_set and len(selected) < top_k:
        best_idx = -1
        best_score = -1e9
        for idx, sim in candidate_set:
            meta = metas[idx]
            src = meta.get("work_id") or meta.get("source_path") or ""
            if per_source.get(src, 0) >= max_per_source:
                continue
            # diversity penalty: max similarity to any already-selected chunk
            if selected:
                max_div = float(
                    np.max(embeddings[selected] @ embeddings[idx])
                )
            else:
                max_div = 0.0
            mmr = mmr_lambda * sim - (1.0 - mmr_lambda) * max_div
            if mmr > best_score:
                best_score = mmr
                best_idx = idx
        if best_idx < 0:
            break
        selected.append(best_idx)
        selected_scores.append(best_score)
        meta = metas[best_idx]
        src = meta.get("work_id") or meta.get("source_path") or ""
        per_source[src] = per_source.get(src, 0) + 1
        candidate_set = [(i, s) for i, s in candidate_set if i != best_idx]

    return list(zip(selected, selected_scores))


def format_chunk(meta: dict, score: float, mmr_score: float, text: str | None = None) -> str:
    kind = meta.get("kind", "?")
    author = meta.get("author") or meta.get("about_member") or "?"
    work = meta.get("title") or meta.get("work_id", "?")
    lang = meta.get("language", "?")
    src_path = meta.get("source_path", "")
    narrator = meta.get("narrator", "")
    src_work = meta.get("source_work", "")
    chunk_idx = meta.get("chunk_index", "?")
    chunk_tot = meta.get("chunk_total", "?")

    header = f"  [{kind} · {lang}] {work}"
    if narrator:
        header += f" — narrator: {narrator}"
    if src_work and src_work != work:
        header += f" (from {src_work})"
    header += f"  ·  chunk {chunk_idx}/{chunk_tot}"

    return (
        f"{header}\n"
        f"    score: cos={score:.4f}  mmr={mmr_score:.4f}\n"
        f"    by: {author}\n"
        f"    path: {src_path}"
    )


def load_chunk_text(meta: dict, chunk_index_in_corpus: int) -> str:
    """Re-read the chunk's text from chunks.jsonl by line index. (Chunks live in
    parallel with embeddings — same row index.)"""
    chunks_path = REPO / "04_processed" / "chunks.jsonl"
    if not chunks_path.exists():
        return ""
    with chunks_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == chunk_index_in_corpus:
                obj = json.loads(line)
                return obj.get("text", "")
    return ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("query", help="The question or query string")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Final result count after rerank")
    p.add_argument("--candidates", type=int, default=INITIAL_CANDIDATES, help="Initial pool size before rerank")
    p.add_argument("--mmr-lambda", type=float, default=MMR_LAMBDA, help="MMR balance (1.0=relevance, 0.0=diversity)")
    p.add_argument("--max-per-source", type=int, default=MAX_PER_SOURCE, help="Cap chunks per source_work_id")
    p.add_argument("--no-rerank", action="store_true", help="Skip MMR + source cap (raw top-K)")
    p.add_argument("--show-text", action="store_true", help="Print first ~400 chars of each chunk")
    args = p.parse_args()

    print(f"\nQuery: {args.query!r}\n", file=sys.stderr)

    t0 = time.time()
    embeddings, metas, manifest = load_corpus()
    print(f"  loaded {embeddings.shape[0]:,} embeddings ({embeddings.shape[1]}-dim) in {time.time() - t0:.2f}s", file=sys.stderr)

    model_name = manifest.get("model", "BAAI/bge-m3")
    print(f"  embedding query with {model_name}...", file=sys.stderr)
    t0 = time.time()
    qvec = embed_query(args.query, model_name)
    print(f"  query embedded in {time.time() - t0:.1f}s\n", file=sys.stderr)

    # Cosine similarity (embeddings + query are L2-normalized).
    t0 = time.time()
    scores = embeddings @ qvec
    if args.no_rerank:
        order = np.argsort(-scores)[: args.top_k]
        results = [(int(i), float(scores[i])) for i in order]
        ranked = [(idx, scores[idx], scores[idx]) for idx, _ in results]
    else:
        # Top-N candidates by raw cosine, then MMR + per-source cap.
        cand_n = min(args.candidates, len(scores))
        cand_idx = np.argpartition(-scores, cand_n - 1)[:cand_n]
        cand_idx = cand_idx[np.argsort(-scores[cand_idx])]
        cand_scores = scores[cand_idx]
        reranked = mmr_rerank(
            qvec, cand_idx, cand_scores, embeddings, metas,
            top_k=args.top_k,
            mmr_lambda=args.mmr_lambda,
            max_per_source=args.max_per_source,
        )
        ranked = [(idx, float(scores[idx]), float(mmr)) for idx, mmr in reranked]
    print(f"  retrieval+rerank in {time.time() - t0:.3f}s\n", file=sys.stderr)

    print("=" * 72)
    for rank, (idx, sim, mmr) in enumerate(ranked, 1):
        meta = metas[idx]
        print(f"#{rank}")
        print(format_chunk(meta, sim, mmr))
        if args.show_text:
            text = load_chunk_text(meta, idx)
            preview = text[:400].replace("\n", " ")
            print(f"    text:  {preview}{'...' if len(text) > 400 else ''}")
        print()
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
