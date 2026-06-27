# ADR-015: Hybrid retrieval — BM25 lexical index fused with dense via Reciprocal Rank Fusion

**Status:** ACCEPTED
**Date:** 2026-06-27
**Author:** Neha (with Claude)

## Context

Dense retrieval (BGE-M3 cosine similarity, RFC-003) uses semantic embeddings and
works well for conceptual questions. However, keyword-specific queries whose
relevant passage uses the query's distinctive terms only *in contrast* or
*negation* suffer a recall failure: the passage is semantically about a broader
concept and scores only moderately on the dense side.

The motivating failure (F20, QA findings 2026-06-25): "What do the books say
about Idol Worship?" returned a "no material found" meta-answer. The relevant
passage — *"Bhakti does not consist … in formal idol-worships: it consists in
love to God"* (*Vindication of Indian Philosophy*) — ranked 34th in dense
cosine similarity and 147th in another work. The 1-per-work MMR cap gave each
work's slot to a higher-scoring general-devotion chunk, so even expanding the
candidate window to 100 failed to surface it.

RFC-011 (intent-aware tier weighting) was already live but does not address this
class of miss — the problem is raw recall, not re-ranking of already-retrieved
chunks.

## Decision

Add a **BM25 lexical index** over all corpus chunks (built lazily at server
startup, cached in process) and fuse it with the dense scores via **Reciprocal
Rank Fusion (RRF)** before candidate selection. The fused candidate pool is then
fed into the existing MMR diversity reranker.

### Implementation (`tools/retrieve.py`)

- **`BM25Index`**: a self-contained BM25 scorer. Built once from the corpus
  chunk list; cached in `_bm25_cache`. Cleared on `/admin/reload`.
- **`lexical_scores(query, index)`**: tokenises the query (lowercase, split on
  punctuation) and returns a normalised BM25 score array over all chunks.
- **`rrf_fuse(dense_ranks, lexical_ranks, k=60)`**: standard RRF —
  `score_i = 1/(k + rank_dense_i) + 1/(k + rank_lexical_i)`. Returns a fused
  score array.
- **`fused_candidate_scores(query, query_vec, metas, embeddings, index)`**:
  convenience helper that combines dense cosine + intent-tier weights + RRF
  fusion into a single score array. Used by all four call sites.

### Call sites wired to fused scores

1. `server.py` `_retrieve` — primary live path.
2. `chat.py` `run_retrieval` — CLI path.
3. `tune_sweep.py` — offline evaluation sweep.
4. `rank_probe.py` — diagnostic tool (also gained `--no-hybrid` flag for
   A/B comparison).

### Critical implementation note: MMR must rank on the FUSED score

MMR selects the final top-k chunks from the fused candidate pool. The diversity
penalty in MMR is applied to the score used for selection. If MMR is given the
**raw dense score** instead of the fused score, a lexically-surfaced chunk
enters the candidate pool but its raw dense score is low, so the 1-per-work cap
drops it in favour of a higher-dense sibling — making hybrid retrieval a no-op
end-to-end. This was a real bug (commit `80e2b2d`) found and fixed at all four
call sites: MMR now ranks on `fused_score`, not `dense_score`.

A secondary bug batch (commit `b5147dd`) fixed: O(n²) BM25 index build (the
BM25 build was re-running over the growing scored list rather than the flat
corpus), wrong BM25 chunk indices on the filtered (work-scoped) path, and a
BM25 cache leak that caused the cache to survive a corpus reload.

## Alternatives considered

- **Dense-only with larger candidate window.** Tried: even `candidates=100`
  didn't surface the idol-worship passage for the motivating query because the
  1-per-work cap eliminated it. Dense recall is a ceiling, not a window issue.
- **TF-IDF instead of BM25.** BM25 is the standard extension of TF-IDF
  (length-normalized, term-frequency-saturated) and consistently outperforms
  plain TF-IDF on short-document retrieval. No additional cost.
- **Cross-encoder reranker (neural).** Would also help but adds significant
  latency (200–400ms per candidate scored) and external model dependency. BM25
  fusion is zero-latency and zero-cost.
- **Query expansion (add synonyms to the query before dense embedding).** Harder
  to implement correctly for multilingual corpus; doesn't fix the root issue that
  the passage names the term only negatively.

## Consequences

**Positive:**
- Keyword-specific queries whose distinctive terms appear in the passage (even
  in contrast) are now recalled. The idol-worship passage surfaced in the top-3
  fused candidates.
- Zero latency overhead: BM25 scoring is a sparse dot-product, sub-millisecond
  for 15K chunks.
- Zero cost overhead: no external API calls.
- MMR, intent-tier weights (RFC-011), and per-source cap continue to apply
  unchanged on the fused pool.

**Negative:**
- BM25 is purely lexical — it does not understand meaning. A query about
  "divine love" will not match a chunk that discusses "bhakti" (without that
  exact English word). The hybrid design relies on dense to cover semantic
  mismatches and BM25 to cover exact-keyword misses.
- The BM25 index is rebuilt at server startup (or `/admin/reload`). On a corpus
  of ~15K chunks this takes under 1 second; on a much larger corpus it would
  need to be persisted.

## References

- [RFC-003 Retrieval & RAG strategy](../rfc/RFC-003-retrieval-and-rag.md) —
  the pipeline this extends (amended 2026-06-27 to cross-reference)
- [RFC-011 Intent-aware citation ranking](../rfc/RFC-011-intent-aware-citation-ranking.md)
  — RFC-011's intent-tier weights are applied before RRF fusion; both are live
- QA finding F20 in [docs/qa-findings-2026-06-25.md](../qa-findings-2026-06-25.md)
- Commits: `c96fa69` (BM25 + RRF functions), `d3d4ac9` (cache + helper),
  `5c63b4a` (server), `9f8c342` (chat + tune_sweep), `e953895` (rank_probe),
  `80e2b2d` (MMR fused-score fix), `b5147dd` (three additional bug fixes)
