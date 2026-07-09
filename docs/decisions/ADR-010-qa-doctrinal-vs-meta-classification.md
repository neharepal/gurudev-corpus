# ADR-010: Q&A internal classification — doctrinal (quote-first) vs meta (plain prose)

> **SUPERSEDED — 2026-07-08**
> The doctrinal/meta split described in this ADR is reversed. Q&A is now a single
> unified quote-and-synthesize mode: every answer may include `citations` (verbatim,
> by reference), `framingParagraphs`, `synthesis`, and `references` in any combination.
> The LLM no longer classifies before branching; `classification` is retained in the
> schema only as an optional audit hint. The frontend already branches on
> `citations.length`, not on this field. See `tools/prompts.py` and `tools/schemas.py`
> for the updated rules.

**Status:** SUPERSEDED (see note above)
**Date:** 2026-06-14
**Author:** Neha (with Claude)
**Amends:** [ADR-007 quote-first curation pattern](ADR-007-quote-first-curation-pattern.md)

## Context

ADR-007 committed the project to a quote-first generation contract: every Q&A
answer leads with verbatim passages plus attribution, and only the thinnest
connective tissue is written in the assistant's voice. That contract is right
for *doctrinal* questions — "What are Gurudev's views on Bhakti?", "How does
Kabir's reading of the Name relate to Gurudev's?" — where the user wants the
source's own words and any paraphrase would be a loss.

But the same Q&A mode also receives *meta* questions — "Who was Bhausaheb
Maharaj?", "When was Gurudev born?", "Which book should I read first?",
"What is the relationship between Nimbal and Allahabad in his life?". For
these, surfacing verbatim quotes (a) is awkward — biographies and indexes
are not written to be quoted as teachings, (b) often returns no good chunk
at all, and (c) trains the user to think Q&A only handles "deep" questions.

Two designs were on the table:

1. **Add a 4th mode** — "About this corpus" or "Ask about the lineage" —
   distinct from Q&A. Users select it explicitly.
2. **Internal classification inside Q&A** — Q&A accepts anything; the LLM
   decides per-call whether to answer in doctrinal or meta format.

A 4th mode forces the user to learn an architectural distinction that
serves the system, not the user. The user-facing mental model is "ask
anything"; splitting it into "ask doctrinal anything" vs "ask meta
anything" is worse UX than letting the model pick the right shape.

## Decision

Keep a single Q&A mode. Inside the Q&A generation call, the LLM first
classifies the question as **doctrinal** or **meta**, then branches into
the corresponding output format.

**Doctrinal format** (unchanged from ADR-007):
- Framing sentence
- 2–5 verbatim Markdown blockquotes with attribution
- `**Why this passage:** <one sentence>` rationale immediately after each
- Optional 1–2 sentence synthesis at end

**Meta format** (new — does NOT inherit the quote-first contract):
- 2–4 sentence plain prose answer in the user's language
- Optional "Works referenced" list of titles + locations (no quotes)
- No `Why this passage` lines, no synthesis section
- If the corpus is silent, say so plainly; never invent biographical facts

**Tie-break rule:** when a question could be read either way AND retrieval
returned good doctrinal material, prefer doctrinal. Showing a faithful
passage is safer than risking a paraphrased fact.

**Audit hook:** every Q&A response ends with a single trailing line
`_classification: doctrinal_` or `_classification: meta_` so we can review
how the LLM is splitting questions in the wild.

## How this amends ADR-007

ADR-007's quote-first contract now applies to **doctrinal Q&A only**. The
underlying principle of ADR-007 — "the user should hear the source, not a
paraphrase" — is preserved: doctrinal answers still quote verbatim. Meta
answers are a different speech act (the user asked a factual question, not
"what does the literature say"), so quoting is not the appropriate response
form.

ADR-007's prohibition on inventing material remains absolute across both
formats. The honesty contract is unchanged.

## Alternatives considered

- **4th mode ("Meta") in the mode picker.** Rejected: forces users to
  classify their own question by architectural category. The user-facing
  mental model is "ask anything"; an explicit Meta tab degrades that.
- **Quote-first for everything, including meta.** Rejected: meta retrieval
  rarely returns chunks that are well-formed teachings. Forcing a verbatim
  quote for "Who was Bhausaheb Maharaj?" returns either an awkward
  bibliographic fragment or nothing at all.
- **Two endpoints (`/api/ask` and `/api/ask-meta`).** Rejected: the request
  shape is identical, the user doesn't know which to call, and the
  classification decision has to happen on the server anyway. One endpoint
  + internal classification keeps the contract simple.
- **Separate metadata retrieval index.** Considered for v2. For v1 a single
  retriever is sufficient; if meta-question recall is poor in practice, we
  add a structured metadata index later. Not blocking this decision.

## Consequences

**Positive:**
- "Ask anything" stays true. No mode-picker friction for meta questions.
- The quote-first contract is preserved where it matters and is dropped
  where it would hurt.
- One Q&A code path, one prompt, one response schema — the classification
  is a branch inside the prompt, not a fork in the system.
- Audit trail via the trailing `_classification:` line lets us watch the
  classifier's behavior without instrumentation overhead.

**Negative:**
- The Q&A system prompt is longer (it now describes both formats and the
  classifier step). Mitigation: the doctrinal sub-format is materially the
  same prose as ADR-007's original instructions, so the delta is the
  classifier + meta sub-format only.
- Misclassification is possible. The tie-break rule (prefer doctrinal)
  errs on the safer side — a faithful quote is rarely a wrong answer; an
  unsupported biographical assertion is.

## Implementation notes

- **Classification happens inside the same LLM call.** Single prompt,
  branched output. No separate classifier call, no second LLM round-trip.
- **Schema extension** (data/mock-conversations.ts and lib/api.ts):

  ```ts
  type Reference = { workTitle: string; location?: string; author?: string };
  type QAAnswer = {
    kind: "qa";
    classification?: "doctrinal" | "meta";  // emitted by the LLM; for audit
    question: string;
    framing: string;
    citations: QACitation[];                // populated for doctrinal; [] for meta
    references?: Reference[];               // optional; for meta
    synthesis?: string;                     // doctrinal only
  };
  ```

  The same `AskResponse` Q&A variant in `lib/api.ts` mirrors this.

- **UI render branch** (`app/chat/page.tsx` `QAAnswerBody`):
  - `answer.citations.length > 0` → doctrinal layout (existing)
  - `answer.citations.length === 0` → meta layout: render `framing` as the
    answer paragraph; render `references` (if any) under a small
    "Works referenced" / "संदर्भ" heading; no quote blocks, no
    "Why this passage" lines, no synthesis section.

- **Prompt update** (`tools/prompts.py` `SYSTEM_PROMPT_QA`): adds a
  "Step 0: classify the question" section, then defines the doctrinal
  and meta sub-formats, then a cross-language section that applies to
  both. Ends with the audit-line requirement.

- **Single retriever for v1.** No separate metadata index yet. Re-evaluate
  once we have real usage data on meta-question recall.

## References

- [ADR-007 Quote-first curation pattern](ADR-007-quote-first-curation-pattern.md) — amended by this ADR
- [PRD.md §4 Phase 2 Goals](../PRD.md)
- Conversation 2026-06-14 — user feedback distinguishing doctrinal from biographical/navigational questions
