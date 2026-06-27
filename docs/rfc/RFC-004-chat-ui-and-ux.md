# RFC-004: Chat UI & UX

**Status:** ACCEPTED 2026-06-13 (finer visual details deferred to Phase 2 implementation per §Deferred)
**Author:** Neha (with Claude)
**Created:** 2026-06-13
**Last updated:** 2026-06-27 (amended for ADR-007 quote-first; mode dropdown; suggested questions; 2026-06-27 content-flagging section implemented)

## Summary

Defines the user-facing chat application: landing screen with mode picker + suggested questions, the three modes' specific UX (Q&A / Pravachan / Simple Reading), citation rendering (Layout 3 — bottom collapsed accordion), source preview with Reading-mode handoff, language auto-detection from input, ADR-006 warm-devotional aesthetic, WhatsApp share, and a content-flagging mechanism with a fix-it admin loop. Mobile-first responsive design.

## Motivation

RFC-001 specified what the demo needs to show. RFC-002/003 designed the corpus and retrieval. This RFC connects them to a real user experience. Without it, the polish-phase implementation invents UX decisions ad hoc.

## Goals

1. Three modes (Q&A, Pravachan, Simple Reading) accessible through one cohesive UI.
2. Layout 3 citation rendering — clean reading surface, sources tucked in a bottom accordion.
3. Bilingual EN+MR end-to-end with auto-detect from input.
4. Warm-devotional aesthetic (ADR-006) consistently applied.
5. Mobile-first responsive (primary user device per PRD §2).
6. Suggested-questions panel: 3 click-to-populate prompts (2 EN + 1 MR).
7. Source preview that can transition to Simple Reading mode for context exploration.
8. WhatsApp share for every answer (sampradaya-WhatsApp is the distribution channel).
9. Content flagging mechanism with admin review loop.
10. Graceful error and empty states.

## Non-goals (v1)

- Sign-in, accounts, personalization (RFC-007).
- Voice input/output.
- Real-time streaming markdown rendering (defer; v1 buffers answer then renders).
- Multiple themes (light/dark toggle) — warm-devotional only.
- In-app commenting/discussion.
- Public discoverability.

## Architecture

**Stack (decided here, pending validation):**

- **Frontend:** Next.js (App Router) — SSR-friendly, good performance, well-suited to mobile. Hosting later via Vercel.
- **Backend:** Same Next.js project's API routes for v1 simplicity. Python services (embeddings, retrieval) called via subprocess or a lightweight FastAPI sidecar if Node-Python interop gets messy. Decision deferred to first implementation spike.
- **State:** local React state + localStorage for "Simple Reading bookmarks" + a small Postgres (Supabase) for the flag queue and admin reviews. (For demo, can use SQLite or even JSON file — Supabase added post-demo.)

**Data flow:**

```
User question ─► Next.js API route ─► Python retrieval service
                                          │
                                          ▼
                                  [Chroma index]
                                          │
                                          ▼
                            top-k chunks + metadata
                                          │
                                          ▼
                                 Anthropic API (Sonnet 4.6)
                                          │
                                          ▼
                            answer + citation refs ─► Next.js ─► browser
```

## Landing screen

The first thing a user sees (revised 2026-06-13 — mode dropdown instead of button row, suggested questions demoted to subtle hint):

```
┌─────────────────────────────────────────────────────────┐
│  गुरुदेव संग्रह                          Mode: Q&A ▾   │   (parchment background)
│  A guided exploration of Nimbal sampradaya literature   │
│                                                          │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Ask anything...                                    │ │   (multi-line input)
│  │                                                    │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│   Try: "What are Gurudev's views on Bhakti?" ·          │   (small italic gray)
│        "श्री गुरुदेव नामसाधनेविषयी काय सांगतात?" ·       │
│        "What did Gurudev do in 1913?"                   │
└─────────────────────────────────────────────────────────┘
```

