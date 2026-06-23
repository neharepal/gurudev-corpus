# Plan: Reference-and-splice citations (latency fix)

Status: **Draft for review** · Supersedes part of ADR-011 (structured output
contract) and touches RFC-010 (progressive streaming).

## Problem (measured)

Doctrinal Q&A answers stall for **~10–26 s of complete silence on the wire**
between the `framing` field closing and the first citation byte. Instrumentation
of the raw Anthropic event loop proved the gap is the **model reproducing long
verbatim quotes** from the retrieved context, not a frontend/decoder/proxy issue:

- Pipeline (PartialJsonDecoder → SSE → Next proxy → React) streams char-by-char
  with ~0.00 s gaps; nothing buffers.
- A `citationPlan` scratchpad field (tried 2026-06-22) did **not** absorb the
  gap — it shifted unchanged to *after* the plan and added ~5 s. So the cost is
  the verbatim reproduction itself, not missing reasoning space.
- Tell-tale: once a body starts it streams ~1500 chars in ~1 s. The 10 s is
  spent *before the first character*, locating/committing the exact source text.

Meta answers (no citations) never stall.

## Core idea

Stop making the model **re-type** quotes it is reading from context. Have it
emit a **reference** (which passage + short span anchors); the backend, which
already holds the chunk text, **splices in the verbatim `body`** and fills the
attribution metadata from `chunk.meta`. The model emits ~10–16 short words per
citation instead of ~1500 chars → the verbatim-reproduction stall disappears.
Bonus: the quote becomes byte-identical to the source (no transcription drift),
and attribution (`workTitle`/`author`/`kind`) comes from trusted metadata.

The model now must **point** accurately instead of **transcribe** accurately.

## Contract change (model-facing tool schema only)

The model already sees passages labeled with opaque letters via
`format_chunks_for_prompt`: `[PASSAGE A] kind=... work="..." author=...` + TEXT.
Reuse that letter as the reference key (indices stay hidden per the existing
anti-leak design).

Per doctrinal citation, the model emits:

| field | who supplies | notes |
|---|---|---|
| `passage` | model | the letter ("A","B",…). **Required** for doctrinal. |
| `quoteStart` | model | first ~4–8 words of the desired quote, copied exactly |
| `quoteEnd` | model | last ~4–8 words, copied exactly (may equal start for short quotes) |
| `location` | model | human locator prose (unchanged) |
| `paraphrase` | model | optional gloss (unchanged) |
| `whyChosen` | model | unchanged |

Backend computes and fills (so the **wire `Quote` shape is unchanged** →
frontend untouched):

| field | source |
|---|---|
| `body` | spliced `chunk.text[start : end_of(quoteEnd)]` |
| `workTitle` | `chunk.meta.title` (authoritative) |
| `author` | `chunk.meta.author` |
| `kind` | `chunk.meta.kind` |

## Backend splice algorithm

`splice_quote(passage_letter, quoteStart, quoteEnd, label_to_chunk) -> Quote`:

1. `chunk = label_to_chunk[passage_letter]` — else fallback (below).
2. In `chunk.text`, find `quoteStart`: exact match first, then
   whitespace-normalized match (collapse runs of whitespace; needed for
   Devanagari/multiline). Record start offset.
3. From the start offset, find `quoteEnd`; `body = text[start : end_index]`.
4. If `quoteEnd` not found after start: take `start` → end of the enclosing
   sentence/paragraph (or chunk end). If `quoteStart` not found at all: degrade
   — use the longer of the two anchors as `body` and log a mismatch counter.
5. Fill `workTitle`/`author`/`kind` from `chunk.meta`.

Carry a `label_to_chunk` map out of `_prepare_request` (the same enumeration
`format_chunks_for_prompt` uses, so labels line up exactly).

## Streaming integration (RFC-010)

`array_item` SSE events already carry the **assembled** citation element. Splice
at that boundary:

- In `ask_structured_stream`, when emitting an `array_item` for the `citations`
  array, run `splice_quote(...)` on the element value before yielding.
- The interim `delta` events for `citations.N.quoteStart`/`quoteEnd` stream
  (tiny, fast) but the frontend ignores unknown leaf paths; the real citation
  lands on `array_item`, which now arrives ~instantly (no 10 s stall).
- Non-streaming path (`ask_structured`) + JSON endpoint: splice in the same
  shared helper during pydantic construction/reconcile so both paths match.

No frontend change expected (`QuoteBlock` consumes the same `Quote`). Verify.

## Edge cases / risks

- **Ambiguous start anchor** (phrase repeats in the chunk): take the first match
  from offset 0; revisit with an occurrence hint only if real data needs it.
- **Devanagari / UTF-8**: substring match is byte/character safe; whitespace
  normalization handles multiline source.
- **Over-long span**: harmless — splice whatever is bounded; the *generation*
  cost is just the two anchors.
- **New failure mode**: anchor mismatch. Mitigated by fuzzy match + degraded
  fallback + a logged mismatch counter to watch in testing.
- `_scrub_chunk_leak`: `body` stays unscrubbed (now provably from source);
  `workTitle`/`author` come from meta, so their scrub is moot but harmless to keep.

## Validation plan (use the existing harness)

1. Implement schema + `splice_quote` + streaming intercept.
2. Harness: measure `framing → first citation` gap. **Expect ~10 s → ~1–2 s.**
3. Verify spliced `body` is an exact substring of the source chunk on N runs;
   track anchor-mismatch rate; tune anchor-length guidance in the field
   descriptions if mismatches are non-trivial.
4. Confirm frontend renders unchanged (no code change).
5. Check meta answers are unaffected.

## Touch list

- `tools/schemas.py` — Quote tool schema + `Quote`/`Citation` pydantic; add
  `splice_quote` (or place in a small helper module).
- `tools/prompts.py` — field-description guidance for `passage`/`quoteStart`/
  `quoteEnd`; ensure label scheme is shared, not duplicated.
- `tools/server.py` — surface `label_to_chunk` from `_prepare_request`.
- `tools/llm_client.py` — splice at the `citations` `array_item` boundary
  (stream) and in the reconcile/`ask_structured` path (JSON).
- `docs/decisions/ADR-011-*` / `docs/rfc/RFC-010-*` — note the contract change.
- Tests / `tune_sweep.py` — update any assertions on `body`.

## Out of scope (separate, already-flagged cleanups)

- Revert the frontend debug cruft (`debugEventCount`, `cit0body` readout),
  restore rAF throttling in `chat-app/app/chat/page.tsx` — it was never the bug.
- Retrieval warm-up at startup to remove the ~10 s cold-embedding first query.
