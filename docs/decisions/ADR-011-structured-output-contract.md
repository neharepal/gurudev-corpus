# ADR-011: Structured-output contract for `/api/ask`

**Status:** PROPOSED
**Date:** 2026-06-17
**Author:** Neha (with Claude)
**Amends:** [ADR-007 Quote-first curation](ADR-007-quote-first-curation-pattern.md), [ADR-010 Q&A classification](ADR-010-qa-doctrinal-vs-meta-classification.md)

## Context

ADR-007 established the **content** contract: every answer is quote-first, in the source's own words, with thin connective tissue. ADR-010 added a within-mode branch (doctrinal vs. meta) and an audit hook (`_classification: ...` trailing line).

Both ADRs left the **format** contract loose. The system prompts described the desired markdown layout in prose ("output a Markdown blockquote", "use the prefix `**Why this passage:**`", "emit a single trailing audit line"). The chat-app `/api/ask` route then parsed that markdown into the typed `AskResponse` shape that the UI consumes.

This had three problems:

1. **Two contracts, one prompt.** The system prompt described both the content rules ("never invent facts", "verbatim quotes") and the format rules ("use this exact prefix in bold"). The model has to satisfy both, and prompt drift on the format side is silent — the markdown still looks plausible, but the parser falls off the happy path.
2. **Brittle parsing.** Converting "free-text markdown" → `AskResponse` is an extra step that can fail on small phrasing changes (a missing `**`, an unexpected divider). Each parser bug is a render bug.
3. **Single source of truth ambiguity.** `chat-app/lib/api.ts` `AskResponse` was the typed shape, but the LLM never saw those types — only an English description of "more or less this layout". The pydantic/TypeScript types and the prompt instructions had to be kept in sync by hand.

The natural fix is structured output: hand the LLM a JSON Schema for the desired response and force it to fill it. The Anthropic SDK supports two mechanisms for that:

- `client.messages.parse(...)` — the newer ergonomic API; takes a pydantic model directly.
- `tools = [...]` + `tool_choice = {type: "tool", name: ...}` — the original mechanism; the model must call the named tool with an `input` object that matches the tool's `input_schema`.

Both are functionally equivalent: the SDK validates types, the JSON Schema fixes the shape, and the model's output lands in a parseable object.

## Decision

Adopt **structured output as the wire contract**. The JSON contract — defined by the pydantic models in `tools/schemas.py` and mirrored in `chat-app/lib/api.ts` — is the source of truth for the response shape. The system prompts in `tools/prompts.py` describe **content** rules only (classification logic, quote-verbatim rule, cross-language paraphrase rule, dedup disclosure, honesty, what-you-must-never-do). They no longer prescribe markdown formatting.

For the Python 3.8 / anthropic 0.72 environment we use the **tool-use** mechanism:

- One tool per mode: `emit_qa_response`, `emit_pravachan_response`, `emit_reading_response`.
- Each tool's `input_schema` is the JSON Schema for that mode's response.
- The call sets `tool_choice = {type: "tool", name: <tool name>}`, forcing the model to emit via the tool.
- The tool's `input` is parsed back into the corresponding pydantic model (`QAResponse`, `PravachanResponse`, `ReadingResponse`).

This is functionally identical to `messages.parse()`; the SDK on the locked-to-3.8.5 anaconda env doesn't expose `.parse()`, so we use the older surface. Migration to `messages.parse()` later is a small refactor that does not change the JSON contract.

### Source of truth

- `tools/schemas.py` — pydantic models AND matching JSON Schema dicts (each shape is the same; the JSON Schema is the Anthropic-facing form).
- `chat-app/lib/api.ts` — TypeScript types that mirror the pydantic shapes. Any change to one must mirror to the other.
- The system prompts in `tools/prompts.py` describe what goes in each field, but not the format of the overall response.

### What the prompts now say

- **Content rules are unchanged:** verbatim quotes, classification logic (ADR-010), cross-language paraphrase via the `paraphrase` field on each `Quote`, dedup disclosure inside `whyChosen` / `whyThisExample`, the "never invent" rule.
- **Format rules are removed:** no more "emit a Markdown blockquote", "use the prefix `**Why this passage:**`", "end with `_classification: doctrinal_`". Those are replaced by the JSON Schema fields (`classification`, `whyChosen`, etc.).
- **The audit hook moves into the schema:** `QAResponse.classification` is a required enum field. The trailing markdown line was a workaround for free-text mode; we no longer need it.

### Failure mode

- If the model fails to use the tool, or the `input` fails pydantic validation, `ChatClient.ask_structured` raises a `RuntimeError`. The FastAPI handler maps that to **502** for the chat-app. The chat-app surfaces the message in its existing error toast — no UI change.
- We deliberately do NOT auto-retry or auto-fall-back to free-text. A schema-validation failure means either the prompt has drifted or the model is being non-compliant; both should be visible.

