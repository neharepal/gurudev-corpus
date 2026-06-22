# ADR-004: Support English + Marathi from day 1 (input and output)

**Status:** ACCEPTED
**Date:** 2026-06-12
**Author:** Neha (with Claude)

## Context

The Nimbal sampradaya is a Marathi cultural context. Most devotees are most comfortable in Marathi, though many also read English (Gurudev Ranade himself wrote much of his philosophy in English).

The original plan staged language support as: "English first, Marathi as a follow-up milestone, but keep Marathi in mind while designing." This was reasonable when the goal was "ship something quickly."

With the July 12 demo deadline locked, the demo audience identified as primarily Marathi-speakers 40+ on phones, and the success criteria including the literal sentence *"It works in Marathi as well,"* English-first becomes a real risk: a v1 that doesn't speak the audience's primary language might satisfy nobody.

The corpus already accumulates material in EN, MR, HI, SA, KN. Retrieval is multilingual at the index level regardless of UI language. The only real question is: does v1 *output* answers in Marathi?

## Decision

**Yes — both input and output support Marathi from v1.**

- Users can type their question in English or Marathi.
- The answer is generated in the same language as the question (with a user-toggle override).
- When the question is in one language but the most relevant source is in another, the answer quotes the original source in its original language and provides a paraphrase or summary in the user's language. Quoting verbatim preserves accuracy and is respectful of the canonical material.
- Other languages (Hindi, Sanskrit, Kannada) are stored in the corpus but answers are not generated in them at launch. Future ADR if priorities shift.

## Alternatives considered

- **English-first v1, Marathi in v2.** Simpler implementation. Rejected because: (a) the demo's success criteria explicitly include Marathi; (b) the 40+ phone-using audience is Marathi-first; (c) an English-only v1 risks looking like "this is for diaspora English speakers," not the Marathi heartland sampradaya.
- **Marathi-first v1, English later.** Equally awkward — Gurudev's English writings are central to the canon, and English questions about them should work natively. Rejected.
- **One mixed language model** (no language toggle, let the LLM auto-detect and respond). Possible. We may end up here in practice if auto-detection is reliable. But starting with explicit language matching keeps the UX predictable.

## Consequences

**Positive:**
- Audience-first design — we're not building for "the easy audience" then expanding.
- Phase 2 retrieval is multilingual from day 1 anyway (since the corpus is multilingual); the LLM does the heavy lifting on generation.
- Marathi support shapes UX from the start: font choice, input method, share-to-WhatsApp wording all bilingual-aware.

**Negative:**
- Slightly higher implementation cost: Marathi font rendering on web, input-method considerations, prompt-engineering for bilingual response, more demo scenarios to script.
- Marathi quality is generally lower than English in current LLMs — we'll need to evaluate Claude's Marathi output carefully and possibly augment with manual review for the demo.
- One more axis of testing during the polish phase.

## References

- [PRD.md §2 Audience, §5 Success criteria, §6 Constraints](../PRD.md)
- RFC-005 (Multilingual EN+MR strategy) — implementation details
- Project memory: `project_gurudev_corpus_design_mode.md`
