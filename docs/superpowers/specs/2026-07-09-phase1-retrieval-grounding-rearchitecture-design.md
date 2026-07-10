# Phase 1 — Retrieval + Grounding Re-architecture (Design Spec)

**Date:** 2026-07-09
**Status:** Design — pending user review before implementation-plan.
**Related:** [`docs/rag-frontier-techniques-report.md`](../../rag-frontier-techniques-report.md),
[`docs/retrieval-investigation-log.md`](../../retrieval-investigation-log.md),
[`docs/DEBUGGING-PROTOCOL.md`](../../DEBUGGING-PROTOCOL.md).

## Goal

Make the Q&A give the reader **as much relevant, grounded information as
possible** — fixing four observed failures at once, without re-indexing the
corpus. Latency is an acceptable trade for quality.

## The four failures this fixes

1. **Buried-but-relevant passage** (e.g. Carlyle Cottage rich passage sits at
   rank ~7 / #30 and never reaches the model). MMR optimizes diversity, not
   relevance, so it structurally cannot rescue it.
2. **Bare/short entity query** (2-token query lands in a sparse embedding
   region; cosine ~0.32). A representation problem — why score-level
   max-combine failed (see investigation log).
3. **OCR junk chunks** (headings, page markers, garble, village-name lists)
   crowd the top-12 on weak queries.
4. **Confident essay with zero citations** (e.g. the Bhakti answer): "quote
   verbatim" is prompt-only, unenforced — a grounding/trust failure.

## Decisions locked in brainstorming

- **Scope:** Phase 1 = all four drop-in levers together; **no re-indexing**.
  (Deeper chunking / re-OCR are Phase 2 / 3, separate specs.)
- **Architecture:** a **fixed enhanced pipeline** (not agentic). One synthesis
  call; each stage testable in isolation.
- **Grounding:** **both** Claude Citations API (spans valid by construction)
  **and** a server-side enforcement guard + deterministic quote verifier.
- **Query understanding:** **rewrite + HyDE**, fused, with BM25 on the original
  query as the exact-match backbone.

## Global Constraints

- No re-embedding the corpus. `quality_score` is computed from the existing
  `04_processed/chunks.jsonl` into `chunks_meta.jsonl`; embeddings untouched.
- Every new stage is **flag-gated** and **fail-safe**: if it errors/times out,
  the pipeline degrades to today's behavior. Nothing regresses.
- Reranker runs **in-process**, lazy-loaded at startup like BGE-M3; device
  auto-detect (MPS/CUDA/CPU), fp16. Model: `BAAI/bge-reranker-v2-m3`.
- Offline eval (`tools/eval_retrieval.py`) is the regression gate. No new
  retrieval/grounding stage is enabled until it validates with zero regressions.
- No wholesale prompt rewrites; the anti-false-negative and tone rules stay.

---

## Pipeline (data flow)

```
1. QUERY UNDERSTANDING (new)
   original question ─────────────────► BM25 (exact entity match — backbone)
   LLM rewrite (Haiku) ───────────────► dense + BM25
   HyDE hypothetical answer (Haiku) ──► dense
   existing EN↔MR translation ────────► dense + BM25
        │  dense: per-passage MAX across vectors (same pattern as translation)
        ▼
2. WIDENED HYBRID (changed)
   RRF fuse(dense, BM25) → top ~80 candidates          (was: straight to MMR→12)
   × quality_score  (junk downweighted, worst floored out)      ← new
        │
        ▼
3. CROSS-ENCODER RERANK (new)
   bge-reranker-v2-m3 scores (original question, passage) for all ~80
   → sort → keep top 12
   MMR retained ONLY after rerank, for near-duplicate dedup
        │
        ▼
4. GROUNDED SYNTHESIS (rebuilt)
   Claude Citations API: 12 passages as documents → answer with cited_text spans
   + enforcement guard (one retry if under-cited) + quote verifier
   + re-derive "Read in full" page from cited spans
```

Notes:
- The reranker is the **relevance authority**; MMR is demoted to dedup.
- **Retrieval width (~80) is decoupled from final width (12)** so a passage
  buried at #30 is still present to rescue. (We already pull 100 candidates
  today, so this is mostly re-plumbing MMR → rerank.)
- Rerank uses the **original** user question (the cross-encoder is
  query-conditioned and handles short queries far better than a bi-encoder).

---

## Components (isolated, independently testable)

### `tools/query_understanding.py` (new)
Mirrors `query_translation.py` (heuristic gate + cached Haiku + fail-safe).
- `rewrite_query(q, *, use_llm=True, rewriter=None) -> Optional[str]` — a fuller
  natural-language reformulation, same language/script as `q`.
- `hypothetical_doc(q, *, use_llm=True, generator=None) -> Optional[str]` — a
  short hypothetical answer paragraph (HyDE), in the corpus language/script.
- Both cached (`lru_cache`), return `None` on failure/empty/echo. Injectable
  hooks (`rewriter`, `generator`) for deterministic tests; `use_llm=False`
  disables all calls (offline eval).

