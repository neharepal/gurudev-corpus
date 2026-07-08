# RFC-013: Source-text cleanup — page furniture (running headers/footers)

**Status:** PROPOSED
**Author:** Neha (with Claude)
**Created:** 2026-07-07
**Last updated:** 2026-07-07

## Summary

Detect and strip **page-furniture lines** — scanned running headers/footers, page
numbers, and header bands — that OCR/pandoc captured as body paragraphs in the
canonical `text.md` files. Do it as an extraction-time pass (in the RFC-009
ingestion pipeline) plus a one-time backfill over existing works, then re-chunk
and re-embed. This is distinct from, and complementary to, the existing
char-junk cleaner and the flag-and-queue workflow.

## Motivation

Surfaced during the Reading-Mode work (2026-07-03..07). In the reader, works
derived from scans open with lines like:

- `NNA I ASD I NVA I Reflections I Feb2014   2` — a running header: codes │ work
  title │ date │ page number, with the pipe separators OCR'd as "I".
- `सहस्रनयनः श्रीमान् शतशीर्षः सहस्रपात्` — a Sanskrit invocation used as a
  per-page running head.

These are the original page's header/footer band, captured **once per scanned
page** and stored as real paragraphs in `text.md` (often adjacent to a form-feed
`\x0c` page-break char). Three concrete harms:

1. **Reader** shows them as body paragraphs (breaks the reading experience).
2. **Pagination/labels:** `_parse_work_text` can mistake a furniture line for a
   section heading, so chapter-aware pagination (RFC-009 reader path) fragments
   and the "chapter" label shows garbage.
3. **Retrieval/citations:** a furniture line can become its own chunk — embedded,
   retrievable, and quotable as if it were content.

## Goals & non-goals

**Goals**
- Remove per-page running headers/footers, page-number-only lines, and header
  bands from canonical `text.md` at the **source**, so every downstream consumer
  (reader, chunker, embeddings, citations, pagination) is clean at once.
- Be **conservative**: never remove real content (short headings, one-off
  invocations, verse lines).
- Idempotent, reviewable, and part of the standard ingestion runbook.

**Non-goals**
- Character-level junk inside a paragraph — already handled by the citation-body
  cleaner (see References). This RFC is **line/paragraph-structural**.
- Fixing OCR accuracy of real text (that is the Devanagari-OCR track).
- Manual per-passage correction — the flag-and-queue workflow (ADR-016) remains
  the human-in-the-loop fallback for stragglers.

## Approach

Add `tools/strip_page_furniture.py`: reads a work's `text.md`, identifies
furniture lines, and writes a cleaned `text.md` **plus a diff report** for review
before applying. Run it as a step in the RFC-009 pipeline for new works, and as a
backfill over the existing corpus.

**Detection — repetition is the primary, safest signal.** A running header
repeats ~once per scanned page across the whole work; real headings do not. So:

1. Normalize lines (collapse whitespace, map OCR pipe-"I" runs, strip page
   numbers) and bucket near-identical short lines across the work.
2. Flag a normalized line as furniture when it recurs above a threshold
   (e.g. ≥ N occurrences or ≥ X% of `\x0c` page breaks).
3. Secondary structural cues raise confidence (used to catch the rare
   non-repeating case, never alone): a form-feed neighbor; contains the work
   title **and** a 4-digit year and/or a trailing bare page number; pipe/"I"
   column runs; a lone numeral line.
4. Leave everything else untouched.

**Where it runs:** at extraction time (after `docx→md` / OCR, before chunking) in
RFC-009, and a one-time backfill. After a backfill: `chunker.py` →
`build_corpus_manifest.py` → `embedder.py` (incremental) → `/admin/reload`.

**Alternatives considered**
- *Parse/render-time filter* (strip in `_parse_work_text` and the chunker):
  reversible and no source mutation, but must be duplicated in every consumer and
  does **not** fix already-embedded furniture chunks. Rejected as the primary fix;
  may be a cheap interim guard in the reader.
- *Flag-and-queue only* (ADR-016): human-verified but does not scale to thousands
  of per-page headers. Kept as the fallback, not the mechanism.

## Risks & mitigations

- **Over-removal of real content** (a short heading, or the `सहस्रनयनः`
  invocation where it is genuine text rather than a running head). → Repetition
  threshold + review-the-diff gate before apply; never auto-apply structural-cue-
  only hits.
- **`text.md` is derived, not raw.** ADR-005 immutability covers `00_raw`; `text.md`
  is regenerable, so editing it is allowed — but keep the raw source and re-run
  reproducible. Commit cleaned text with the report.
- **Re-embed cost** after backfill — incremental embedder by `chunk_id` (ADR-012)
  limits it to changed works.

## Open questions

1. Apply gate: auto-apply above a high-confidence repetition threshold, or always
   human-review the per-work diff first?
2. Also harden `_parse_work_text` so a furniture line can never be promoted to a
   "chapter" (defense in depth for the reader, independent of source cleanup)?
3. Backfill scope: whole corpus, or start with the worst offenders (scanned works
   with dense running heads) identified by the detector's repetition report?

## References
- RFC-009 (ingestion pipeline) — where the extraction-time step lands.
- ADR-016 (content-flagging workflow) and the citation-body garble cleaner
  (char-junk, Phase 1) — complementary cleanup layers.
- ADR-013 (reading-mode real-data path) — the consumer where this was observed.
- ADR-005 (raw immutable; derived text regenerable).
