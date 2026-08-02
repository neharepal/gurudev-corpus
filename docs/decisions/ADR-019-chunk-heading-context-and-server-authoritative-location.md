# ADR-019: Stamp `##`/`###` heading context onto every chunk and let the server author `quote.location`

**Status:** PROPOSED
**Date:** 2026-08-02
**Author:** Neha (with Claude)

## Context

The RFC-020 rebuild of Kakanchi Pravachane produced a `text.md` with a
clean two-level hierarchy: 5 `## भाग N` sections holding 47 `### <chapter
title>` chapters. The `/read/{slug}/toc` endpoint reads that structure and
serves a working, ornamented reader-mode TOC.

But when the same corpus is cited in a Q&A answer, the citation footer
today shows only:

    — Kakanchi Pravachane · Kakasaheb Tulpule

Chapter and section never appear — not for KP, and not for any of the
other works whose canonical `text.md` also carries `###` markers
(Mysticism in Maharashtra: 16 headings; Bhagavadgita as Pathway to
God-Realization: 4). The structure was built but never carried through to
the citation layer.

A grep-driven audit found three connected gaps that together produce this:

1. **Chunker ignores headings.** `tools/chunker.py::chunk_text` splits
   `body_text` on blank lines and greedy-packs paragraphs; the returned
   dicts carry only `{text, char_start, char_end}`. `emit_chunks_for_source`
   builds each row's metadata from `base_meta` (work-level: `work_id`,
   `author`, `title`, `language`). Result: every chunk row in
   `04_processed/chunks.jsonl` has zero `section` / `chapter` fields, even
   for works whose `text.md` is full of `##`/`###` markers.
2. **`_enrich_citation_location` is dead code.** Defined at
   `tools/server.py:2325` when ff4784d shipped alongside the RFC-020
   data rebuild, `grep` finds zero callers. And even if wired in, it reads
   `chunk["meta"]["chapter"]` — a field the chunker never populates.
3. **`quote.location` is currently LLM-composed.** With no server-side
   authoritative label, the model emits whatever it thinks fits. In
   practice, for KP that reliably becomes work title + author, never
   chapter — the LLM cannot see chunk metadata beyond `cite_text`, so it
   has no source of truth for the chapter.

The chunker's silence about headings is the root — until each chunk knows
where in the book's outline it sits, no downstream layer can reliably
label a citation.

### Why the earlier attempts didn't work

Two earlier attempts got partway and both fell short.

**Attempt 1 — half-wired enricher (`ff4784d`, RFC-020 ship).**
`_enrich_citation_location` landed as a function definition only.
`grep -n _enrich_citation_location tools/server.py` finds a single
match — the definition itself. No caller was ever added. And even if
one had been added, the function looks up
`chunk["meta"]["chapter"]` / `chunk["meta"]["section"]`, fields the
chunker doesn't produce, so the lookup would have returned nothing
regardless. (The subsequent revert commit `93ed8a5` was RFC-021
Changes 1+2 rollback — orthogonal, touched only
`_enforce_and_verify_qa` and `splice_qa_citations`.)

**Attempt 2 — headings-in-body (implicit, as a side effect of RFC-020).**
The RFC-020 rebuild wrote `## भाग N` and `### <chapter>` markers into
`text.md`. Because the chunker splits on blank lines and greedy-packs
paragraphs, chunks that *happen to start at a heading boundary* now
carry the heading lines verbatim inside their `cite_text` / `text` /
`embed_text`. A sample row:

    cite_text: '## भाग १\n\n### वैकुंठचतुर्दशीनिमित्त\n\n१९०१ साली …'

So the heading context is technically present — but as embedded raw text,
not as a queryable field, and only in a tiny subset of chunks. Why this
isn't enough:

- **Coverage is 0.4%.** KP has 12,172 chunk rows in `chunks.jsonl`. Only
  ~52 begin at a `##` or `###` boundary; the other 99.6% see no heading
  anywhere in their content and have no way to know their chapter.
- **Placement is LLM-controlled.** For the few chunks that do carry the
  heading, whether the model puts it into `quote.location` (desired) or
  leaves it inside `quote.body` (undesired — the quote then starts with
  `## भाग १` and `###` markers that render raw in the frontend) is not
  enforced anywhere.
- **The heading-in-body leak is a small regression at the edges** for
  the chunks it does affect: instead of a clean quote body, the reader
  sees markdown syntax bleeding into the citation.

This ADR is the missing follow-through: stamp typed metadata onto every
chunk (100% coverage, not 0.4%), wire the enricher (both callsite and
data source), and let the server author `quote.location` deterministically
so the LLM has no role to play in the labelling.

## Decision

Do three connected things in one commit-and-deploy:

### A. Track `##`/`###` context in the chunker

In `tools/chunker.py`, add a `build_heading_index(body_text)` helper that
walks the text once and returns a list of `(offset, level, title)` tuples
for every line matching `^##\s+…` (level 2) or `^###\s+…` (level 3).
Add a companion `headings_at(index, offset) → (section, chapter)` that,
for a given char offset, returns the last-seen level-2 heading before or
at that offset and the last-seen level-3 heading between the section and
the offset. Ties/edge cases resolve to the heading at or before the
chunk's `char_start` — the point the reader lands on when they follow
"Read in full."

