# QA findings — 2026-06-25

Running catalogue from a manual QA pass across modes. **Not yet fixed** — to be
prioritized and planned into fixes after testing. Each entry: symptom → root
cause (confirmed where noted) → fix scope.

---

## F1 — Degraded "…" citations (QnA)

**Symptom:** citations render as `start … end` stubs, e.g.
*"According to Nārada the highest kind … mystical nature of the Bhakti which he
has enunciated."* — incomplete sentences instead of the full passage.

**Root cause (confirmed from source):** reference-and-splice needs the model's
quote anchors to byte-match the source chunk to locate the span. The model
lightly *normalizes* the source as it quotes, so the anchor misses and it falls
back to the `_degrade` stub:
- source `Nârada` (circumflex) vs model `Nārada` (macron) — `gandhi-and-other-indian-saints/text.md:4206`
- source `does not consists` (OCR typo) vs model `does not consist`

**Fix scope:** backend, contained. Make anchor matching tolerant (fold
diacritics + whitespace + minor OCR), and when the span still can't be located,
fall back to the **full source passage** — never the `…` stub.

---

## F2 — Follow-ups repeat content / not conversational (QnA)

**Symptom:** a follow-up ("Can you give more such examples?") re-cited a passage
already shown in the prior answer; no new material.

**Root cause (confirmed in code):** follow-ups are sent as brand-new standalone
questions with **no conversation history** — `server.py` `AskRequest.history` is
commented "not used by the single-turn pipeline today." So the follow-up is
answered cold and nothing prevents re-citing the same passages.

**Desired behavior (user):** each follow-up = a new question **carried with the
context of previous turns**, like a chat — and it should bring *new* material,
not repeat.

**Fix scope:** frontend → backend → prompt (the "threaded-follow-up refactor"
the code already anticipates). Thread prior Q&A as context; avoid already-shown
passages.

---

## F3 — Reading mode shows mock content / pagination inert

**Symptom:** in the reading view, advancing to "Page 2 of 18" updates the page
counter and progress bar but the **paragraphs don't change**.

**Root cause (confirmed in code):** the reading view
(`chat-app/app/read/[slug]/page.tsx`) is backed by **mock data** —
`getReadingPage(slug)` (line 113) is keyed only on `slug`, and it renders the
fixed `page.paragraphs` (line 262). The Next button (line 305) only bumps a
`currentPage` counter. Reading mode is **not wired to real corpus content** yet.

**Fix scope:** larger — this is unfinished work, not just a bug. Needs a backend
endpoint to serve a work's real, paginated text + the frontend reader wired to
fetch the current page's content.

---

## F4 — No "read the full text" link from QnA citations

**Symptom:** we intended a link from a QnA citation to open the work in Reading
mode; it isn't there.

**Root cause (confirmed in code):** the "read in full" link exists only for
**Pravachan** examples (`chat-app/app/chat/page.tsx:770`, `/read/{readSlug}`).
QnA citations (`QuoteBlock`) have no such link, and the QA citation wire shape
may not carry the work slug needed to build one.

**Fix scope:** small, but **coupled to F3** (reading must serve real content
first). Add the link to QnA citations + ensure each citation carries `work_id`.

---

## F5 — Citation font size not uniform across scripts

**Symptom:** a citation containing Devanagari renders in a noticeably **larger**
font than a Latin-only citation; should be uniform regardless of source script.

**Root cause (confirmed in code):** `chat-app/components/QuoteBlock.tsx:9,13`
applies the `font-deva` class to the **whole** quote block when the body
contains *any* Devanagari (`/[ऀ-ॿ]/`), and that font renders visually larger.

**Fix scope:** frontend CSS — equalize size across scripts (e.g.
`font-size-adjust`, or apply `font-deva` only to Devanagari runs).

---

## F6 — Pravachan mode slow to answer  ✅ DONE (5f0a851)

**Symptom:** pravachan takes much longer to answer than QnA.

