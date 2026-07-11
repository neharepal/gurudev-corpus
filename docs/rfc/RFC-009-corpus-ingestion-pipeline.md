# RFC-009: Corpus ingestion pipeline (new-material runbook)

**Status:** ACCEPTED 2026-06-17
**Author:** Neha (with Claude)
**Created:** 2026-06-16
**Last updated:** 2026-07-10

## Amendments

- **2026-07-10** — Added **Step 4.5 (Duplicate quality gate)**: a batch file matching an
  existing work is no longer auto-skipped; extract it, compare quality, and replace the
  ingested text if the new source is cleaner/more complete. Updated **Step 8** and
  **Risks §1** for ADR-012 (chunk_id-keyed embedding carry-over — row reordering no longer
  forces a full rebuild). Added **Step 7.5 (Chunk-quality scores)** for the junk-weight
  retrieval feature.

## Summary

Defines the end-to-end procedure for bringing a new batch of text material into the corpus and making it retrievable. Covers all material types — canonical works, athvani, biography, periodicals, reference — with conditional branches per type. Pins the order of operations (triage → stage → extract → verify → structure → catalog → chunk → embed → smoke-test → changelog), the responsibilities of each step, and the artifacts produced. References existing scripts (`tools/chunker.py`, `tools/embedder.py`, `tools/verify_canonical.py`, `tools/ingest_athvani.py`) and the structural conventions in RFC-002.

## Motivation

The corpus is being assembled incrementally — drive dumps arrive periodically with mixed material (canonical PDFs, athvani recollections in .docx, biographical pamphlets, reference bibliographies). Each prior batch was handled ad-hoc; conventions emerged informally. As the corpus grows, ad-hoc handling becomes:

1. **Error-prone.** Verification (line-by-line against Internet Archive for canonical works) was retrofitted after PGHL transcription errors surfaced; a new batch should not repeat that gap.
2. **Unrepeatable.** A new contributor (or future-Claude in a fresh session) cannot pick up where the last batch left off without spelunking through chat history.
3. **Unsafe for embeddings.** The 11-14h BGE-M3 run is the single most expensive artifact in the repo; the ingest procedure must protect it from accidental rebuilds.

This RFC turns the implicit procedure into an authoritative runbook.

## Goals

- One document describes the steps for every material type.
- Each step names its inputs, outputs, and the script (if any) that performs it.
- Verification is a first-class step, with type-specific rules.
- Embeddings are protected: incremental append by default; full rebuild only on model change (per ADR-009).
- The runbook is short enough to follow end-to-end in one sitting per batch.

## Non-goals

- Structural decisions about the corpus layout — those live in RFC-002.
- Retrieval/embedding model choice — those live in ADR-009.
- Chunking parameters (size, overlap) — those live in RFC-003.
- Ingestion of audio/video material — deferred to RFC-008.

## Proposed design

### Pipeline overview

```
new batch arrives  ──►  1. triage       ──►  2. stage in 00_raw/
                                                       │
                       7. chunk        ◄──  3. extract │
                          │                            │
                       8. embed        ──►  4. verify  │
                          │                            │
                       9. smoke-test   ──►  5. structure into 01_canonical/
                          │                       (or 02_aggregated/ for athvani)
                       10. changelog        │
                          │            ──►  6. catalog in 03_catalog/
                          ▼
                       retrievable
```

### Step 1 — Triage

**Input:** A new batch (typically a Google Drive zip, e.g. `Neha-20260616T___.zip`).

**Action:** Open the zip's top-level listing without extracting. For each file or folder, classify into one of:

