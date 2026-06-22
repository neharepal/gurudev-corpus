# RFC-001: Demo MVP scope (July 12, 2026)

**Status:** ACCEPTED 2026-06-12
**Author:** Neha (with Claude)
**Created:** 2026-06-12
**Last updated:** 2026-06-12

## Summary

Define exactly what's IN and OUT for the July 12, 2026 sampradaya-meeting demo. Local-browser-only, ~10 min Zoom slot, ~30 attendees including senior sadhaks. Scripted-first (6 questions, ~5 min), audience-driven Q&A second (~5 min). All 3 modes built; Q&A and Pravachan demoed live; Simple Reading kept demo-ready as standby.

## Motivation

The July 12 demo is the forcing function for v1. Without a tight scope, the next 30 days drift. This RFC pins:

- Which corpus subset is in (so corpus prep doesn't blow up).
- Which 6 questions must answer beautifully (so we know what to gold-tune).
- Which UX features ship for the demo (so RFC-003/004 stay scoped).
- What's explicitly deferred (so we don't argue about it later).

This RFC blocks all implementation tasks (#1–#11). It does not block other design RFCs (#17, #18, #19, #20) which can proceed in parallel.

## Goals

1. A working chat UI on Neha's laptop browser, projected via Zoom screen-share, that handles **6 scripted questions** with high quality and **arbitrary audience questions** with graceful coverage.
2. **Honest behavior:** no hallucination. When the corpus is silent on a topic, the chat says so.
3. **Bilingual end-to-end:** English and Marathi questions both work, both yield answers in matching language, both render Devanagari cleanly.
4. **Three modes built:** Q&A (default), Pravachan (talk-builder), Simple Reading (guided paragraph-by-paragraph).
5. **Audience experience:** the three demo success-criteria sentences land —
   - *"It is so easy to get the answer I want."*
   - *"This captures exactly and entirely what I wanted."*
   - *"It works in Marathi as well."*

## Non-goals (for this demo)

- Public deployment / hosted infrastructure. Demo is local, screen-shared via Zoom.
- User accounts, login, sign-up. The browser session is Neha's. RFC-007 handles deployment + auth.
- Other languages for generation (Hindi, Sanskrit, Kannada). Corpus stores them; demo answers EN + MR only.
- Voice input/output.
- Audio source material — out of scope per ADR-005 / PRD §7.
- Mobile UI polish. Demo is on a laptop; mobile-first design proceeds in RFC-004 but is not the demo surface.
- Multi-user features (sharing, annotations, comments).
- Full corpus parity — see §Scope below for what's IN.

## Scope

### Corpus subset (Option B — broad, gold-tuned)

**IN** for the demo:

- **All canonical works moved into `01_canonical/` so far** — text extracted to `text.md`, `meta.yaml` populated.
  - Ranade: PGHL parts 1-3, PGKL parts 1-3, BGPGR parts (EN), Hindu Mysticism, Mysticism in Maharashtra preface, Introduction to Karnataka Mysticism, Daily Thoughts (×3 editions), Vedant, Bhajanamrut, Sant Vachanamrut (and the Tukaram/Eknath/Ramdas/Jnaneshwar individual ones), Santanchya Sahavasat (SS_1-5, SS_6-8), Sevenfold Stream of Spiritual Life, Reflections, Essays and Reflections, Contemporary Indian Philosophy, Gurudeo's Abhang, Opportunities of College Life, Parmarthapar Vyakhyane parts 1–7, Parmartha Sopan (MR+HI), Dhyangita.
  - Nimbargi: Bodhsudha (5 editions).
  - Kakasaheb: Maharajachi Sutre, Kakanchi Pravachane parts 1–3, Kakanchi Charcha.
  - Bhagavadgita ध्यानप्रधान भक्तियोग bundle (18 chapter booklets — needed for Q6).
  - Other authors: Patankar Pravachan Part 3 (and any other "other_authors" entries from the dashboard).

- **All athvani folders aggregated via the story_index** — multi-variant matcher run, stories deduplicated, variants preserved.
  - `about_gurudev_ranade/` (most stories), `about_bhausaheb_maharaj/`, `about_amburao_maharaj/`, `about_nimbargi_maharaj/`, `about_other_devotees/`.

- **Biographical/reference entries** placed per attribution dashboard.

**OUT** for the demo:

- Audio source material (out indefinitely per ADR-005 / PRD §7).
- Skipped entries (~11 files marked `skip` in the attribution dashboard).
- Hindi-only generation (corpus stores Hindi; generation in EN + MR only).
- Anything not in the dashboard's 69 decisions (i.e., not in current batches).

### Scripted demo questions

These are the 6 questions Neha will type/paste during the first ~5 min of the demo. They must answer with high quality (gold-tuned during the polish week).

| # | Question | Mode | Lang | Purpose |
|---|---|---|---|---|
| 1 | What are Shri Gurudev's views on Bhakti? | Q&A | EN | Doctrinal — broad theme synthesis. |
| 2 | श्री गुरुदेवांचे भक्तीविषयी विचार काय आहेत? | Q&A | MR | Bilingual showcase — same question, Marathi. |
| 3 | What did Shri Gurudev do in the year 1913? | Q&A | EN | Biographical / honesty test. If corpus has no 1913-specific record, the answer should honestly say so. |
| 4 | Examples of Gurudev's love and respect for his Guru | Q&A | EN | Anecdotal — pulls athvani. Should weave multiple stories with citations. |
| 5 | श्री गुरुदेव नामसाधनेविषयी काय सांगतात? | Q&A | MR | Fresh Marathi theme — exercises Marathi corpus content + Marathi generation. |
| 6 | Share some athvanis corresponding to Adhyay 12 of the Geeta and how it relates to Gurudev's life. | Pravachan | EN | Cross-reference + multi-variant by theme. Shows synthesis: canonical (BGPGR + Bhagavadgita ध्यानप्रधान भक्तियोग ch. 12) → athvani about Gurudev's bhakti → suggested sequence. |

**"Gold-tuned"** means: during the polish phase, we evaluate each of these against a hand-written reference answer, iterate on prompts and retrieval until the actual answer matches. These six are reproducible-quality.

### Modes — demo behavior

| Mode | Built | Demoed live? | Notes |
|---|---|---|---|
| Q&A | Yes | Yes (Q1–Q5) | Default mode. |
| Pravachan | Yes | Yes (Q6) | Output is a structured outline: thesis + supporting passages + athvani + sequence. |
| Simple Reading | Yes | Standby only | Built and demo-ready in case time permits or audience asks. Demoed if Q5/Q6 run short. |

### Demo UX requirements (informs RFC-004)

- **Landing screen** — a "Start new conversation" gateway with:
  - Mode picker (Q&A / Pravachan / Simple Reading) — user selects mode for the conversation about to begin.
  - **Suggested questions panel** — 3 click-to-populate prompts (2 English + 1 Marathi). Tappable on mobile, clickable on demo laptop.
- **Language handling** — **auto-detect from input.** No visible toggle. The detected language drives the answer's language.
- **Citation handling** — citations appear alongside each answer. Clicking a citation reveals the surrounding source passage. *Special interaction:* the source preview can transition the user into Simple Reading mode for that work, so the user can continue reading the source from where the citation came. This naturally bridges the Q&A and Reading modes.
- **Mode switch flow** — Mode is per-conversation; switching modes starts a new conversation (you can't half-Q&A-half-Pravachan inside one session).
- **Aesthetic direction** — "warm devotional." See ADR-006 (to be written next): off-white/parchment background, sepia text, maroon accent (sampradaya-adjacent), warm serif body fonts with proper Devanagari companion. *Not* clean-modern-tech-product feel.
- **Citation panel UI shape** — three candidate layouts to mock up before the polish phase: (a) right-side panel pinned to the answer; (b) inline footnote markers expanding to cards; (c) collapsed "Sources" section at the bottom of each answer. Defer pick to RFC-004 after seeing mockups.

### Demo flow (10 min slot)

- 0:00–0:30 — Neha opens chat, shows landing screen with mode picker + 3 suggested questions.
- 0:30–4:30 — Q&A mode: Q1, Q2 (Marathi via copy-paste), Q3 (honesty moment), Q4, Q5 (Marathi). ~45 sec each.
- 4:30–6:30 — Switch to Pravachan mode for Q6. Show structured output, drill into one citation → optionally drop into Reading mode briefly.
- 6:30–9:30 — Audience-driven questions. Type whatever they ask. Demonstrate honest "not in corpus" handling if needed.
- 9:30–10:00 — Wrap up. Show 3 suggested questions panel one more time. Acknowledge "this is local for now, hosted soon."

## Alternatives considered

- **Option A — Narrow corpus subset** (only ~20–30 files strictly needed for the 6 scripted questions). Faster prep (~3 days). Rejected because senior sadhaks in the open Q&A half will ask things outside that narrow band, and "not in corpus" answers for *anything not on our list* would undermine confidence.

- **Single-mode demo** (Q&A only, defer Pravachan and Simple Reading to v2). Faster build. Rejected because Q6 is a natural showcase of the corpus's depth, and demoing only chat-Q&A undersells the platform's range. Pravachan mode demos a "wow moment" that single-shot Q&A can't.

- **Deploy to a public URL for demo** instead of local screen-share. Possible. Rejected because (a) the user explicitly chose local for the demo, (b) it removes a class of risk (network, hosting bugs), (c) auth/access-control work would need to be done — out of scope for v1.

- **Pre-recorded video demo** instead of live. Reduces risk. Rejected because senior sadhaks asking unscripted questions is the *whole point* — a recording can't demonstrate honest "I don't know" behavior in real time. Live is the requirement.

## Tradeoffs & risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Senior sadhaks ask an obscure question; chat hallucinates instead of honestly saying "not in corpus." | Medium | Aggressive prompt engineering for honesty; pre-demo dry runs with adversarial questions; "honesty score" as a polish-phase metric. |
| Marathi answer quality is meaningfully lower than English. | Medium-high | Use Claude Sonnet 4.6 (best multilingual). Evaluate Marathi outputs during polish. If quality is poor, fall back to "answer in English with key Marathi terms preserved." |
| Network/Zoom latency makes the demo feel slow. | Low-medium | All retrieval and LLM calls are local-laptop calls (no public hosting yet), but Anthropic API has its own round-trip. Pre-warm the cache; show streaming output so the wait feels productive. |
| One of the 6 scripted questions returns a flawed answer during live demo. | Medium | Polish-phase iterative tuning (treat each scripted question as a gold test case with a reference answer); rehearse the full 10 min flow 3+ times before July 12. |
| Audience question hits a corpus gap we didn't anticipate. | High | Lean into it — "the corpus is being curated and this gap is now logged." Turn the failure mode into a vision-of-progress moment. |
| Marathi typing on the demo laptop is hard. | Confirmed | Suggested-questions panel includes 1 Marathi prompt; remaining Marathi questions pre-written for copy-paste. |
| The "warm devotional" aesthetic takes longer to nail than a generic UI. | Low-medium | Lock visual design choices in ADR-006 before RFC-004 implementation. Avoid bikeshedding by committing to a specific color palette + font early. |

## Open questions (resolve before/during polish phase)

| # | Question | Owner | Resolve by |
|---|---|---|---|
| OQ-1 | Citation panel UI: right-side / inline-expandable / bottom-collapsed? | RFC-004 + mockups | Day 18 |
| OQ-2 | Exact gold-tuning evaluation rubric for the 6 questions. | Polish week | Day 22 |
| OQ-3 | Final dress-rehearsal date — recommend July 9 or 10. | Neha | Day 25 |
| OQ-4 | Marathi font fallback chain — Noto Serif Devanagari + warm serif? | ADR-006 | Day 8 |
| OQ-5 | Reading-mode-from-citation interaction polish. | RFC-004 | Day 18 |

## References

- [PRD.md](../PRD.md) — overall product scope.
- [ADR-001](../decisions/ADR-001-treat-as-system-design.md) — why this RFC exists.
- [ADR-002](../decisions/ADR-002-lineage-aware-folder-structure.md) — corpus structure assumed.
- [ADR-004](../decisions/ADR-004-bilingual-from-day-one.md) — bilingual requirement.
- ADR-006 (to be written) — visual aesthetic direction ("warm devotional, old yellow pages with maroon paprika").
- RFC-002 (Corpus structure) — formalizes what `01_canonical/`, `02_aggregated/` look like.
- RFC-003 (Retrieval & RAG) — chunking, embeddings, model choice.
- RFC-004 (Chat UI & UX) — addresses OQ-1, OQ-5.
- RFC-005 (Multilingual EN+MR) — addresses Marathi font fallback (OQ-4) and language-detect specifics.
