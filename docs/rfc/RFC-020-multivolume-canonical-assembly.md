## RFC-020: Multi-volume canonical assembly

**Status:** ACCEPTED (Neha OK 2026-07-30 — see amendment §D3-b below re: Phase 2 finding)
**Author:** Neha Repal (with Claude)
**Created:** 2026-07-30
**Related:** RFC-009 (ingestion pipeline), RFC-013 (page-furniture cleanup),
RFC-017 (small-to-big chunking), RFC-018 (citation aliases), ADR-005 (raw
immutable / derived regenerable), ADR-012 (chunk_id carry-over)

## Summary

Give the corpus a first-class, config-driven way to assemble a **single
canonical work from multiple published volumes** — one `text.md` per work,
built by a generic pipeline pointed at a per-work YAML manifest. The
initial customer is **Kakasaheb Tulpule's काकांची प्रवचने (Kakanchi
Pravachane)**, whose 5 published volumes today collapse into one broken
`text.md`: vols 4–5 were re-OCR'd cleanly with Surya on 2026-07-20 but vols
1–3 still carry pdftotext output with catastrophic Devanagari glyph
reordering (`पष्ु प` for `पुष्प`, `वैकंु ठचतर्द ु शीनिमित्त` for
`वैकुंठचतुर्दशीनिमित्त`, etc.). Vols 1–3 have now been Surya-OCR'd on
2026-07-30; the work needs a clean rebuild that preserves volume + chapter
structure and cites the printed reality (भाग N + पुष्प M), not page numbers
that get stripped during cleanup.

The scope is deliberately broader than one work: the same pipeline covers
any multi-volume canonical work the corpus holds now
(contemporary-indian-philosophy essays across two volumes; ACPR
silver-jubilee volumes) or acquires later (a hypothetical भाग ६ of
Kakanchi Pravachane, other volume-set publications). Adding a volume =
drop the PDF, add one YAML entry, re-run the pipeline. No code changes
unless the volume needs a novel structural parser.

## Context / Problem

`01_canonical/kakasaheb_tulpule/lectures/kakanchi-pravachane/mr/text.md` is
the single canonical file for a five-volume printed work. Two things are
broken about how it was assembled:

1. **Mixed OCR provenance.** The current file is a concatenation of five
   volumes, three of which came from pdftotext (2025-ish era) and two of
   which came from Surya (2026-07-20). Devanagari conjuncts and matras
   were reordered by pdftotext in vols 1–3, so a substantial fraction of
   the text is not readable by a human, retrievable by BM25, or reliably
   embeddable by BGE-M3. Vols 4–5 are clean.
2. **No structural markers.** Volume boundaries and chapter (पुष्प /
   lecture) headers are not represented in the canonical file; the reader
   UI cannot build a real TOC, and chunks land without a `chapter` field,
   so citations render as "काकांची प्रवचने, page ?" rather than
   "काकांची प्रवचने भाग २ · पुष्प १७".

The Surya re-OCR of vols 1–3 landed today (2026-07-30) at
`_surya_ocr_job/out_raw/kakanchi-pravachane-vol{1,2,3}/results.json`,
alongside the existing vol 4–5 outputs. We now have five clean per-volume
OCR outputs and need a repeatable way to fold them into one canonical
work.

The **naive fix** — a one-off script that concatenates five files — has
been rejected for two reasons: (a) the same shape appears in other
multi-volume works we already hold, and (b) more volumes of Kakanchi
Pravachane may be published, so the design must accept a sixth volume as
"add a YAML entry" rather than "rewrite the script".

## Design decisions

Eight decisions, each already agreed with Neha; captured here so the
implementation can proceed without re-litigating them.

### D1. One work, multiple volumes

All five vols merge into a single canonical work
`kakanchi-pravachane`, not five separate works
(`kakanchi-pravachane-vol1`, `-vol2`, …).

**Rationale:** matches the printed reality (all five volumes carry the
title काकांची प्रवचने), keeps citations simple ("भाग २ · पुष्प १७"
rather than requiring the reader to know that "vol 2 pushpa 17" belongs
to a different corpus work than "vol 3 lecture 1"), and keeps
sadhak-facing retrieval consistent — a query for "काकांची प्रवचने" hits
one work with a rich internal structure, not five siblings the reader
has to know about.

