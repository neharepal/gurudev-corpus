# RFC-010: Progressive streaming for the answer surface

**Status:** ACCEPTED 2026-06-18
**Author:** Neha (with Claude)
**Created:** 2026-06-17
**Last updated:** 2026-06-18

## Picks confirmed (Q1–Q5, 2026-06-17 discussion)

- Q1: hand-rolled partial-JSON state machine in `tools/streaming.py`
- Q2: phase 1 includes `delta` events for long string fields
- Q3: emission order, reconciliation on `done`
- Q4: heartbeats on by default, 15s
- Q5: CLI tools unchanged (non-streaming JSON path via `Accept: application/json`)

## Summary

Replace the current "wait silently, then render the whole answer at once" UX with **end-to-end progressive streaming**: the LLM streams its tool-call JSON fields, the FastAPI service forwards them as Server-Sent Events (SSE), the Next.js `/api/ask` route proxies the SSE stream, and the React chat surface renders each structured field (framing, citations, examples, synthesis) the moment it arrives. The structured output contract from ADR-011 is preserved — we stream the *fields* of the same JSON shape, not raw markdown.

## Motivation

A user tested the chat-app against the real backend (2026-06-17) and the first piece of feedback was: *"took way too long for the answer to render. Not a good use experience."*

Current end-to-end latencies (measured 2026-06-17 sweep run `20260617-143621`):

| Mode | LLM time | Output tokens |
|---|---|---|
| QA (EN) — first hit | 14.7s retrieval + 39.4s LLM = **54s** | 1784 |
| QA (EN) — cached prompt | 0.6s + 9–14s = **10–15s** | 369–627 |
| QA (MR) | 0.6s + 39s = **40s** | 1910 |
| Pravachan (MR) | 0.6s + 87s = **88s** | 3500 (capped) |
| Reading | 0.4s + 4.5s = **5s** | 280 |

QA at 10–15s with no feedback feels broken; Pravachan at ~90s is intolerable without progressive output. The product is a sadhak-facing devotional tool — the user expects a research-like flow where text accumulates while they read along, not a CLI-like "submit then block." Streaming is the single highest-leverage UX intervention available; nothing else reduces *perceived* wait time as cheaply.

A loading spinner with "Searching the literature…" already exists in the chat-app but is no substitute for progressive output. Once the LLM is *generating* the answer, the user should see it.

## Goals

- **Time-to-first-token under 1 second** from the moment retrieval completes. The user sees text begin to appear well before the full answer is ready.
- **Field-by-field progressive render.** Framing appears, then citation 1's quote, then citation 1's whyChosen, then citation 2, …, then synthesis. Each field renders in its product-correct visual slot as it arrives, not as a raw text blob.
- **Preserve the ADR-011 structured-output contract.** No regression to free-text markdown. The JSON schema and pydantic models are unchanged. We are streaming the *building* of the same object, not a different shape.
- **Single round-trip from chat-app to FastAPI.** No second connection, no polling. SSE over the existing `/api/ask` path.
- **Graceful degradation.** If the chat-app cannot consume SSE (older browser, edge runtime quirk), it falls back to the existing non-streaming path with no loss of correctness.
- **No additional infrastructure.** Same dev-mode setup (one Python process + one Next.js process). Production hosting concerns stay with RFC-007.

## Non-goals

- Cancellation mid-stream (user clicks "stop"). Useful, but deferred — most answers complete in <60s and a cancel button is its own UX project.
- Per-token text shimmer / typewriter animation. Tokens-as-they-arrive is enough; we don't need a synthetic typing effect on top.
- Retry / resume on network drop. Deferred. Stream restart is acceptable on connection loss.
- Streaming the **retrieval** step. Retrieval is one shot (~0.5–15s); only the LLM phase is long enough to benefit from streaming. The retrieval result is sent as the first event in the stream.
- Auth, rate limiting, request budgeting. Deferred to RFC-006 (access control) and RFC-007 (hosting).
- Bidirectional streaming (i.e., user sends follow-ups during generation). Out of scope; the threaded-follow-up flow per the post-demo TODO is a separate turn-based exchange.

## Proposed design

### End-to-end flow

