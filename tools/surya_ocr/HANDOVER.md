# HANDOVER — Re-OCR the garbled books on the M4 (for Claude on the new device)

**You (Claude on the M4) have ONE narrow job: OCR 15 PDFs at the best possible
quality and hand the text back.** You do NOT touch the corpus, embeddings, app,
or git repo on this machine — all of that lives on the main (Intel) Mac, which
does the compare/replace/re-embed once your output returns.

## Why this machine
The main Mac is Intel x86 → PyTorch caps at 2.2.2 → Surya caps at 0.4.5, CPU-only.
This M4 is Apple Silicon → it installs the **latest Surya** and runs on the **MPS
GPU** — much better recognition (especially Devanagari) and ~10–20× faster. That is
the whole reason the job moved here.

## What you were given
This folder (`_surya_ocr_job/`, AirDropped from the main Mac) contains:
- `pdfs/` — 15 source PDFs, named `<work_id>.pdf`. These are the books an OCR audit
  flagged as GARBLED under tesseract (see the list below). The source scans are
  believed to be good; tesseract was the limitation.
- `run_ocr.sh` — sets up a venv, installs latest surya, OCRs each PDF on MPS, then
  assembles markdown. Safe to stop/resume (skips books already done).
- `assemble.py` — turns Surya's cached JSON (`out_raw/`) into `out/<work_id>.md`.
  This is decoupled from OCR on purpose: if the text formatting needs fixing, re-run
  ONLY this, never the hours of OCR.

## Do this
```bash
cd _surya_ocr_job
bash run_ocr.sh
```
- Surya downloads models on first run (needs internet). Confirm the torch line prints
  `MPS available: True` — if it prints False you are on CPU; stop and fix (wrong python
  / non-Apple-Silicon).
- These are mostly Marathi/Devanagari (a few English, one Kannada+Marathi). The current
  Surya foundation model is language-agnostic and needs no `--langs`. If the installed
  version's CLI differs, run `./venv/bin/surya_ocr --help` and adapt `run_ocr.sh` — you
  have latitude to fix version drift; the goal is clean text, not a specific command.
- The books are large (100–350 pp; ~1.1 GB total). Expect a meaningful run; let it
  finish or resume in passes.

## Quality bar (spot-check before handing back)
Open 2–3 `out/*.md` and sanity-check the Devanagari: conjunct consonants intact, no
mojibake, words not split by stray spaces, real sentences. Compare a page against the
same page in the PDF. Note any book where the SOURCE scan itself is too poor to OCR
(that one needs a better copy, not a better engine) in a short `out/NOTES.md`.

## Hand back
Return the **entire `out/` folder** (the `.md` files + `out/NOTES.md` if you wrote one)
to the main Mac — AirDrop it back. Do NOT bother returning `out_raw/` or `venv/`.
The main Mac's Claude then quality-compares each against the tesseract `text.md`,
replaces in place where better (keeping the same `work_id`), and force-re-embeds.

## The 15 works (worst-first from the audit)
English (better copy may exist on Internet Archive; OCR still worth trying):
  vindication-of-indian-philosophy, acpr-silver-jubilee-vol1, acpr-silver-jubilee-vol2
Devanagari / mixed:
  jivandarshan-deshpande, kannada-sahityatil-punyasmruti, sadhakbodh, javak-patre-tipane,
  gurudev-paramarthik-shikvan, sonari-pane-2000, kushal-pradhyapak, allahabad-days-mr,
  kannad-parmarth-sopan, parmartha-mandir, swanandacha-gabha
Partial (only Marathi captions were garbled; English/Kannada were clean):
  pawanbhumi-jamkhandi

Full audit with sample passages: `docs/ocr-quality-audit-2026-07-14.md` on the main Mac.
