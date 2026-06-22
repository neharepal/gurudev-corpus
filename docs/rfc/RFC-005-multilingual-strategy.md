# RFC-005: Multilingual (English + Marathi) strategy

**Status:** ACCEPTED 2026-06-13
**Author:** Neha (with Claude)
**Created:** 2026-06-13
**Last updated:** 2026-06-13

## Summary

Defines how the chat platform handles English and Marathi across input, retrieval, generation, and presentation. Locks in input-language detection by script, single multilingual vector index (BGE-M3 from RFC-003), original-language quotes preserved verbatim with user-language paraphrase below, and the Marathi font stack from ADR-006. Hindi/Sanskrit/Kannada are stored in the corpus but not generated to in v1.

## Motivation

ADR-004 committed us to bilingual EN+MR from day 1. RFC-003 and RFC-004 reference multilingual behavior in passing but don't pin the details. This RFC consolidates them in one place so implementation tasks have a single reference for language handling.

## Goals

- Devotee asks in English → answer in English.
- Devotee asks in Marathi → answer in Marathi.
- When the best-supporting passage is in a different language than the question, **the passage is quoted verbatim in its original language** (per ADR-007 quote-first); a user-language paraphrase or short summary appears below the quote.
- Marathi text renders cleanly across desktop and mobile browsers (Devanagari font stack).
- Mixed-script content (English text with embedded Devanagari terms, or vice versa) renders correctly.

## Non-goals (v1)

- Hindi answer generation (corpus stores Hindi sources; generation is EN + MR only at launch).
- Sanskrit answer generation (same reasoning).
- Kannada answer generation (same).
- Auto-translation of one full language to another (we preserve originals; paraphrasing is per-quote, not document-level).
- User-selectable interface language toggle. **Input language is the signal.** A user typing in Marathi gets a Marathi interface for that conversation; switching is per-message.

## Language detection

### Input → answer-language decision

1. **Script-based first pass:** if the input contains any Devanagari character, treat as Marathi.
2. **Latin-script default to English.**
3. **Mixed scripts in one question** (e.g., "What does Gurudev say about नामसाधना?"): use the dominant script by character count for the answer language; the embedded terms stay in original script.
4. **Transliterated Marathi in Latin script** (e.g., "What does Gurudev say about namasadhana?"): treated as English. We do not attempt to detect transliterated Marathi — too brittle.

### Edge cases

- Very short input (<3 words) and ambiguous: default to English.
- Question with only proper nouns and Devanagari numbers: treat as Marathi.

This is intentionally simple. Heuristics need to be fast and predictable, not perfect. If a devotee gets the wrong language, the corrective signal is to rephrase — and the UI never *hides* the input from the user, so they always know what they typed.

## Retrieval

Single multilingual vector index (BGE-M3) handles both languages. Marathi and English chunks coexist; retrieval returns the most relevant chunks regardless of language.

**No language filter at retrieval time.** A Marathi question may legitimately surface English Ranade passages (where Gurudev wrote in English about the same topic). Filtering by language would deprive the answer of the most authoritative source.

The generation step decides which retrieved chunks to quote and how to present them in the user's language.

## Generation — per-mode multilingual handling

Per RFC-003 / ADR-007 quote-first pattern:

### Both languages match (question and best chunk in same language)

Standard quote-first answer in that language.

### Question in MR, best chunk in EN (common case for doctrinal questions)

```
मूळ ग्रंथातील उल्लेख इथे आहे:

> "Bhakti is at once the means and the end of mysticism. It is by bhakti
>  that the soul approaches God."
> — Pathway to God in Hindi Literature, ch. 4, p. 87 (canonical) · Shri Gurudev Ranade

(मराठीतून सारांश: भक्ती ही मार्ग आणि साध्य दोन्ही आहे. भक्तीने आत्मा परमेश्वराकडे पोहोचतो.)

[optional brief synthesis in Marathi]
```

- Quote stays in **original language** (English) — never paraphrased into Marathi as if it were the source.
- A short **Marathi summary or paraphrase** appears in italic / lighter weight directly below the attribution, clearly marked as a paraphrase, not as the original.
- The framing sentences ("मूळ ग्रंथातील उल्लेख इथे आहे:") and any synthesis are in Marathi.

### Question in EN, best chunk in MR (common case for athvani)

```
Here's what the corpus contains on this:

> "ती. बाबांच्या पत्रांच्या पेट्या अत्यंत काळजीपूर्वक जपल्या जात..."
> — निंबाळचे जुने घर (athvani, narrator: Vijaya Apte) · from "जैसी गंगा वाहे"

(English paraphrase: The trunks of Bha. Babanchya — Shri Gurudev's — letters were preserved with utmost care...)

[optional brief synthesis in English]
```