- **Title** in Marathi: "गुरुदेव संग्रह" (Gurudev Sangrah) with English subtitle smaller below.
- **Mode picker is a dropdown** in the top-right: `Mode: Q&A ▾`. Clicking reveals a menu of all available modes. Scales to any number of modes (current 3 + future Compare Narrators / Topical Study / etc.). Default selection: **Q&A**. Picker shows on every screen, not just landing.
- **Input box** is the focal element — multi-line, generous padding. Submit on Enter (Shift+Enter for newline). Placeholder text in current language.
- **Suggested questions appear as a small italic gray hint line directly ABOVE the chat input box** (revised 2026-06-13). Format: `Try: "Q1" · "Q2" · "Q3"`. Color around `#8E8472` (muted bronze, low contrast). Each suggestion is click-to-populate. Localized to the selected mode (Q&A prompts vs Pravachan vs Reading).
- **Chat input box is anchored to the bottom of the page** — matches user mental model of chat apps and keeps the page calm above. On desktop the page above the input is mostly visual breathing room, anchored by a low-opacity Nimbal ashram outline watermark (placeholder SVG until we have a real outline image to swap in).
- On mobile, the dropdown moves below the title, suggestions wrap to multiple lines, the ashram watermark scales down.

## Q&A mode UX (quote-first per ADR-007)

Once a question is submitted, the screen transitions to conversation view. The answer surfaces **verbatim passages from the corpus**, not LLM paraphrase:

```
┌─────────────────────────────────────────────────────────┐
│  गुरुदेव संग्रह                         Mode: Q&A ▾    │
│  ◁ Back to start                          [⚐]  [Share] │
├─────────────────────────────────────────────────────────┤
│  YOU                                                     │
│  What are Shri Gurudev's views on Bhakti?                │
│                                                          │
│  GURUDEV SANGRAH                                         │
│  Here's what the corpus contains on this:                │
│                                                          │
│    │ "Bhakti is at once the means and the end of        │
│    │  mysticism. It is by bhakti that the soul          │
│    │  approaches God, and it is in bhakti that the      │
│    │  soul finds its fulfilment."                       │
│      — Pathway to God in Hindi Literature, ch. 4, p. 87 │
│        Shri Gurudev Ranade · canonical                  │
│                                                          │
│    │ "Among the Marathi sants, Jnaneshwar, Tukaram,     │
│    │  Eknath, and Ramdas embody the bhakti path in      │
│    │  its lived form."                                  │
│      — Mysticism in Maharashtra, preface                │
│        Shri Gurudev Ranade · canonical                  │
│                                                          │
│  These passages together describe bhakti as both        │
│  path and culmination.                                  │
├─────────────────────────────────────────────────────────┤
│  Ask a follow-up...                          [Send]      │
└─────────────────────────────────────────────────────────┘
```

- **Question** ("YOU") rendered in muted bronze, smaller font.
- **Framing sentence** at the top of the answer ("Here's what the corpus contains on this:") — brief, in primary sepia.
- **Quotes are visually distinct** — left border (maroon, 2-3px wide), indented, italic body in primary sepia, larger reading font. Each quote is a `<blockquote>` element.
- **Attribution line** directly below each quote, slightly smaller, muted bronze. Format: `— Title, location (source-type)`. For athvani, includes narrator: `— निंबाळचे जुने घर (athvani, narrator: Vijaya Apte)`.
- **No `[#N]` markers in the body** — per ADR-007 the quote IS the citation. The attribution sits with the quote.
- **No separate "Sources" accordion at the bottom** for the typical case — the quotes ARE the sources, presented in line. (Optional fallback: when there are MANY supporting passages — say 6+ — a small "View all sources" link below the synthesis opens an accordion of additional ones.)
- **Optional brief synthesis** at the end (1–2 sentences max), rendered as plain text in primary sepia.
- **Tapping an attribution line** opens the source preview overlay (shows surrounding context + "Read in Simple Reading mode" handoff).
- **Mode picker `Mode: Q&A ▾`** persists at top — clicking switches mode for the next question (starts a new conversation).
- **Flag icon `[⚐]`** at top of each answer — opens the flag modal.
- **Share icon** at top — opens the share menu.
- **Follow-up input** at the bottom — conversation continues; retrieval context refreshes per follow-up.