```
LLM (Anthropic streaming events)
   │  tool_use input_json_delta blocks, partial JSON
   ▼
FastAPI service  tools/server.py:  POST /ask
   │  Buffer partial JSON.  Whenever a complete top-level
   │  or list-element field is decodable, emit one SSE event
   │  carrying that field.  Keep partial deltas if the user
   │  wants char-by-char render of long quote bodies.
   ▼  text/event-stream  data: {"type":"framing","value":"…"}
Next.js  /api/ask  app/api/ask/route.ts
   │  runtime: "nodejs".  Reads the FastAPI SSE body, re-emits
   │  identically into its own SSE Response.  Adds nothing,
   │  removes nothing, transforms nothing — pure proxy.
   ▼  text/event-stream  data: {"type":"…","value":"…"}
React chat surface  app/chat/page.tsx
   │  Reads the response body as a ReadableStream.  For each
   │  SSE event, updates one slice of useReducer state.  Each
   │  field renders into its product-correct visual slot the
   │  instant it arrives.
   ▼
Devotee sees text accumulate
```

### Event schema

The SSE stream carries one or more of these event types, in this rough order:

| Event type | Fired when | Payload |
|---|---|---|
| `retrieval` | retrieval finishes (before LLM call begins) | `{chunks: [{workTitle, kind, language, cos, mmr}], elapsed_s}` — used by the UI to show "Found N passages in [retrieval time]s" while LLM generates |
| `field` | the LLM has produced a decodable top-level field of the response (e.g. `framing`, `classification`, `thesis`) | `{name: "framing", value: "…"}` |
| `array_item` | an element of an array field has been decoded (e.g. one citation, one example) | `{array: "citations", index: 0, value: {quote: {...}, whyChosen: "…"}}` |
| `delta` (optional, phase 2) | mid-field token deltas for long string fields like a quote body | `{path: "citations.0.quote.body", text: "…"}` |
| `done` | LLM call complete, full structured response validated against pydantic | `{response: <full AskResponse>, usage: {input, output, cache_read, cache_creation}, llm_elapsed_s}` |
| `error` | upstream failure (Anthropic API error, JSON validation error) | `{error: "…", recoverable: false}` |

The `done` event carries the full validated response. The React side can compare what it built progressively against the final shape and reconcile if any field arrived out of order or partially.

### Server-side implementation (FastAPI)

The Anthropic SDK exposes streaming via `client.messages.stream()` which yields events including `MessageStartEvent`, `ContentBlockStartEvent`, `ContentBlockDeltaEvent` (with `InputJSONDelta` for tool calls), and `ContentBlockStopEvent`. For tool-use streaming the model emits the tool's `input` field as a sequence of partial JSON strings.

Two parsing strategies, chosen per field:

1. **Buffered field-level decode.** Accumulate the JSON string; after every delta, attempt to parse the buffer with a tolerant streaming JSON parser (e.g. `partial_json_parser` or `simdjson` with truncation tolerance, or hand-roll a small balanced-brace state machine). When a new top-level key's value closes, emit a `field` event. When a new element of an array closes, emit an `array_item` event.
2. **Char-by-char delta passthrough (phase 2).** For specific long fields — citation quote bodies, the Pravachan thesis, the meta-mode framing — pass the deltas through as `delta` events keyed by JSON path, so the UI can typewriter them. The buffered decoder still fires the `field` event when complete.

Phase 1 implements only #1. Phase 2 layers #2 on top.

`POST /ask` becomes:

```python
from fastapi.responses import StreamingResponse
import json

@app.post("/ask")
async def ask(req: AskRequest):
    async def event_stream():
        # 1. Retrieval (already fast; sent as the first event)
        chunks, retrieval_s = retrieve_for(...)
        yield sse({"type": "retrieval", "chunks": [chunk_meta(c) for c in chunks], "elapsed_s": retrieval_s})

        # 2. Stream the LLM call.
        with client.messages.stream(
            model=pick_model(req.mode),
            max_tokens=MAX_TOKENS_BY_MODE[req.mode],
            system=[system_prompt_block(req.mode)],
            tools=[tool_for(req.mode)],
            tool_choice=tool_choice_for(req.mode),
            messages=[user_msg(req)],
        ) as stream:
            decoder = PartialJsonDecoder()
            for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "input_json_delta":
                    decoder.feed(event.delta.partial_json)
                    for emit in decoder.drain():
                        yield sse(emit)  # field or array_item

            final_msg = stream.get_final_message()
            parsed = response_model_for(req.mode).model_validate(tool_use_input(final_msg))
            yield sse({"type": "done", "response": parsed.model_dump(), "usage": cache_stats(final_msg)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

def sse(payload): return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
```

The `PartialJsonDecoder` is the only non-trivial piece — see Open Questions §1 for the parser choice.

### Client-side implementation (Next.js route)

`chat-app/app/api/ask/route.ts` becomes a pure SSE passthrough:

