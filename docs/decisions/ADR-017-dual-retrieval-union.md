# ADR-017: Dual-retrieval union — RRF-fuse per-variant dense rankings instead of MAX-combining

**Status:** ACCEPTED
**Date:** 2026-07-12
**Author:** Neha (with Claude)

## Context

A query is embedded in several variants for cross-lingual reach (ADR-015 / RFC-014):
the original, a Marathi translation (`translate_query`), an English translation
(`translate_to_english`), and — when enabled — rewrite/HyDE strings. Previously these
were combined at the **score level** by element-wise MAX of the per-passage cosines into
a single dense score array, which was then tier-weighted and RRF-fused with BM25.

The MAX combine has a dilution failure: it is driven by **absolute cosine magnitude**, so
the variant with the highest cosine dominates. A passage that is **rank-1 for the Marathi
translation but only modest in absolute cosine** loses to English passages with higher
absolute cosine and falls out of the top-k. Observed live: "the incident when lightning
struck Gurudev's house" (English query) — the Marathi incident passages ranked #14 under
the Marathi query alone but were diluted to #28 by the MAX combine, so the answer missed
the incident. This is the weaker form of an idea that predated the re-architecture
(translate, retrieve separately, merge results).

## Decision

Keep each query variant's dense scores as a **separate ranking** and **RRF-fuse the
rankings** (`retrieve.rrf_fuse_multi`) rather than MAX-combining into one score array.
Each variant contributes `1/(k + rank)` from its own ranking, so a passage that is rank-1
for **any** variant earns full rank credit regardless of absolute cosine. Intent tier
weights (ADR-011 / RFC-011) are applied to each variant before fusion; BM25 remains one
additional ranking in the same RRF (ADR-015). `rrf_fuse` is now a thin wrapper over
`rrf_fuse_multi([dense], lex)`, so the single-ranking path is unchanged.

The per-passage MAX is retained solely for the `cos_score` readout in the retrieval event
(tier deltas are additive, so the max is identical whether weighted before or after).

## Consequences

- **Cross-lingual recall improves** without hurting monolingual: a Marathi-relevant passage
  keeps its rank credit. Validated — the lightning incident's works (Guru Ha Parabrahma
  Kewal, १९२७-१९५७) now surface at the top-8 of the English query.
- **No doctrinal regression:** "What is bhakti?" stays all-canonical; "What are Gurudev's
  views on social service?" stays canonical-first (checked against the earlier MAX behaviour).
- **Exact-chunk recall still bounded by chunking granularity:** dual-retrieval surfaces the
  right *works* reliably, but a single incident sentence buried in a large mixed chunk still
  ranks below its siblings. That is a re-chunk concern (Phase 2), orthogonal to this ADR.
- **Cost/latency unchanged:** same number of query embeddings and translation calls; only
  the fusion arithmetic changed.

## References

- ADR-015 (hybrid BM25 + RRF), ADR-011/RFC-011 (intent tier weighting), RFC-014 (re-arch)
- `tools/retrieve.py` `rrf_fuse_multi` / `fused_candidate_scores(extra_dense=…)`;
  `tools/server.py` `_retrieve`; `tools/tests/test_rrf_multi.py`
