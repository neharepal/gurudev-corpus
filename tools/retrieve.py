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
INITIAL_CANDIDATES = 100  # pull more for MMR + per-source cap to whittle down
MMR_LAMBDA = 0.7           # 1.0 = pure relevance, 0.0 = pure diversity
MAX_PER_SOURCE = 2         # at most N chunks per source_work_id in final result

# Lineage-master author folders. Their canonical writing is the "primary" tier
# for source-preference rules in the prompt and the retrieval boost above.
PRIMARY_AUTHORS = frozenset({
    "gurudev_ranade",
    "bhausaheb_maharaj",
    "nimbargi_maharaj",
    "kakasaheb_tulpule",
    "amburao_maharaj",
})


# ---------------------------------------------------------------------------
# Lexical (BM25) scoring — no external dependencies
# ---------------------------------------------------------------------------

import math
import re as _re

# Small English + Marathi stopword set for BM25 tokenisation.
# Keeps the index lean without over-pruning (proper nouns like "Bhakti" survive).
_STOPWORDS: frozenset = frozenset({
    # English function words
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "of",
    "for", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "not",
    "that", "this", "it", "its", "he", "she", "they", "we", "you", "i",
    "his", "her", "their", "our", "your", "my", "what", "which", "who",
    "whom", "when", "where", "why", "how", "all", "each", "every", "both",
    "more", "than", "so", "if", "no", "nor", "yet", "still", "such",
    "about", "also", "just", "there", "then", "now", "will", "would",
    "could", "should", "may", "might", "must", "can",
    # Marathi common function words (transliterated common stop forms)
    "आणि", "किंवा", "पण", "तर", "हे", "हा", "ही", "त्या", "त्यांचे",
    "मध्ये", "वर", "च", "ला", "ने", "से", "को",
})


def _tokenize_bm25(text: str) -> list:
    """Tokenize `text` for BM25.

    - Lowercases the entire string
    - Splits on whitespace to get raw tokens
    - For each hyphenated token "a-b", also emits "a" and "b" individually
    - Drops single-character tokens and EN/MR stopwords
    - Devanagari tokens are kept as-is (after lowercasing has no effect on them)
    """
    lowered = text.lower()
    raw_tokens = _re.split(r"[\s]+", lowered)
    result: list = []
    for raw in raw_tokens:
        # Strip leading/trailing punctuation except hyphens within words
        tok = raw.strip(".,;:!?\"'()[]{}…")
        if not tok:
            continue
        # If the token contains a hyphen, emit the full form AND sub-parts
        if "-" in tok:
            result.append(tok)
            parts = tok.split("-")
            for p in parts:
                p = p.strip()
                if p and len(p) > 1 and p not in _STOPWORDS:
                    result.append(p)
        else:
            if len(tok) > 1 and tok not in _STOPWORDS:
                result.append(tok)
    return result


class BM25Index:
    """In-memory BM25 index over a fixed list of texts.

    Build once with BM25Index.build(texts), then call .score(query_tokens)
    as many times as needed.  Thread-safe for reads after construction.

    BM25 parameters: k1=1.5, b=0.75 (standard defaults).
    """

    K1: float = 1.5
    B: float = 0.75

    def __init__(
        self,
        n_docs: int,
        avgdl: float,
        df: dict,           # term -> document frequency (int)
        postings: dict,     # term -> list of (doc_id, tf)
        doc_lengths: list,  # list[int] — token count per doc
    ) -> None:
        self._n = n_docs
        self._avgdl = avgdl
        self._df = df
        self._postings = postings
        self._doc_lengths = doc_lengths  # list of ints, index == doc_id

    @classmethod
    def build(cls, texts: list) -> "BM25Index":
        """Build the index from a list of text strings.

        Each element of `texts` corresponds to a chunk at the same position
        in the embeddings array.  Tokenisation uses _tokenize_bm25.
        """
        import time as _time
        t0 = _time.time()
        n = len(texts)
        df: dict = {}
        postings: dict = {}
        doc_lengths: list = []

        for doc_id, text in enumerate(texts):
            toks = _tokenize_bm25(text)
            doc_lengths.append(len(toks))
            tf_local: dict = {}
            for tok in toks:
                tf_local[tok] = tf_local.get(tok, 0) + 1
            for tok, tf in tf_local.items():
                df[tok] = df.get(tok, 0) + 1
                if tok not in postings:
                    postings[tok] = []
                postings[tok].append((doc_id, tf))

        avgdl = float(sum(doc_lengths) / n) if n > 0 else 1.0
        elapsed = _time.time() - t0
        print(
            f"[BM25] index built: {n} docs, {len(df)} terms, avgdl={avgdl:.1f}, "
            f"time={elapsed:.2f}s",
            file=sys.stderr,
        )
        return cls(n_docs=n, avgdl=avgdl, df=df, postings=postings,
                   doc_lengths=doc_lengths)

    def score(self, query_tokens: list) -> np.ndarray:
        """Return a BM25 score array of length n_docs.

        Chunks with no query-term overlap score exactly 0.0.
        """
        out = np.zeros(self._n, dtype=np.float32)
        if not query_tokens or self._n == 0:
            return out

        seen: set = set()
        for tok in query_tokens:
            if tok in seen or tok not in self._postings:
                seen.add(tok)
                continue
            seen.add(tok)
            df_t = self._df[tok]
            idf = math.log((self._n - df_t + 0.5) / (df_t + 0.5) + 1.0)
            for doc_id, tf in self._postings[tok]:
                dl = self._doc_lengths[doc_id]
                tf_norm = (tf * (self.K1 + 1)) / (
                    tf + self.K1 * (1.0 - self.B + self.B * (dl / max(self._avgdl, 1.0)))
                )
                out[doc_id] += idf * tf_norm
        return out