```typescript
import { NextRequest } from "next/server";

export const runtime = "nodejs";  // SSE doesn't work on the edge runtime today

export async function POST(req: NextRequest) {
  const body = await req.json();
  const upstream = await fetch(`${BACKEND_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
    body: JSON.stringify(body),
  });
  if (!upstream.ok || !upstream.body) {
    return new Response(JSON.stringify({ error: "Backend unavailable" }), { status: 502 });
  }
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
    },
  });
}
```

### Client-side implementation (React)

`chat-app/app/chat/page.tsx` switches from `await fetch(...).then(r => r.json())` to a `ReadableStream` reader. State is held in a `useReducer` whose state shape is the same `AskResponse` discriminated union with all required fields optional during build-up. Each SSE event dispatches an action:

```typescript
type StreamAction =
  | { type: "retrieval"; chunks: ChunkMeta[]; elapsedSec: number }
  | { type: "field"; name: string; value: unknown }
  | { type: "array_item"; array: string; index: number; value: unknown }
  | { type: "done"; response: AskResponse; usage: Usage }
  | { type: "error"; message: string };
```

The render tree is unchanged; the only difference is each slot reads from the reducer state and renders whatever is present. Partial citation lists render the citations they have; missing fields render skeletons or nothing.

### Backwards compatibility

`/api/ask` keeps non-streaming JSON responses as a fallback for older clients or curl scripts. The decision is per-request via the `Accept` header:

- `Accept: application/json` → current behavior, single JSON response.
- `Accept: text/event-stream` → SSE stream as designed.

The chat-app uses SSE. `tools/chat.py` and `tools/tune_sweep.py` keep using the non-streaming JSON path — there's no UX value to streaming in a CLI/batch context.

## Alternatives considered

### A. Sleep + smarter loading message ("Searching the works of Gurudev… Considering 8 passages…")

Cheaper than streaming but the underlying wait is the same. Users still stare at static text for 10–90s. Helps for small QA queries; useless for Pravachan. Loses against streaming on every metric except implementation effort.

### B. Synthetic typewriter on the final response

After the full JSON arrives, animate the text in field by field at a fake "typing speed." Looks like streaming but is purely cosmetic — the user still waited the full LLM duration before any text appeared. Worse than honest streaming because it spends UX budget on the wrong abstraction; the time-to-first-token doesn't improve.

### C. WebSockets instead of SSE

WebSockets are bidirectional and slightly faster to establish, but the streaming traffic here is unidirectional (server → client) and per-request. WebSockets add: a separate connection lifecycle, ping/pong keepalives, framing complexity, and Vercel/Next.js Edge-runtime incompatibility. SSE rides on plain HTTP, works through every proxy, integrates cleanly with `fetch()`, and is exactly the right shape for "stream of typed events from server to one client." WebSockets would be the right call if we needed cancellation, mid-stream user input, or multi-client broadcast.

### D. Stream raw markdown text, parse client-side

The pre-ADR-011 shape. Simpler to stream because there's no partial-JSON problem. But it throws away the structured rendering (citation cards, classification branch, references list) we just built. Hybrid options ("stream markdown then re-classify") double the work. Rejected.

### E. Drop tool-use, switch back to JSON-mode prompting, stream the JSON text directly

JSON-mode (non-tool, "produce JSON") streams as plain text, and a streaming JSON parser can handle it. Requires `client.messages.parse()` which is unavailable on our pinned Python 3.8 / anthropic 0.72 (the same constraint that drove ADR-011's choice). Reconsider when we move to Python ≥3.9.

## Tradeoffs & risks

### Partial JSON parsing is the load-bearing piece

The whole design hinges on the FastAPI service being able to decode partial tool-call JSON robustly. Anthropic emits `input_json_delta` events with arbitrarily-chunked string fragments. A naive `json.loads()` on each delta will fail nearly every time. We need a parser that:

- Accepts the current buffer.
- Tolerates trailing partial syntax (an open string, an unclosed `]`, a half-emitted UTF-8 char).
- Tells us which fields have fully closed since the last call.

Options surveyed for Open Question §1: `partial-json-parser` (PyPI), a hand-rolled JSON-Lines-style walker, or piping through Anthropic's own event-stream helpers if they expose closed-field events. Phase 1 should pick one and measure on the sweep's six questions.

### Multi-byte UTF-8 at chunk boundaries

Marathi text (Devanagari) uses 3-byte UTF-8 sequences. The Anthropic stream can split a sequence mid-codepoint, surfacing as either a partial-decode error or a lone surrogate. The FastAPI side must accumulate raw bytes and decode only when a complete codepoint boundary is reached. The SSE wire format (UTF-8 text) only sees clean codepoints.

### React state-management complexity

Field-by-field state updates over a long-running stream can churn React's reconciler if naively implemented. The mitigation: hold the building object in a single `useReducer` ref; only commit to component state at controlled intervals (e.g., once per `field` event, once per `array_item`, debounced 16ms for `delta` events in phase 2). Tested on the 6-question sweep, the worst case is Pravachan with ~12 events over ~90s — trivial for React.

### Proxy buffering

Some HTTP proxies (Vercel's edge cache, nginx with default config) buffer responses, defeating SSE. Mitigations: `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no` for nginx, and the runtime hint that `/api/ask` is nodejs-runtime (not edge). Production deployment is RFC-007 — this RFC just guarantees the headers and runtime are set in dev.

### Anthropic streaming cost model

Streaming responses don't change the per-token cost — same input + output tokens, same prompt caching. There is a marginal overhead for the SSE event envelope (~20 bytes per event) but it's negligible at the volumes we're discussing.

### Failure mode: pydantic validation fails on the final assembled object

After streaming, we still validate the full response. If validation fails (e.g., the LLM emitted a `kind` mismatch or a missing required field), we have already shown the user a partial answer. The `error` event tells the UI "what you just saw is incomplete and may be wrong"; the UI shows a clear `Couldn't finish that answer` state with a retry button. Acceptable degradation. The non-streaming path has the same failure mode but reveals it at the start.

