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

<!-- append new findings below as testing continues -->
