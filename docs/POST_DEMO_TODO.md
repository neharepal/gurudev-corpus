# Post-Demo TODO — Gurudev Sangrah

Captured during the iterative build leading up to the **2026-07-12 sampradaya demo**. Items here are deferred until after the demo so we can focus the remaining 27 days on demo-day quality (landing + Q&A + Pravachan + Reading paths in EN + MR).

Add new items below as they come up. Each item carries: a brief description, why it was deferred, and a rough size estimate (XS / S / M / L) so we can plan Phase 2.

---

## 1. Persistence & auth

- [x] **localStorage persistence** for reading position, drawer chat history, and language toggle (closed 2026-06-15). Hook at `chat-app/hooks/usePersistentState.ts`. Keys: `gd:lang`, `gd:read:{slug}:page`, `gd:read:{slug}:chat`, `gd:chat:{id}:{mode}:followups`.
- [ ] **Cross-device sync via auth + server-side state.** Devotee on phone in the morning, laptop in the evening. Likely magic-link or phone OTP since the audience is bilingual EN+MR and phone-first. (L — RFC of its own; session storage, conflict resolution, schema.)
- [ ] **Bookmarks** for passages and athvani worth returning to. Stored per-user. (M — requires auth.)

## 2. Backend wiring (mock → real)

- [x] **`/api/ask` route in the chat-app** scaffolded + UI wired 2026-06-15 — chat page (Q&A + Pravachan) and reading drawer now `POST` to `/api/ask` via `lib/api.ts`. Mock body in the route swapped for real retrieval (closed 2026-06-17). The route now forwards to a FastAPI service in `tools/server.py` that runs BGE-M3 retrieval + Anthropic tool-use per ADR-011. (M.)
- [x] **Loading affordance** — wired 2026-06-15. Chat page shows `Searching the literature...` (or Marathi equivalent); reading drawer shows `Searching this work...` while pending. Streaming (token-by-token) is still TBD; deferred to when the LLM call is plumbed in. (S to add streaming on top of current state.)
- [x] **Q&A prompt update** to emit `whyChosen` rationale per citation (closed 2026-06-15 in `tools/prompts.py`). Parsing pass on the markdown response is still TBD when wiring the UI fetcher.
- [x] **Adaptive Pravachan structure** — Pravachan prompt updated 2026-06-15 with a "decide question type first" step. Athvani-collection questions skip Thesis + Gurudev's words; thematic questions emit all four sections. Renamed Examples → Stories throughout.
- [ ] **Reading-mode in-page chat retrieval** — drawer mock cycles through paragraphs; real implementation needs the `/api/ask` mock body swapped for retrieval scoped to the current work. (Mock route already accepts `work` arg; just swap the body.)
- [ ] **Bilingual cross-language retrieval check** — BGE-M3 should handle EN question → MR corpus, but UX needs to communicate the language switch ("This passage is in Marathi — here's a brief gloss") if the answer language differs from the question language. (M, mostly UX.)
- [ ] **Meta-mode follow-ups** — chat page currently no-ops a follow-up against a meta answer (no citations to cycle through). Real backend will issue a fresh `/api/ask` call per follow-up; until then, meta answers are single-turn. Linked to ADR-010. (S, blocked on real retrieval wiring.)
- [x] **Real LLM classification** (closed 2026-06-17) — the LLM now classifies inside the single Q&A call per ADR-010, emitted as the `classification` field on the structured response per ADR-011. `isMetaQuestion` keyword router removed from `route.ts` along with `getMockAnswer`.
- [ ] **Reading mode work picker** — landing's `submit()` falls back to `DEFAULT_READING_SLUG[lang]` when the user types a custom Reading question that doesn't match a chip. Real implementation: the user picks a work from a list rather than us guessing. Noted in `app/page.tsx` inside `submit()`. (M.)

## 3. Content & data