Same pattern, mirrored. Marathi quote verbatim, English paraphrase below, English framing.

### System prompt language

The system prompt is **language-agnostic** — Claude is instructed to detect the user's language and respond accordingly. Mode-specific templates have phrasing patterns in both languages for the framing sentences (e.g., `Here's what the corpus contains` ↔ `मूळ ग्रंथातील उल्लेख इथे आहे`).

## Marathi quality acceptance bar

We're using Claude Sonnet 4.6 (ADR-003) for generation. Sonnet's Marathi is strong for paraphrase, summarization, and conversational prose. Three quality bars to hit during polish (Week 4):

1. **No nonsense.** Marathi output must be grammatically coherent and meaningful. Hallucinated word formations are unacceptable.
2. **Correct register.** Devotional/scholarly tone, not casual chat tone. Use respectful honorifics (श्री, ती. = तीर्थरूप, etc.) consistently.
3. **Faithful paraphrase.** When paraphrasing an English quote in Marathi, the meaning must be preserved without invented details.

**During polish week (Week 4), each of the 6 demo questions is evaluated in both languages.** If any Marathi output fails bar 1 or 2, we fix the prompt before demo. If bar 3 fails systematically, fall back to "quote in English, do not paraphrase" as the safer default for that question.

## Font rendering

Per ADR-006:

- **Latin:** Lora (or system serif fallback)
- **Devanagari:** Noto Serif Devanagari (or system Devanagari serif fallback)
- Both must visually harmonize — same x-height, weight, color.

**Loading strategy:** Noto Serif Devanagari is ~200 KB woff2 — load lazily after first contentful paint if no Devanagari is detected on the landing screen, eagerly otherwise.

**Mixed text** (English line with embedded Devanagari, or vice versa) inherits the page's font stack. Browsers automatically use the appropriate font per glyph if both are loaded — no special markup needed.

## Transliteration

For v1: **no transliteration helpers** in the UI. Users type what they type. If they want to see Marathi terms in Latin, the source-preview overlay can show a transliteration alongside — defer to a future v2.

For the corpus side, transliterations of person names and key terms can live in `03_catalog/glossary.yaml` (per RFC-002 §5) — useful for retrieval query expansion later, not for v1.

## Edge cases and graceful failures

| Case | Behavior |
|---|---|
| User asks in Marathi, retrieval returns 0 chunks | "मूळ ग्रंथात या विषयावर थेट उल्लेख आढळला नाही." (Marathi version of "no direct mention in corpus") |
| User asks in English, retrieval returns 0 chunks | "The corpus doesn't have material directly addressing this question." |
| Marathi generation produces nonsense (very rare with Sonnet, but possible) | Fall back to English answer with a note "Marathi response unavailable for this question" |
| Mixed-script question detected | Use the dominant script for the response language; preserve embedded foreign-script terms in original script |
| Question is just `?` or whitespace | Show input validation hint in current detected language |

## Open questions

| # | Question | Resolve in |
|---|---|---|
| OQ-1 | Should we display Latin transliteration of Marathi quotes as a third line under the attribution? Could help English-only devotees engage with Marathi sources. | Polish week — if devotees ask for it after dress rehearsals |
| OQ-2 | When the question is bilingual (intentional mixing), should the response be bilingual too? | Polish — likely answer in dominant language, embed foreign terms in original script |

## Tradeoffs

- **Script detection is brittle for transliterated Marathi** typed in Latin. Mitigation: the audience self-corrects (typing in Devanagari to get a Marathi answer is a learnable cue).
- **Cross-language paraphrase quality depends on the LLM.** Sonnet 4.6 is good but not perfect. Polish-week evaluation is the safety net.
- **Marathi font** adds ~200 KB to initial load if eagerly loaded. Acceptable for desktop, slight concern for low-bandwidth mobile. The lazy-load strategy mitigates.

## References

- [PRD.md §2 Audience, §5 Success criteria](../PRD.md) — bilingual is a demo success criterion
- [ADR-004 Bilingual from day 1](../decisions/ADR-004-bilingual-from-day-one.md)
- [ADR-006 Warm devotional aesthetic](../decisions/ADR-006-warm-devotional-aesthetic.md) — font choices
- [ADR-007 Quote-first curation pattern](../decisions/ADR-007-quote-first-curation-pattern.md) — informs cross-language quote/paraphrase handling
- [RFC-003 Retrieval & RAG strategy](RFC-003-retrieval-and-rag.md) — BGE-M3 multilingual embeddings
- [RFC-004 Chat UI & UX](RFC-004-chat-ui-and-ux.md) — language-detect UX behavior