### Markdown rendering for humans

`tools/render.py` converts a structured response back into markdown for two purposes:

1. The CLI (`tools/chat.py`) prints a readable answer to the terminal.
2. The tuning sweep (`tools/tune_sweep.py`) writes per-question `.md` reports so we can diff runs.

This renderer is **not on the request path** for the chat-app. Production traffic flows `pydantic → JSON → fetch → TypeScript`. The renderer is for review only.

## Alternatives considered

- **Keep free-text markdown + parser.** Rejected: the brittleness was the motivating problem; doubling down on it makes future prompt edits costlier.
- **Use `messages.parse()` today.** Rejected for now: the SDK on the locked env does not expose it. We are tracking the upgrade as part of the eventual Python 3.9+ migration; ADR-011 explicitly says the migration is a small refactor — the JSON contract stays the same.
- **Tool-use but no pydantic mirror in `lib/api.ts`.** Rejected: the chat-app already has the typed shape; keeping the two in lockstep gives end-to-end type safety. The mirror is the entire point.
- **Per-field separate LLM calls (one for classification, one for content).** Rejected: a single call with a structured schema gets us the same field separation without extra round-trips or extra cost.

## Consequences

**Positive:**
- Prompt-drift on format is impossible — the JSON Schema is enforced.
- Adding fields (e.g., `Quote.paraphrase`) requires updating only `schemas.py` and `api.ts`. No prompt rewrite needed for the format side.
- The wire shape is self-describing — anyone reading `lib/api.ts` or `tools/schemas.py` sees the contract.
- The chat-app's `/api/ask` route becomes a thin proxy; all retrieval + classification + formatting lives in the Python service.

**Negative:**
- The system prompts are longer in the "what to put in each field" sense, even as they shed the format-prose. Net length is roughly comparable.
- Tool-use adds a small token overhead vs. free-text (the tool schema is part of the input). Mitigated by prompt caching (the system prompt and the tool schema are both cached).
- We have two places — `schemas.py` and `lib/api.ts` — that must agree. Mitigated by keeping the shapes small and using the pydantic dump as the wire format (no hand-written serialization).

## Implementation notes

- **Tool definition shape** (per mode):
  ```python
  {
      "name": "emit_qa_response",
      "description": "...",
      "input_schema": QA_INPUT_SCHEMA,  # JSON Schema dict, not pydantic
  }
  ```
- **Parsing** in `ChatClient.ask_structured`:
  ```python
  tool_use = next(b for b in response.content if b.type == "tool_use")
  parsed = response_model.model_validate(tool_use.input)
  ```
- **CORS** is allowed for `http://localhost:3000` only (the local Next.js dev). Production deployment will need to set `GURUDEV_BACKEND_URL` and expand the allowlist.
- **Health check:** `GET /health` returns `{ok, model, chunks}` so we can monitor that the embedding model + corpus loaded cleanly.

## Future migration to `messages.parse()`

When the anaconda env moves to Python 3.9+ and the Anthropic SDK to 0.40+, replace the tool-use block in `ChatClient.ask_structured` with:

```python
response = self.client.messages.parse(
    model=...,
    response_format=response_model,  # pydantic class directly
    ...
)
parsed = response.parsed
```

No change to the JSON Schema, the prompts, the chat-app, or the FastAPI surface. The migration is a single function body.

## References

- [ADR-007 Quote-first curation](ADR-007-quote-first-curation-pattern.md) — content contract preserved
- [ADR-010 Q&A classification](ADR-010-qa-doctrinal-vs-meta-classification.md) — `classification` is now a schema field
- `tools/schemas.py` — pydantic + JSON Schema source of truth
- `chat-app/lib/api.ts` — TypeScript mirror
- `tools/server.py` — FastAPI surface

## Amendment (2026-06-22): Q&A citations quote by reference

Doctrinal Q&A citations no longer ask the model to emit the verbatim `quote.body`
(plus `workTitle`/`kind`/`author`). Instead the model emits a **reference** —
`quote.passage` (the passage letter), `quote.quoteStart`, `quote.quoteEnd` — and
the backend splices the verbatim `body` and authoritative attribution from the
referenced chunk's metadata (`tools/schemas.py:splice_qa_citations`). The **wire
`Quote` shape the chat-app consumes is unchanged** — splicing happens server-side
before pydantic validation, so the frontend is untouched.

Motivation was latency (the model stalled multi-seconds reproducing long verbatim
text); measurement showed the stall is mostly intrinsic per-request grounding and
only partly recovered, but the change is retained for its **correctness** benefit:
quotes are now byte-identical to the source and attribution can't drift. Other
modes (pravachan, reading) still use the verbatim `Quote`. See
[PLAN-reference-and-splice-citations.md](../PLAN-reference-and-splice-citations.md).