## Pravachan mode UX (revised 2026-06-14)

**Purpose:** research assistant for pravachan preparation. Surfaces raw, citable material that the devotee will sequence and write in their own voice. The system does NOT draft the pravachan. It does NOT propose ordering.

For Q6-style questions: "Share some athvanis corresponding to Adhyay 12 of the Geeta and how it relates to Gurudev's life."

```
┌─────────────────────────────────────────────────────────┐
│  ◁ Back to start                          [⚐]  [Share]  │
├─────────────────────────────────────────────────────────┤
│  PRAVACHAN RESEARCH BRIEF                                │
│                                                          │
│  Your question                                           │
│  > "Share some athvanis corresponding to Adhyay 12      │
│  >  of the Geeta and how it relates to Gurudev's life." │
│                                                          │
│  Thesis                                                  │
│  Adhyay 12 of the Gita teaches bhakti as the most       │
│  intimate and complete path; Gurudev's life shows...    │
│                                                          │
│  Gurudev's words                                         │
│  > "Bhakti is at once the means and the end..."         │
│  > — BGPGR, ch. 12 (canonical) · Shri Gurudev Ranade   │
│                                                          │
│  Examples                                                │
│                                                          │
│  1. The trunks of Bhausaheb Maharaj's letters           │
│     > "ती. बाबांच्या पत्रांच्या पेट्या अत्यंत…"           │
│     > — निंबाळचे जुने घर (athvani, narrator: Vijaya Apte)│
│     Why this example: shows bhakti-toward-guru as       │
│     daily devotional practice, not metaphor.            │
│     [→ Read in full]                                    │
│                                                          │
│  2. Allahabad mornings                                  │
│     > "..."                                             │
│     > — Allahabad days (athvani, narrator: V.H. Date)   │
│     Why this example: illustrates sustained nama-       │
│     sadhana — the disciplined side of bhakti.           │
│     [→ Read in full]                                    │
│                                                          │
│  3. Dharwad-University library donation                 │
│     > "..."                                             │
│     > — (athvani, narrator: …)                          │
│     Why this example: bhakti as outward generosity —    │
│     gives the talk a closing image.                     │
│     [→ Read in full]                                    │
└─────────────────────────────────────────────────────────┘
```

**Four sections, in order:**

| Section | What |
|---|---|
| **Your question** | Verbatim restatement of what the user asked. Makes the brief self-contained. |
| **Thesis** | 1–2 sentences — starting point, not a final position. |
| **Gurudev's words** | One verbatim passage from a canonical work that grounds the thesis. (Plain-language section name — was originally "Canonical anchor" in the v1 draft; renamed 2026-06-14 for clarity.) |
| **Examples** | 3–5 athvani, each with verbatim quote + attribution + a single-sentence "Why this example" connecting it to the thesis + a `[→ Read in full]` link that opens the source in Simple Reading mode. |

**Dropped from the v1 design:**
- No "Suggested sequence" — the devotee decides ordering.
- No bottom-of-brief summary/conclusion.
- No "Copy outline / Export" buttons — research material isn't an exportable outline.

**Mode-aware navigation:**
- The `[→ Read in full]` link per example is the key interaction. It opens Simple Reading mode at the source work, scrolled to the chunk the quote came from. This makes Pravachan mode a launch pad into deeper reading.

**Citation rendering** matches Q&A mode (per ADR-007 inline quote-first, no separate sources accordion).

**Follow-up input** at bottom — devotee can refine: "give me more athvani about namasadhana specifically" / "find another canonical quote — this one's too short".

