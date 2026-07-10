# RFC-014: Retrieval + Grounding Re-architecture (Phase 1)

**Status:** PROPOSED
**Author:** Neha (with Claude)
**Created:** 2026-07-09
**Last updated:** 2026-07-09

## Summary

Move the Q&A pipeline from a competent **single-shot** RAG stack (BGE-M3 dense +
BM25 + RRF + intent-tier weighting + MMR → Claude synthesis) to a **retrieve-wide
/ rerank-narrow, query-understood, grounded** pipeline. Phase 1 adds four
drop-in, flag-gated, fail-safe capabilities **without re-embedding the corpus**:

1. **Cross-encoder reranking** (`BAAI/bge-reranker-v2-m3`) over a widened
   candidate pool — the relevance authority; MMR demoted to dedup.
2. **Query understanding** — LLM rewrite + HyDE, with BM25 on the original query
   as the exact-match backbone.
3. **Index-time junk scoring** — deterministic, script-agnostic quality signal to
   downweight OCR/structural garbage.
4. **Grounding** — Claude Citations API (spans valid by construction) + a
   server-side enforcement guard + a deterministic quote verifier.

Phase 1 is split for delivery into **1A (retrieval quality)** and **1B
(grounding)**. Deeper chunking and re-OCR are deferred to Phase 2/3.

## Motivation

Four failures were reproduced and root-caused by hand (see
[`retrieval-investigation-log.md`](../retrieval-investigation-log.md)) and
independently confirmed by a survey of frontier RAG systems
([`rag-frontier-techniques-report.md`](../rag-frontier-techniques-report.md)):

| Failure | Evidence | Root cause |
|---|---|---|
| **Buried-but-relevant passage** | Carlyle Cottage rich passage (chunk 10524: Fergusson College, ~₹300–400, 1917) ranks ~#7 and never reaches the model | MMR optimizes **diversity**, not query-relevance — it structurally cannot rescue a buried passage |
| **Bare/short entity query** | "कारलाईल कॉटेज" cosine ~0.32; a full question rises to ~0.46 and surfaces the passage | A 2-token vector lands in a **sparse embedding region** (a representation problem) |
| **OCR junk in top-12** | For the bare query, **10 of 12** chunks sent to the model were page-markers, headings, village lists, garble | No data-quality gate; short/garbled chunks spuriously match weak queries |
| **Confident essay, zero citations** | The Bhakti answer made specific claims (dates, Sanskrit) with **no citations** | "quote verbatim" is prompt-only and **unenforced** |

Repeated reactive patches (BM25 stopwords, embedding max-combine expansion, tier
tuning, work-scoping) each traded one failure for another — the signal to stop
patching and fix the architecture. Guiding principle from the product owner:
**maximize information AND relevance; latency is an acceptable trade.**

## Background: current architecture

`embed(q) → dense (+EN↔MR translation vectors) → intent-tier weight → RRF
fuse(dense, BM25) → MMR (top_k=12, max 2/source) → synthesize with a custom
quoteStart/quoteEnd citation mechanism`. Strengths: hybrid lexical+dense, RFC-011
canonical-priority weighting, verbatim quote splicing + "Read in full"
deep-linking. Gaps: no relevance reranking, no query understanding, no data-quality
gate, no citation enforcement/verification.

## Proposed design

A **fixed enhanced pipeline** (not agentic — chosen for testability and bounded
latency; agentic retrieval is a future phase):

```
1. QUERY UNDERSTANDING  original + LLM rewrite + HyDE → dense (MAX) ; BM25 on original (backbone)
2. WIDENED HYBRID       RRF fuse → top ~80 candidates × quality_score (junk downweighted)
3. CROSS-ENCODER RERANK bge-reranker-v2-m3 (original question, passage) → keep top 12  (MMR → dedup only)
4. GROUNDED SYNTHESIS   Claude Citations API + enforcement guard + quote verifier + deep-link from spans
```

Design details, module interfaces, and per-task code live in the design spec and
plans (see References). Key decisions:

- **Retrieval width (~80) is decoupled from final width (12)** so a buried
  passage is *present* to be rescued. Do **not** just raise top_k — "lost in the
  middle" makes loosely-ranked extra context *worse*.
- **Reranker is the relevance authority.** MMR (a diversity objective, scored on
  the same weak RRF signal) cannot elevate a buried passage; a cross-encoder
  recomputes query-conditioned relevance from scratch. MMR is retained only for
  near-duplicate OCR dedup, after reranking.
- **Query understanding moves the search *anchor*, not just scores.** This is
  categorically different from the failed embedding max-combine, which retained
  the weak query's noise floor (fusion-of-scores ≠ fusion-of-representations).
  BM25 on the original query stays the backbone for exact/obscure entity names
  the LLM has never heard of.
- **Junk is downweighted, never deleted** (score multiplier + hard floor),
  protecting short-but-legitimate content (shlokas, aphorisms).
