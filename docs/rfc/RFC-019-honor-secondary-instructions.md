# RFC-019: Honor secondary instructions in the user's question

**Status:** ACCEPTED 2026-07-22 (decisions: reuse `synthesis` field; surface
one honest line when an instruction cannot be fully honored; ship straight
to prod; scope to `qa` mode only, extend to `pravachan` after validation)
**Author:** Neha (with Claude)
**Created:** 2026-07-22
**Last updated:** 2026-07-22
**Related:** ADR-007 (quote-first curation), ADR-010 (Q&A classification —
reversed 2026-07-08), ADR-011 (structured-output contract),
RFC-014 (retrieval/grounding), RFC-017 (small-to-big + arthasahit)

## Summary

Every user question may carry, alongside the factual ask, one or more
**secondary instructions** — how to format the answer (bullets, table, one
sentence), how to order it (chronological, by importance), how to scope it
(only from work X, only after 1940), what to exclude, what language, what
persona. Today the QA path ignores everything past the topic: the model
treats the message as a retrieval query and returns a prose framing + citation
cards regardless of what the reader actually asked for. This RFC teaches the
model to read the whole message and shape the answer accordingly, without
adding a per-intent classifier or per-format router. The vehicle is (a) a
prompt-level "primary ask + secondary instructions" reading rule and (b)
promoting `synthesis` from an optional afterthought to the **user-shaped
answer** — a markdown-capable field that carries bullets, tables, ordered
lists, or one-sentence replies as the question demands. Citations remain
untouched: always shown, always the evidence.

## Motivation

Concrete case (2026-07-22, two independent runs by Ninad Pingale and Neha):

