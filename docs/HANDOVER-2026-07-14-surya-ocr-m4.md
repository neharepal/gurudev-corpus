# HANDOVER — Surya re-OCR of garbled books (M4 offload) — 2026-07-14

Master pickup note. Two machines are involved; this doc says who does what.

## The situation
An OCR-quality audit (`docs/ocr-quality-audit-2026-07-14.md`) flagged **15 ingested
books as GARBLED** — but the source scans are believed good; **tesseract** (the engine
used at ingestion) is the limitation on Devanagari. Plan: **re-OCR the 15 with the
latest Surya**, quality-compare, and replace the corpus text where better.

**Why two machines:** the main Mac is **Intel x86** → PyTorch is capped at 2.2.2 →
Surya capped at **0.4.5, CPU-only** (old model, slow). The user's **M4** is Apple
Silicon → **latest Surya + MPS GPU** (better recognition, ~10–20× faster). So OCR runs
on the M4; everything else stays here.

## Split of work

### On the M4 (Claude there) — OCR only
- Input: `_surya_ocr_job/` folder (AirDropped) = `pdfs/` (15 books) + `run_ocr.sh` +
  `assemble.py` + `HANDOVER.md`.
- Run `bash run_ocr.sh` → produces `out/<work_id>.md`.
- Full instructions: **`tools/surya_ocr/HANDOVER.md`** (also copied inside the folder).
- Hand back: the `out/` folder only.

### On the main Mac (Claude here) — the rest
When `out/*.md` returns, for each work:
1. **Quality-compare** Surya `out/<id>.md` vs the ingested tesseract `text.md`
   (Devanagari %, mojibake/stray-char counts, spot-read passages). This is RFC-009
   Step 4.5 (duplicate quality gate) applied to a same-work replacement.
2. **Replace in place** only where Surya is clearly better: overwrite the work's
   `text.md`, keep the same `work_id`; update `meta.yaml`
   (`text_extraction_method: surya-ocr <ver>`, quality_notes, re-OCR date).
3. **Re-chunk** (`tools/chunker.py`) and **re-embed**.
4. **Smoke-test** a query that hits the replaced book; append `CORPUS_CHANGELOG.md`.

## ⚠️ Embedder gotcha for the replace step (verified 2026-07-14)
`tools/embedder.py` carries over vectors by **chunk_id only — it never compares text**
(`build_id_to_vec` keys on `id`; the partition loop puts any id already in the map into
carryover). It also has a count-match short-circuit. So replacing a work's `text.md`
while chunk_ids stay the same → the embedder **keeps the OLD (stale) vectors** and does
not re-embed the new text. RFC-009's claim that it "detects this by id and re-encodes"
is wrong for the *replace* case.

**Until the text-hash fix lands (proposed for the Phase-2 embedder work), force the
re-embed of replaced works** by one of:
- delete the replaced works' rows (by `id` prefix `="<work_id>--"`) from
  `04_processed/embeddings/chunks_meta.jsonl` + the aligned rows of `embeddings.npy`
  before running the embedder (so those ids are "new" → re-encoded), **or**
- run the embedder with `--restart` (full rebuild; expensive), **or**
- land the text-hash change first, then a normal incremental run detects the diff.

The clean long-term fix is the **text-hash check in the embedder** — recommended, folds
into the Phase-2 embedder work. See RFC-017 / the Phase-2 plan.

## Status / ledger
- Audit committed: `da7664b`. Handoff kit: `tools/surya_ocr/` (this commit).
- 15 source PDFs staged in `_surya_ocr_job/pdfs/` (gitignored, ~1.1 GB) — AirDrop target.
- Task #41 (Re-OCR garbled books with Surya) = in progress, blocked on M4 run.
- Unrelated in-flight: Phase 2 small-to-big (#40) — GPU re-embed still pending the M4
  too; the Phase-2 full re-embed and this re-OCR can share the same M4 session.