## Simple Reading mode UX

Shows the **actual extracted text from the corpus** (verbatim from `text.md`), not a paraphrase. For "Read PGHL chapter 4":

```
┌─────────────────────────────────────────────────────────┐
│  Pathway to God in Hindi Literature                     │
│  Shri Gurudev Ranade · Chapter 4 (excerpt)              │
│  ◁ Back to start          ━━━━━━━━━━░░░░  Page 4 of 18 │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ¶ 1   (actual extracted paragraph from text.md, verbatim) │
│                                                          │
│  ¶ 2   (next actual paragraph, unchanged from source)    │
│                                                          │
│  ¶ 3   ...                                              │
│                                                          │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Have a question about this passage?               │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

- The text is **read directly from `01_canonical/.../text.md`** — the same source used for retrieval chunks. Devotee sees Gurudev's actual writing, paragraph by paragraph.
- **Header** with work title, author, chapter, and a progress bar.
- **`¶ N` markers** in muted bronze for paragraph anchors (handy for citation deep-links).
- **Bookmark state** persisted to localStorage (per-device for v1; per-account post-auth).
- **Inline question box** at bottom — asking here uses Q&A mode prompt with a metadata filter restricting to the current work, but the answer still follows the quote-first pattern (likely the relevant passage IS in the current chapter).
- **Navigation** — forward/back buttons (or swipe on mobile).
- **From a Q&A mode attribution**, you can land here at the exact paragraph the quote came from (deep link to `¶ N`).
- **No LLM involvement in rendering text** — Simple Reading mode is essentially a corpus-text viewer with bookmarks; the LLM only enters when the devotee asks an inline question.

## Citation rendering — quote-first inline (per ADR-007)

The original Layout 3 (bottom accordion) became unnecessary once we adopted quote-first: **the quotes ARE the citations**, presented inline in the answer body, with attribution directly below each quote. There's no separate "Sources" section in the typical case.

A small accordion only appears when there are many supporting passages (6+) — a `View N more sources ▾` link below the synthesis opens it. This is rare for v1 demo questions.

Visual treatment per quote:
- Left border (2-3px maroon, `#7A2E2A`)
- Indent
- Italic body text in primary sepia
- Slightly larger font for the quote
- Attribution line below in muted bronze, smaller, format `— Title, location (source-type)` (and narrator for athvani)
- Hover/tap on attribution → source preview opens

User preference noted: they liked Layout 1 (right-side panel) and Layout 3 (bottom accordion) in earlier mockups, but the quote-first pattern obviates both. If we ever return to a synthesis-based answer pattern, Layout 3 is what we'd use.

## Source preview + Reading-mode handoff

Tapping a source row opens a small overlay:

```
┌─────────────────────────────────────────────────┐
│  Pathway to God in Hindi Literature, ch. 4      │
│  ────────────────────────────────────────       │
│  "Bhakti is at once the means and the end       │
│  of mysticism. It is by bhakti that the soul    │
│  approaches God, and it is in bhakti that the   │
│  soul finds its fulfilment."                     │
│                                                  │
│  — Shri Gurudev Ranade, p. 87                   │
│  ─────────────────────                          │
│  [Read this chapter in full →]                  │
│  [Close]                                        │
└─────────────────────────────────────────────────┘
```

- Shows the verbatim chunk plus a small surrounding context.
- **"Read this chapter in full →"** button transitions to Simple Reading mode at this paragraph. Powerful: a chat conversation can become a deep reading session.
- Closing returns to chat.

## Language detection and display

- **On input:** detect language from the user's text (Devanagari script → MR / EN classifier for Latin script with heuristics for transliterated names).
- **Answer language matches input.** No visible toggle.
- **When the question is in one language but the relevant source is in another:** quote the source in its original language with a paraphrase in the user's language. E.g., user asks in Marathi about a passage from Ranade's English PGHL — answer is in Marathi with an inset English quote.
- **Fonts:**
  - Latin text: Lora (or system serif fallback)
  - Devanagari: Noto Serif Devanagari (or system Devanagari serif fallback)
  - Same x-height, same color, same weight — visual harmony per ADR-004 and ADR-006.

