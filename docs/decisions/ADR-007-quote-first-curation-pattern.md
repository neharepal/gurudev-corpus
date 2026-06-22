# ADR-007: Adopt quote-first curation pattern over LLM synthesis

**Status:** ACCEPTED
**Date:** 2026-06-13
**Author:** Neha (with Claude)

## Context

The original generation contract in RFC-003 specified a *synthesis* pattern: the LLM retrieves chunks, weaves them into a paraphrased answer in its own voice, and cites sources with `[#N]` markers. This is the standard RAG pattern used by tools like Perplexity and (increasingly) ChatGPT.

For a sampradaya corpus, the user surfaced a problem: devotees should hear Shri Gurudev's words, not Claude's paraphrase. When a devotee asks "What does Gurudev say about bhakti?", the value is in the actual passages — Gurudev's own writing — not in an LLM-generated précis.

This isn't a UI nit. It changes:
- The generation system prompt (LLM is now curator + connective tissue, not author).
- The retrieval contract (chunks must be quotable-length and coherent on their own, not just topic-relevant).
- The citation surface (citations now anchor the verbatim passage, not a paraphrase of it).
- The trust profile (lower hallucination surface because the LLM is mostly arranging existing text).

## Decision

Adopt a **quote-first curation pattern** for all generation modes (Q&A, Pravachan, Simple Reading answers).

The LLM's job becomes:

1. Select 2–5 passages from the retrieval results that *directly* address the question.
2. Present each passage *verbatim* with its source attribution.
3. Write minimal connective tissue: a short framing sentence, optional brief context between quotes, and optionally a brief synthesis at the end (1–2 sentences).
4. Cite *the quote* itself — there's no separate `[#N]` marker; the quote is the citation, with attribution rendered immediately below it.

The shape of a typical Q&A answer:

```
Here's what the corpus contains on this:

> "Bhakti is at once the means and the end of mysticism. It is by bhakti that 
> the soul approaches God, and it is in bhakti that the soul finds its 
> fulfilment."
> — Pathway to God in Hindi Literature, ch. 4, p. 87

> "Among the Marathi sants, Jnaneshwar, Tukaram, Eknath, and Ramdas embody 
> the bhakti path in its lived form."
> — Mysticism in Maharashtra, preface

These passages together describe bhakti as both path and culmination.
```

The synthesis paragraph at the end is *optional* and *short* (1–2 sentences). When sources directly speak for themselves, the LLM should stay out of the way.

## Alternatives considered

- **Pure synthesis (the original RFC-003 plan).** Rejected: devotees should hear the source, not the model.
- **Pure verbatim search results (no LLM).** Rejected: search-result lists feel cold and don't answer the question conversationally. The LLM should orchestrate which passages to surface and provide minimal framing.
- **Hybrid: quote-first for canonical, synthesis for athvani.** Considered. Rejected because: even for athvani, devotees value the narrator's voice. Apply quote-first uniformly; differentiate only via the source-type tag in attribution (canonical / oral / biography).
- **User-selectable mode (synthesis vs. quote-first toggle).** Rejected: needless complexity; quote-first is right for this audience.

## Consequences

**Positive:**
- Trust: every claim in the response is verbatim from a known source. Hallucination surface drops dramatically.
- Citation quality: citations are the quoted passages themselves — no risk of "the answer says X but the citation actually says Y" mismatch.
- Honesty contract becomes natural: when the corpus doesn't have a quotable passage, the model literally has nothing to quote → naturally says "the corpus doesn't directly address this."
- Bilingual handling becomes cleaner: original-language quote is the canonical content; paraphrase/translation can sit alongside in the user's language without conflating which is the "real" answer.
- Reverential tone: devotees experience Gurudev's voice, mediated only lightly by the system.

**Negative:**
- Less conversational flow. A polished synthesis sometimes reads more elegantly than a quote sequence. We accept this tradeoff.
- Retrieval must surface quotable passages — not just relevant ones. Chunks that are mid-paragraph fragments may not work; we may need to re-chunk on quote boundaries.
- Pravachan mode's "thesis" section is harder — a thesis is *by definition* an authored statement. Either we accept a Pravachan thesis as the one place the LLM speaks, or we draw the thesis from a canonical passage too. Reconsider when we discuss Pravachan UX.
- Output length is more variable: when many passages are relevant, the answer is longer; when one passage suffices, the answer is short.

## Implementation notes

- **System prompt update** (RFC-003 §Generation): explicit instruction to prefer verbatim quotes, write minimal connective tissue, optionally synthesize at end.
- **Chunk quality** (RFC-003 §Chunking): respect paragraph + sentence boundaries even more strictly. Mid-sentence chunks are useless as quote material.
- **Retrieval ranking** (RFC-003 §Retrieval): consider boosting chunks that are well-bounded (start with a clean sentence, end at a paragraph break).
- **UI rendering** (RFC-004): quotes are visually distinct (indented, slightly different background, attribution line below). No `[#N]` superscript markers needed in the body since the quote IS the citation.
- **Mockups** (`tools/chat-ui-mockups.html`): regenerate to reflect this pattern.
- **Simple Reading mode** is mostly unchanged — it was always showing source text. The mockup just used a paraphrase by mistake.

## References

- [RFC-003 Retrieval & RAG strategy](../rfc/RFC-003-retrieval-and-rag.md) — to be amended
- [RFC-004 Chat UI & UX](../rfc/RFC-004-chat-ui-and-ux.md) — to be amended
- [PRD.md §4 Phase 2 Goals](../PRD.md)
- Conversation 2026-06-13 — user feedback identifying paraphrase as undesirable