| Type | Examples | Destination |
|---|---|---|
| **canonical** | Books, lectures, letters BY a lineage member (Gurudev, Bhausaheb, Nimbargi, Kakasaheb, Amburao) | `01_canonical/<author>/<work_type>/<work-id>/<lang>/text.md` |
| **athvani** | Recollections, anecdotes ABOUT a lineage member, narrated by a named devotee | `02_aggregated/about_<member>/athvani/<story-id>/` |
| **biography** | Full biographies, sometimes anthological | `02_aggregated/about_<member>/biography/<work-id>/` |
| **periodical** | Magazines, newsletters, conference proceedings | `02_aggregated/periodicals/<title>/<issue>/` |
| **reference** | Bibliographies, indexes, scholarly cross-references | `03_catalog/reference/` |
| **skip** | Duplicates, corrupt files, marketing material | `00_raw/_skipped/` with one-line note in `_skipped/README.md` |

Triage output: a `batch-<date>-triage.yaml` (see Step 2) listing every file and its classification. If a file is ambiguous, mark `type: TBD` and resolve before Step 3.

### Step 2 — Stage in `00_raw/`

Per ADR-005, raw zips are immutable archives; extracted staging uses move semantics (files leave staging once they're in their final structured home).

**Action:**

1. Move the unmodified zip to `00_raw/<batch-name>.zip`. Compute and record its SHA-256 in `00_raw/checksums.yaml`.
2. Extract the zip into `00_raw/drive_dump_YYYY-MM-DD/<contributor>/` (folder name follows RFC-002).
3. Save the triage YAML at `00_raw/drive_dump_YYYY-MM-DD/batch-triage.yaml`.

No file under `00_raw/drive_dump_YYYY-MM-DD/` is modified after this point — files are MOVED OUT to their structured homes in Step 5.

### Step 3 — Extract text

Convert each file to UTF-8 Markdown.

| Source format | Extraction method | Notes |
|---|---|---|
| `.pdf` (text layer) | `pdftotext -layout` | **Verify the layer is real Unicode, not legacy-font mojibake** (see below); multi-column PDFs often need `-raw` |
| `.pdf` (scanned or legacy-font) | render + tesseract (OCR sub-procedure below) | OCR noise is the largest source of bad chunks (index pages, page numbers, headers) |
| `.docx` | `pandoc -t markdown_strict` | Native text — always prefer over a PDF of the same work |
| `.txt` | direct copy with charset normalization | |
| `.html` | `pandoc -f html -t markdown_strict` | Strip nav/footer noise manually |

Extraction goes into the file's eventual structured destination **as `extracted.md`** (not `text.md` yet — `text.md` is the verified version produced by Step 4).

> **A "text layer" can be a trap.** Some Marathi PDFs embed a legacy display font
> (Shree-Lipi / Lipika-style) that renders as Devanagari on screen but has **no Unicode
> mapping**, so `pdftotext` emits mojibake (`pi˜iRy Ï]tbo]¡ti>`). `pdffonts` shows the fonts
> with `uni=no`. Always eyeball `pdftotext … | head` before trusting a text layer; if it's
> garbled, treat the file as **scanned** and run the OCR sub-procedure (rasterize + OCR
> recovers clean text, since the glyphs render correctly as an image).

#### OCR sub-procedure — Devanagari scans (validated 2026-07-10, `tools/ocr_ingest_2026-07-10.py`)

Marathi devotional scans OCR **cleanly and for free with tesseract** when the scan is a
modern print at ≥300 DPI — no Surya, no paid vision-LLM needed. (Our 2026-06-22 finding
that "tesseract fails on Devanagari" was specific to *bad* scans: 150 DPI, archaic
letterpress typefaces. Judge per scan.)

1. **Render** each page to PNG at **300 DPI**: `pdftoppm -r 300 -png in.pdf out/pg`.
2. **OCR** each page with **`-l mar+san+eng`**. Many editions are trilingual (Marathi verse
   + English translation + Marathi commentary); `mar` alone garbles the English lines, and
   adding `eng` does not hurt the Devanagari. Add `san` for Sanskrit shlokas.
3. **Two environment gotchas — both silent failures:**
   - Run under a **UTF-8 locale** (`LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8`) or text tools
     (`sed`, and tesseract stderr handling) choke on Devanagari bytes.
   - **Pipe the image to tesseract via stdin** (`tesseract stdin stdout -l …`, feeding the
     PNG bytes) rather than by path. Leptonica's C `fopen` fails intermittently on this box
     (`failed to open locally … image file not found`) regardless of locale or cwd; stdin
     bypasses it. (Running from an ASCII cwd helps but stdin is the reliable fix.)
4. **Cleanup (conservative — do not reflow verse):** drop standalone page-number lines
   (bare digits, but keep `॥…॥` verse markers), de-hyphenate English line-break hyphens,
   collapse 3+ blank lines. Leave tesseract's line structure otherwise intact.
5. **Quality gate (Step 4):** spot-check ≥3 random pages against the PDF — Devanagari ratio
   plausible, diacritics intact, no mojibake, English clean. The bar is *no hand-cleaning
   needed downstream*; if a book fails, re-run at higher DPI or reconsider the engine.

> _Phase 3 (retro re-OCR of already-ingested garbled scans) remains a separate tracked
> effort; this sub-procedure is the standard for all **new** batches going forward._

### Step 4 — Verify

The single most important step. Different rules per material type.

#### Canonical works

**Hard gate.** A canonical work cannot proceed to Step 5 (final placement) until verification passes.

1. **Source the authoritative version.** Most of Gurudev's published works are on Internet Archive (e.g., *Pathway to God in Hindi Literature*, 1954 ed., IA item `pathwaytogodinhi0000ranar`). Record the IA item URL in `meta.yaml` under `external_verification.source`.
2. **Run `tools/verify_canonical.py`** to align the extracted text against the IA version page-by-page. The tool emits a `verification-<work-id>.md` report under `04_processed/canonical_audit/`.
3. **Review the diffs.** Acceptable divergences: OCR noise on the IA side, transliteration variants (े vs ॆ), edition-specific paragraph breaks. Unacceptable: missing sentences, mistranscribed quotes, dropped footnotes that change meaning.
4. **Fix the extracted text** until divergences are explainable. Re-run the verifier until the alignment report is clean.
5. **Promote** `extracted.md` → `text.md`. Set `meta.yaml` `external_verification.verified: true` with the date and the verifier's commit SHA.

If **no IA (or other published) source exists** for a canonical work, treat it like an athvani — set `external_verification.verified: false` with a `reason: no_public_source_available` note (per below).

#### Athvani, biography, periodical (no public source for line-by-line check)

**Soft gate (flag, not block).** These can proceed to Step 5 without external verification, BUT:

- `meta.yaml` MUST record: a **named narrator** (for athvani), a **named author** (for biography/periodical), a **source description** (the document the recollection was transcribed from), and a **received_on** date.
- `meta.yaml` carries `external_verification: { verified: false, reason: <one-line> }`. This is the flag — answers drawing on unverified material can still be quoted, but the lack of external corroboration is visible in metadata for downstream filters.
- Spot-check transcription quality: open three random paragraphs, confirm Marathi diacritics are intact, confirm no encoding mojibake.

#### Reference

Catalog metadata only; no verification needed. These are bibliographic, not teaching material — the prompt already forbids citing reference as Gurudev's words (per `SYSTEM_PROMPT_QA`).

### Step 4.5 — Duplicate quality gate (replace-if-better)

A batch file that matches an already-ingested work is **NOT auto-skipped.** A later drive
dump often carries a cleaner scan, a native `.docx` in place of an OCR'd PDF, or a more
complete edition. Triage (Step 1) marks such a file `type: duplicate-candidate`; resolve
it here, after extraction (Step 3), because the decision needs the extracted text.

**Action — for each `duplicate-candidate`:**

1. **Identify the ingested twin.** Match by title/author against `03_catalog/catalog.yaml`
   and locate its `text.md`.
2. **Extract the new source** to `extracted.md` (Step 3) and compare against the ingested
   `text.md` on:
   - **Extraction cleanliness** — mojibake, legacy-font garble (a PDF text layer can render
     visually yet extract as junk — check with `pdftotext | head` before trusting size),
     residual page-headers/index noise, broken diacritics.
   - **Completeness** — char count, chapter/section coverage, dropped footnotes.
   - **Fidelity** — native `.docx` text beats OCR; a higher-DPI or text-layer PDF beats a
     noisy scan.
3. **Decide and log** (mirror the changelog's `Upgraded:` / `Declined upgrade:` entries):
   - **Replace** — new source is materially cleaner/more complete. Overwrite the existing
     `text.md` **in place, keeping the same `work_id`** (so chunk_ids stay stable and the
     embedder carries over unchanged chunks by id — Step 8). Update `meta.yaml` `sources`
     with the new `raw_path`/`received_in_batch`/`checksum`. This edits an existing work,
     so its chunks WILL re-embed (Step 8 detects changed text by id) — expected and cheap.
   - **Decline** — near-identical or worse. Move the file to `00_raw/_skipped/` with a
     one-line reason. A <1% char-count delta with no cleanliness gain is a decline.
4. **Never create a second work_id for the same work.** Replacement is in-place; declining
   drops the file. Two ids for one work double it in retrieval.

> Precedent: 2026-06-22 batch *Upgraded* `studies-in-indian-philosophy` (swapped garbage
> Wikimedia OCR for a clean text-layer extract, same id) but *Declined* `creative-period`
> (new source near-identical). 2026-07-10 batch *Declined* the `charitra-tatvajnan-tulpule`
> docx (1,725,268 vs 1,723,830 chars — 0.08% delta, no cleanliness gain).

### Step 5 — Structure into `01_canonical/` or `02_aggregated/`

**Action:**

1. Create the destination folder per RFC-002's layout. For canonical: `01_canonical/<author>/<work_type>/<work-id>/<lang>/`. For athvani: `02_aggregated/about_<member>/athvani/<story-id>/`.
2. Move (per ADR-005) the verified `text.md` into the destination.
3. Write `meta.yaml` with all required fields. Schema is enumerated in RFC-002 §3; mandatory fields for any work: `id`, `title`, `author` (or `narrator` for athvani), `work_type`, `original_language`, `languages_available`, `sources` (with `raw_path`, `received_on`, `received_in_batch`, `checksum_sha256`), `tags`, `status`, `external_verification`.
4. Status field progression: `extracted` → `verified` → `published`. After Step 5, the work is at `verified`; it moves to `published` after Step 9 smoke-test passes.

### Step 6 — Catalog in `03_catalog/`

The catalog is what surfaces a work in the corpus browser and gives downstream tooling a deterministic list of "what's in the corpus."

**Action:** Add or update entries in:

- `03_catalog/works.yaml` — one row per work with `id`, `title`, `author`, `languages`, `path`.
- `03_catalog/attribution.yaml` — provenance bundle per ADR-002.
- For athvani: `03_catalog/story_index.yaml` per RFC-002 §4.

Run `tools/build_corpus_browser.py` to regenerate `tools/corpus_browser.html` so the new work appears in the human-facing browser.

### Step 7 — Chunk

**Action:** Run `tools/chunker.py`. This **rewrites** `04_processed/chunks.jsonl` from scratch (no incremental mode today — see Risks §1).

```bash
/Users/neharepal/opt/anaconda3/bin/python tools/chunker.py
```

**Sanity-check** the output: chunker prints per-source counts. Confirm the new work appears in the relevant kind bucket and the chunk count looks plausible (rough heuristic: ~1 chunk per ~600 tokens of text).

### Step 7.5 — Chunk-quality scores

The junk-weight retrieval feature (`ENABLE_JUNK_WEIGHT`) reads a `quality_score` per chunk
to demote low-signal chunks (index pages, page-number litter, OCR noise). This is the
partial fix to Risks §2's "extraction quality is human-gated" gap. After chunking (and
after the embed in Step 8 regenerates `chunks_meta.jsonl`), run the idempotent scorer:

```bash
/Users/neharepal/opt/anaconda3/bin/python tools/build_chunk_quality.py
```

It writes `quality_score` into each `chunks_meta.jsonl` row from the row-aligned chunk text.
It does **not** touch `embeddings.npy` (no re-embed) and is safe to re-run. Run it whenever
`chunks_meta.jsonl` is regenerated (i.e. after every batch's Step 8).

### Step 8 — Embed

**Default mode: incremental, keyed by `chunk_id` (ADR-012).** `tools/embedder.py` builds a
`{chunk_id → vector}` map from the existing embeddings, then for the new `chunks.jsonl`:
copies the vector for any chunk whose `id` is unchanged, and encodes only genuinely new or
text-changed chunks. Because carry-over is keyed by id (not row position), **chunker
row-reordering no longer invalidates existing embeddings** — inserting an alphabetically-earlier
work is safe. Per-run cost: a few minutes per new work on BGE-M3, vs. 11-14h for a full rebuild.

```bash
/Users/neharepal/opt/anaconda3/bin/python tools/embedder.py
```

Editing an already-ingested work (Step 4.5 replace) changes that work's chunk text; the
embedder detects this by id and re-encodes just those chunks — no `--restart` needed.

**Full rebuild** (`--restart`) only when:
- The embedding model changes (per ADR-009 the old embeddings are archived to `04_processed/embeddings/_archive/`).
- The `chunk_id` scheme itself changes (ids no longer match, so carry-over can't map them).

If you must `--restart`, run it overnight. Confirm `ANTHROPIC_API_KEY` is NOT needed (embedder is local; no API calls). After any embed, re-run **Step 7.5** (chunk-quality) since `chunks_meta.jsonl` was rewritten.

### Step 9 — Smoke-test

**Action:** Confirm the new material is retrievable and renders correctly end-to-end.

1. **Retrieval:** pick a distinctive phrase from each new work. Run `tools/retrieve.py "<phrase>"` and confirm the new work's chunks appear with cos ≥ 0.6.
2. **Answer rendering:** pick one representative question per new work. Run `tools/chat.py "<question>"` and read the answer for correct attribution and verbatim quote integrity.
3. **Multi-question regression:** if the batch is large (>5 works) or touches the canonical category, re-run `tools/tune_sweep.py` and diff `summary.md` against the prior run. Watch for: cosine drift on existing questions, classification flips, biography-percentage changes.

Promote each work's `meta.yaml` `status` to `published`.

### Step 10 — Changelog

**Action:** Append an entry to `docs/CORPUS_CHANGELOG.md` (create if it doesn't exist):

```markdown
## v.YYYY-MM-DD — Batch <batch-name>

Added: <work-id> (<author>, <work_type>, <language>)
Verified-against: <IA item URL or "no public source — flagged">
Chunks added: <N> (corpus total: <M>)
Embedding mode: incremental | restart
Smoke-test: pass | fail-and-rolled-back
```

This file is the authoritative answer to "what's in the corpus as of date X" and "when did we add work Y."

## Alternatives considered

### A. Per-material-type RFCs (RFC-009 canonical, RFC-010 athvani, …)

Cleaner separation, but most steps are identical across types. The conditional branches in Steps 1, 4, and 5 capture the actual differences. A unified runbook is what the contributor reads end-to-end; splitting it into five RFCs would push them to flip between documents.

### B. Hard gate on verification for all material types

Safer, but in practice it would block 90% of athvani material indefinitely — most recollections have no published authoritative version, only the family/disciple narrator. We chose **flag, not block** (decision recorded in the conversation 2026-06-16): athvani proceeds with `verified: false` and a reason; the flag is queryable downstream if we ever need to filter.

### C. Full embedding rebuild every batch

Mechanically simpler — no incremental concerns — but 11-14h on BGE-M3 makes this impractical for any batch cadence faster than monthly. Incremental is the only sustainable mode.

## Tradeoffs & risks

### 1. Chunker row-order stability — RESOLVED by ADR-012

**Resolved 2026-06-24.** The embedder now keys carry-over by `chunk_id`, not row index
(ADR-012), so `tools/chunker.py` rewriting `chunks.jsonl` in a different order no longer
invalidates existing embeddings — the `{chunk_id → vector}` map re-aligns them regardless of
row position. Inserting an alphabetically-earlier work is safe; no `--restart` needed. Two
batches (2026-06-24, 2026-06-29) have since run incremental across reordering with rows
verified aligned.

_Historical note:_ originally the chunker's unsorted `iterdir()` shuffled row indices and the
embedder's row-keyed resume could corrupt embeddings — which is why the 2026-06-17 batch
deferred a 14h full rebuild. ADR-012 removed that coupling; the open question below is closed.

### 2. Extraction quality is the dominant variable

Sweep findings (run 2026-06-16) showed that the single biggest source of bad retrieval results was OCR noise leaking through the chunker (index pages, page-number-littered chunks, mid-word script switches). The verifier catches semantic divergences but not aesthetic ones like residual page-headers. **Until the chunker grows a "drop low-signal chunks" pass, extraction quality is human-gated at Step 3.**

### 3. Marathi-language athvani lacks any public source

Almost all athvani exists only in the family's typewritten or hand-recorded archives. The `external_verification: false` flag is honest, but it means a meaningful fraction of the corpus will never be IA-corroborable. Downstream filters (if we ever add a "verified only" toggle) need to be aware that this hides ~30-50% of material.

### 4. Reference material is easy to misclassify as canonical

Q1 sweep surfaced an index page from *Hindu Mysticism* as chunk 8 — high cosine on "Bhakti" because the index says "Bhakti, p. 6, p. 12, p. 89…". Triage Step 1 must catch this: a back-of-book index is `reference`, not `canonical`. When in doubt, sample-read 3 paragraphs — references are almost always recognizable by density of page-number references.

## Open questions

1. **Chunker → embedder coupling.** ~~Should we refactor to key by `chunk_id` rather than row index…~~ **RESOLVED (ADR-012, 2026-06-24)** — carry-over is now keyed by `chunk_id`; chunker re-orderings no longer invalidate embeddings. See Risks §1.
2. **Re-ingestion of edited works.** If a user reports a transcription error in an already-ingested work and we fix it, how do we surface the affected embeddings for re-computation? Open.
3. **Multi-language single work.** A canonical work that exists in both EN and MR (e.g., *Pathway to God in Marathi Literature*) needs two `text.md` files under separate `<lang>/` folders. Are they one logical work with two language editions, or two distinct works? RFC-002 implies one work; chunker.py emits separate chunks per language. Pin this for future verification work.
4. **Triage YAML schema.** Step 1 calls for `batch-triage.yaml` but its exact schema isn't specified. Settle this on the next ingestion (will surface naturally) and back-fill the schema into RFC-002 §3.

## References

- RFC-002: Corpus structure (folder layout, `meta.yaml` schema)
- RFC-003: Retrieval and RAG (chunking parameters, embedding model)
- ADR-002: Lineage-aware folder structure
- ADR-005: Raw zip is the immutable archive; extracted staging uses move semantics
- ADR-007: Quote-first curation pattern
- ADR-009: Embedding model (BGE-M3)
- `tools/chunker.py`, `tools/embedder.py`, `tools/verify_canonical.py`, `tools/ingest_athvani.py`, `tools/retrieve.py`, `tools/tune_sweep.py`
- POST_DEMO_TODO.md §2 (real LLM classification; real retrieval wiring)