### Cancellation backpressure

A user can navigate away mid-stream. The `fetch` from the React side gets `AbortSignal`; we propagate that to close the SSE connection from the Next.js route, which closes the FastAPI connection, which uses `stream.close()` to release the Anthropic SDK iterator. The Anthropic side still bills for tokens already generated before the abort, which is correct.

## Open questions

1. **Partial JSON parser choice.** Three candidates: (a) `partial-json-parser` from PyPI (small, focused, last released 2024); (b) hand-rolled brace/quote state machine inside `tools/server.py` (~80 LOC, no dep, total control); (c) `ijson` in incremental mode (mature, lower-level, may require more wrapping). Phase 1 should bench all three on the 6-question sweep's full-output JSON and pick on robustness > speed (the LLM is the bottleneck, not the parser).
2. **Should `delta` events ship in phase 1 or phase 2?** Char-by-char passthrough for long fields (Pravachan thesis, citation quote bodies) is a real UX win — the user sees a paragraph filling in token by token — but adds the most state-management complexity. Phase 1 scope: only `retrieval` / `field` / `array_item` / `done` / `error`. Phase 2: add `delta`. Calibrate after measuring phase 1 perceived latency.
3. **Reconciliation order.** If the LLM emits citations[1] before citations[0] (shouldn't happen, but possible), should the UI render in JSON order or LLM emission order? Phase 1: emission order, with a final reconciliation on `done`. Document this in ADR-011 amendment if we change the contract.
4. **Heartbeats.** Connections idle for >30s through some proxies are killed. Should the FastAPI side emit a `:heartbeat` SSE comment every 15s? Probably yes; cost is zero, robustness gain is meaningful. Defaults to on.
5. **CLI / sweep impact.** `tools/chat.py` and `tools/tune_sweep.py` keep the non-streaming JSON path. But adding streaming might break the existing markdown renderer in `tools/render.py` if it expects the full structured response in one shot. Verify: it expects a `dict` or pydantic instance — yes, the non-streaming path keeps providing that. Safe.

## References

- ADR-011: Structured-output JSON contract (tool-use pattern; the streaming design preserves this contract by streaming the building of the same JSON)
- ADR-010: QA doctrinal-vs-meta classification (classification is one of the streamed fields)
- ADR-007: Quote-first curation pattern (verbatim quotes stream char-by-char in phase 2)
- RFC-001: Demo MVP — informs which modes are highest-priority for streaming (all three are in scope)
- RFC-003: Retrieval and RAG — retrieval timing data feeds the latency budget
- RFC-004: Chat UI & UX — paragraph-rendering, loading states, citation cards
- POST_DEMO_TODO §2 §5: existing items for "loading affordance — streaming TBD" and "real LLM classification" — this RFC closes the streaming half of that item
- Anthropic SDK streaming docs: https://github.com/anthropics/anthropic-sdk-python (search `messages.stream`)
- Server-Sent Events: https://html.spec.whatwg.org/multipage/server-sent-events.html
- Next.js streaming runtime notes: https://nextjs.org/docs/app/api-reference/file-conventions/route#streaming