- **Grounding uses both** Citations-API (span validity by construction) **and** a
  server-side enforcement guard (fixes the zero-citation essay) **and** a quote
  verifier (a mismatch means the *source* is OCR-corrupt → flag for repair, the
  detection half of the citation-garble Phase 2 work).

### Correction to the frontier report's junk heuristic

The report (and initial spec) proposed a **Devanagari-script-ratio** junk signal.
Our corpus is **trilingual** — ~60% of the canonical works are English — so a
Devanagari-ratio gate would wrongly flag legitimate English prose. Phase 1 uses a
**script-agnostic** signal (Devanagari **or** Latin letters both count as real)
plus a **bilingual** stopword check. This is a deliberate deviation.

## Alternatives considered

- **Raise top_k / rely on long context** — rejected: "lost in the middle"
  (U-shaped positional bias) degrades answers; widen retrieval, narrow what
  reaches the model.
- **Embedding max-combine query expansion** — tried and reverted (investigation
  log): keeps the weak query's noise floor; a representation fix (rewrite/HyDE) is
  required.
- **Agentic / ReAct retrieval loop** — deferred: more powerful for multi-hop but
  variable latency, harder to test/guarantee. Phase 1 keeps a fixed pipeline;
  retrieval is structured so a later phase can wrap it in a loop.
- **BM25 stopword tuning / tier-weight tuning alone** — insufficient; addressed
  symptoms, not the buried-passage / grounding root causes.
- **Claude Citations API only (no enforcement)** — insufficient: by-construction
  span validity does not force the model to cite; enforcement is needed for the
  zero-citation case.

## Phasing

- **Phase 1A — Retrieval quality** (no re-embed): junk scoring, reranker, query
  rewrite+HyDE. Offline-validatable. Plan:
  [`2026-07-09-phase1a-retrieval-quality.md`](../superpowers/plans/2026-07-09-phase1a-retrieval-quality.md).
- **Phase 1B — Grounding** (synthesis path): Citations API + enforcement +
  verifier + deep-link. Plan: *to be written.*
- **Phase 2** (re-embed): small-to-big / semantic chunking, better fusion.
- **Phase 3** (heavy): re-OCR worst scans (Surya/Marker), proper-noun cleanup.

Each stage is behind an env flag (`ENABLE_JUNK_WEIGHT`, `ENABLE_RERANK`,
`ENABLE_QUERY_REWRITE`, `ENABLE_HYDE`, `GROUNDING_MODE`) and validated on the gold
eval before it is enabled.

## Evaluation

`tools/eval_retrieval.py` (offline, no API) is the regression gate. Phase 1
extends it: ~30–40 labeled queries (incl. bare + verbose entity, doctrinal),
**Recall@12**, and a **junk-in-top-12** counter. API-gated metrics (small labeled
set, run manually): rewrite/HyDE lift, **% of doctrinal answers with ≥1 verified
citation** (target 100% when relevant passages exist). Success criteria: (a) bare
Carlyle query surfaces the rich passage in top-12; (b) no doctrinal answer with
zero citations when relevant passages exist; (c) junk-in-top-12 ≈ 0; (d) **no
regression** on existing gold.

## Risks & mitigations

- **Reranker latency/hardware** (~0.6B model, ~2.3 GB) — in-process, device
  auto-detect (MPS/CPU); latency accepted per product principle; flag-off
  fallback to MMR.
- **Query-rewrite/HyDE drift** — retrieve with original **and** rewrites and fuse;
  BM25 on the original anchors exact matches; both fail-safe to no-op.
- **Junk false-positives** — flag-and-downweight (not delete), hard floor only for
  the worst, script-agnostic + bilingual signals; thresholds tuned on labeled
  chunks; validated by the junk-in-top-12 metric against regressions.
- **Citations-API rework touching deep-linking** — map returned spans back to
  chunk `source_path + char_start → reading_page_for_offset`; fail-safe to the
  existing custom quote mechanism.
- **Every stage degrades to today's behavior on failure** — if all new stages
  fail, the pipeline *is* the current pipeline. Nothing regresses.

## References

- Design spec: [`2026-07-09-phase1-retrieval-grounding-rearchitecture-design.md`](../superpowers/specs/2026-07-09-phase1-retrieval-grounding-rearchitecture-design.md)
- Plan 1A: [`2026-07-09-phase1a-retrieval-quality.md`](../superpowers/plans/2026-07-09-phase1a-retrieval-quality.md)
- Research report: [`rag-frontier-techniques-report.md`](../rag-frontier-techniques-report.md)
- Investigation log: [`retrieval-investigation-log.md`](../retrieval-investigation-log.md)
- Debugging protocol: [`DEBUGGING-PROTOCOL.md`](../DEBUGGING-PROTOCOL.md)
- Supersedes the ranking role of MMR from RFC-011 (canonical-priority weighting is retained on the dense side).