def lexical_scores(query: str, texts: list) -> np.ndarray:
    """Build a one-shot BM25 index from `texts` and return scores for `query`.

    For the production path, the index is built lazily and cached by the caller.
    This function is exposed for unit tests that pass synthetic texts directly.

    Returns a float32 array of length len(texts).  All-zero when query is empty
    or has no token overlap with any text.
    """
    if not texts:
        return np.zeros(0, dtype=np.float32)
    qtoks = _tokenize_bm25(query)
    if not qtoks:
        return np.zeros(len(texts), dtype=np.float32)
    idx = BM25Index.build(texts)
    return idx.score(qtoks)


def rrf_fuse(
    dense_scores: np.ndarray,
    lex_scores: np.ndarray,
    *,
    k: int = 60,
) -> np.ndarray:
    """Reciprocal Rank Fusion of dense + lexical scores.

    fused[i] = 1/(k + dense_rank[i]) + 1/(k + lex_rank[i])

    - dense_rank[i] is the 1-based rank of chunk i by dense score (rank 1 = highest).
    - lex_rank[i]   is the 1-based rank of chunk i by lex score, but ONLY for
      chunks with lex_score > 0.  Chunks with lex_score == 0 receive no lexical
      contribution (effectively lex component = 0).

    When all lex_scores are zero (pure-concept query), the lexical term vanishes
    and fused order == dense order — existing behaviour is fully preserved.
    """
    n = len(dense_scores)
    fused = np.zeros(n, dtype=np.float64)

    # Dense rank component (all chunks participate)
    dense_order = np.argsort(-dense_scores)  # highest first
    dense_rank = np.empty(n, dtype=np.int64)
    dense_rank[dense_order] = np.arange(1, n + 1)
    fused += 1.0 / (k + dense_rank)

    # Lexical rank component (only chunks with lex_score > 0)
    lex_mask = lex_scores > 0
    if lex_mask.any():
        lex_nonzero_idx = np.where(lex_mask)[0]
        lex_order = lex_nonzero_idx[np.argsort(-lex_scores[lex_nonzero_idx])]
        for rank_1based, chunk_idx in enumerate(lex_order, 1):
            fused[chunk_idx] += 1.0 / (k + rank_1based)

    return fused.astype(np.float32)


# ---------------------------------------------------------------------------
# Corpus-level BM25 cache (lazy, built on first hybrid retrieval call)
# ---------------------------------------------------------------------------

# Cache: id(metas_list) -> BM25Index.  Keyed by object identity because
# server.py holds a single STATE.metas list across requests; chat.py and
# tune_sweep.py rebuild metas each call (different id), so they get a fresh
# index, which is fine (those are one-shot scripts).
_BM25_CACHE: dict = {}


def _load_all_chunk_texts(metas: list) -> list:
    """Read 04_processed/chunks.jsonl once sequentially, returning a text per chunk.

    Each element aligns with metas[i] — the i-th line of chunks.jsonl.
    Returns '' for any missing or malformed line.
    This is O(n) vs the O(n²) repeated-seek of calling load_chunk_text per chunk.
    """
    import json as _json
    chunks_path = REPO / "04_processed" / "chunks.jsonl"
    if not chunks_path.exists():
        return [""] * len(metas)
    texts: list = []
    with chunks_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    texts.append(_json.loads(line).get("text", ""))
                except Exception:
                    texts.append("")
            else:
                texts.append("")
    # Pad if file is shorter than expected
    while len(texts) < len(metas):
        texts.append("")
    return texts


def _get_or_build_bm25_index(
    metas: list,
    *,
    texts: list = None,
) -> "BM25Index":
    """Return a cached BM25Index for `metas`, building it on first call.

    If `texts` is provided (same length as metas), it is used as the document
    corpus.  Otherwise texts are loaded from chunks.jsonl in a single sequential
    pass via _load_all_chunk_texts — O(n), not O(n²).
    """
    cache_key = id(metas)
    if cache_key not in _BM25_CACHE:
        if texts is None:
            texts = _load_all_chunk_texts(metas)
        _BM25_CACHE[cache_key] = BM25Index.build(texts)
    return _BM25_CACHE[cache_key]


