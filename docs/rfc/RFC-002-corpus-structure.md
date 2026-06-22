# RFC-002: Corpus structure

**Status:** ACCEPTED 2026-06-13
**Author:** Neha (with Claude)
**Created:** 2026-06-12
**Last updated:** 2026-06-12

## Summary

Formalize the on-disk layout of the Gurudev Corpus repository. Defines the five top-level folders (`00_raw`, `01_canonical`, `02_aggregated`, `03_catalog`, `04_processed`), the per-work and per-story sub-structures within each, the `meta.yaml` schemas, naming conventions, and provenance tracking. Implementation tasks reference this RFC.

## Motivation

The corpus structure has been emerging organically through implementation. Multiple decisions (lineage-aware folders, bundle attribution, raw-as-immutable archive, etc.) have been made but only documented as standalone ADRs. This RFC consolidates them into a single specification that:

1. **Anyone reading the corpus understands the layout** without needing to spelunk in old chat history.
2. **Implementation tasks (#1, #3, #5, #7) can reference this RFC** as their authoritative input.
3. **Phase 2 retrieval (RFC-003)** can rely on a known structure for indexing and metadata filtering.
4. **Future contributors** can add content following the conventions, not improvising.

## Goals

- Specify the directory layout with examples.
- Specify the `meta.yaml` schema for canonical works.
- Specify the `meta.yaml` schema for athvani stories (and the story_index design).
- Specify the bundle model used by the attribution dashboard.
- Specify naming conventions (slugs, language codes, dates).
- Specify provenance: where each file came from, what batch, what attribution decision.
- Be explicit about what's mutable vs. immutable.

## Non-goals

- The RAG-side concerns (chunking, embedding, vector index) are RFC-003's job.
- UI concerns (how the corpus surfaces in chat) are RFC-004's job.
- Multilingual generation specifics (RFC-005).
- Hosting / deployment (RFC-007).

## Proposed design

### 1. Top-level directory layout

```
gurudev-corpus/
├── 00_raw/                    # immutable archives + per-batch staging (working area)
├── 01_canonical/              # authored works, preserved verbatim, organized by author
├── 02_aggregated/             # synthesized/aggregated content (athvani, biography, periodicals)
├── 03_catalog/                # cross-cutting indexes, schemas, reference, story_index
├── 04_processed/              # Phase 2 RAG outputs: chunks, embeddings, vector index
├── docs/                      # design docs (PRD, RFCs, ADRs, roadmap)
├── tools/                     # scripts and dashboards (attribution dashboard, ingestion tools)
└── README.md
```

Each numbered prefix encodes pipeline stage: raw → canonical/aggregated → catalog → processed. Numbers help with sort order and visually communicate flow.

### 2. `00_raw/` — immutable archives + per-batch staging

```
00_raw/
├── Neha-20260611T212253Z-3-001.zip       # batch 1 zip (immutable archive)
├── Dump 2/                                # batch 2 zips folder (TBD: rename to drive_dump_2026-06-12_zips/)
│   ├── Neha-20260612T141537Z-3-001.zip
│   └── ...
├── drive_dump_2026-06-11/                 # batch 1 staging (working area)
│   └── Neha/
│       └── ...                            # extracted file tree, files move out as cataloged
├── drive_dump_2026-06-12/                 # batch 2 staging
│   ├── Neha/
│   ├── loose/
│   ├── श्री पाटणकर यांची प्रवचने भाग ३/
│   └── भगवद्गीता ध्यानप्रधान भक्तियोग/
├── _skipped/                              # files marked "skip" in attribution dashboard
└── attribution-decisions-2026-06-12.json  # dashboard export (one per attribution session)
```

Conventions:

- **Zips are immutable.** They are the canonical archive of "what was received and when." Never modified.
- **Staging is a working area.** Files MOVE out into `01_canonical/`, `02_aggregated/`, etc., as cataloged. (Per ADR-005.)
- **Staging folders use the `drive_dump_YYYY-MM-DD/` prefix.** Each batch gets its own. If multiple zips come in one day, they go into one folder.
- **`_skipped/`** holds files explicitly excluded from the corpus per attribution decisions. Kept around (not deleted) — they may be reconsidered later.
- **Attribution decision JSONs** are kept here for audit trail.

### 3. `01_canonical/` — authored works, lineage-aware

Per ADR-002, organized by lineage member:

```
01_canonical/
├── nimbargi_maharaj/
│   └── books/
│       └── bodhsudha/
│           ├── meta.yaml
│           └── mr/
│               ├── source.pdf
│               └── text.md
├── bhausaheb_maharaj/
│   └── books/
├── amburao_maharaj/
│   └── books/
├── gurudev_ranade/
│   ├── books/
│   │   ├── pathway-to-god-in-hindi-literature/
│   │   │   ├── meta.yaml
│   │   │   └── en/
│   │   │       ├── source.docx  (could be source.pdf — single source file per language)
│   │   │       └── text.md
│   │   ├── pathway-to-god-in-kannada-literature/
│   │   │   └── en/
│   │   ├── bhagavadgita-as-pathway-to-god-realization/
│   │   │   ├── en/                # English BGPGR
│   │   │   └── mr/                # Marathi ध्यानप्रधान भक्तियोग companion
│   │   └── ...
│   ├── lectures/
│   ├── letters/
│   └── (about/  — future: anthologies ABOUT Gurudev, e.g. Glimpses of Sri Gurudev)
├── kakasaheb_tulpule/
│   ├── books/
│   │   ├── maharajachi-sutre/
│   │   ├── kakanchi-pravachane/
│   │   └── kakanchi-charcha/
│   └── lectures/
└── other_authors/
    └── patankar/
        └── pravachan-3/
            └── mr/
```

#### Per-work folder layout

Each canonical work is one folder. The folder slug is language-neutral (transliterated kebab-case English). Inside:

```
<work-slug>/
├── meta.yaml                  # required — see §6 for schema
├── en/                        # if English edition exists
│   ├── source.<ext>           # original (PDF, DOCX, etc.)
│   ├── text.md                # cleaned markdown extraction (Phase 2 input)
│   └── (additional files: pages/, figures/, etc. as needed)
├── mr/                        # if Marathi edition exists
│   ├── source.<ext>
│   └── text.md
├── hi/                        # Hindi edition (if any)
├── sa/                        # Sanskrit edition (if any)
└── kn/                        # Kannada edition (if any)
```

#### Multi-file sources (bundles)

Some works arrive as multiple source files — e.g., the **Bhagavadgita ध्यानप्रधान भक्तियोग** bundle has 18 chapter booklets (.pub + .pdf). Two options for layout:

**Option A (default):** chapter files at the language root.
```
bhagavadgita-as-pathway-to-god-realization/mr/
├── source.pdf                  # main / compiled, if any
├── ch01-source.pdf
├── ch02-source.pdf
├── ...
├── ch01-text.md                # per-chapter extraction
└── text.md                     # full work concatenated (optional)
```

**Option B (subfolder per chapter):** for very large multi-file works (>30 files), nest in `chapters/`.
```
.../mr/
├── meta.yaml
├── chapters/
│   ├── 01/source.pdf
│   ├── 01/text.md
│   ├── 02/...
└── full-text.md
```

We default to Option A unless a work has >15 files, in which case Option B.

### 4. `02_aggregated/` — synthesized content

Three subkinds, all lineage-aware:

```
02_aggregated/
├── athvani/                  # multi-narrator stories about a lineage member
│   ├── about_nimbargi_maharaj/
│   │   └── stories/
│   ├── about_bhausaheb_maharaj/
│   │   └── stories/
│   ├── about_amburao_maharaj/
│   │   └── stories/
│   ├── about_gurudev_ranade/
│   │   └── stories/
│   │       └── the-old-house-at-nimbal/
│   │           ├── meta.yaml
│   │           └── mr/
│   │               ├── consolidated.md      # editorial merger (curator-written)
│   │               └── variants/
│   │                   ├── source_jaisi-ganga-vahe_p17-19.md
│   │                   └── source_<another>.md
│   └── about_other_devotees/
├── biography/                # curated biographical anthologies ABOUT a lineage member
│   └── about_gurudev_ranade/
│       └── glimpses-of-sri-gurudev/
│           ├── meta.yaml
│           └── en/
│               ├── source.pdf
│               └── text.md
└── periodicals/              # serial publications (Sadhakbodh, Kalyani Masik, etc.)
    └── sadhakbodh/
        └── mr/
            ├── meta.yaml
            └── source.pdf
```

#### Why biography is separate from athvani

Both are *about* a lineage member, not *by* them. But they are structurally different:

- **Athvani** = oral tradition. Multiple narrators tell the same incident differently. We preserve variants verbatim and (optionally) consolidate.
- **Biography** = curated authored work. A single author/editor presents an organized account. There's no "variant" model — biography is a canonical-like work, just *about* someone rather than *by* them.

Phase 2 retrieval treats them differently: athvani is for "what do devotees recall?", biography is for "what's the published account?".

#### Per-athvani-story folder layout

Each story gets a folder under `02_aggregated/athvani/about_<member>/stories/`. The folder slug is descriptive English kebab-case (e.g., `the-old-house-at-nimbal`).

```
<story-slug>/
├── meta.yaml                  # required — schema in §6
├── en/                        # if English variants exist (often empty for athvani — most are Marathi)
└── mr/
    ├── consolidated.md        # editorial merger across variants (may not exist if single-variant)
    └── variants/
        ├── source_<work-id>_<location>.md   # one file per source telling, named for traceability
        ├── source_<work-id>_<location>.md
        └── ...
```

**Variant filenames** follow `source_<source-work-id>_<location>.md` pattern. Examples:
- `source_jaisi-ganga-vahe_p17-19.md`
- `source_dada-tendulkar-athvani_ch3.md`

Each variant file carries YAML frontmatter linking to source work, page, narrator, language, raw source path, batch. (See §6.)

#### Story_index

The story index is the **master deduplication structure** for athvani: a single file (`03_catalog/story_index.yaml`) that lets us know when a new athvani candidate matches an existing story (so we add it as a variant) versus is a new story (so we create a new entry).

Schema and matching algorithm details: in §6 and RFC-003. Located in `03_catalog/` because it spans all athvani subfolders.

### 5. `03_catalog/` — cross-cutting indexes + schemas + reference material

```
03_catalog/
├── catalog.yaml               # master index: every work + every story, one row each
├── story_index.yaml           # athvani deduplication structure (per §6)
├── duplicates.yaml            # known duplicates across batches (raw file dedup map)
├── glossary.yaml              # Marathi / Sanskrit / Kannada terms, transliterations, translations
├── schemas/                   # YAML schema templates for new content authors
│   ├── work_meta.yaml
│   └── story_meta.yaml
└── reference/                 # bibliographic and meta files (not source content)
    ├── chronological-order-of-writings/
    │   └── en/
    └── kanada-saints-bio/
        └── en/
```

`reference/` holds material like "Chronological Order of Writings of Shri Gurudeo" — useful for Phase 2 (timeline questions) but not source teaching material. Phase 2 RAG should weight reference content low and never quote it as Gurudev's teaching.

### 6. `04_processed/` — Phase 2 RAG outputs

```
04_processed/
├── chunks.jsonl               # all chunked text with metadata, one JSON per line
├── embeddings/                # vector embeddings (format TBD in RFC-003)
└── vector_index/              # the built vector index (FAISS / Chroma / pgvector)
```

This folder is **derived from `01_canonical/` and `02_aggregated/`**. Can be regenerated from scratch if chunking strategy changes. Not part of the source-of-truth corpus — it's a build artifact.

Full design in RFC-003.

### 7. `meta.yaml` schemas

#### For canonical works

```yaml
id: <kebab-case-slug>            # unique, matches folder name
title: <original title in original script>
title_en: <English title>        # optional if original is English
title_translit: <Latin-script transliteration>  # optional
author: gurudev_ranade           # one of the lineage members; matches folder
co_authors: []                   # optional
work_type: book                  # book | lecture | letter | article | essay
original_language: en            # en | mr | sa | kn | hi
languages_available: [en]        # which language subfolders are populated
year_first_published: 1938       # if known
year_this_edition: 1938
publisher: ""
edition: ""
isbn: ""
sources:                         # provenance — which raw files this work was assembled from
  - raw_path: 00_raw/drive_dump_2026-06-11/Neha/...
    received_on: 2026-06-11
    checksum_sha256: <if computed>
tags: [vedanta, bhakti]
subject_persons: []
related_works: []
status: verified                 # raw | cataloged | extracted | verified
text_extraction_method: pandoc   # pdf-text | ocr-tesseract | pandoc | manual | mixed
quality_notes: ""
notes: |
  Free-form.
```

#### For athvani stories

```yaml
id: <kebab-case-slug>
title: <Marathi original title>
title_translit: <Latin script>
title_en: <English title>
about_member: gurudev_ranade     # one of the lineage members
languages_available: [mr]
themes:                          # tags for retrieval filtering
  - nimbal
  - gurudev-daily-life
people_involved:                 # named individuals in the story
  - Shri Gurudev Ranade
  - Bhausaheb Maharaj (via letter correspondence)
  - ...
subject_focus: "<one-line description>"
estimated_date_range: "1925-1958"
location: Nimbal
variants:                        # one entry per source telling
  - source_work_id: jaisi-ganga-vahe
    source_work_title: "जैसी गंगा वाहे"
    source_work_author: "Vijaya Apte (Shakuntala Ranade)"
    source_work_publisher: "..."
    narrator: "Vijaya Apte / Shakuntala Ranade"
    language: mr
    file: mr/variants/source_jaisi-ganga-vahe_p17-19.md
    page_or_section: "pp. 17-19"
    compiler: "Dilip R. Naik"
    raw_source: 00_raw/...
    received_in_batch: "drive_dump_2026-06-11"
    distinctive_details: |
      What only this variant has — important for Phase 2.
consolidated:
  status: single_variant         # single_variant | partial | complete
  by: "<curator name>"           # if curated
  on: 2026-06-12
  notes: |
    What was merged / what was excluded.
notes: |
  Free-form.
```

#### Story index entry (`03_catalog/story_index.yaml`)

```yaml
version: 1
last_updated: 2026-06-12
stories:
  the-old-house-at-nimbal:
    canonical_title: "निंबाळचे जुने घर"
    title_en: "The Old House at Nimbal"
    about_member: gurudev_ranade
    one_line: "Physical description of Gurudev's old Nimbal house (1925–58), later Samadhi Mandir"
    key_people: [bhausaheb-letters, sonopant-dandekar, sangli-yuvraj]
    locations: [nimbal]
    period: "1925-1958"
    fingerprint_phrases:        # distinctive Marathi/English phrases for matching
      - "धारवाड युनिव्हर्सिटी"
      - "जुन्या घराचे वर्णन"
      - "शेट्ट्यप्पांची खोली"
    variant_count: 1
    variant_files:
      - 02_aggregated/athvani/about_gurudev_ranade/stories/the-old-house-at-nimbal/mr/variants/source_jaisi-ganga-vahe_p17-19.md
```

### 8. Naming conventions

- **Folder slugs** — kebab-case, English transliteration when possible. `the-old-house-at-nimbal`, not `निंबाळचे-जुने-घर`. Reason: shell-friendly, version-control-friendly, consistent.
- **Language subfolders** — ISO 639-1 codes: `en`, `mr`, `hi`, `sa` (Sanskrit), `kn` (Kannada). For mixed: use the dominant language and note in meta.
- **Variant filenames** — `source_<source-work-id>_<location>.md`. The `_<location>` part can be page range, chapter, or other anchor.
- **Date strings** — ISO 8601 (`YYYY-MM-DD`) everywhere. Estimated dates use ranges (`1925-1958`) or approximation (`circa 1920s`).
- **Author folder names** — lineage members use kebab-case English transliteration: `gurudev_ranade`, `bhausaheb_maharaj` (note underscore — easier on shell quoting than `gurudev-ranade`).
- **About prefix** — athvani folders use `about_<member>` to make subject explicit.

### 9. Bundle model (used by the attribution dashboard)

A **bundle** is one attribution decision applied to multiple files. The attribution dashboard surfaces ~5 bundles where a single editorial decision (author + work_slug + language) applies to many files (e.g., Bhagavadgita 39-file source bundle → all 39 land in one work folder).

Bundle entries in the dashboard data carry:

```yaml
is_bundle: true
name: "<human label, e.g. 'Patankar Pravachan Part 3 (28 files)'>"
file_count: 28
files:
  - 00_raw/drive_dump_2026-06-11/.../...
  - 00_raw/drive_dump_2026-06-12/.../...
```

When executed during move-plan time, all files in the bundle move to the same `01_canonical/<author>/<type>/<work-slug>/<lang>/` folder. Individual chapter/sub files retain their original names.

### 10. Provenance — what we track

Every file in `01_canonical/` and `02_aggregated/` must trace back to its origin:

- **`meta.yaml`** records `sources[].raw_path` — the path in `00_raw/...` where the file originated.
- **`meta.yaml`** records `received_in_batch` — the batch identifier.
- **Variant frontmatter** records `extracted_from` — the specific raw file the variant text was extracted from.
- **Attribution decision JSONs** in `00_raw/` document the curator's choices for each batch.

If we ever need to know "where did this come from?", these four lookups cover it.

### 11. What's mutable vs immutable

| Path | Mutable? | Notes |
|---|---|---|
| `00_raw/<zip files>` | **Immutable** | Never modify or delete |
| `00_raw/drive_dump_*/...` | Mutable | Working staging area; files move out |
| `00_raw/_skipped/...` | Mutable | Can be reconsidered |
| `00_raw/attribution-decisions-*.json` | **Immutable** | Append-only audit log |
| `01_canonical/.../source.<ext>` | **Immutable** | Original work, never edited |
| `01_canonical/.../text.md` | Mutable | Regenerate if extraction improves |
| `01_canonical/.../meta.yaml` | Mutable | Updated as we learn |
| `02_aggregated/.../variants/*.md` | **Immutable** after first write | Preserve each narrator's telling verbatim |
| `02_aggregated/.../consolidated.md` | Mutable | Curated editorial product |
| `02_aggregated/.../meta.yaml` | Mutable | Updated as variants accrue |
| `03_catalog/catalog.yaml` | Mutable | Index, regenerable |
| `03_catalog/story_index.yaml` | Mutable | Updated each ingestion |
| `03_catalog/schemas/...` | Mutable | Template files for new content |
| `04_processed/...` | **Derived** | Regenerable from `01_canonical/` and `02_aggregated/` |
| `docs/PRD.md, RFCs, ADRs` | Append-only | ADRs never rewrite past decisions |
| `tools/...` | Mutable | Utilities |

## Alternatives considered

- **Flat structure** (no lineage subdirectory; everything in `works/<id>/`). Rejected per ADR-002. Lineage is too retrieval-relevant.
- **Database-backed corpus** (Postgres or SQLite as source of truth, files as blobs). Rejected: bad for version control, harder to inspect, slower to onboard. File-based corpus is the right surface for a single-curator project.
- **Single `meta.yaml` per author** (instead of per-work). Rejected: too coarse; per-work metadata is needed for citations.
- **No `04_processed/`** (treat RAG outputs as ephemeral). Rejected: keeping built artifacts in the repo makes the project portable (clone, no rebuild needed for casual inspection).
- **One global `meta.yaml`** indexing everything. We have `catalog.yaml` for that role. Per-work `meta.yaml` lives alongside the work for locality.
- **Use Git LFS for source PDFs** (in case we version-control the corpus). Considered. Decision deferred — for v1, repo is local-only and standard git is fine. If we ever go remote-versioned, add LFS for `source.*` files.

## Tradeoffs

**Positive:**
- Filesystem structure is the navigation surface — a developer or contributor can `cd` and `ls` to learn the corpus.
- Every file has a known home; ambiguity is rare.
- Provenance is recoverable in 100% of cases.
- Phase 2 retrieval can filter by metadata (author / language / work_type / about_member) at the index level.

**Negative:**
- More structure means more conventions to learn for new contributors.
- Some works don't fit cleanly (joint biographies, comparative essays) — ambiguity falls to the curator's judgment.
- `meta.yaml` proliferation: hundreds of small YAML files. Mitigated by schemas + validation tooling.
- `04_processed/` could get large if we store every embedding; will need a size budget.

## Open questions

| # | Question | Resolve in |
|---|---|---|
| OQ-1 | Should we adopt Git LFS for `source.*` files before the corpus is shared/cloned? | When/if we go remote-versioned (post-demo) |
| ~~OQ-2~~ | ~~Should `text.md` include front-matter?~~ — **Resolved 2026-06-13:** YAML frontmatter on every `text.md` (canonical + variants + biography + periodicals). Optimize for Phase 2 RAG efficiency over human readability of intermediate files (which won't be read directly — only through the chat). | — |
| OQ-3 | Numbering convention for serial works (PGHL parts 1/2/3) inside a single language subfolder — `part-1-source.docx` vs `01-source.docx` vs `source-part-1.docx`? | Cosmetic; consensus before bulk extraction |
| OQ-4 | Should `04_processed/` be in the repo or `.gitignored`? | RFC-003 |

## References

- [PRD.md §3 Phase 1 — the corpus](../PRD.md)
- [ADR-002 — Lineage-aware folders](../decisions/ADR-002-lineage-aware-folder-structure.md)
- [ADR-005 — Raw zip immutable](../decisions/ADR-005-raw-zip-immutable-staging-uses-move.md)
- [RFC-001 — Demo MVP scope](RFC-001-demo-mvp.md) — references this RFC for what corpus is in scope
- RFC-003 (Retrieval & RAG) — uses `04_processed/` and chunking
