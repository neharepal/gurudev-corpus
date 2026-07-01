# Runbook

Operational runbook for debugging recurring issues. Each entry: **symptom →
how to confirm → root cause → fix → verification**. Confirmed findings note the
evidence (live capture, offline replication, or source trace).

---

## R1 — "Read in full" opens the wrong page (or page 1) — 2026-06-30

**Symptom:** From a Q&A answer, clicking "Read in full" on a citation opens the
reader at **page 1** (for a book not currently open) or **stays on the current
page** (for a book already open). The cited passage's page is lost. Reporter
noted it is page 1 *for every citation, all works* — not "off by a page or two".

### How to confirm (no API cost)

1. **Is the chat-app bundle stale?** The live backend already emits `readPage`
   correctly for resolvable works (proven by capture below). If page 1 happens
   for *every* work including resolvable ones, the running Next.js bundle
   predates the `readPage`/deep-link frontend code → **rebuild / hard-reload the
   chat-app first.** This is the cheapest check and explains a universal page 1.
2. **Is it the path-resolution gap?** If page 1 only happens for specific
   (mostly Marathi / pravachan / Nimbargi) works, it's defect 1a below.
3. Offline page-mapping check (no server, no API):
   `python3 tools/tests/test_reading_page_for_offset.py` (offset→page helper),
   plus the resolution sweep used during diagnosis (see "Evidence").

### Root cause — TWO distinct backend defects

**1a — Path-resolution gap (yields page 1).** `_enrich_citation_readpage`
(`tools/server.py:1186`) resolves a work's `text.md` via `reading_page_for_offset`
→ `_resolve_text_path` (`tools/server.py:190`), which only knows `catalog.yaml`
plus **5 hardcoded `…/books/` fallback dirs**. Of 39 canonical works, 5 fall
through both, so `reading_page_for_offset` returns `None` → `readPage` is never
set → the link omits `?page=` → reader opens page 1. The "Read in full" link
still *shows* because splice sets `workId` independently of page resolution.

Affected works (confirmed via realistic offline harness):

| work_id | real location | why the fallback misses it |
|---|---|---|
| `bodhsudha` | `nimbargi_maharaj/books/` | no `nimbargi_maharaj` candidate dir |
| `kakanchi-pravachane` | `kakasaheb_tulpule/lectures/` | fallback only checks `/books/` |
| `sukhasahita-dukharahita` | `kakasaheb_tulpule/lectures/` | same |
| `n-g-damle-pravachan` | `other_authors/lectures/` | same |
| `patankar-pravachan-3` | `other_authors/lectures/` | same |

**1b — Offset drift (latent; surfaces once 1a is fixed).** The chunker
(`tools/chunker.py:197-202`) stores `char_start`/`char_end` as a **synthetic
running counter** over *stripped, `\n\n`-rejoined* paragraphs — not true byte
offsets into `text.md`. `reading_page_for_offset` (`tools/server.py:242`) and the
reader's `_parse_work_text` (`tools/server.py:97`) assume real absolute offsets.
They drift, and the drift **accumulates with document depth**. Measured on
`contemporary-indian-philosophy` (300 pages): error grows from +2 pages early to
**+21 pages** deep. So even when `readPage` is set, deep citations land on the
wrong page.

### What was already (partially) done

- `a7e1254` (2026-06-29) added `passage` to the `Quote` pydantic model so the
  reference letter survives validation into the `done` response — necessary
  plumbing, but it does **not** fix 1a or 1b. `readPage` still wrong/missing.
- The frontend chain is **sound** and needs no change for this: the reader
  (`app/read/[slug]/page.tsx:152-216`) honors `?page=N` in all cases (fresh /
  stored / already-open); the SSE→`QuoteBlock` path preserves `readPage`
  verbatim. Confirmed by trace.

### Fix (decided: do both)

- **1a:** resolve `text.md` from the chunk's own `meta.source_path` (it already
  carries the exact path) instead of guessing from a hardcoded dir list.
- **1b:** compute the page by **locating the verbatim quote `body` within the
  reader's parsed paragraphs**, ignoring the broken `char_start`. No
  re-chunking / re-embedding required.
- Add a Python test asserting `readPage` end-to-end on a citation (the gap that
  let this regress: only the offset helper and `workId` splice were covered).

### Evidence (for future reference)

- **Live capture (current code, 2026-06-29)** — `done` citations carried real
  pages: `pathway-to-god-in-hindi-literature` p.155, `hindu-mysticism` p.140,
  `pathway-to-god-in-kannada-literature` p.14 → backend emits `readPage` for
  resolvable works; server is not stale; schema fix works.
- **Offline harness** — for `bodhsudha` (Marathi), `workId` set but
  `_resolve_text_path` returns `None` → `readPage` null → page 1.
- **Drift sweep** — offset-based page vs verbatim-text page diverged on all 13
  sampled chunks of `contemporary-indian-philosophy`, up to +21 pages.

---

## R2 — Back link says "Return to your Pravachan" when coming from Q&A — 2026-06-30

**Symptom:** Arriving at the reader via "Read in full" from a **Q&A** answer, the
back link reads "Back to your Pravachan" (Marathi: "तुमच्या प्रवचनाकडे परत").

**Root cause (source):** `app/read/[slug]/page.tsx:430` hardcodes
`lbl.backToPravachan` whenever `?from=` is present, ignoring that the `from` URL
encodes `mode=qa` vs `mode=pravachan`.

**Fix:** derive the label from the `from` URL's `mode` param (Q&A → "Back to your
answer" / pravachan → "Back to your Pravachan" / else generic "Back").

---

## R3 — Going "Back" from the reader re-runs the Q&A answer — 2026-06-30

**Symptom:** After "Read in full", pressing Back returns to `/chat?…&q=…` and the
answer **re-streams from scratch** instead of showing the prior (cached) answer.

**Root cause (source):** `app/chat/page.tsx:250` fetches `/api/ask` in a
`useEffect` keyed by `questionFromUrl` on every mount; the completed answer is
never cached, so back-navigation re-triggers a full streaming request (and a
billable LLM call).

**Fix:** cache the completed answer (keyed by `mode|lang|q`, e.g. sessionStorage)
and hydrate from cache on mount instead of re-fetching; only call `/api/ask` on a
cache miss.