The volume is a **structural coordinate** inside the work, exactly as
"chapter" is inside a Pathway-to-God book. Volume N and chapter M land
as citation fields, not as work IDs.

### D2. Config-driven, not code-driven

Each multi-volume work gets a YAML manifest at
`03_catalog/multivolume_works/<work_id>.yaml`. The pipeline is generic
and reads the manifest; no work-specific Python module exists.

**Rationale:** adding a volume must not require touching code. Neha
should be able to add a sixth volume of Kakanchi Pravachane, or a new
multi-volume work entirely, by dropping a PDF, appending YAML, and
re-running. The alternative — a `build_kakanchi_pravachane.py` script —
puts a code change on the critical path for every new volume, and each
future multi-vol work spawns its own bespoke script.

The directory location (`03_catalog/multivolume_works/`) was chosen over
a flat `03_catalog/kakanchi_pravachane_volumes.yaml` because we already
expect at least three multi-vol works; a subdirectory keeps
`03_catalog/` navigable.

### D3. Two structural parsers, dispatched by config

Each volume declares a `structure` key that dispatches to one of two
parser modules under `tools/multivolume/parsers/`:

- **`pushpa`** — Kakasaheb's numbered lecture format. Chapter markers
  like `पुष्प १`, `पुष्प २`, … each followed by a title line. Used by
  Kakanchi Pravachane vols 1, 2, 4, 5.
- **`lectures`** — date-and-venue-headed lectures. Chapter markers like
  `<date> — <venue>`. Used by vol 3 (three lectures given 1973 / 1976 /
  1978 at Pune / Sangli / Vijapur).

**Rationale:** the volumes really do split into two structural
families, and one dispatch key per volume keeps the manifest small and
the parser code focused. A third parser gets added when — and only when
— a novel structural pattern appears; the config change is one line.

Parsers must be **conservative**: on an unrecognised chapter-marker
candidate, emit a warning and pass the text through unsegmented rather
than guess. Structural mis-parse silently corrupts the TOC and every
chunk's chapter metadata; a loud "N warnings" is recoverable.

### D4. Citation format: भाग N + पुष्प M

For `pushpa`-structured volumes, chunks carry `volume=<N>` and
`chapter=पुष्प <M>` (with an optional `chapter_title` string). For
`lectures`-structured volumes (vol 3), chunks carry `volume=<N>` and
`chapter=<date> — <venue>`.

Citations render as "काकांची प्रवचने · भाग २ · पुष्प १७" or
"काकांची प्रवचने · भाग ३ · १९७३ पुणे".

**Rationale:** structural coordinates survive text edits and reflows;
printed page numbers do not, and RFC-013 will strip them anyway.
Citing page numbers that have been removed from the text would rot on
the first cleanup pass. भाग + पुष्प is the citation form Kakasaheb's
own compilations use, so it is also the form sadhaks recognise.

### D5. Pipeline as a generalised script

The entry point is `tools/build_multivolume_work.py`, not
`build_kakanchi_pravachane.py`. CLI shape:

    python tools/build_multivolume_work.py \
        --config 03_catalog/multivolume_works/kakanchi-pravachane.yaml

    # Rebuild a single volume (skip the others; useful when re-OCR'ing one)
    python tools/build_multivolume_work.py --config … --vol 3

    # Show what would change without touching the canonical file
    python tools/build_multivolume_work.py --config … --dry-run

    # Force a full rebuild, ignoring idempotency
    python tools/build_multivolume_work.py --config … --restart

**Idempotent by default.** The script hashes each vol's Surya
`out_raw/<vol>/results.json` and skips vols whose hash hasn't changed
since the last successful assembly (recorded in a sidecar
`text.md.assembly-state.json`). A run with no source changes exits
"nothing to do".

**Rationale:** naming the script after the pipeline shape, not the
customer, keeps the tools directory legible when we add
contemporary-indian-philosophy and the ACPR silver-jubilee volumes.
Idempotency lets Neha re-run the script freely during iterative
cleanup without paying for redundant work.

### D6. Chunk + embed is a separate command