## Aesthetic implementation — ADR-006 mapped

Direct CSS custom properties (from ADR-006):

```css
:root {
  --bg-page:        #F8F2E4;
  --bg-surface:     #FCF8EC;
  --bg-panel:       #F4ECD8;
  --text-primary:   #2D2924;
  --text-secondary: #6E665B;
  --accent-maroon:  #7A2E2A;
  --accent-gold:    #A88556;
  --border-soft:    #D8CDB5;
  --font-serif:     'Lora', 'Charter', 'Georgia', 'Noto Serif Devanagari', serif;
  --font-mono:      'Iosevka Slab', 'IBM Plex Mono', monospace;
}
```

- **Animations:** subtle, 200–300ms ease.
- **No drop shadows:** use tonal differences for elevation.
- **Reading width capped** at 70ch for canonical text in Simple Reading mode.

## Content flagging mechanism

### User-facing

- **Per-answer flag button `[⚐]`** in the header of every answer.
- Tapping opens a small modal:

```
┌─────────────────────────────────────────────────┐
│  Report an issue with this answer               │
│  ──────────────────────────────────────         │
│  What's wrong?                                  │
│  ○ Wrong attribution                            │
│  ○ Quoted text doesn't match the source         │
│  ○ Mentions something not actually in the corpus│
│  ○ Translation or paraphrase issue              │
│  ○ Missing important context                    │
│  ○ Sources are mislabeled or in wrong section   │
│  ○ Other                                        │
│                                                  │
│  Add detail (optional, helps Neha review)       │
│  ┌────────────────────────────────────────────┐ │
│  │                                            │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  [Cancel]                          [Submit flag]│
└─────────────────────────────────────────────────┘
```

- Submission writes a flag entry. **Auto-attached:**
  - question text
  - full answer text
  - all retrieved chunks with their citations
  - conversation id (for chronology)
  - flagged_at timestamp
  - selected category + free text
  - language of the conversation
- After submit: "Thank you. Neha will review and correct if needed." (Marathi version when interface is in Marathi.)

### Storage

For demo (July 12): **`03_catalog/flag_queue.yaml`** — a YAML file, append-only, one entry per flag. Neha can `cat` it or open in an editor.

```yaml
flags:
  - flag_id: <uuid>
    flagged_at: <ISO>
    category: wrong-attribution
    detail: "The PGHL citation seems to point to part 2 but quotes from part 3"
    conversation:
      mode: qa
      language: en
      question: "What are Shri Gurudev's views on Bhakti?"
      answer: "..."
      citations:
        - id: 1
          chunk_id: <id>
          source_work_id: pathway-to-god-in-hindi-literature
          ... # full chunk metadata
    status: open      # open | reviewing | fixed | not-an-issue | wontfix
    review_notes: ""
    resolved_at: null
```

Post-demo: graduate to Supabase or similar with admin UI. For v1 demo, the YAML file is sufficient — there's no Phase 2 admin staff needing concurrency.

### Admin review surface

**For v1 demo: out of scope.** Neha reads `flag_queue.yaml` directly.

**Post-demo:** add a `/admin/flags` route gated by Neha's auth. Surface each flag with a side-by-side view (original answer + chunks + user note + buttons to mark Fixed / Not-an-issue / Revisit, plus a notes textarea). When marked Fixed, optionally enter what was corrected in the corpus for the audit trail.

### Corpus update workflow

When a flag leads to a corpus fix:
1. Neha edits the relevant `meta.yaml` or `text.md` (or `consolidated.md` for athvani).
2. The `04_processed/` chunks for that work are re-embedded.
3. The flag entry status → `fixed`; `resolved_at` set; `review_notes` records what changed.
4. Optionally: the flagger receives a notification (post-auth feature).

