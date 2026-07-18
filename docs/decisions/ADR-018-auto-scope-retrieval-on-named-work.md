# ADR-018: Auto-scope retrieval when the query explicitly names a work

**Status:** ACCEPTED (with 2026-07-18 revision — see below)
**Date:** 2026-07-18
**Author:** Neha (with Claude)

## Context

When a sadhak asks a question that mentions a specific work by title —
e.g., "What are the key messages in Amar Sandesh Sudha?", "What does
Sadhak-Bodh say about namasmarana?", "Compare Pathway to God in the Vedas
and Parmartha Sopan" — the current retrieval pipeline runs an **unscoped
search across the entire 282k-chunk corpus**. The named work's chunks
compete against everything else for the top-k slots, and often lose:

- Cross-language penalty: an English query about a Marathi-only book
  gets diluted by strongly-scoring English chunks from other works even
  though the Marathi book was explicitly requested.
- Topical bleed: "key messages in Amar Sandesh Sudha" retrieves chunks
  about "key messages" from unrelated books because the query token
  overlap with the intended book is small.
- Observed live: Chaitanya asked about *Amar Sandesh Sudha* — the answer
  cited passages from four OTHER books instead, correctly noting "the
  retrieved passages do not include a direct text from a work titled *Amar
  Sandesh Sudha*." The book has 368 chunks in the index; retrieval simply
  never surfaced them.

The retrieval pipeline already supports a hard `work_id` filter (via the
`req.work` param on `/ask`), but it's only set when the user manually picks
a work from a dropdown — free-text queries never trigger it. This ADR is
about auto-setting that filter when the query itself makes the intent clear.

## Decision

Add a **query-understanding pass** at the start of `_prepare_request` that
detects whether a query is explicitly asking about a single specific work,
and if so, sets `metadata_filter = {"work_id": <detected>}` — the same
mechanism the manual dropdown uses.

Detection is two-tier for cost and latency:

1. **Substring pass (0 ms, $0):** case-insensitive substring match of the
   query against every work's `title` / `title_en` / `title_translit`,
   longest-first. Titles shorter than 8 characters are excluded (too many
   false positives on topical words). If exactly ONE work matches, scope
   to it and skip the LLM.
2. **LLM pass (~500 ms, ~$0.001, Haiku):** runs ONLY when substring is
   ambiguous (multiple matches) or empty (nickname / paraphrase / translated
   title, e.g. "the Kaka book on sadhana", "गुरुदेवांच्या पत्रांबद्दल").
   Haiku picks a single `work_id` from a candidate list or returns null.
   Response is validated against the candidate set — the model can only
   return a legal `work_id`, never a hallucinated one.

Behavior fanout:

- **Single confident match →** scope; retrieval sees only that work's chunks.
- **Ambiguous (multiple valid works) →** do NOT scope; run unscoped. The
  sadhak asking to compare two works needs both.
- **No match →** run unscoped. Topical / conceptual queries are unaffected.
- **`req.work` already set (manual dropdown) →** honor it, skip detection.

The detected work is logged to the activity log's `auto_scope` field so the
maintainer can see when auto-scope fired and to which work — a diagnostic
for the "why did retrieval only surface this one book?" question the log
would otherwise not answer.

Env flags:

- `ENABLE_QUERY_UNDERSTANDING=0` disables the whole pass. Default on.
- `QUERY_UNDERSTANDING_LLM=0` disables the Haiku fallback, substring-only.
  Useful when Anthropic is down or for cost-sensitive dev.

## Consequences

- **Named-work queries route to the right corpus subset.** A query like
  "What is in Amar Sandesh Sudha?" auto-scopes to 368 chunks; the retriever
  picks the most relevant among them; the LLM sees passages from that
  specific book and can answer substantively.
- **Topical queries are unchanged.** No auto-scope fires unless the query
  names a work.
- **Ambiguous / comparative queries are unchanged.** "Compare X and Y" hits
  substring twice → not scoped → both books remain retrievable.
- **Manual dropdown still wins.** If the sadhak explicitly picks a work in
  the UI (`req.work` set), we honor it and skip auto-detection. No
  UI/UX regression.
- **Small added cost.** Substring hits cost nothing. LLM fallback runs on a
  small fraction of queries (nicknames + ambiguous cases), Haiku is cheap
  (~$0.001), no perceived latency because it runs BEFORE retrieval, in
  parallel with the retrieval's warm-up.