Assembly (rebuild `text.md`) and re-embedding are two commands, not
one:

    python tools/build_multivolume_work.py --config …    # ~seconds
    python tools/rechunk_and_embed.py --work kakanchi-pravachane   # ~30 min

**Rationale:** the assembly loop is where 90% of the iteration
happens — parser tweaks, per-vol strip rules, cleanup passes. Paying
the ~30-minute embedding cost on every assembly run would slow
iteration to a crawl. Splitting the commands lets Neha assemble a
dozen times, eyeball the result, and only trigger the embed once the
canonical file is right.

`rechunk_and_embed.py` is not new — it's the existing
`chunker.py` + `embedder.py` sequence, wrapped so a caller can name
one work and get a full "chunk then embed then reload" for that work.
Per ADR-012, `chunk_id`-keyed incremental embedding still applies:
only the chunks whose IDs are new pay the embed cost.

### D7. Snapshot backups with dates, not overwrites

Every rebuild writes a backup **before** overwriting:

    text.md.pre-<YYYY-MM-DD>-<reason>.bak

Old backups are never deleted by the pipeline. `<reason>` is a short
kebab-case tag the caller passes on the CLI
(`--backup-reason surya-vol1-3`), defaulting to `rebuild`.

**Rationale:** the current file has one `.pre-surya-2026-07-20.bak`
backup and it has already been useful for verifying vols 4–5. We
expect several rebuild passes as parsers tighten; overwriting a
backup on rebuild N+1 would erase the state we might need to
diff against. Backups are cheap on disk (a text.md is ~1–5 MB).
`git` also carries history, but `.bak` files live next to `text.md`
which is the natural place for a human reviewer to look.

### D8. Structural output as a machine-readable index

Alongside `text.md`, the pipeline emits `text.index.json` (colocated,
same directory). One record per chapter:

    {
      "volume": 2,
      "chapter_key": "पुष्प 17",
      "chapter_title": "…",
      "source_page": 84,
      "byte_offset": 152304,
      "byte_length": 4218
    }

**Rationale:** this file is consumed by (a) the reader UI to render a
real TOC without re-parsing `text.md` at request time, and (b) the
chunker so every chunk carries `volume` / `chapter_key` /
`chapter_title` metadata for citations. Emitting it during assembly
(where the parser already knows the structure) is strictly cheaper
than re-deriving it later, and it decouples the reader from the
canonical file's exact formatting.

`source_page` is the printed page number from Surya's OCR output — kept
for provenance and cross-checking against the printed table of
contents (see Phase 4), even though citations no longer use it.

## Config schema

    # 03_catalog/multivolume_works/kakanchi-pravachane.yaml
    work_id: kakanchi-pravachane
    author_slug: kakasaheb_tulpule
    kind: lectures
    language: mr
    title: "काकांची प्रवचने"

    # Where the OCR outputs live. Relative paths resolve to
    # <repo_root>/<ocr_source_root>/<vol.pdf | vol name>.
    ocr_source_root: _surya_ocr_job/out_raw

    volumes:
      - vol: 1
        pdf: kakanchi-pravachane-vol1.pdf
        structure: pushpa
        title: "काकांची प्रवचने भाग १"

      - vol: 2
        pdf: kakanchi-pravachane-vol2.pdf
        structure: pushpa
        title: "काकांची प्रवचने भाग २"

      - vol: 3
        pdf: kakanchi-pravachane-vol3.pdf
        structure: lectures
        title: "काकांची प्रवचने भाग ३"
        # Optional per-vol back-matter guard: strip everything from
        # this string onward (inclusive). Anchored, whitespace-tolerant.
        end_matter_strip_from: "किंमत रु"

      - vol: 4
        pdf: kakanchi-pravachane-vol4.pdf
        structure: pushpa
        title: "काकांची प्रवचने भाग ४"

      - vol: 5
        pdf: kakanchi-pravachane-vol5.pdf
        structure: pushpa
        title: "काकांची प्रवचने भाग ५"

**Commentary.**

- `work_id`, `author_slug`, `kind`, `language`, `title` mirror the
  fields the rest of the corpus already uses (see `03_catalog/catalog.yaml`
  for shape). The canonical `text.md` path is derived:
  `01_canonical/<author_slug>/<kind>/<work_id>/<language>/text.md`.