**Root cause (confirmed):** `tools/llm_client.py:pick_model` put pravachan on
**Opus** (vs QnA's Sonnet), generating a **7000-token** structured discourse.

**Fix (done):** `pick_model` now returns Sonnet for every mode → QnA-like
responsiveness. Deliberate, reversible quality tradeoff. **Needs a backend
restart to take effect.**

---

## F7 — "Ranade" should always be "Gurudev" / "Shri Gurudev"

**Symptom:** many places show "Ranade" / "Gurudev Ranade" / `gurudev_ranade`;
the convention should be **always "Gurudev" or "Shri Gurudev", never "Ranade"**.

**Locations:** citation attribution (`· gurudev_ranade`), framing prose ("Gurudev
Ranade's writings"), Reading header ("Shri Gurudev Ranade · …"), author display.

**Fix scope:** frontend author-display mapping (`gurudev_ranade` → "Shri
Gurudev") + a prompt instruction (refer to him as Gurudev / Shri Gurudev, never
"Ranade"). Decide the standard: e.g. "Shri Gurudev" in attributions, "Gurudev"
in prose.

---

## F8 — Chatbot personality / voice

**Request:** give the assistant a personality — **warm, happy, deeply
respectful** to the reader; **excited** to share knowledge, insight, and
perspectives from the vast literature; and eager for the reader to **know more
about Gurudev and his works**. Applies across the system prompts (qa / pravachan
/ reading framing + synthesis), while keeping quotes verbatim and not turning
answers into gush. Fix scope: prompt changes in `tools/prompts.py`.

---

## F9 — Keep RFCs/ADRs updated

**Request:** as these changes land, update the RFCs/ADRs accordingly (e.g.
RFC-001 model choice now Sonnet for pravachan; reading-mode real-data endpoint;
personality/voice; Gurudev naming convention). Fix scope: docs under
`docs/rfc/` and `docs/adr/` (or wherever they live) — touch the affected ones as
each fix lands, plus a sweep at the end.

---

## F10 — Reading mode must serve only *verified* content

**Constraint (user):** reading mode now serves raw `text.md` verbatim, which can
include OCR errors / unverified scans. Reading should only present content we
**know is verified/clean**.

**Open question:** what marks content as "verified"? (a per-work/per-section
quality flag? canonical-only? a curated allowlist?) No explicit flag is known
yet. **Interim plan:** restrict reading to `kind=canonical` works and run the
garble cleaner (`clean_quote_body`) over served paragraphs, until a real
verification flag exists. Confirm the definition before finalizing.

---

## F11 — "Continue reading" / reading progress surface

**Request/UX gap:** a reader can't easily get back to a work they were reading,
nor see what they've started.

**Current state:** per-work resume already works — the reading page persists the
page in `localStorage` (`gd:read:{slug}:page`), so reopening a work restores the
page. Missing is an *entry point* listing started works.

**DECIDED (2026-06-25): a "Continue reading" shelf on the Reading landing.** As
the user reads, store a progress record per work in `localStorage`
(`{ slug, workTitle, page, totalPages, lastReadAt }`). Render a **"Continue
reading"** row at the TOP of the reading landing (home, reading mode), ABOVE
"begin a new work" — cards with the work title, a progress bar, and "p.X/Y",
most-recent first, each resuming that work at its saved page; optional remove
control. Self-contained frontend feature (no backend).

---

## F12 — Returning home from a book lands on Q&A, not the Reading landing  ✅ DONE

**Symptom:** from inside a work, "Back to start" went to the Q&A landing.
**Cause:** `chat-app/app/read/[slug]/page.tsx` back-link was `/?lang=…` (no mode);
home defaults to Q&A.
**Fix (done):** back-link now `/?mode=reading&lang=…`.

---

## F13 — "Mysticism in Maharashtra" gives a 404 in Reading mode

**Diagnosis:** the work exists on disk
(`01_canonical/gurudev_ranade/books/mysticism-in-maharashtra/en/text.md`,
work_id `mysticism-in-maharashtra`) and the backend `GET /read/mysticism-in-maharashtra`
returns **HTTP 200**. It is NOT a reading suggestion and NOT in `catalog.yaml`.
So the 404 is a **frontend slug mismatch** — some link sends a slug that doesn't
resolve. NEED: which surface the user clicked it from (reading suggestion?
"Read in full" citation link? continue-reading shelf? pravachan readSlug?).
Likely fixes: correct the offending slug, and/or register canonical readable
works in `catalog.yaml` (also fixes the FS-fallback's wrong title-casing, e.g.
"Pathway To God In Hindi Literature").

---

## F14 — "Read in full" must deep-link to the citation's page

**Request:** F4's "Read in full" link opens the work at page 1; it must open at
the **reading page that contains the cited passage** (that's where the user
wants to go).

**Approach:** server computes each citation's reading page from the cited
chunk's `char_start` (mapped to the paragraph index via the SAME pagination the
`/read` endpoint uses), exposes it as `Quote.readPage`; the "Read in full" link
becomes `/read/{workId}?page={readPage}`; the reader honors a `?page=` URL param
(overriding the saved page). Built via worktree subagent.

---

## F15 — "Read in full" / reader back-nav should return to the origin

**Symptom:** opening a work via a "Read in full" link and pressing "Back to
start" goes to the Reading landing, losing where you came from — whether that
was a **Q&A session** (#2) or **another book** you were reading (#3).

**Cause:** the F4 "Read in full" link omits `?from=`, so the reader's
origin-aware back (`returnTo = search.get("from")`) has nothing to use, and falls
through to the default (`/?mode=reading`, the landing).

**Fix:** every "Read in full" link (QnA citations via `QuoteBlock`, and any
in-reader citation links) passes `from` = the current URL (the QnA session, or
the current book's reader URL). The reader's back link then returns there; only
fall back to the Reading landing when there's no origin. Make "Back to start"
prefer `returnTo` when present.

**Note (F14 verify):** if "Read in full" still opens page 1, suspect a stale
frontend (hard-refresh) or a citation from a work with no ingested `text.md`
(no `readPage` computable — overlaps F13). Code chain verified correct.
Also still TODO: a regression test for `reading_page_for_offset` (works, untested).

---

## F16 — Activate "Report issue" + "Share" buttons (gates garble Phase 2)

The `AnswerToolbar`'s **"Report issue"** and **"Share"** buttons are currently
inactive. They must be wired up first, because:
- **Report issue = the flag-and-queue entry point** for garble Phase 2. Clicking
  it flags the answer / a passage (optionally with a note) and POSTs to a backend
  endpoint that records it to a **queue** (file/log). No inline editing by users.
- **Share** = share the current answer (copy a shareable link / Web Share API).

## Garble verifier — Phase 2 (decisions locked 2026-06-25)

- **Flag-and-queue** (NOT inline correction): user flags via "Report issue" →
  recorded to a queue. Maintainer applies the correction to the source chunk
  later.
- **Re-embed IS in scope:** after a source chunk is corrected, that chunk is
  re-embedded (the `/admin/reload` endpoint then picks it up live).
- **Order:** F16 (activate Report/Share) → flag-and-queue wiring → maintainer
  correction tool → re-embed. Build on F16.

---

## Status (2026-06-26): all catalogued build items complete

F1–F16 are all built, merged to `main`, and live. The **only** outstanding work
is the **garble Phase 2 maintenance step** (not a build): a tool/process for a
maintainer to read `logs/issue_reports.jsonl`, correct the flagged source chunk's
text, and re-embed it (then `/admin/reload` picks it up live). Everything else
from this QA pass is done.

## F17 — Reading-mode "Ask about this work" chat isn't intelligent (demo feedback)

**Symptom:** the reader's drawer chat only quotes a passage from the work; it
can't actually answer basic questions.

**Cause:** the drawer posts `/ask` with **mode=reading**, which returns a
`ReadingResponse` (framing + ONE verbatim passage), not a synthesized answer.

**Fix:** route the drawer's questions through the **Q&A pipeline scoped to the
current work** — backend: when `mode=="qa"` and `req.work` is set, apply
`metadata_filter={"work_id": req.work}` (the existing max_per_source line already
gives `top_k` for work-filtered retrieval). Frontend: the drawer sends `mode=qa`
+ `work=slug` and renders the full Q&A answer (framing + citations + synthesis),
drawn only from that work.

## F18 — Correct paragraphs in Reading mode → review queue (demo feedback)

**Request:** in the reader, let the user select/highlight a paragraph, submit the
corrected text, and add it to the review queue.

**Fix:** per-paragraph "suggest correction" affordance → a form prefilled with the
paragraph text → submit to the queue. Extend the F16 `/report` endpoint with a
correction type carrying `{ slug, page, paragraphN, original, corrected }`,
appended to `logs/issue_reports.jsonl` (or a sibling corrections queue). Builds on
F16. (This is the user-facing half of garble Phase 2's flag-and-queue, for
reading text specifically.)

## F19 — Question/UI language mismatch (demo feedback)

**Concern:** what if someone asks in English while in Marathi mode, or vice
versa? Today the answer's prose language follows the `lang` toggle, not the
question — so a mismatch gives an answer in the "wrong" language.

**Decision/fix:** the assistant's **prose** (framing, whyChosen, synthesis;
pravachan thesis/whyThisExample; reading framing) should be written in the
**same language as the user's question**, regardless of the UI `lang` toggle
(English question → English answer; Devanagari question → Marathi answer). The
`lang` toggle remains a fallback hint for short/ambiguous questions. **Verbatim
quotes stay in their source language** (ADR-007). The `paraphrase` gloss is
provided when the quote's language differs from the **question's** language
(was: the user's toggle). Prompt-only change (`tools/prompts.py`).

## F20 — Retrieval misses keyword-specific passages (e.g. "idol worship")

**Symptom:** "What do the books say about Idol Worship?" returns a meta answer
("the retrieved passages do not contain material… on idol worship"), but the
corpus clearly covers it — *Vindication of Indian Philosophy*, *Philosophical and
Other Essays*, *Herakleitos*, *Patankar Pravachan 3* all discuss "idol-worship".

**Diagnosis (free probe, no API):** the relevant passage ("*Bhakti does not
consist…in formal idol-worships: it consists in love to God*") has only MODERATE
**dense similarity** to the query — cosine **rank 34** (Vindication) / **147**
(Philosophical Essays) of 15,306 — because the passage is semantically about
Bhakti/love-of-God and names "idol-worship" only in contrast. General-devotion
chunks outscore it. Verified: even `candidates=100` doesn't surface it, because
the **1-chunk-per-work cap** then gives each work's slot to its higher-scoring
non-idol chunk. So this is a dense-retrieval RECALL limit, not a candidate-window
or content gap.

**Fix:** HYBRID retrieval — complement dense embeddings with **lexical/keyword
matching** (e.g. BM25 or a term-overlap scorer) so passages containing the
query's distinctive terms are recalled even when dense similarity is moderate.
Implementation sketch: inject lexical candidates (chunks containing the query's
rare content words) into the candidate pool before MMR, and/or reciprocal-rank-
fuse dense+lexical scores; ensure a keyword-matched chunk can win its work's slot.
Touches `tools/retrieve.py` + `server.py` `_retrieve` — sequence AFTER F18
(server.py overlap). Highest-value remaining retrieval-quality item.

<!-- append new findings below as testing continues -->