def fused_candidate_scores(
    query: str,
    dense_scores: np.ndarray,
    metas: list,
    *,
    texts: list = None,
    rrf_k: int = 60,
    primary_fused_bonus: float = None,  # resolved below; default = PRIMARY_FUSED_BONUS
) -> np.ndarray:
    """Return RRF-fused scores for candidate selection.

    `dense_scores` must already include intent tier-weight adjustments.
    `texts` is optional pre-loaded text list for the BM25 index; if omitted,
    texts are loaded lazily (and cached) from disk.

    The fused score is only used to pick the top-`candidates` pool that feeds
    MMR rerank. MMR still uses the raw dense vectors for diversity scoring.

    After RRF fusion, chunks whose author is in PRIMARY_AUTHORS *and* whose
    tier is "canonical" receive `primary_fused_bonus` so that Gurudev's own
    works are preferred over secondary sources even when the lexical (BM25)
    signal is absent or weaker on the dense side.  The bonus is additive and
    modest (~0.015 vs RRF range 0.01–0.03) so a secondary source with a much
    higher relevance signal can still outrank a primary-author chunk.
    """
    bm25_idx = _get_or_build_bm25_index(metas, texts=texts)
    qtoks = _tokenize_bm25(query)
    lex = bm25_idx.score(qtoks) if qtoks else np.zeros(len(dense_scores), dtype=np.float32)
    fused = rrf_fuse(dense_scores, lex, k=rrf_k)

    # Apply fused-side primary-author / canonical bonus (uniform across call sites).
    # Default resolves after module load to avoid forward-reference in signature.
    if primary_fused_bonus is None:
        primary_fused_bonus = PRIMARY_FUSED_BONUS
    if primary_fused_bonus and metas:
        fused = fused.astype(np.float64)
        for i, m in enumerate(metas):
            if chunk_tier(m) == "canonical" and m.get("author") in PRIMARY_AUTHORS:
                fused[i] += primary_fused_bonus
        fused = fused.astype(np.float32)

    return fused


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


# Intent-aware tier weighting (RFC-011). Deltas are added to cosine BEFORE MMR.
# Magnitudes are starting values; cosine top scores ~0.5-0.7, so these reorder
# near-ties without swamping a genuinely strong match. Tune via tune_sweep.py.
TIER_WEIGHTS: dict[str, dict[str, float]] = {
    "doctrinal":    {"canonical": 0.10, "recollections": 0.04, "reference": -0.12},
    "narrative":    {"canonical": 0.00, "recollections": 0.10, "reference": -0.08},
    "navigational": {"canonical": 0.00, "recollections": 0.00, "reference":  0.08},
    "unknown":      {"canonical": 0.05, "recollections": 0.00, "reference": -0.08},
}
PRIMARY_AUTHOR_BONUS = 0.04   # canonical works by lineage masters (PRIMARY_AUTHORS)
# Fused-side bonus added AFTER RRF fusion so the preference applies uniformly
# across all retrieval paths (dense-only + lexical).  RRF scores sit in the
# range ~0.01–0.033 for a k=60 kernel (max ~1/61 per signal; ~2/61 when both
# dense and lexical fire).  A bonus of 0.003 is roughly 2–3× the gap between
# adjacent ranks at the top (1/61 - 1/62 ≈ 0.00026 per rank-step), enough to
# lift a primary-author chunk over a comparably-ranked secondary in a near-tie,
# while a secondary source that scores strongly on BOTH dense and lexical signals
# will still outrank the primary-author chunk (its raw fused score ≈ 0.033
# easily exceeds primary_fused 0.016 + 0.003 = 0.019 for dense-only primary).
PRIMARY_FUSED_BONUS = 0.003   # added to RRF fused score for canonical primary-author chunks
DUP_THRESHOLD = 0.92          # cosine >= this between two chunks => near-duplicate


def apply_intent_tier_weights(
    scores: np.ndarray,
    metas: list[dict],
    intent: str,
    *,
    weights: dict[str, dict[str, float]] = TIER_WEIGHTS,
    primary_bonus: float = PRIMARY_AUTHOR_BONUS,
) -> np.ndarray:
    """Add an intent-conditioned per-tier delta to each score; return a new array.

    `intent` is one of the keys in `weights`; an unrecognised intent falls back
    to the "unknown" row. Canonical chunks by a lineage-master author get
    `primary_bonus` on top. Non-mutating.
    """
    table = weights.get(intent) or weights["unknown"]
    boosted = scores.copy()
    for i, m in enumerate(metas):
        tier = chunk_tier(m)
        delta = table.get(tier, 0.0)
        if tier == "canonical" and m.get("author") in PRIMARY_AUTHORS:
            delta += primary_bonus
        boosted[i] += delta
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
    dup_threshold: float = DUP_THRESHOLD,
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
            # Authority-aware dedup: a near-duplicate of an already-selected
            # (higher-ranked) chunk is dropped — the intent weighting made the
            # higher-authority copy win the earlier slot. (RFC-011)
            if selected and max_div >= dup_threshold:
                continue
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