- `structure` is a **required** per-vol key. Adding a new value here
  requires a matching parser module — the pipeline fails loudly at
  startup rather than mis-parsing.
- `end_matter_strip_from` is one example of a per-vol escape hatch;
  more may be added (`front_matter_strip_until`, `chapter_number_start`
  for volumes that don't start at 1). Escape hatches live in the
  manifest, never as branches in shared parser code.
- The manifest is the source of truth for `03_catalog/catalog.yaml`'s
  `kakanchi-pravachane` entry: after assembly the pipeline can print
  the recommended catalog fragment for Neha to paste.

## Pipeline architecture

Module layout under `tools/`:

    tools/
      build_multivolume_work.py            # CLI entry point
      rechunk_and_embed.py                 # wrapper around chunker+embedder
      multivolume/
        __init__.py
        config.py                          # YAML load + validate
        pages.py                           # Surya results.json → per-page text
        parsers/
          __init__.py                      # dispatch table
          pushpa.py                        # 'पुष्प N' + title
          lectures.py                      # '<date> — <venue>'
        cleanup.py                         # page-furniture strip, sentence rejoin
        assemble.py                        # write text.md + text.index.json
        state.py                           # idempotency (source-hash sidecar)

**Dispatch.** `parsers/__init__.py` exposes a single dict:

    PARSERS = {"pushpa": pushpa.parse, "lectures": lectures.parse}

Each parser takes a list of Surya page records and returns a list of
`Chapter` records (`{volume, chapter_key, chapter_title, source_page,
paragraphs: List[str]}`). Adding a parser is: implement the function,
register the key, add tests. No orchestrator change.

**Data flow.**

    YAML → config.load()
         → for each vol:
              pages.load(surya_output) → page-record list
              parsers[vol.structure](pages, vol) → chapter list
              cleanup.apply(chapters, vol) → cleaned chapter list
         → assemble.write(canonical_dir, all_volumes)
              → text.md (frontmatter + volume/chapter markdown headings)
              → text.index.json
              → text.md.pre-<date>-<reason>.bak (before overwrite)

**Frontmatter of `text.md`** follows the existing convention (see any
`01_canonical/**/mr/text.md`): `work_id`, `title`, `author`,
`language`, `kind`, `source: "assembled from N volumes via
tools/build_multivolume_work.py, YYYY-MM-DD"`.

**Volume / chapter markdown headings.** Two heading levels dedicated
to structure:

    ## भाग २
    ### पुष्प १७ — <title>

The reader UI's chapter-aware pagination (RFC-009 reader path) already
splits on markdown headings; this shape is what it expects. The chunker
picks up the same headings for chunk metadata.

## Phased delivery

Seven phases, each with a **human review gate**. Neha reviews the
artifact, gives an explicit "proceed", and only then does the next
phase run. No phase auto-triggers the next.

### Phase 1 — OCR completeness audit

**Goal:** confirm Surya covered every page of every volume before we
build anything on top.

**Artifact:** `docs/audits/kakanchi-pravachane-ocr-audit-<date>.md` —
per-vol table with printed page count (from the PDF) vs Surya page
count vs pages Surya produced empty text for. Any gap gets a row.

**Gate:** Neha OKs; if gaps exist, we decide per-vol whether to re-OCR
(with a page-range override) or accept.

### Phase 2 — Structure extraction

**Goal:** run each parser and produce a chapter list per volume, with
no cleanup or assembly yet.

**Artifact:** `docs/audits/kakanchi-pravachane-chapters-<date>.md` —
one section per volume, one line per chapter (`vol`, `chapter_key`,
`chapter_title`, `source_page`, first ~10 words of body). Warnings
list at the end for any candidate the parser skipped.

**Gate:** Neha eyeballs the chapter list against the printed
अनुक्रमणिका. Chapter count and titles must match; if they don't, the
parser is tightened before proceeding.

### Phase 3 — Text-quality pass

**Goal:** apply structural cleanup — strip page numbers and per-page
running headers/footers (per RFC-013), rejoin sentences that OCR cut
across page breaks, normalise Devanagari punctuation (।, ॥, curly
quotes), apply per-vol `end_matter_strip_from`.

**Artifact:** per-vol before/after diff sample —
`docs/audits/kakanchi-pravachane-cleanup-<date>.md` with 5 randomly
sampled paragraphs per volume, showing raw OCR vs cleaned.

**Gate:** Neha reviews the samples. Any regression (real text
mis-stripped, or a punctuation change that alters meaning) is fixed
before proceeding.

### Phase 4 — Index extraction and cross-check

**Goal:** extract the printed table of contents (अनुक्रमणिका) from
each volume's OCR output, and cross-check it against the chapter list
produced in Phase 2. This catches (a) chapters the parser missed, (b)
chapter titles the parser truncated, (c) mismatches between the
printed TOC and the actual body of the book.

**Artifact:**
`docs/audits/kakanchi-pravachane-index-crosscheck-<date>.md` — a
three-column diff (printed TOC entry / Phase-2 chapter / disposition).

**Gate:** every discrepancy is triaged (parser bug / TOC typo /
acceptable variant). No unresolved diffs proceed.

### Phase 5 — Canonical assembly

**Goal:** write the final `text.md` + `text.index.json` + backup.

**Artifact:** the new canonical file, plus a one-page
`docs/audits/kakanchi-pravachane-assembly-<date>.md` recording total
volumes, total chapters, total paragraphs, byte size, and a checksum.

**Gate:** Neha reviews a rendered version of the file (open in the
reader with the local dev server) — TOC looks right, chapter headings
render, sample passages look clean. Sign-off is explicit before the
next phase touches embeddings.

### Phase 6 — Re-chunk + re-embed

**Goal:** regenerate chunks with `volume` / `chapter_key` /
`chapter_title` metadata; embed all new / changed chunks; reload the
server index.

**Artifact:** embed diff report — chunks added / removed / unchanged.
Per ADR-012 the incremental path handles most of the work; the
audit-line "N chunks re-embedded, M chunks unchanged" appears in the
run log.

**Gate:** run the eval suite (`tools/eval_retrieval.py` gold cases,
plus 3–5 hand-authored queries against known Kakanchi passages).
Retrieval must return the expected chunks with the expected citation
metadata. Regression on unrelated works must be zero.

### Phase 7 — Deploy

**Goal:** push the new canonical file + embeddings to the Lightsail
prod host and smoke-test.

**Artifact:** a short deploy log — commit SHA, files deployed,
smoke-test results (5 queries whose expected citations are known,
each verified end-to-end in the deployed UI).

**Gate:** Neha runs the smoke-test queries in prod. If any fail, roll
back to the previous `text.md` (from the dated `.bak`) + previous
embedding artifacts.

## Non-goals

- **Not fixing OCR accuracy at the character level.** Surya is already
  good enough for Kakanchi Pravachane's five volumes; residual OCR
  errors are the Devanagari-OCR-quality track's problem, not this
  RFC's. This RFC assumes the Surya output is authoritative.
- **Not a new chunking strategy.** Chunking stays as RFC-017
  (parent/child); this RFC only ensures that chunks carry the right
  `volume` and `chapter` metadata.
- **Not a new retrieval mechanism.** Retrieval is unchanged
  (RFC-014 + RFC-017). Only the citation surface benefits, via
  richer chunk metadata.
- **Not new UI.** The reader already renders markdown headings as a
  TOC; the `text.index.json` sidecar is a future affordance, not a
  Phase-5 requirement.
- **Not a general-purpose OCR pipeline.** OCR itself
  (`_surya_ocr_job/`) is upstream of this RFC and stays as it is.
- **Not covering non-Devanagari multi-volume works** in the first
  cut. The English essay collections could reuse the pipeline (see
  Future extensions) but their per-vol parsers are out of scope for
  the initial implementation.

## Migration / rollout

The existing `kakanchi-pravachane` work is live in prod. Cutover must
not break it. Order of operations:

1. **All work happens off-prod first.** The pipeline runs locally;
   the resulting `text.md` and `text.index.json` live in a branch
   until Phase 5 signs off.
2. **The current `text.md` is preserved** as
   `text.md.pre-2026-07-30-multivolume-assembly.bak` before the new
   file overwrites it. Rollback = `mv` the backup back.
3. **The current embeddings stay live** until Phase 6 explicitly
   swaps them. Per ADR-012, `chunk_id` carry-over means unchanged
   chunks keep their embeddings; only new chunks (those with fresh
   `volume` / `chapter` metadata, which changes the `chunk_id`) get
   re-embedded. Expect most / all Kakanchi chunks to change since
   the source text of vols 1–3 is substantially rewritten by Surya.
4. **The catalog entry may need one edit.** If
   `03_catalog/catalog.yaml`'s `kakanchi-pravachane` entry has stale
   metadata (title, chapter count, etc.), Phase 5's assembly-log
   artifact prints the recommended replacement fragment.
5. **`03_catalog/work_roles.yaml`** already lists
   `kakanchi-pravachane` as a container work (see RFC-018) — no
   change needed there.
6. **Deploy is Phase 7's job**, gated on Phase 6's eval passing. No
   partial deploys — either the new canonical file + new embeddings
   go together, or neither does. Mixed state would leave chunk IDs
   pointing at text that no longer exists.
7. **If the rollback fires**, it fires whole: restore
   `text.md` from `.bak`, restore the previous `embeddings.npy` +
   `chunks_meta.jsonl` from the prior artifact set, `/admin/reload`.
   This is a manual runbook step; the pipeline does not auto-roll-back.

## Future extensions

The pipeline is designed for multi-vol reuse; specific candidates:

- **contemporary-indian-philosophy** — Gurudev Ranade's essay
  collection spans two published volumes. Structural family: numbered
  essays with English titles. Likely a new parser (`essays`), added
  when we ingest.
- **ACPR silver-jubilee volumes** — commemorative multi-volume set;
  structure per-vol is inconsistent (essays, tributes, photo-only
  sections). Needs per-vol overrides in the manifest, possibly a
  `mixed` parser that consumes an explicit chapter list from YAML
  when auto-detection can't cope.
- **A hypothetical Kakanchi Pravachane भाग ६.** Adding it is: drop
  the PDF into `_surya_ocr_job/pdfs/`, run Surya OCR (existing
  batch script), append one YAML block to
  `03_catalog/multivolume_works/kakanchi-pravachane.yaml`, re-run
  `build_multivolume_work.py --vol 6`. No code changes if it is
  `pushpa` or `lectures`-structured.
- **Multi-volume works discovered later** in Kannada or English —
  the pipeline is language-agnostic; the manifest declares
  `language`, and cleanup rules that are Devanagari-specific
  (punctuation normalisation) are gated on that.
- **Alignment across editions.** If a later reprint changes pagination
  or renumbers पुष्प, the manifest can hold an optional
  `chapter_number_start` per vol, and the citation format tolerates
  the shift without breaking historical references (which are keyed
  to the printed chapter number, not the pipeline-emitted one).

## References

- RFC-009 (ingestion pipeline) — where the assembly step sits in the
  broader flow (raw → OCR → canonical → chunks → embeddings).
- RFC-013 (source-text page-furniture cleanup) — the closest prior
  art; Phase 3 uses its detection strategy for per-page headers /
  footers / page numbers.
- RFC-017 (small-to-big + arthasahit) — the chunking scheme that
  Phase 6 feeds. `volume` / `chapter_key` metadata flows through to
  every child chunk and drives citation rendering.
- RFC-018 (citation aliases) — `kakanchi-pravachane` is listed as a
  container work there; nothing changes in that resolution once
  chapter metadata is richer.
- ADR-005 (raw immutable, derived regenerable) — the canonical
  `text.md` is derived, so overwriting it (with backup) is allowed.
- ADR-012 (chunk_id carry-over) — makes Phase 6's re-embed
  incremental where the text is unchanged.
- `_surya_ocr_job/out_raw/kakanchi-pravachane-vol{1..5}/results.json`
  — the OCR inputs.
- `01_canonical/kakasaheb_tulpule/lectures/kakanchi-pravachane/mr/text.md`
  — the current (broken) canonical file, to be replaced by Phase 5.
