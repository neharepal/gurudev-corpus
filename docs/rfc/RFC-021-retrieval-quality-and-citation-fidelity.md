## RFC-021: Enforce our existing reference-only citation contract

**Status:** PROPOSED
**Author:** Neha Repal (with Claude)
**Created:** 2026-08-01
**Blocks:** RFC-020 Phase 7 (deploy) — canonical KP data is ready but not shippable until the escape hatches below are closed
**Related:** schemas.py::splice_quote_dict, grounding.py::verify_citations, RFC-017 (small-to-big chunking), RFC-020 (multi-vol canonical assembly)

---

## Summary

**We already have reference-only citations by design.** The LLM is meant to return `passage` + `quoteStart` + `quoteEnd` anchors, and the server is meant to splice the actual quote body from the source chunk. The LLM should never author the quote text that reaches the user.

**The implementation has drifted.** A series of well-intentioned "don't break on edge cases" fallback branches now let the LLM's own `body` field survive to the final response. Combined with a non-strict tool-use call, this means the design is not actually enforced — the LLM can, and does, invent quote text from training-data memory when the retrieved context doesn't cover the query.

This RFC proposes closing the escape hatches. Nothing new is invented; the design that already exists is made to enforce itself.

## Context — what surfaced the drift

RFC-020 rebuilt Kakanchi Pravachane (5 vols → 1 canonical text.md). Phase 6 re-chunked + re-embedded. Smoke-test on the English query *"When was Shri Gurudev initiated?"* revealed:

- Local returned 1 citation: KP, with body `कारण १९०९ साली त्यांनी महाराजांकडून नाम घेतले होते`
- **Empirical verification:** the KP chunk the LLM was handed (`kakanchi-pravachane--mr--0506`) is about त्रिगुण/Gita 2.45. It contains neither `१९०९` nor `१९०१` nor `मच्चित्त` nor the quoted phrase. `grep -c 'कारण १९०९ साली त्यांनी महाराजांकडून नाम घेतले' 04_processed/chunks.jsonl` returns 0.
- The LLM invented the quote from training-data memory of the OLD KP source text (which the sampraday literature publishes verbatim, and Claude has seen).

Prod behaves better on the same query — 2 citations, one from Kannada Literature Memorial, one from KP with the same `१९०९` body. Prod's LLM was faithfully quoting: prod chunk `--0506` (from the OLD KP text.md still on prod) contains that phrase verbatim. Prod is not "correct" — it's masking a systemic failure with luck-of-the-corpus.

## Investigation

Three parallel deep-dives ran on 2026-08-01, artifacts at `/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/`:

- `rfc021_investigation.md` — code mechanism (splice, verify, retrieval, BM25, cross-language, guard inventory) — 726 lines
- `rfc021_prompts_schema.md` — LLM tool schema + prompt archaeology — 591 lines
- `rfc021_empirical.md` — 5 live queries against local, prod-vs-local comparison — 283 lines

Additionally verified by direct SSH into Lightsail:

- **Env flags are UNSET in both prod and local:** `ENABLE_HYDE`, `ENABLE_QUERY_REWRITE`, `ENABLE_RERANK`, `GROUNDING_MODE`. Prod and local run identical retrieval config.
- **`parents.jsonl` alignment is clean:** 19,464 parent_id refs from chunks, 19,464 entries in parents.jsonl, 0 missing. Agent 1's stale-parents hypothesis is debunked.
- **Same chunk_id contains different sections in prod vs local** — deterministic id + different source = different content. The LLM's local hallucination reproduced prod's chunk content from training memory.

## The design vs the implementation

### The design

The `_QA_CITATION_QUOTE_SCHEMA` (schemas.py L303-348) declares `passage`, `quoteStart`, `quoteEnd` as required. `splice_quote_dict` is written to extract the actual quote body from the referenced chunk using those anchors. The design is: LLM points at what to cite; server extracts what was cited. The LLM never authors the body the user sees.

### The escape hatches — where the LLM's body survives despite the design

Enumerated from the agents' investigations, each anchored to file:line:

**E1. Non-strict tool-use.** The Anthropic API call omits `strict: true`. The schema lacks `additionalProperties: false`. The `required` list is a documented preference, not an enforced constraint. Result: the LLM can emit `body` alone without `passage`/`quoteStart`/`quoteEnd`, and the API accepts it.

- Fix: turn on `strict: true` on the tool. Set `additionalProperties: false` on the citation schema.

**E2. `has_ref = False` branch.** `splice_quote_dict` at L637-641: when the LLM emits `body` without any reference fields, the code sets `has_ref = False` and preserves the model's body untouched. This branch exists to support legacy modes with no retrieval, but it lets any LLM slip through for QA too.

- Fix: for `mode="qa"`, refuse to accept a citation without `passage`+`quoteStart`+`quoteEnd`. Drop it.

**E3. "Unknown passage letter" branch.** `splice_quote_dict` at L644-655: when `label_to_chunk.get(passage)` returns None (LLM cites a passage that doesn't exist in the retrieved set), the code comments *"Use the model's own body if it gave one."* and preserves it.

- Fix: drop the citation. The LLM cited something that isn't in the retrieved set; that's exactly the "quoted from memory" failure.

**E4. "Empty text" branch.** `splice_quote_dict` at L687: `quote["body"] = clean_quote_body(text) if text else (model_body or "")`. When the retrieved chunk's text is empty (rare but possible), the LLM's body is preserved.

- Fix: drop the citation on empty text.

**E5. `verify_citations` is advisory.** `grounding.verify_citations` (grounding.py L97-121) computes a fuzzy match between LLM's body and chunk text, but only appends a flag record to a YAML review queue. Never rejects. Never replaces. Gated on `GROUNDING_MODE=enforce` which is set nowhere.

- Fix: run verification unconditionally. On mismatch (<85% partial-ratio), drop the citation. Default `GROUNDING_MODE=enforce` on.

**E6. TRANSLATE follow-up mode intentionally inverts the contract.** `prompts.py::L660-673` (case b.1 in `build_user_message`) explicitly tells the LLM: *"emit `passage=""`, `quoteStart=""`, `quoteEnd=""`, and fill `quote.body` with the verbatim ORIGINAL passage from `<conversation_history>`"*. System prompt (L653-654) announces: *"CASE (b) OVERRIDES THE STANDARD CITATION CONTRACT."* Zero verification against source.

- Fix: the TRANSLATE follow-up should refer back to the ORIGINAL citation (persisted from the prior turn) and re-splice from the same chunk. The LLM adds a translation; it does NOT re-emit the quote body. This closes the widest gap.

## The fix — five specific changes

Each change is scoped to enforce the design that already exists. Ordered by impact + independence:

**Change 1 — Refuse LLM-authored bodies for QA citations (closes E2, E3, E4)**

In `splice_quote_dict`, replace every "preserve model_body" fallback with "return False + clear body" so the caller drops the citation. Enumerate:

```
# has_ref = False in QA mode → drop
if mode == "qa" and not has_ref:
    return False

# Unknown passage in QA mode → drop, don't preserve model_body
if chunk is None:
    quote["body"] = ""       # was: preserve model_body
    return False

# Empty text → drop, don't fall back to model_body
if not text:
    quote["body"] = ""       # was: model_body or ""
    return False
```

Legacy modes (`pravachan`, `reading` with no retrieval) may still want the current permissive behavior; keep it there by gating on `mode`.

**Change 2 — Activate `verify_citations` as a hard gate (closes E5)**

Remove the `GROUNDING_MODE=enforce` gate. Run verification unconditionally in the QA path. On <85% partial-ratio mismatch:

- Log the mismatch (still writes the review flag)
- Drop the citation from the response

If ALL citations get dropped and the LLM's answer prose still references them, retry with the LLM told: *"your quoted text didn't match the source; please cite only what you can find verbatim."*

**Change 3 — Strict tool-use schema (closes E1)**

Set `strict: true` on the citation tool definition passed to the Anthropic API. Set `additionalProperties: false` on `_QA_CITATION_QUOTE_SCHEMA`. Make `passage`, `quoteStart`, `quoteEnd` required (they already are, but strict mode makes it binding at the API layer).

**Change 4 — Fix TRANSLATE mode (closes E6)**

The follow-up prompt should:
- Load the ORIGINAL citation from `<conversation_history>` including its `passage` letter
- Ask the LLM to emit the passage letter + a translated `quote.paraphrase`
- Server re-splices `quote.body` from the same chunk as the prior turn

The LLM never emits body. Same design as first-turn QA.

**Change 5 — Retrieval quality gate (defense in depth)**

If, after Changes 1-4, top-K similarity scores don't exceed some threshold (e.g., no cosine > 0.7 in top 5), respond with:
- Answer prose framed as "the corpus doesn't directly answer this question, but here's related context"
- Zero citations
- No LLM-authored quote text

Better than serving nothing; worse than serving a real citation; refuses to fabricate.

## What this RFC does NOT solve

Deliberately out of scope — each deserves its own investigation:

- **Retrieval diversity regression** (2 → 1 citation from Kannada Memorial dropping out of local's top-K). Empirically real (F6 in the investigation), driven by chunk substitution shifting BM25 stats. If Changes 1-4 land, the failure mode becomes "0 citations" instead of "1 hallucinated citation" — which is acceptable but not great. Fixing retrieval diversity properly needs a separate RFC (options: MMR by work_id, source-diversity constraint, HyDE/rerank flags on).
- **Cross-language embedding quality**. Marathi query returns 4 citations, English query returns 1 for the same question. BGE-M3 is multilingual but has same-language bias. Out of scope; separate RFC.
- **Auto-scope substring matcher clamps small works**. Q5 regression noted in `rfc021_empirical.md`. Trivial two-line fix; can be a follow-up commit.
- **Chapter-title deterministic location field**. RFC-020 introduced structural heading metadata; wiring `_enrich_citation_location` (currently dead code) is a follow-up improvement, not a fidelity fix.
- **LLM training-data memory itself**. Cannot be prevented at the LLM layer. Structural defense (this RFC) is the only reliable answer.

## Rollout

1. Change 1 + Change 2 land together. Local test on 10 known queries; verify no hallucinated citations reach the response. Zero-citation responses are acceptable when retrieval is weak.
2. Change 3 lands next. Confirm the Anthropic API rejects malformed tool calls rather than silently accepting them.
3. Change 4 lands with a translate-mode test.
4. Change 5 lands after Changes 1-4 stabilize; tuned via the eval set.
5. Once locally clean, run 50 queries. Ship to prod (RFC-020 Phase 7) once the eval set is stable.

## Non-goals

- Building an eval harness. Worth doing, but this RFC doesn't gate on it. A follow-up RFC-022 should scope a proper regression eval.
- Adding new features. Every proposed change enforces an existing design; nothing new is invented.
- Fine-tuning models. Standard Anthropic Claude, no custom weights.

## Open questions

1. Should Changes 1-2 apply to `pravachan` and `reading` modes too, or QA only? These modes have different retrieval patterns; the LLM-authored `body` may be intentional for `reading` (verbatim passage from the currently-open book). Investigate before wide rollout.
2. Change 5's threshold (cosine > 0.7 in top 5) — what's the right number? Needs a small eval set to calibrate; can start conservative (>0.75) and lower if too many queries get "no grounded answer."
3. Change 3 — `strict: true` on Anthropic tool-use is relatively new. Confirm it's stable and doesn't cascade into other retry paths.

## References

- Investigation artifacts:
  - `/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/rfc021_investigation.md` (code mechanism)
  - `/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/rfc021_prompts_schema.md` (prompt + schema archaeology)
  - `/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/rfc021_empirical.md` (live query diagnostic)
- Key code paths:
  - `tools/schemas.py::_QA_CITATION_QUOTE_SCHEMA` (L303-348)
  - `tools/schemas.py::splice_quote_dict` (L618-721)
  - `tools/grounding.py::verify_citations` (L97-121)
  - `tools/prompts.py::build_user_message` (L640-680) — TRANSLATE follow-up mode
  - `tools/llm_client.py` — Anthropic API tool-use invocation
- Related RFCs:
  - RFC-017 (small-to-big chunking)
  - RFC-020 (multi-vol canonical assembly, whose Phase 7 is blocked on this RFC)