### `tools/reranker.py` (new)
- `class Reranker`: lazy-loads `BAAI/bge-reranker-v2-m3` (FlagEmbedding
  `FlagReranker(..., use_fp16=True)` or HF), device auto-detect.
- `rerank(query: str, passages: list[str]) -> list[float]` — batched scores.
- `available() -> bool`; on load failure the server logs and disables rerank.

### `tools/chunk_quality.py` (new, pure functions)
- `quality_score(text: str) -> float` in `[0,1]`, `is_junk(text) -> bool`.
- Signals (combined into a multiplier; thresholds tuned on ~100 hand-labeled
  chunks): Devanagari-script-ratio < 0.5; digit-ratio > 0.2; length < ~200
  chars / ~30 words; Marathi-stopword-count < 2; symbol-to-word > 0.1.
- No I/O; unit-tested against labeled fixtures.

### `tools/build_chunk_quality.py` (new, one-time)
- Reads `04_processed/chunks.jsonl`, writes `quality_score` (and `junk_flag`)
  into `chunks_meta.jsonl`. Idempotent. **No re-embed.**

### `tools/citation_verify.py` (new, pure)
- `verify_quote(cited_text: str, source_text: str) -> ("ok"|"flag", score)` via
  Devanagari-normalize → exact substring → `rapidfuzz.partial_ratio`. Below
  threshold → caller writes to `flag_queue` (citation-garble Phase 2 detection).

### Synthesis path (server / `llm_client`) — rebuilt
- Switch QA synthesis to the **Claude Citations API**: the 12 reranked passages
  are passed as document blocks; the model returns text with `citations`
  carrying `cited_text` + document index + char range.
- **Enforcement guard:** trigger a retry when the answer is **under-cited** —
  defined concretely as: the answer body is non-trivial (more than a one-line
  "not covered" note) AND **zero** citations were produced AND **≥1 non-junk
  passage** was supplied to the model. On trigger, do **one** retry with a hard
  "you must cite the supplied passages" instruction. If it is still under-cited
  after the retry, surface the answer as-is (no loops) and log the event.
- **Deep-link preservation:** map Citations API `document-index + char-range →
  chunk source_path + char_start →` existing `reading_page_for_offset`, so
  "Read in full" still jumps to the right page.
- **Fallback:** Citations API failure → current custom quoteStart/quoteEnd path.

---

## Configuration / flags

Env flags (default off until each is validated, then flip on):
`ENABLE_JUNK_WEIGHT`, `ENABLE_RERANK`, `RERANK_CANDIDATES` (default 80),
`RERANK_TOPK` (default 12), `ENABLE_QUERY_REWRITE`, `ENABLE_HYDE`,
`GROUNDING_MODE` (`legacy` | `citations` | `citations+enforce`).

---

## Error handling / graceful degradation

| Stage | Failure | Behavior |
|---|---|---|
| rewrite / HyDE | Haiku error/timeout | use original query |
| reranker | unavailable / OOM / timeout | fall back to MMR ranking |
| Citations API | error | fall back to custom quote mechanism |
| junk scoring | — | pure metadata, no runtime surface |

If every new stage fails, the pipeline **is** today's pipeline.

---

## Evaluation (makes it measurable, not vibes)

- **Expand the gold set** (`eval_retrieval.py`) 12 → ~30–40 labeled queries:
  bare + verbose entity (Carlyle), doctrinal (Bhakti), place/person,
  navigational; expected `work_id`s and, where possible, chunk-level relevance
  for **Recall@12**.
- **Offline (no API):** reranker **Recall@12** on entity queries; **junk-in-top-12
  rate**. Freely runnable; the regression gate.
- **API-gated (small labeled set, run manually):** rewrite/HyDE lift; grounding
  metrics — **% of doctrinal answers with ≥1 verified citation** (target 100%
  when relevant passages exist), verifier pass rate.
- **Success criteria:** (a) Carlyle bare query surfaces the rich passage in
  top-12; (b) no doctrinal answer with zero citations when relevant passages
  exist; (c) junk-in-top-12 ≈ 0; (d) no regression on existing gold.

---

## Rollout order (each flag-gated, validated before enabling)

1. **Junk scoring** — build `quality_score`; validate junk-in-top-12 drop offline.
2. **Reranker** — widen to 80 → rerank → 12; validate Recall@12 offline.
3. **Query rewrite + HyDE** — validate entity-query lift.
4. **Grounding** (Citations API + enforcement + verifier) — validate grounding
   metrics.

One-time setup: reranker model download (~2.3 GB); one `chunks_meta` rebuild.
No re-embed.

---

## Testing

- **Unit:** `chunk_quality`, `citation_verify` (pure); `query_understanding`,
  enforcement guard (stubbed Haiku); `reranker` (small stub).
- **Integration:** extended offline eval harness (`eval_retrieval.py`) exercising
  junk-weight + rerank end to end.

## Out of scope (later phases)

- Small-to-big / semantic re-chunking, contextual retrieval (Phase 2 — requires
  re-embed).
- Re-OCR of worst scans (Surya/Marker), proper-noun cleanup (Phase 3).
- Agentic / multi-hop retrieval loop (fixed pipeline chosen for Phase 1).
