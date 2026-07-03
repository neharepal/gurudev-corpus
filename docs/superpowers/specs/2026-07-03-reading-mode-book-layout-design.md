# Reading Mode — book-like layout (design)

**Date:** 2026-07-03 · **Status:** approved (pending spec review)

## Goal
Make Reading Mode feel like reading a printed book, **without** changing the
established aesthetic (parchment background, colors, Crimson Pro / Noto Serif
Devanagari fonts). Small typographic + layout changes only.

## Scope
Frontend: `chat-app/app/read/[slug]/page.tsx`, `chat-app/app/globals.css`
(+ possibly `tailwind.config.ts`). Backend: `tools/server.py` (pagination).
No new dependencies. Palette/textures/fonts untouched.

## Changes

### 1. Book-style paragraphs *(frontend/CSS)*
- First-line **indent ~1.4em**; **no blank-line gap** between paragraphs
  (remove the current `mb-7` inter-paragraph spacing).
- The **chapter-opening paragraph is flush** (no indent) — standard convention.
  Continuation paragraphs (including the first paragraph on a continuation page)
  are indented.
- Body size/leading unchanged (17.5px / 1.7). Text stays **left-aligned/ragged**
  (no justification — Marathi has no hyphenation → rivers).

### 2. Sticky context header *(frontend)*
- A quiet single line at the top of the reading column: **`Work Title · Chapter`**.
- `position: sticky; top: 0`, so it stays visible while scrolling a page.
- Understated: small serif, hairline rule beneath, **parchment background**
  (opaque enough to mask text scrolling under it), modest z-index. Not a solid
  app-style bar.
- Shows the **current page's chapter** (which, per §3, is unambiguous — one
  chapter per page).

### 3. Chapter starts a new page — chapter-aware pagination *(backend)*
- Replace fixed "PAGE_SIZE paragraphs per page" with: fill a page up to
  `PAGE_SIZE` paragraphs, **but a change of `chapter` forces a new page**. A
  chapter longer than `PAGE_SIZE` spans multiple pages (continuation pages).
- **Single shared helper** `paginate(paragraphs) -> List[List[paragraph]]`
  (pure, deterministic). Every consumer uses it so page numbers agree:
  - `read_work()` — `pages = paginate(all)`, `total_pages = len(pages)`,
    serve `pages[page-1]`.
  - `reading_page_for_offset()` — find the page whose paragraphs span the
    given char offset; return its 1-based index. (Deep-link "jump to cited
    passage" MUST still land on the right page.)
  - `reading_page_for_body()` — same, by matched paragraph.
- `read_work` response gains a boolean **`chapterStart`** (true when this page
  is the first page of its chapter) so the frontend knows whether to render the
  chapter opener (flush first paragraph + optional in-prose chapter heading)
  vs a continuation page (indented first paragraph, no in-prose heading).

### 4. Folio *(frontend/CSS)*
- A **centered page number** ("Page X of Y" / localized) placed **below** the
  text column, styled as a book folio. The existing navigation slider stays.

### 5. Quieter reading surface *(frontend)*
- The per-paragraph "suggest correction" link becomes **hover-revealed**
  (opacity 0 by default; visible on paragraph hover and on keyboard focus for
  accessibility). Behavior unchanged — just not always-on chrome.

## Explicitly out of scope
- No drop cap (awkward on Devanagari conjuncts + शिरोरेखा).
- No justified text. No measure change (stays `max-w-reading: 70ch`).
- No per-page running-head repetition (the one sticky header §2 covers it).
- No palette/texture/font changes.

## Data flow
`read_work(slug, lang, page)` → `_parse_work_text` (paragraphs w/ `chapter`,
`char_start/end`) → `paginate()` → page slice + `chapterStart` + `chapter`
+ `totalPages` → frontend renders sticky header, prose, folio. Deep-links from
citations call `reading_page_for_offset()` → same `paginate()` → correct page.

## Testing / verification
- `tsc --noEmit` (frontend) and `py_compile` (backend) clean.
- Pagination: a work WITH chapters (e.g. `charitra-tatvajnan-tulpule`, 4 chapters)
  — every chapter's first paragraph lands on a page where `chapterStart=true`;
  `totalPages` ≥ number of chapters; no page mixes two chapters.
- Deep-link integrity: for a sample chunk, `reading_page_for_offset(offset)`
  returns a page whose paragraph span contains that offset (paginate consistency).
- A work WITHOUT meaningful headings degrades gracefully to ~PAGE_SIZE per page.
- Manual: sticky header stays pinned + shows correct chapter; paragraphs indent
  with no gaps; correction link hidden until hover.

## Risks
- Deep-link page mapping drifting from `read_work` pagination — mitigated by the
  single shared `paginate()` helper used by all three call sites.
- Very short chapters → many short pages. Acceptable (book-like); no cap.