In `emit_chunks_for_source`, call these once per source and stamp
`section` and `chapter` (empty string when absent) onto every parent
AND child row. Neither field affects the chunk id, char range, or text —
purely additive metadata.

Behavior on works without heading markers is a no-op: `section` and
`chapter` come out empty, downstream enrichment sees nothing to override,
citations for those works stay exactly as they are today.

### B. Wire `_enrich_citation_location` and let the server author `location`

In `tools/server.py`, extend `_enrich_citations_readpage` to also call
`_enrich_citation_location(c, label_to_chunk)` on every citation.
Add the same call to the true-streaming per-item enrichment path
(currently `_enrich_citation_readpage` at line 2615). The function
overwrites `quote.location` from the underlying chunk's structural
metadata:

- both `section` and `chapter` present → `"<section> · <chapter>"`
  (e.g. `"भाग १ · वैकुंठचतुर्दशीनिमित्त"`)
- only `chapter` → `"<chapter>"`
- only `section` → `"<section>"`
- neither → do not overwrite (keep whatever the LLM emitted; matches
  today's behavior for works without heading structure)

The existing function signature is correct; the `.meta.chapter` lookup
matches the shape of chunks returned by `_retrieve` (verified at
`tools/retrieve.py:624`: chunks are constructed as `{"meta": meta, …}`).

This turns `quote.location` into a **server-authored** field for any work
with `##`/`###` markers, and preserves the LLM's guess as fallback for
works without them.

### C. Re-chunk KP and rsync the sidecar files to prod

The chunker change is only visible once chunks are regenerated. Steps:

1. Locally re-run the chunker restricted to Kakanchi Pravachane, replacing
   its rows in `04_processed/chunks.jsonl` and `04_processed/parents.jsonl`
   in place.
2. Verify a spot-sample: a KP row's `section` reads `भाग N`, `chapter`
   reads a real chapter title.
3. Embeddings are unchanged — chunk text and IDs are stable, so
   `04_processed/embeddings/*` needs no touching.
4. Take a `.bak` of both JSONL files (matching the existing
   `.pre-rfc020-2026-08-01.bak` convention), rsync the two updated files
   to prod, restart the backend so the in-memory `STATE.metas` reloads.

## Non-goals

- **Not rewriting the LLM prompt to compose location differently.** The
  LLM has no reliable way to know the chapter; letting it guess more
  aggressively would trade one form of hallucination for another.
  Server-authored is the right layer.
- **Not backfilling `##`/`###` markers into books that lack them.**
  That's the tracked, book-by-book work of task #58 (per project memory
  `project_toc_allowlist`). This ADR is the mechanism; every book that
  earns heading structure automatically gets richer citations from the
  next re-chunk onward.
- **Not adding a new field to the citation schema.** `quote.location`
  already exists in `QAResponse`; we're just making the server the
  source of truth for it where possible.
- **Not touching the reader-mode TOC.** That reads directly from
  `text.md`, unrelated to chunk metadata.

## Consequences

**Positive**
- KP citations gain `भाग N · <chapter>` provenance — the RFC-020 outline
  finally becomes visible to the reader in the answer surface, not only
  in the reader-mode TOC.
- Mysticism in Maharashtra (16 headings) and Bhagavadgita as Pathway
  (4 headings) benefit automatically from the same commit — no per-book
  work required beyond re-chunking them once.
- Future books that get their hierarchy restored under task #58 gain
  citation labels for free at their next re-chunk. Payoff scales linearly
  with the book-restoration effort.
- Removes a class of LLM-drift: `quote.location` for structured works is
  now deterministic and cannot hallucinate a chapter that doesn't exist.

**Negative / risks**
- Two new fields on every chunk row (empty string for most works today):
  small storage overhead (~24 bytes × chunk count), no runtime cost.
- The heading index needs to cope with unusual `text.md` shapes — HTML
  comments, indented headings, `####` and deeper (ignore), and headings
  inside code fences. Chunker walks are plain-regex today; we accept the
  same class of edge cases (a `###` inside triple-backticks would be
  mis-attributed). Given canonical texts don't use code fences, this is
  a theoretical risk.
- One backend restart to pick up the reloaded JSONLs.

**Neutral**
- No prompt changes, no schema changes, no embedding recompute, no
  frontend changes. The QuoteBlock already renders `quote.location` when
  present.

## Rollout

1. Land chunker change + server wiring in one commit; local type-check.
2. Local: re-chunk KP, verify a spot-sample citation footer via `curl`
   on `/ask`.
3. Push branch, review.
4. On approval: rsync JSONLs to prod, restart backend.

## Verification

Local:

```sh
curl -s -X POST http://localhost:8765/ask \
  -H "Content-Type: application/json" \
  -H "X-Invite-Code: $INVITE" -H "X-Sadhak-Name: adr019-test" \
  -d '{"mode":"qa","question":"Give excerpts from Kakasaheb lectures","lang":"en"}' \
  | jq '.citations[] | {workId: .quote.workId, location: .quote.location}'
```

Expected: every citation whose `workId == "kakanchi-pravachane"` has
`location` matching `भाग [१२३४५] · .+`. Every non-KP citation from a
work without heading structure has `location` = whatever the LLM composed
(unchanged).

Prod: same curl against the deployed backend after rsync + restart.
