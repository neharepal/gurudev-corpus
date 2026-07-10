# Debugging Protocol — Retrieval & Answer Quality

A required, repeatable process for diagnosing "the answer is wrong / thin /
missing a source" problems. It exists because ad-hoc guessing here is expensive:
retrieval has many stages (dense, BM25, RRF fusion, intent-tier weighting, MMR)
and a naive fix at the wrong stage wastes hours and can silently regress others.

Findings from each investigation go in
[retrieval-investigation-log.md](./retrieval-investigation-log.md). **Grep that
log before starting** — your hypothesis may already be ruled out.

---

## The iron rules

1. **Root cause before any fix.** No code change until you can point to evidence
   for *where* and *why* it breaks. "It's probably X" is not evidence.
2. **Baseline first.** Run the offline gold eval and record the number *before*
   touching anything. That is your regression floor.
3. **Never overfit to one query.** A fix that makes one query pass but isn't
   validated against the full gold set is not a fix. Add a gold case for the new
   failure, then require **zero regressions** on the rest.
4. **Separate retrieval from synthesis.** Determine whether the target passage
   actually *reaches the LLM* before blaming the prompt (see recipe C).
5. **Attribute the loss to a stage.** Dense, BM25, fused, intent-weighting, MMR
   — find which stage drops the passage, then fix *that* stage.
6. **Log it.** Add an entry to the investigation log — including dead ends and
   *why* they failed. An unrecorded dead end will be retried.
7. **Respect API cost.** Diagnose offline (no API). When you truly need the live
   answer, make **one** diagnostic call — never a loop.

---

## Tools

- **`tools/eval_retrieval.py`** — offline gold-set harness. No server, no LLM
  API (uses local BGE-M3 embeddings + BM25). `--top-k`, `--verbose`. This is the
  regression gate for any retrieval change. Add a gold case for every new
  confirmed failure mode.
- **`tools/retrieve.py`** — the retrieval internals you'll instrument:
  `embed_query`, `fused_candidate_scores` (dense+BM25 RRF), `apply_intent_tier_weights`
  (`TIER_WEIGHTS`), `mmr_rerank`, `_get_or_build_bm25_index`, `load_chunk_text`.
- **`tools/intent.py`** — `classify_intent` (heuristic + Haiku fallback);
  `_heuristic_intent` for the offline label.
- **`04_processed/chunks.jsonl`** — row-aligned chunk text (line i ↔ `metas[i]`).

---

## Diagnostic recipes (offline, no API)

### A. Where does the target rank in each channel?
For a query and an expected `work_id`/chunk, print its best rank under:
dense (`emb @ qvec`), BM25-only (`_get_or_build_bm25_index(...).score(tokens)`),
and fused (`fused_candidate_scores`). A passage strong in dense but weak in fused
means fusion/intent-weighting is demoting it — not a semantics problem.

### B. What is the intent, and what tier multiplier is applied?
Print `intent.classify_intent(q, use_llm_fallback=False)` and, for the target vs
a canonical work, `weighted[i] / dense[i]`. The `unknown` tier prior is a common
silent culprit for entity/biography queries (see 2026-07-09 log entry).

### C. Does the target chunk actually reach the LLM? (retrieval vs synthesis)
Run the **real** pipeline offline with live params — `top_k=12`,
`max_per_source=2`, `mmr_lambda=retrieve.MMR_LAMBDA` — and check whether the
target chunk index is in the final set.
- In the set but not quoted → **synthesis / prompt** problem.
- Not in the set → **retrieval** problem; use recipe A to find the stage.

### D. Inspect the actual chunk text the LLM would see
Load `chunks.jsonl` and print the top-k chunk bodies. Confirm they are real prose
and genuinely on-topic — OCR junk (page markers, headings, garbled scans,
list pages) frequently fills slots for weak/short queries.

### E. Live confirmation (at most one call)
`curl -s -X POST localhost:8765/ask -d '{"mode":"qa","question":"…","lang":"mr"}'`
then inspect `citations` / `framing` / `references`. One call, not a loop.

---

## When you have a candidate fix

1. Apply it behind the smallest possible change.
2. Run `tools/eval_retrieval.py` → must be **≥ baseline PASS, zero regressions**.
3. Run affected unit tests (`pytest tools/tests/test_hybrid_retrieval.py`, etc.).
4. Restart the server; do recipe E once to confirm live.
5. Commit with a message that states the root cause and the evidence.
6. Add / update the investigation-log entry.

## Known stable facts (as of 2026-07-09)
- Corpus: 16,386 chunks, BGE-M3 dim 1024. `top_k=12`, `max_per_source=2`,
  `INITIAL_CANDIDATES=100`, `MMR_LAMBDA=0.7`.
- `TIER_WEIGHTS["unknown"] = {canonical:+0.02, recollections:+0.02, reference:-0.08}`.
- Bare 1–2 word queries are a known weak-signal failure mode; full questions
  retrieve markedly better. **REPLACE the weak query — do not max-combine.**