- [ ] **Real athvani in the reading slugs** — the three athvan reading pages (`athvan-bhausaheb-letters`, `athvan-allahabad-mornings`, `athvan-dharwad-donation`) are placeholder text. Source from the curated athvani collections. (M — data work.)
- [ ] **More canonical works** in Reading mode — currently only `Pathway to God in Hindi Literature` (English) is mocked. Need actual chunked versions of *Pathway to God in Marathi Literature*, *Pathway to God in Kannada Literature*, *Bhajnamrut*, the collected letters, and *Selected discourses*. (L — depends on Phase 1 ingestion.)
- [ ] **Audit suggestion content** — devotee-facing example questions should be hand-curated by the user; current set is reasonable but is not authoritative. (XS)
- [ ] **Marathi UI-string audit** — verify every visible string renders cleanly in `मराठी` mode. Some translations were Claude-generated. (S)
- [ ] **Empty / error / no-results states** for every retrieval surface. Round-4 critic flagged this; out of scope for demo. (M)

## 4. Sharing & community features

- [ ] **Flag mechanism** — wire the `⚐ Report issue` button on `AnswerToolbar` to a real modal and write to `flag_queue.yaml` per RFC-004 §Content flagging. Currently a noop. (S)
- [ ] **WhatsApp share** — wire the `↗ Share` button per RFC-004 §WhatsApp share. (S)
- [ ] **Contribute an athvan** — a way for devotees to submit recollections for inclusion in the corpus. (L — moderation flow.)

## 5. UI polish & accessibility

- [ ] **Mobile responsive** — landing, chat answer, and Reading drawer all assume `lg+`. Designed-for-laptop currently; sadhaks on phones get a degraded experience. (M)
- [ ] **Per-mode discoverability** — Round-2 critic argued modes should be on-page, not drawer-only. We rejected for the demo, but worth re-evaluating once we have real usage data. (XS to re-evaluate; M if we restore visible tabs.)
- [ ] **"About this archive" expansion** — drawer currently shows a 200-char paragraph. Could open a small modal with more context (founder, lineage chart, citation policy from ADR-007). (S)
- [ ] **Q&A page follow-up wiring** — the bottom composer on `/chat/[id]` is a noop. Needs to actually submit a follow-up and append to the thread (same pattern as the reading drawer). (S)
- [ ] **"Start new conversation" affordance** — from a chat page, the only way back is "Back to start". A "New question" button would let the user start fresh without breadcrumbing through landing. (XS)

## 6. Licensing & attribution

- [ ] **Painted Gurudev portrait attribution** — file at `public/lineage-portrait.jpg` is a colorized oil painting signed "Pandit (Miraj)". Need formal credit on the page or in About, and verify licensing. (XS to add, M if we have to chase the rights holder.)
- [ ] **Paper-texture background licensing** — `public/paper-bg.jpg` sourced from magnific.com's free-photo CDN. Confirm the free-use license terms or swap for a confirmed CC0 texture. (S)
- [ ] **Citation policy on every page** — ADR-007 mandates verbatim quotes, but a "How citations work" note in About would build trust with the academic audience among sadhaks. (XS)

## 7. Observability & feedback

- [ ] **Lightweight analytics** — page views, mode usage, language toggle, suggestion click-through. Plausible or self-hosted Umami. (S)
- [ ] **User feedback channel** — an email or form to collect post-demo feedback from the 30 sadhaks. (XS)
- [ ] **Retrieval quality eval set** — 20-50 gold questions with expected passages, so we can detect retrieval regressions when the embedding model or chunking changes. Important once the corpus grows past PGHL. (M)

---

## Convention

When adding an item:
- Lead with `- [ ]` so it shows as an unchecked task in Markdown viewers
- Bold the headline
- Add a one-line *why* and a size (XS / S / M / L)
- Link to the source incident or RFC section if relevant

When closing an item: change `[ ]` to `[x]` and add the closing date in parentheses, e.g. `(closed 2026-07-20)`.