- **Silent failure mode:** wrong scope. A false-positive substring match on
  a short/common title (mitigated by the 8-char threshold) or an LLM
  mis-pick (mitigated by validation against the candidate set) would
  return only that work's chunks — the LLM correctly says "the retrieved
  passages don't cover the question" rather than hallucinating, and the
  activity log's `auto_scope` field lets the maintainer catch it. Recovery
  is a single-query correction (user asks without the work name, or with
  a different phrasing).
- **Precision-first tuning:** the substring threshold and the LLM
  validation are set to prefer "no scope" over "wrong scope." Recall (a
  correct scope missed) degrades to today's unscoped behavior — no worse
  than baseline. Precision (a wrong scope applied) is the failure we
  optimize against.

## Alternatives considered

- **Score boost instead of hard filter.** Boost the named work's chunks
  in the ranking but still let others surface. Rejected because in the
  observed failure mode, cross-language / topical bleed pushes the target
  book's chunks so far down the ranking that a moderate boost doesn't
  save them — they'd need boosts high enough to essentially amount to a
  filter. If we later find comparative queries need both a boost AND
  retrieval breadth, we can add score-boost as a second tier for ambiguous
  matches.
- **Every-query LLM pass.** Send every /ask through Haiku for full intent
  extraction. Simpler code (no substring fallback) but adds ~$0.001 per
  query universally. Rejected as unnecessary; ~80% of queries have no
  named work and the substring pass costs nothing.
- **Post-hoc: run unscoped retrieval, then check whether named-work chunks
  appear.** If not, run a second scoped retrieval. Rejected: two retrieval
  passes per query is expensive (~600 ms extra), and the LLM in the
  answering step can already do this in principle but doesn't reliably.

## Post-launch revision (2026-07-18) — LLM tier deleted; quoted-title tier added

**Observation.** On the first day of live traffic, the LLM fallback fired
twice — both were **false positives** on topical queries:

| Query | Method | Detected work | Correct? |
|---|---|---|---|
| "What are the key messages in Amar Sandesh Sudha?" | substring | amar-sandesh-sudha | ✓ |
| "What are the key messages in Amar Sandesh Sudha?" | substring | amar-sandesh-sudha | ✓ |
| "What are Gurudev's views on Bhakti?" | **llm** | charitra-tatvajnan-tulpule | ✗ |
| "What are Gurudev's views on Bhakti?" | **llm** | charitra-tatvajnan-tulpule | ✗ |

The Bhakti query is textbook topical — no book title, no paraphrase of
one. But Haiku pattern-matched "views" against the title fragment "Life
and **Philosophy**" (`charitra-tatvajnan-tulpule`) and returned it. The
metadata_filter then locked retrieval to that single biography; all 12
top chunks came from it; the answer was 100% biography-cited even though
an unscoped run of the same query surfaces Pathway to God (7), Bhagavadgita
(7), Studies in Indian Philosophy (3), Essays (2) — none of which contain
the biography above rank #128,130.

**Root cause.** The zero-substring-hit branch of `_llm_pick_work` asked
Haiku "which of these 40 works is the query about?" against a candidate
pool with no anchoring signal in the query. The prompt cannot
distinguish "the user paraphrased a book title" from "the user asked a
topical question and none of these works are the subject." Haiku
overreaches on surface pattern matches (English "views" ↔ English
"Philosophy") because the prompt asks it to *find a match*, not to
*decide whether a match exists*. The validation-against-candidate-set
defense guarded against hallucinated work_ids but not against
plausibly-wrong ones.

**Prior art — this is a named industry failure mode.** Independent
research (2026-07-18) confirmed:

- **Document-Level Retrieval Mismatch (DRM)** — Reuter et al. 2025
  ([arxiv 2510.06999](https://arxiv.org/abs/2510.06999)) — the retriever
  selects information from an entirely incorrect source document. Named
  and studied.
- **LangChain SelfQueryRetriever** — prompt says verbatim *"If there are
  no filters that should be applied return `NO_FILTER` for the filter
  value."* Failure mode: LLM ignores that instruction and invents
  filters on topical queries anyway (issue #29711).
- **LlamaIndex VectorIndexAutoRetriever** — silently falls back to an
  empty filter spec on parse failure.
- **OpenAI file_search, Google NotebookLM, Vertex AI Search, Perplexity,
  Anthropic Projects** — none ship an LLM classifier that decides
  "this query is about doc X." Every commercial system reviewed leaves
  scope selection to the caller (checkbox, toggle, filter param, project
  boundary). NotebookLM's own docs advise the user to *"mention source
  names in the query"* to narrow it.

The industry consensus is *don't auto-scope from an unanchored LLM;
require a hard signal*.

**Revised design — two deterministic tiers, no LLM.**

1. **Quoted-title tier (highest precision, explicit user intent).** Any
   double-quoted span in the query (straight `"..."`, curly `"..."` /
   `"..."`, German `„..."`) is treated as a hard title claim.
   Bidirectional case-insensitive substring match against
   `title` / `title_en` / `title_translit`. Exactly one work → scope,
   `method="quoted"`. Multiple works → ambiguous, no scope. Zero works
   matched → fall through to the substring tier. Single quotes are
   deliberately excluded — they collide with English possessives
   ("Gurudev's").
2. **Unquoted substring tier (backwards-compat, weak but 100% correct
   in observed traffic).** Case-insensitive substring match of every
   ≥8-char title against the query, longest-first. Exactly one work →
   scope, `method="substring"`. The 8-char threshold guards against
   short titles ("Vedant") colliding with topical words ("Vedanta").
3. **LLM tier: deleted.** No fallback, no per-query Haiku cost, no
   latency, no misfires.

The `QUERY_UNDERSTANDING_LLM` env flag is removed. `ENABLE_QUERY_UNDERSTANDING`
still gates the whole pass.

**Cross-lingual and paraphrase recall — user affordance replaces LLM guess.**
The GAP3 Devanagari case
("कार्लाईल कॉटेज बद्दल चरित्र आणि तत्वज्ञान या ग्रंथातून काय माहिती
मिळेल") no longer needs the LLM's paraphrase judgment: the user quotes
the title (`"चरित्र आणि तत्वज्ञान"`, or `"Charitra va Tatvajnan"`, or
`"Life and Philosophy"`, any variant that appears in `title_translit` or
`title_en`) and the quoted tier catches it directly. A one-line UI hint
in the ask box surfaces the convention:
*"Tip — put a book title in quotes to search only that book."*

For paraphrases NOT covered by any of `title` / `title_en` /
`title_translit` (e.g. "the Kaka book on sadhana"), the recall gap is
accepted — the future path is a `title_variants` alias index (RFC-018
adjacent), not an LLM.

**Alternatives considered.**

- *Stricter LLM prompt with explicit topical abstention + verbalized
  confidence + entailment check.* Rejected as first-line fix: still
  relies on the LLM's semantic judgment that just failed on Bhakti,
  adds latency and cost, has not been calibrated against real traffic.
  Preserved as an option once we have alias coverage and a labeled
  evaluation set.
- *Substring-only (no quoted tier).* Rejected: leaves the GAP3
  Devanagari case unrecoverable without alias data. Quoted tier is
  additive and adds no risk.
- *Quoted-only (drop substring tier).* Rejected: substring pass is 2/2
  correct in observed traffic; removing it would regress the
  Amar Sandesh Sudha UX for users who never learn the quote convention.

**Consequence for the `Consequences` section of the original decision.**
The "Small added cost" bullet is now zero — no LLM calls under any
tier. The "Silent failure mode: wrong scope" bullet no longer includes
the LLM mis-pick class; only substring false-positives (guarded by the
8-char threshold, empirically clean) or quoted-tier ambiguity (which
correctly returns no-scope).

**Evidence — regression tests.** `tools/tests/test_query_understanding_scope.py`
now has 21 tests, all deterministic:

- Tier 1: quoted exact / partial / Devanagari / transliteration / smart
  quotes / short title / ambiguous / no-match-fallthrough / no-match-but-
  substring-hits.
- Tier 1 safety: apostrophes in "Gurudev's" NOT parsed as quotes.
- Tier 2: substring behavior preserved (English, hyphenated, Devanagari,
  case-insensitive, longest-wins, short-title-below-threshold, ambiguous).
- ADR-018 regression: the Bhakti query returns None; a family of
  topical patterns ("views on X", "teachings on X", "How does Gurudev
  approach Y", Marathi equivalents, person queries) all return None.

## References

- ADR-011 / RFC-011 (intent tier weighting) — same layer of the pipeline,
  different signal.
- ADR-015 (hybrid BM25 + RRF), ADR-017 (dual-retrieval union) — retrieval
  mechanics this ADR builds on.
- RFC-018 (cross-reference citation alias index) — natural home for the
  title-alias extension that would restore paraphrase-detection recall.
- `tools/query_understanding.py::extract_mentioned_work` — the detector.
- `tools/server.py::_prepare_request` — wiring point.
- Activity log entry `2026-07-18T06:49:28+00:00` (local) — the Bhakti
  misfire that motivated the revision.
