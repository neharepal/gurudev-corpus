# ADR-014: Conversational follow-ups carry history and new-material enforcement

**Status:** ACCEPTED
**Date:** 2026-06-25
**Author:** Neha (with Claude)

## Context

Q&A follow-up questions were sent as independent, single-turn requests with no knowledge of the prior conversation (F2, QA findings 2026-06-25). The `AskRequest.history` field existed in `tools/schemas.py` but was documented as "not used by the single-turn pipeline today." The result was that asking "Can you give more such examples?" after an initial answer would re-cite passages already shown, because the model had no context of what "such examples" referred to or which passages were already in front of the user.

## Decision

Q&A follow-up requests now include the **full conversation history** (prior user turns and assistant answers) in `AskRequest.history`. The Q&A system prompt instructs the model:

1. Read the conversation history before answering.
2. Do not repeat passages already cited in earlier turns.
3. Treat the follow-up as a continuation of the conversation, not a standalone question.

The `history` field was already in the `AskRequest` pydantic schema and the TypeScript `AskRequest` interface on the frontend; activating it required wiring the prior turns from the frontend's session state into the request body, and updating the server-side prompt assembly to pass history as Claude messages before the new question.

Follow-ups remain **ephemeral** (session-scoped, not persisted to disk). See commit `bb4476f` for the prior decision to make follow-ups non-persistent; `020647e` activates history without changing persistence.

## Alternatives considered

- **Separate "threaded" endpoint (`/api/thread`).** Rejected: the existing `/api/ask` shape already includes `history`; no new endpoint needed. Adding a second endpoint would split the API surface for no benefit.
- **Server-side session store (persist history server-side by session id).** Considered for v2. For v1, the frontend sends history on each request. Simpler, stateless server. Migration to server-side sessions (post-auth) is straightforward: replace the payload with a session id and let the server look up history.
- **Re-embed prior answers and use them as retrieval filters.** Overcomplicated. Sending history as conversation context lets the model do the "don't repeat" reasoning in the generation step without additional retrieval machinery.

## Consequences

**Positive:**
- Follow-up questions feel conversational. "Give more examples" or "Can you say more about that?" produce genuinely new material.
- No new passages already in the user's view are re-cited, making follow-up answers denser with new content.
- The existing schema and TypeScript interface required no shape changes — only wiring.

**Negative:**
- Each follow-up request is larger (history adds tokens to the input). Mitigated by Anthropic prompt caching; the system prompt and tool schema are cached, and the history tokens are the incremental cost.
- Very long conversations (10+ turns) could push input length into expensive territory. For the demo scale (2–3 follow-up turns typical), this is not a concern.

## References

- [RFC-003 Retrieval & RAG strategy](../rfc/RFC-003-retrieval-and-rag.md) — amended (2026-06-25) to record this
- [ADR-011 Structured output contract](../decisions/ADR-011-structured-output-contract.md) — `AskRequest.history` field
- QA finding F2 in [docs/qa-findings-2026-06-25.md](../qa-findings-2026-06-25.md)
- Commit `020647e` — implementation; commit `bb4476f` — prior ephemeral decision
