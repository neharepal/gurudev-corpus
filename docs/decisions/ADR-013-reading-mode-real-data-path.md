# ADR-013: Reading mode — real-data backend endpoint, pagination, and citation deep-links

**Status:** ACCEPTED
**Date:** 2026-06-25
**Author:** Neha (with Claude)

## Context

RFC-004 (Chat UI & UX) described "Simple Reading" mode as showing the actual extracted text from `text.md`, paragraph by paragraph. The initial implementation used a mock `getReadingPage()` function that always returned the same fixed paragraphs regardless of which work was loaded or which page was requested (F3, QA findings 2026-06-25). Page-navigation updated a counter in the UI but did not change the content shown.

Two related UX gaps were also present:

- **F4 / F14:** "Read in full" links from Q&A citations opened the reader at page 1, not at the page containing the cited passage. The citation knew the chunk's byte offset in the work (`char_start`) but nothing mapped that to a reader page.
- **F12:** "Back to start" from inside a reading session returned to the Q&A landing, not the Reading landing, because the back-link lacked a `mode=reading` param.

## Decision

### 1. Backend endpoint `GET /read/{slug}`

A new FastAPI endpoint in `tools/server.py` serves real paginated corpus text:

- Looks up the work in `03_catalog/catalog.yaml`; falls back to a filesystem scan of `01_canonical/` for works not yet in the catalog (e.g., `pathway-to-god-in-hindi-literature`).
- Strips YAML front matter from the source `text.md`, splits on blank lines into paragraph blocks, tracks `## `section headings, and skips blocks shorter than 80 characters (decorative lines, titles).
- Paginates at **4 paragraphs per page** (`totalPages = ceil(N / 4)`).
- Returns `{workSlug, workTitle, author, chapter, totalPages, paragraphs: [{n, body}]}` — the `ReadingPage` shape already defined in the frontend type.
- **Author display:** `gurudev_ranade` → "Shri Gurudev"; all other author IDs are title-cased with underscores replaced by spaces.
- **Cache:** parsed work text is cached in-process (`_reading_cache`); the existing `POST /admin/reload` clears it.
- **Error behavior:** work not found (catalog + filesystem) → HTTP 404; `text.md` missing → HTTP 404; page out of range → clamped to valid range.

See commits `16d15cf` (endpoint), `0340bc5` (backend tests), `5066b04`/`24207fe` (frontend wire-up).

### 2. Frontend wire-up

`chat-app/app/read/[slug]/page.tsx` was converted from using `getReadingPage()` (mock) to a `useEffect` fetch against a new Next.js API proxy route `GET /api/read?slug=…&lang=…&page=…` (see `chat-app/app/api/read/route.ts`). The proxy forwards to `$GURUDEV_BACKEND_URL/read/{slug}`, mirroring the `/api/ask` pattern. The `ReadingPage` TypeScript type import from `mock-conversations.ts` is retained (type-only); the data mock is not deleted (preserving other exports in that file).

### 3. Citation deep-links (`readPage`)

The structured `Quote` type gains a `readPage` field. When the backend splices a Q&A citation, it computes `readPage` from the cited chunk's `char_start` offset: using the same paragraph-level pagination as `/read/{slug}`, it maps the character offset to a paragraph index and then to a page number. The "Read in full" link becomes `/read/{workId}?page={readPage}`, so the reader opens at the page that contains the cited passage. The reader honors a `?page=` URL query param, overriding the saved `localStorage` page on initial load. See commits `84dbc5c` (F4: "Read in full" link) and `61c5013` (F14: deep-link to citation's page).

### 4. Back-navigation fix

The in-reader "Back to start" link includes `?mode=reading` so returning home lands on the Reading landing, not the Q&A landing. "Read in full" links pass a `?from=` param encoding the originating URL (a Q&A session or another book); the reader's back link returns to `from` when present, and falls back to `/?mode=reading` otherwise. See commits `464ee14`/`f72775b` (F12) and `d4b6271` (F15).

## Alternatives considered

- **Serve the full `text.md` to the frontend and paginate client-side.** Rejected: PGHL has ~1 400+ paragraphs; sending the entire book on each request is wasteful. Server-side pagination keeps the response small and consistent.
- **Use catalog entries only (no filesystem fallback).** Rejected: several canonical works (e.g., `pathway-to-god-in-hindi-literature`) were not yet in `catalog.yaml` at the time of implementation. A filesystem fallback avoids needing a catalog update before the reading feature works. The fallback should be regarded as a temporary convenience; works should be added to `catalog.yaml` for proper title and metadata.
- **Compute `readPage` on the frontend.** Rejected: the frontend does not have direct access to chunk metadata (char offsets are a backend concern). Computing it server-side alongside splice keeps the logic co-located.

## Consequences

**Positive:**
- Reading mode now shows real corpus text, not mock data. Page navigation fetches new content from the server.
- "Read in full" links from citations deep-link to the correct page, directly placing the reader at the cited passage.
- The `_author_display_name` convention ("Shri Gurudev", never "Ranade") is enforced at the API layer for all reading responses.

**Negative:**
- Works not in `catalog.yaml` get titles inferred from their slug (title-cased slug), which can produce slightly wrong casing (e.g., "Pathway To God In Hindi Literature" vs. the correct form). Mitigation: add such works to `catalog.yaml`.
- The 80-character paragraph filter may skip some short-but-legitimate paragraphs (Doha verses, section epigraphs). The threshold may need per-work tuning.

## Open items

- **Works without `text.md` 404:** if a canonical work has no extracted `text.md`, the endpoint returns 404. This is surfaced in reading (F13: "Mysticism in Maharashtra" slug mismatch). Root cause is a frontend slug mismatch in that case, but the general gap remains: not all works in the catalog have an extracted `text.md`.
- **Reading should be limited to verified canonical works (F10):** `text.md` files may contain OCR errors or unverified scans. Until a per-work quality/verification flag exists, reading mode should restrict to `kind=canonical` works and run the garble cleaner (`clean_quote_body`) over served paragraphs. This is an open constraint, not yet enforced by the endpoint.
- **Regression test for `reading_page_for_offset`:** the function that maps char offsets to page numbers is correct but untested. A unit test should be added.
- **`catalog.yaml` should eventually list all readable works** to ensure correct titles, language availability, and kind filtering.

## Author display convention

`gurudev_ranade` → "Shri Gurudev" in all user-facing text. This is enforced in `_author_display_name` (backend), `QuoteBlock` author rendering (frontend), and the system prompts. See also ADR-006 Amendment (2026-06-25).

## References

- [RFC-004 Chat UI & UX](../rfc/RFC-004-chat-ui-and-ux.md) — Simple Reading mode specification
- [ADR-011 Structured output contract](ADR-011-structured-output-contract.md) — wire shape for `Quote.readPage`
- [ADR-006 Warm devotional aesthetic](ADR-006-warm-devotional-aesthetic.md) — author display and voice amendments
- [docs/superpowers/plans/2026-06-25-reading-mode-real-data.md](../superpowers/plans/2026-06-25-reading-mode-real-data.md) — implementation plan
- QA findings F3, F4, F10, F12, F13, F14, F15 in [docs/qa-findings-2026-06-25.md](../qa-findings-2026-06-25.md)