> **Q:** "List of places Gurudev visited. Only list in bullet points."
>
> **A (both runs):** A prose framing paragraph (*"…mention a number of
> places… Here is what the available passages record."*) followed by 5–6
> citation cards. No bulleted list of place names anywhere. Different runs
> returned overlapping-but-different subsets.

The reader gave two instructions: (1) enumerate places, (2) as bullets. The
app honored neither cleanly. It surfaced citations that happened to mention
places, and the model wrote a prose framing that soft-acknowledged the
listing ask without producing a list. The bullets were not emitted because
**there is nowhere in the schema for bullets to live** — `framing` is a short
prose intro, `synthesis` is unused for most doctrinal Q&A, citations are
individual quote cards. A user-shaped answer has no home.

This generalises beyond format. Every one of these is currently invisible to
the model:

- "Answer in one sentence."
- "Only cite from Ranade's own writing."
- "Chronological order please."
- "In Marathi."
- "Focus on the 1940s."
- "Compare Bhausaheb and Amburao."
- "No repetition."

Each is a legitimate reader request, none of them changes what to retrieve
in a structural sense, and none of them is honored today. The failure mode
is quiet: the reader gets a plausible-looking answer that just isn't what
they asked for, and there is no error to flag.

### Why an intent classifier is the wrong fix

The temptation is to detect "list-of" questions and route them through a
listing template. This scales badly:

- Each new secondary-instruction type needs a new detector + template.
- Combinations multiply ("chronological list in Marathi, one sentence per
  entry").
- The model already understands English (and Marathi). Teaching it to read
  the whole message is cheaper than teaching a Python router to parse it.
- Real questions carry instructions we cannot pre-enumerate ("respond as if
  explaining to a first-time visitor to Nimbal", "keep it under 100 words",
  "exclude anything Kakasaheb wrote").

The general fix operates one level up: **prompt the LLM to read the whole
message as instructions**, and give the output schema room to carry a
user-shaped answer.

## Goals

- **Every explicit secondary instruction in the user's message is honored,**
  to the extent the retrieved passages allow.
- **Citations remain first-class,** exactly as today. ADR-007 (quote-first)
  is preserved; this RFC does not weaken the evidence contract.
- **Zero per-intent branching in Python.** The change is prompt + schema +
  one frontend render site, not a new dispatch layer.
- **Graceful under-honor.** If an instruction cannot be honored (chronological
  order but passages lack dates; 10 items requested but only 4 exist), the
  answer honors what it can and says one line about what it couldn't.
- **No padding to satisfy format.** Model must not invent facts to fill a
  requested item count or fabricate dates to satisfy an ordering ask.
- **No citation loss to satisfy brevity.** "Answer in one sentence" shortens
  `synthesis`, never suppresses citations.

## Non-goals

- **Not a new intent classifier.** No `is_listing_question(q)` helper, no
  format routing table.
- **Not a rewrite of retrieval.** Retrieval stays as today (RFC-014 + RFC-017).
  Instructions about *how to answer* are LLM-side; instructions about *what to
  retrieve* (e.g., "only from Bhagavadgita") stay a retrieval concern and are
  out of scope for this RFC.
- **Not a new mode.** No `/ask?mode=listing` variant. This lives inside the
  existing `qa` mode.
- **Not persona / voice engineering.** "Respond as X" style asks are honored
  where compatible with ADR-007 (quote-first, never invent), but persona
  design is out of scope.

## Proposed design

Three touchpoints: prompt, schema, frontend renderer. Plus a small test
harness.

### 1. Prompt: primary + secondary decomposition

Add a top-of-prompt reading rule to `SYSTEM_PROMPT_QA` in
`tools/prompts.py`. Sketch:

> **READ THE WHOLE QUESTION**
>
> Every user message contains (a) a primary factual ask and (b) zero or more
> secondary instructions about **how** to answer. Secondary instructions
> include, but are not limited to:
>
> - **Format** — bullets, table, one sentence, prose paragraph, ordered list.
> - **Length** — "in one sentence", "briefly", "under 100 words".
> - **Ordering** — chronological, by importance, alphabetical.
> - **Scope inside the retrieved evidence** — "only what Ranade himself
>   wrote", "only from the biography", "focus on the 1940s".
> - **Exclusions** — "no repetition", "don't mention X".
> - **Language** — answer in Marathi, answer in English, mixed.
> - **Comparison shape** — "compare X and Y", "list differences".
>
> You must honor every secondary instruction the retrieved passages allow.
> Place the honoring answer in the `synthesis` field (markdown allowed).
> `framing` is a 1–2 sentence intro; citations are the evidence, always
> shown regardless of format or length instructions.
>
> **If an instruction cannot be honored** — the passages lack the ordering
> key, the requested item count exceeds available evidence, the requested
> language would require translation the passages don't support — honor
> what you can, then add one short line to `synthesis` naming what was
> not fully honored and why. **Never pad, invent dates, or manufacture
> items** to satisfy a format ask.
>
> **When the user gave no secondary instructions,** produce the default
> shape: `framing` as a 1–2 sentence prose intro; `synthesis` may be
> empty or a short synthesizing paragraph.

The prompt also gains a small positive example:

    Q: "List of places Gurudev visited. Only list in bullet points."
    → framing (1-2 sentences): brief context.
    → synthesis: markdown bulleted list of place names, one bullet per
      place, with a parenthetical passage-label (A, B, ...) linking each
      to a citation card below.
    → citations: quote cards as usual (evidence for each bullet).

And an anti-example:

    ANTI:
    Q: "List all initiations. Chronological."
    Passages give 6 initiations but only 2 have dates.
    → BAD: model invents plausible-looking years for the other 4 to
      satisfy the ordering.
    → GOOD: chronological where dates exist, then an "undated" section
      with the remaining 4, plus one line "4 of the 6 initiations have
      no date in the source passages."

### 2. Schema: promote `synthesis` to the user-shaped answer

The current `QAResponse` shape (`tools/schemas.py:160`):

    framing            : str = ""              # short prose intro
    framingParagraphs  : Optional[List[str]]   # long-answer alternative
    citations          : List[Citation]        # evidence cards
    synthesis          : Optional[str] = None  # rarely used

After this RFC:

    framing            : str = ""              # UNCHANGED — short prose intro
    framingParagraphs  : Optional[List[str]]   # UNCHANGED
    citations          : List[Citation]        # UNCHANGED
    synthesis          : Optional[str] = None  # PROMOTED: markdown-capable,
                                               # carries user-shaped answer

**No new field.** `synthesis` already exists; it becomes the natural home for
the format-honoring answer body.

**Markdown allowed in `synthesis`.** The frontend already renders inline
markdown (bold/italic via `chat-app/lib/render-inline-md.ts` shipped
43dde13). Block-level markdown (`- ` bullets, `1. ` ordered lists, tables)
needs a small rendering upgrade — see §3.

**Validator preserves the "at least one of framing / framingParagraphs"
rule.** `synthesis` remains optional; default behavior is unchanged.

**No wire-shape break.** `chat-app/lib/api.ts` `AskResponse` already types
`synthesis?: string | null`. Frontend gets a longer, richer synthesis on
some answers and nothing changes on others.

### 3. Frontend: render block markdown in `synthesis`

Current `synthesis` render sites (from RFC context + git grep):

- `chat-app/app/chat/page.tsx` — inline-md via `renderInlineMd()` only.
- `chat-app/app/read/[slug]/page.tsx` — same, drawer synthesis.

Add a block renderer, `chat-app/lib/render-block-md.ts`, that handles:

- `**bold**`, `*italic*` — already via `render-inline-md.ts`.
- `- item` / `* item` → `<ul><li>…</li></ul>`
- `1. item` → `<ol><li>…</li></ol>`
- `| col | col |` two-line tables → `<table>`
- Blank lines → paragraph breaks.

Keep the same React-node-only pattern used in `render-inline-md.ts`: zero
`dangerouslySetInnerHTML`, walk tokens, emit `React.createElement` nodes.
XSS surface stays flat.

**Deliberately narrow markdown subset.** No headings, no images, no links
(the LLM shouldn't be emitting arbitrary URLs into synthesis; citation cards
carry the readSlug deep-links). Adding features later is additive.

### 4. Citation deep-links from `synthesis`

When `synthesis` lists items ("- Nimbal", "- Nashik") that map 1:1 to
citations, the reader wants to click a bullet and land on the backing
citation. Two options:

- **(a) Passage-label suffix.** LLM ends each bullet with `(A)` / `(B)`
  referring to the passage-label already threaded through citations. Cheap
  to parse in the frontend: match `\(([A-Z])\)` at end of `<li>`, wire an
  anchor scroll to the matching citation card. Minimal ceremony.
- **(b) First-class link markdown.** Extend the block renderer to accept
  `[Nimbal](passage:A)` and render as `<a href="#cite-A">`. Cleaner in the
  markdown, more work in the renderer, higher risk of the model emitting
  malformed link syntax.

**Recommendation: start with (a).** It piggybacks on the passage-label
convention that already exists (`prompts.format_chunks_for_prompt`), no new
markdown syntax to teach, easy to skip in the renderer if the LLM omits it.
Revisit (b) if we find (a) is too fragile.

### 5. Tests

Under `tools/tests/`:

**`test_qa_secondary_instructions.py`** (prompt-hygiene, no LLM call):

- `test_prompt_declares_primary_plus_secondary_reading`: assert the
  prompt names the phrase "secondary instructions" (or equivalent) and
  lists at least three instruction types (format, length, ordering).
- `test_prompt_has_no_padding_rule`: assert the prompt bans fabricating
  items or dates to satisfy an ask.
- `test_prompt_says_citations_always_shown`: assert brevity/format asks
  cannot suppress citations.

**`tools/tune_sweep_secondary_instructions.yaml`** (live-LLM tuning
harness, opt-in via `tune_sweep.py`):

Ten hand-authored questions each combining a factual ask with a specific
secondary instruction. Expected checks (regex / structural):

    - Q: "List of places Gurudev visited. Only bullet points."
      expect_synthesis_matches: '^\s*-\s+' (bullets present)
      expect_synthesis_min_lines: 3
      expect_citations_min: 3
    - Q: "In one sentence, who was Bhausaheb Maharaj?"
      expect_synthesis_max_words: 40
      expect_citations_min: 1
    - Q: "Compare Bhausaheb and Amburao in a table."
      expect_synthesis_matches: '^\|'
      expect_citations_min: 2
    - Q: "Answer in Marathi. Where did Gurudev meet his master?"
      expect_synthesis_matches: '[ऀ-ॿ]+'  # Devanagari
    - ... (six more covering ordering, exclusions, scope, brevity, combos)

Sweeps run before every merge that touches `SYSTEM_PROMPT_QA` or
`QAResponse`. Failures block. Cost per full sweep ≈ 10 questions × $0.03 ≈
$0.30.

### 6. Backward compatibility

- **No wire break.** All existing clients (chat-app, CLI) already accept
  `synthesis?: string | null`.
- **Default behavior unchanged.** Questions without secondary instructions
  produce the same `framing` + `citations` as today. `synthesis` stays
  empty or short.
- **Existing tests still pass.** The `test_qa_system_prompt_hygiene.py`
  jargon-ban rules (2026-07-22, commit cad85d5) are additive; this RFC
  layers on top.

## Alternatives considered

- **Per-intent Python router.** Detect "list of" / "compare" / "in one
  sentence" via regex or a classifier LLM call, then dispatch to
  per-intent templates. Rejected: infinite catalog of intents, poor
  composability, moves logic that belongs in the LLM into brittle
  Python code. The whole reason we're on structured output (ADR-011) is
  to *reduce* Python-side formatting logic.
- **Free-text markdown output** (revert ADR-011 for the answer body).
  Rejected: throws away the structured-output guarantees, re-introduces
  the parser fragility ADR-011 was written to eliminate. Nothing about
  honoring secondary instructions requires losing the schema.
- **Model fine-tune** on a bank of question+instruction+ideal-answer
  examples. Rejected as premature: we're on a general Claude model that
  already follows format instructions well when told to; the failure is
  that we're NOT telling it to. Fine-tune becomes interesting later if
  prompt-level instruction-following plateaus.
- **New `synthesis_shape` enum field** (`"prose" | "bullets" | "table" |
  "single-sentence"`) that the model fills, and a frontend switch that
  renders per shape. Rejected: encodes format choices twice (the shape
  field AND the synthesis body), risks divergence, and doesn't
  generalise to combinations ("chronological table in one paragraph"
  wouldn't fit a single enum). Markdown IS the format vocabulary; use
  markdown.
- **Delegate the whole answer to `framingParagraphs`.** Rejected:
  `framing` / `framingParagraphs` are the "intro"; overloading them
  with the user-shaped body would blur the schema semantics we already
  have and would need the same markdown-rendering work anyway.
- **Reject secondary instructions and be explicit about it** (e.g.,
  "the app answers with citations; format asks are ignored"). Rejected:
  user-hostile; the whole point of a devotional-corpus RAG app is to
  serve the reader's actual question.

## Tradeoffs & risks

1. **Model may over-honor format asks by dropping evidence.** "Answer in
   one sentence" → model shortens synthesis AND drops citation count.
   Prompt rule "citations always shown regardless of length" mitigates;
   test harness verifies.
2. **Model may pad to satisfy count-based asks.** "List all 10 places"
   when only 6 are in evidence → invents 4. Prompt rule explicit; test
   harness includes a "requested-count exceeds evidence" case.
3. **Streaming shape.** RFC-010 (progressive streaming) emits fields
   incrementally. A large markdown `synthesis` is chunky; the streaming
   contract needs to send synthesis chunks in order (already the case,
   since it's a string field), and the frontend renderer needs to be
   safe against partial markdown (e.g., unclosed `**`). Verify in
   integration test.
4. **Markdown renderer XSS.** Any new markdown feature is a potential
   XSS surface. We stay with React-node emission (no
   `dangerouslySetInnerHTML`); each block-level construct is
   whitelisted; no attribute-carrying tags. Same discipline as
   `render-inline-md.ts`.
5. **Prompt drift under future edits.** The primary+secondary rule is
   several paragraphs; future edits may nibble at it. Test harness
   (`test_prompt_declares_primary_plus_secondary_reading`) locks the
   rule name and the type list.
6. **Multilingual synthesis.** "Answer in Marathi" produces Devanagari
   `synthesis`. Fonts + block-md renderer must both handle Devanagari
   (they do today for citations; verify for synthesis).
7. **Cost.** Slightly larger prompt (the reading rule), slightly larger
   completions (synthesis is now substantive on many answers).
   Estimate: +200 tokens system, +150 tokens per answer average → ~$0.001
   per /ask. Negligible at current volume.
8. **User confusion when instructions can't be honored.** The "one line
   saying what wasn't honored" needs to feel like transparent honesty,
   not an excuse. Wording in the prompt example matters; needs eyeball
   review during rollout.

## Open questions

1. **Should retrieval also read secondary instructions?** "Only cite from
   Ranade's own writing" is *both* a synthesis constraint AND a
   retrieval constraint (filtering by `author='gurudev_ranade'`). Doing
   both at retrieval time is cheaper and cleaner, but requires a
   separate query-understanding pass (query rewriting per ADR-018) that
   currently only fires on named-work detection. Defer to a follow-up
   RFC; this RFC handles them at synthesis time only, which is correct
   but wasteful (retrieval returns junk that synthesis then ignores).
2. **Passage-label deep-linking in bullets (§4 option (a) vs (b)).**
   Start with (a); revisit if fragile.
3. **What about `pravachan` mode?** `PravachanResponse` has a similar
   shape (framing + examples). Secondary instructions apply there too
   ("give me three pravachan examples about anger in one line each").
   Not in scope for this RFC — ship for `qa` first, extend to
   `pravachan` in a follow-up if the pattern generalises cleanly.
4. **`reading` mode is out of scope entirely.** It's not a question-
   answering flow; secondary instructions don't apply the same way.
5. **When secondary instructions conflict with each other** ("in one
   sentence with bullets"), the LLM should reconcile by honoring the
   more specific one. Whether we spell this out in the prompt or trust
   the model to reconcile is TBD; propose we leave it implicit and see
   how the tuning sweep behaves.
6. **When secondary instructions conflict with ADR-007 (quote-first).**
   "Answer without citations" — must be refused, citations are the
   product. Prompt makes this explicit: "citations always shown."
7. **Retention.** How long should the "not fully honored" line stay in
   the answer? Some readers will find it annoying on repeat use. Could
   be UI-side collapsible; defer to post-launch feedback.

## Rollout

1. **Ship prompt change + schema doc + test harness.** No code path
   changes in Python; `synthesis` field already exists.
2. **Ship `render-block-md.ts` + wiring at both synthesis render
   sites.** Vercel auto-deploys.
3. **Manual sanity sweep** on the 10-question tuning harness; eyeball
   the outputs; adjust prompt wording as needed.
4. **Announce in the admin activity dashboard** so we can watch what
   real users ask and how synthesis handles it.
5. **After ~1 week of live traffic**, review admin/activity for
   secondary-instruction questions and grade honoring rate. Iterate on
   prompt if needed. If honoring rate is low on a specific type (say,
   ordering), consider a targeted example addition.
6. **Extend to `pravachan` mode** once the pattern is validated in `qa`.

## References

- ADR-007 (quote-first): evidence contract preserved by this RFC.
- ADR-011 (structured-output contract): the schema mechanism this RFC
  extends; no wire break.
- RFC-014 (retrieval/grounding): retrieval side unchanged.
- RFC-017 (small-to-big): parent/child chunking unchanged.
- RFC-018 (citation aliases): unaffected; alias resolution happens
  server-side before synthesis.
- `tools/prompts.py::SYSTEM_PROMPT_QA` — target of the prompt change.
- `tools/schemas.py::QAResponse` — target of the field promotion (no
  new field).
- `chat-app/lib/render-inline-md.ts` — precedent for the block
  renderer's React-node emission pattern.
- `tools/tests/test_qa_system_prompt_hygiene.py` — precedent for
  prompt-level assertion tests.
- 2026-07-22 admin/activity rows for question "List of places Gurudev
  visited. Only list in bullet points." — motivating case.