For demo: re-embedding is a manual re-run of the indexer. Post-demo: automate on file save.

### Anti-abuse

For v1 (invite-only, ~500 devotees): not a concern. Post-public-launch (out of v1 scope) we'd add rate limiting per user. The flagging UI does NOT show flags to other users — there's no public "this answer is disputed" badge in v1.

## WhatsApp share

Tapping the share button on any answer opens a share menu:

- **Copy link** — copies a link to a hosted version of this specific conversation (post-deployment) or just the answer text for v1 local demo.
- **Share on WhatsApp** — opens `https://wa.me/?text=...` URL with the answer + a citation summary prepacked. The text format:

```
[Question]
What are Shri Gurudev's views on Bhakti?

[Answer from Gurudev Sangrah]
For Shri Gurudev Ranade, bhakti is not a sentimental devotion...

Sources:
- Pathway to God in Hindi Literature, ch. 4, p. 87 (Ranade)
- Mysticism in Maharashtra, preface (Ranade)

— via Gurudev Sangrah
```

This is the v1 distribution channel — sharing is how devotees evangelize the tool to each other in the sampradaya WhatsApp group.

## Error and empty states

| Scenario | Behavior |
|---|---|
| Retrieval returns 0 chunks | "The corpus doesn't have material relevant to this question. Try rephrasing, or ask about a topic the lineage's literature addresses." |
| Anthropic API timeout/error | "Something went wrong reaching the language model. Try again in a moment." + retry button. |
| Marathi input but corpus has weak Marathi coverage for this topic | Answer notes the gap honestly per RFC-003 moderate-honesty stance. |
| User asks a non-question | Reflect back in current language: "Could you rephrase that as a question?" |
| Network drops during answer | Show partial answer if any + reconnect indicator. |

All error messages have Marathi versions, used when the interface language is Marathi.

## Mobile responsiveness

- **Single-column layout** under 700px.
- **Mode picker stacks vertically** in landing screen.
- **Citation accordion** native pattern — tap to expand.
- **Touch targets** at least 44px tall.
- **Font defaults** larger on mobile (17px → 18px for body) given the 40+ audience demographic.
- **Bottom-fixed input box** with keyboard-aware padding.
- **No hover-dependent interactions** — everything works on tap.

## Alternatives considered

- **Chat UI as separate single-page React app** (not Next.js). Rejected because: SSR helps mobile performance; routing for `/`, `/admin`, `/conversation/<id>` is natural in Next.js.
- **Citation Layout 1** (right-side panel). User picked Layout 3 for reading flow; revisitable in v2.
- **Mode picker persistent at top** (visible throughout conversation). Rejected because: keeps UI compact and discourages mid-conversation mode switching (which would lose retrieval context anyway).
- **Auto-language toggle button** instead of detect-from-input. Rejected because: input language IS the intent signal; an explicit toggle adds clutter for negligible benefit.
- **Flagging as in-line "thumbs up/down"** like ChatGPT. Rejected because: too vague for actionable correction. The category-selector flag form is more useful for someone reviewing and fixing.
- **Streaming token-by-token rendering** for v1. Defer because: complicates the citation-marker rendering (citations get inserted post-generation). v2 can stream the body and append citations at end.

## Tradeoffs

- **Layout 3 hides sources by default.** Some devotees may not realize the citations are there. Mitigation: keep the most recent answer's accordion expanded by default; clear visual cue.
- **Mobile-first** means desktop demo (July 12) gets a mostly-mobile-shaped UI on a laptop screen. Acceptable — feels personal/tidy rather than over-spaced.
- **Auto-detect language** is brittle for transliterated names. Mitigation: if confidence is low, default to English; user can rephrase if wrong.
- **Flagging without an admin UI for v1** means flags accumulate in a YAML file. Mitigation: Neha checks periodically and edits the corpus by hand.

