# Gurudev Corpus

Source-of-truth repository for the works, lectures, and oral tradition surrounding **Shri Gurudev Ranade** (the Nimbal lineage), including writings of Kakasaheb Tulpule and other authors in the tradition.

This is Phase 1 of a two-phase project. Phase 2 will build a chat platform that answers questions by citing material curated here.

## Languages in scope

English (primary, first milestone) → Marathi (next) → Sanskrit, Kannada, Hindi (later). Structure is designed so any work can carry parallel translations side by side.

## Directory map

```
00_raw/           # untouched dumps — never edit, never delete
  inbox/          # drop new PDFs, DOCX, scans, transcripts here

01_canonical/     # works preserved true-to-original, one folder per author
  gurudev/
    books/        # one folder per book → <slug>/{meta.yaml, en/, mr/, ...}
    lectures/
    letters/
  kakasaheb_tulpule/
  other_authors/

02_aggregated/    # synthesized content (oral tradition, many tellings)
  athvani/
    stories/      # one folder per story → variants kept + consolidated
  parables/

03_catalog/       # cross-cutting indexes
  schemas/        # meta.yaml templates for works and stories
  catalog.yaml    # master index of every work (built up over time)
  duplicates.yaml # raw-file dedup mapping
  glossary.yaml   # Marathi/Sanskrit/Kannada terms + transliteration

04_processed/     # built later in Phase 1: chunks, embeddings, search index
```

## Per-work layout

Every canonical work (book, lecture, letter) gets its own folder:

```
01_canonical/gurudev/books/pathway-to-god-in-hindi-literature/
  meta.yaml
  en/
    source.pdf       # original, immutable
    text.md          # cleaned extraction (OCR/parse)
  mr/
    source.pdf
    text.md
```

The folder slug is language-neutral; the languages it carries are listed in `meta.yaml`.

## Per-story layout (athvani)

```
02_aggregated/athvani/stories/<story-slug>/
  meta.yaml
  en/
    consolidated.md      # merged authoritative telling
    variants/
      source_<work-id>.md   # each verbatim variant from a source work
```

The variants are never destroyed — Phase 2 chat can say "this story is told by X, Y, and Z; here's how each differs."

## Workflow

1. **Dump** raw files into `00_raw/inbox/` (any format, any organization).
2. **Catalog** each file: identify what it is, where it belongs, what language(s).
3. **Extract** text into the appropriate `01_canonical/.../text.md` or `02_aggregated/.../variants/`.
4. **Consolidate** athvani variants into a merged version once enough sources are collected.
5. **Process** (Phase 1 final step): chunk + embed everything in `01_canonical/` and `02_aggregated/` into `04_processed/` for Phase 2 RAG.

Raw files in `00_raw/` are immutable. Everything downstream can be re-derived from them.
