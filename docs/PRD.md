# Product Requirements Document — Gurudev Corpus

**Status:** [ACCEPTED v2 — locked 2026-06-12]
**Last updated:** 2026-06-12
**Owner:** Neha (with Claude drafting)

---

## 1. Problem statement

The Nimbal sampradaya has a deep body of literature — Shri Gurudev Ranade's writings in English, Marathi, Hindi, and Kannada; Kakasaheb Tulpule's pravachans; the *athvani* tradition recording the lives and teachings of Nimbargi Maharaj, Bhausaheb Maharaj, Amburao Maharaj, and Gurudev; recorded discourses; biographical anthologies; periodicals. This material is **scattered** across PDFs, DOCX files, recordings, oral tradition, and several parallel curated collections.

For a devotee with a question — *"What does Gurudev teach about namasadhana?"*, *"What happened during Gurudev's Allahabad years?"*, *"Are there multiple tellings of the surgery-without-anesthesia incident?"* — finding the answer today requires either deep familiarity with the corpus or reliance on a handful of experts. Most devotees do neither, and the literature stays under-used.

**This product makes the entire corpus answerable in natural language (English or Marathi), with cited, source-traceable replies.**

## 2. Audience

| | |
|---|---|
| **Size** | ~500 sampradaya devotees (estimated upper bound) |
| **Age** | Predominantly 40+ |
| **Primary device** | Mobile phones |
| **Tech comfort** | Mixed — UI must be very simple |
| **Distribution channel** | Existing sampradaya WhatsApp group (used for launch + ongoing) |
| **Languages** | Marathi-first cultural context; English fluent; both supported from day 1 |
| **Out of scope (v1)** | General public, academic researchers, non-sampradaya users |

**Implications already flowing from this:**
- Mobile-first UI, not "responsive web app." Phones are the *primary* surface.
- Larger touch targets and font defaults for 40+ users.
- Marathi font rendering must be excellent (not an afterthought).
- "Share to WhatsApp" should be a first-class action on every answer.
- No-account onboarding (sign-in friction kills 40+ adoption).

## 3. Phase 1 — The Corpus

### Goals
- **Single source of truth** for Nimbal sampradaya literature, on Neha's device, replicable elsewhere.
- **Preserve canonical works verbatim** — Gurudev's books, Kakasaheb's pravachans, etc. are never edited.
- **Aggregate oral tradition (athvani)** — when the same story is told by 2–3 different narrators, variants are preserved and a consolidated version is curated.
- **Multilingual:** English, Marathi, Hindi, Sanskrit, Kannada — accept everything as received.
- **Structured for retrieval** — every file carries `meta.yaml` provenance; chunks know their source for citation in Phase 2.
- **Lineage-aware** — folders organized by guru (Nimbargi → Bhausaheb → Amburao + Ranade as peers → Kakasaheb).

### Non-goals (Phase 1)
- Editorial improvement of source material.
- Translation between languages (preserve as-is; translation is a Phase 2 generation concern).
- Audio transcription of pravachan recordings — **deferred but high-value** (see §7).

### Status (2026-06-12)
- Repo skeleton + lineage-aware folder structure in place.
- 222 source files ingested across 2 batches; 19 high-confidence canonical works moved into structured locations.
- Attribution dashboard built; 69 uncertain attributions decided.
- Athvani pipeline validated end-to-end on one story.
- Move execution + bulk athvani aggregation + canonical text extraction pending — see task list.

## 4. Phase 2 — The Chat Platform

### Goals
- **Free-form question input** in English or Marathi (mobile-friendly text input).
- **Detailed, accurate, cited answers** — every claim traceable to a specific source (book/page, athvani variant, etc.).
- **Honest about provenance:**
  - Distinguishes *canonical teaching* (what Gurudev said/wrote) from *oral recollection* (what devotees recalled).
  - Acknowledges when sources differ across narrators.
  - Acknowledges when sources are silent — refuses to invent.
- **Bilingual input/output** — answer in the same language as the question; quote source material in its original language with a paraphrase if the question is in a different language.
- **Mobile-first UI** — large touch targets, generous font defaults, Marathi rendering, WhatsApp-share on every answer.
- **Three explicit modes** (v1):
  1. **Q&A mode** *(default)* — devotee asks a single natural-language question; gets a cited, source-traceable answer. The everyday lookup flow.
  2. **Pravachan mode** — structured talk-builder. Devotee gives a topic; system produces a thesis grounded in canonical works, 3–5 supporting passages with citations, illustrative athvani, and a suggested sequence. Output is a draftable outline, not a conversation.
  3. **Simple Reading mode** — guided reading of a chosen source text. Devotee picks a work or chapter; system presents it paragraph by paragraph; devotee can ask questions inline ("what does this term mean?", "how does this connect to Bhausaheb's view?"). The system remembers where they left off so the next session resumes there.
- **Single curator (Neha) for v1** — no contributor accounts, no review workflow.

### Non-goals (v1, including demo)
- Voice input/output (defer to v2).
- User accounts, login, personalization (post-demo).
- Sharing answers via in-app features (WhatsApp share is enough).
- Discussion / commenting / annotation.
- Hindi / Sanskrit / Kannada answer generation (English + Marathi only at launch; corpus stores everything multilingually).
- Public discoverability (invite-only, sampradaya-WhatsApp distribution).

### Modes — design implications

Modes are not three separate apps — they share the same corpus, retrieval pipeline, and citation system. The differences are at the **interaction layer**:

| Mode | Input shape | Output shape | State |
|---|---|---|---|
| Q&A | single question | answer + citations | stateless (or short conversation history) |
| Pravachan | topic + optional sub-themes | thesis + supporting passages + athvani + sequence | session-scoped outline |
| Simple Reading | work/chapter selection | paragraph-by-paragraph + optional inline Q&A | persistent (resume where left off) |

**RFC-004 (Chat UI)** must address how the user switches between modes (top-of-screen tabs? mode picker before each session?) and which mode is the default landing experience.

**RFC-003 (Retrieval & RAG)** is mode-aware: Pravachan mode needs a *broader* retrieval (more sources, more diverse) and a different generation prompt (build an outline, not answer a question). Simple Reading retrieves nothing at all by default — it just reads the chosen text, with retrieval triggered only when the devotee asks an inline question.

## 5. Success criteria

### Demo (July 12, 2026)

The three sentences Neha wants devotees to walk away saying:

> *"It is so easy to get the answer I want."*  (**accessibility**)
> *"This captures exactly and entirely what I wanted."*  (**fidelity**)
> *"It works in Marathi as well."*  (**multilingual**)

**Tactical acceptance criteria for the demo:**
- A working chat UI on Neha's laptop browser, projected.
- ~10 hand-curated Q&A scenarios spanning: doctrinal, biographical, lineage, athvani-comparative, terminological, Marathi-input, and one pravachan-prep example.
- Every shown answer has citations rendered.
- At least 2 demo scenarios run in Marathi end-to-end (input + output).
- Zero hallucination incidents during dry runs.
- 5–10 minute presentation time — demo flows without manual interventions.

### Long-term (12–24 months post-launch)

- Adopted by a majority of active sampradaya devotees within 6 months of (eventual) public launch in the WhatsApp group.
- The default tool devotees reach for when preparing pravachan material.
- Surfaces forgotten content; makes corpus gaps visible (the curator-side benefit).
- Operable by someone other than Neha — corpus + tools survive a handoff.

## 6. Constraints

| Constraint | Detail |
|---|---|
| **Hard deadline** | 2026-07-12 — sampradaya meeting demo (local browser, not deployed). |
| **Operator** | Sole curator (Neha). Implies simple admin tools; no multi-tenant complexity. |
| **Budget** | Self-funded. Implies cost-conscious model choices, prompt caching, multilingual open-source embeddings, modest hosting. |
| **Languages** | EN + MR from day 1. Other languages later. |
| **Mobile-first** | Designed for 40+ devotees on phones, not desktop-first then "made responsive." |
| **No content access tiers** | Per user (§ Q5): all corpus material is freely accessible to invited devotees. No per-user restrictions. |
| **System design discipline** | PRD/RFC/ADR documentation required for major decisions; implementation does not begin until corresponding RFC is accepted. |

## 7. Out of scope for v1 — explicit deferrals

These are real and important but not for July 12 / v1:

- **Hosted deployment** — demo is local-only; deployment goes to RFC-007 post-demo.
- **Voice input/output** — older devotees may eventually prefer voice queries (especially in Marathi). RFC for v2.
- **Audio material** — out of scope for v1 and probably indefinitely. The user has prior experience that text extraction quality from these recordings is too poor to justify the curation effort. The relevant Drive folders (`प. पू. श्री काकासाहेब प्रवचने/` #301–334, `Gurudev/Recordings/` for Aaji, Pad, Aarti, etc.) exist but are not being ingested. If transcription tooling improves materially (Whisper for Marathi, etc.), revisit.
- **Other languages** (Hindi, Sanskrit, Kannada) for answer generation — corpus stores them, but Phase 2 answers in EN + MR only.
- **User accounts / sign-in / personalization.**
- **Sharing/annotation in-app** — WhatsApp share covers the social use case.
- **Multi-contributor corpus updates** — Neha curates, may take help, but operates as sole admin.
- **Content access tiers / restricted material** — confirmed not needed.
- **Product name** — pick one later.

## 8. Open questions

| # | Question | Resolution route |
|---|---|---|
| ~~Q1~~ | ~~Is pravachan-prep a chat use case or a distinct UX mode?~~ — **Resolved 2026-06-12:** distinct mode. See §4. | — |
| Q2 | Which LLM model? (Sonnet 4.6 default, but pin) | RFC-003 |
| Q3 | Which embedding model? (multilingual open-source likely) | RFC-003 |
| Q4 | What's the canonical-vs-oral disclosure UX? (badges? labels in citations?) | RFC-004 |
| Q5 | How are demo Q&A scenarios curated? Hand-picked? Tested against gold answers? | RFC-001 (Demo MVP) |
| ~~Q6~~ | ~~Audio transcription — defer or pull forward?~~ — **Resolved 2026-06-12:** out of scope (see §7). | — |
| Q7 | Product name. | not urgent; pick before public launch |
| Q8 | Deployment platform for production. | RFC-007 (post-demo) |
| ~~Q9~~ | ~~How is the existing sampradaya WhatsApp group leveraged for launch?~~ — **Resolved 2026-06-12:** Neha is in contact with senior devotees who will coordinate launch. Out of scope for the design docs. | — |

---

## Drafting notes

This v1 draft tries to keep "preservation" and "accessibility/Q&A" as twin first-class goals, with "pravachan preparation" called out explicitly because the user mentioned it and it's structurally different from chat-Q&A. The doc is intentionally opinionated where the user gave clear signal (mobile-first, no access tiers, etc.) and explicit-with-open-questions everywhere else.

**Please redline.** Anything wrong in tone, missing in scope, or wrong in emphasis — mark it. After redlining I'll lock v1 and write ADR-001 capturing the system-design-mode commitment.