## Open questions

| # | Question | Resolve in |
|---|---|---|
| OQ-1 | Confirm Next.js as the v1 frontend stack (or pick alternative). | First implementation spike — within 3 days |
| OQ-2 | Should mode-switching mid-conversation be allowed, or strictly per-conversation? | Polish phase |
| OQ-3 | Concrete contract for "language detect" heuristic edge cases (transliterated text, mixed scripts in single question). | RFC-005 |
| OQ-4 | Will the demo use a phone-frame projector view, or laptop-shaped browser window? | Pre-demo dry run |
| OQ-5 | Add visual indicator when retrieval falls back to broader corpus (e.g., "I didn't find Q-specific results, here's nearby material")? | Polish phase |

## Deferred to Phase 2 implementation

Captured 2026-06-13 — user explicitly chose to refine these during build, not in mockup iteration:

- **Nimbal ashram outline as background watermark.** Placeholder SVG sketch acceptable for early build; swap in a real outline image when available.
- **More prominent Q&A synthesis line at end of answers.** Current spec says "1–2 sentences max." During implementation, evaluate whether to label it ("In summary:") or make it visually distinct (a thin top rule, italic, etc.).
- **Resolving the visual collision between mode dropdown (top-right of every screen) and per-answer flag/share icons.** The intent is: mode dropdown sits in a global header strip; flag/share are per-answer action row controls visually below it. The implementer should ensure the two zones don't overlap.
- **Pravachan mode presentation.** User wants to revisit before implementation. Current outline shape held as placeholder.

## References

- [PRD.md §4 Phase 2, §5 Success criteria](../PRD.md)
- [ADR-004 Bilingual from day 1](../decisions/ADR-004-bilingual-from-day-one.md)
- [ADR-006 Warm devotional aesthetic](../decisions/ADR-006-warm-devotional-aesthetic.md)
- [RFC-001 Demo MVP scope](RFC-001-demo-mvp.md) — for the 6 scripted questions and demo flow
- [RFC-002 Corpus structure](RFC-002-corpus-structure.md) — for citation metadata
- [RFC-003 Retrieval & RAG strategy](RFC-003-retrieval-and-rag.md) — for answer/citation contract
- RFC-005 (Multilingual EN+MR) — for language-detect specifics
- RFC-007 (Deployment) — for hosting and auth
- `/tools/citation-panel-mockups.html` — the Layout 3 selection

## Amendment (2026-06-27): Content-flagging section implemented

The §"Content flagging mechanism" specified in this RFC is now fully built and
merged. Key implementation notes against the spec:

- **Storage:** `03_catalog/flag_queue.yaml` as specified (migrated from an
  interim `logs/issue_reports.jsonl` in commit `25ab503`).
- **Flag entry shape:** matches the RFC-004 schema; adds a `correction` block
  for in-reader paragraph corrections (F18, garble Phase 2).
- **Status field values:** `pending | approved | rejected | applied` (the RFC
  specified `open | reviewing | fixed | not-an-issue | wontfix`; the shipped
  values are simpler and map directly to the `apply_flags.py` workflow).
- **Report modal:** category radios per RFC-004 spec, plus optional detail,
  with Marathi confirmation toast.
- **WhatsApp share:** per RFC-004 line 25, the share menu includes WhatsApp
  (`https://wa.me/?text=…`), Copy link, and native Web Share API fallback.
- **Admin review surface:** `/admin/flags` dashboard with approve/reject
  (not deferred as the RFC originally said — built in commit `d0fb2dd`).
- **Corpus update workflow:** `tools/apply_flags.py` CLI — review approved
  corrections, apply to `text.md` with backup + diff, mark applied, re-embed.

See [ADR-016](../decisions/ADR-016-content-flagging-workflow.md) for the full
design decision, alternatives, and commit references.
