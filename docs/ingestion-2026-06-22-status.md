# Ingestion Status — Batch `drive_dump_2026-06-22` (Drive "Dump 3")

**Branch:** `ingestion/drive-dump-2026-06-22` · **As of:** 2026-06-23 · **Embed step:** NOT run (paused per operator).

Handoff note written while you slept. Background OCR + benchmark all finished.

## TL;DR
- 27 files → 1 internal byte-dup → 26 distinct → **~20 works** (16 new + 2 upgrades + 2 stub-completions).
- **10 works fully structured + committed** (Step 5 done). Rest blocked on your decisions below.
- OCR engine question answered with a real benchmark (see §3).

## 1. Works structured + committed (10) — `status: extracted`, `verified: false`
| Work | Destination | Lang | OCR quality |
|---|---|---|---|
| herakleitos | canonical/gurudev_ranade/books | en | clean (minor artifacts) |
| evolution-of-my-own-thought | canonical/gurudev_ranade/books | en | clean (text layer) |
| vindication-of-indian-philosophy | canonical/gurudev_ranade/books | en | OCR clean |
| gandhi-and-other-indian-saints | canonical/gurudev_ranade/books | en | clean (text layer) |
| sadhakbodh | canonical/kakasaheb_tulpule/letters | mr | OCR clean — **completed prior failed stub** |
| ranade-and-his-spiritual-lineage | biography/about_gurudev_ranade | en | OCR clean |
| nimbargi-maharaj-biography-en | biography/about_nimbargi_maharaj | en | OCR |
| kannada-sahityatil-punyasmruti | biography/about_gurudev_ranade | mr | OCR clean |
| jivandarshan-deshpande | biography/about_gurudev_ranade | mr | usable, layout-noisy |
| nimbargi-maharaj-charitra-athavani-mr | biography/about_nimbargi_maharaj | mr | clean (docx) |

## 2. Pending — needs your decision

### 2a. Two upgrades (existing OCR-only works) — replace?
- **studies-in-indian-philosophy** — existing Wikimedia OCR opens with pure garbage; new source is clean. **→ recommend REPLACE.**
- **creative-period** — existing and new are *both* clean and near-identical length (22.5K lines each). **→ recommend KEEP existing** (marginal benefit, replacing is destructive).

### 2b. Athvani-collection books — how to model? (not yet structured)
These are book-length recollection volumes, not single stories. Existing convention files such anthologies under `biography/` (e.g. `shri-gurudevanchya-athvani-pustak`). Options: file as biography-kind now (fast, retrievable), or split into `athvani/stories/<id>/variants/` later (heavier curation, RFC-002 §4; ADR-008 says dedup-at-retrieval so splitting may be unnecessary).
- santsabha-sittings-vamanrao-kulkarni (mr, OCR good)
- dada-tendulkar-shesh-ruperi-pane (mr, usable/noisy)
- smruti-sangam (mr+en, clean; compiler Rajendra Chauhan — multi-tribute anthology)

### 2c. OCR path for the failures — ROOT CAUSE per file (diagnosed 2026-06-23)
tesseract fails on all three, but for **three different reasons** — only one is an image-quality problem. Evidence: `pdfimages -list` + rendered page inspection (`pdftoppm`).

| File | Pages | Scan | Why tesseract fails | Better images help? |
|---|---|---|---|---|
| **amrutavalli** | 78 | 150 DPI color, clean but soft | **Resolution too low** (150 DPI < tesseract's 300 DPI comfort zone). Surya already reads it cleanly at 150. | **YES** — a 300 DPI rescan makes it trivial for any engine. (Not strictly needed; Surya works on the current scan.) |
| **hindi-parmarth-sopan** | 539 | 600 DPI bitonal, **pristine & crisp** | **Old/letterpress Devanagari typeface + archaic orthography** (old-style conjuncts/matras). tesseract's Hindi model is trained on modern fonts. Pure model limitation. | **NO** — scan is already excellent. Needs a model robust to historical Devanagari (Surya / Google Vision / vision-LLM). |
| **pawanbhumi-jamkhandi** | 12 | ~300 DPI color, fine | **Complex souvenir-brochure layout** — multi-column, photos, mixed English+Marathi side-by-side. tesseract page segmentation can't cope. | **NO** — needs layout-aware OCR (Google Vision / Surya layout) or a vision-LLM. Only 12 pages → vision-LLM is cheap+ideal here. |

**So the "arrange better images" offer only helps amrutavalli.** The other two are clean scans that fail on typeface/layout, not pixels. Recommended path: Google Cloud Vision (handles all three) or vision-LLM (best for the 12-page pawanbhumi brochure and historical Hindi); Surya is the no-cloud fallback and already proven on amrutavalli.

## 3. OCR engine benchmark (answer to "better tool for Devanagari?")
Tested on the 3 worst files at 300 DPI:

| File | tesseract `--skip-text` | tesseract `--force-ocr` 300dpi | Surya |
|---|---|---|---|
| amrutavalli (78pp scan) | 2.5K chars (junk) | — | **57 lines clean Marathi ✓** |
| lecture vols 1–7 | 1.4–13K (thin) | **43–107K (readable, noisy)** | not run |
| mahayudhacha (mojibake layer) | 615K mojibake | recovered (proven on page sample) | — |
| hindi-parmarth-sopan (539pp) | 1.09M junk | **still junk** | needs Surya/Vision |

**Conclusions:**
- `--force-ocr` (ignore bad text layer + OCR images) rescues mahayudhacha and the lecture series — `.force.md` drafts are in `_extracted/`.
- Tesseract genuinely fails on amrutavalli / hindi-parmarth-sopan; **Surya reads amrutavalli cleanly**.
- Modern Surya is awkward on this Intel Mac (no torch wheel for latest → had to pin `numpy<2` + Surya 0.4.5; CPU-slow). **For bulk Devanagari, Google Cloud Vision is the best ROI**; Surya is the no-cloud fallback; vision-LLM for the highest-value works.

## 4. Next steps — progress 2026-06-23
1. ✅ **2a applied:** studies-in-indian-philosophy replaced with clean text-layer; creative-period kept (declined).
2. ✅ **2c re-OCR DONE** (engines per root-cause diagnosis): amrutavalli→Surya (141 chunks); pawanbhumi→vision-LLM (14 chunks, trilingual); hindi-parmarth-sopan→Sonnet vision, all 539pp (269 chunks, first `hi` work).
3. ✅ **2b athvani structured:** 213 stories from 3 books via `tools/structure_athvani_2026-06-22.py` (line-numbering bug found + fixed). QA'd clean.
4. ✅ **Step 6 catalog:** 10 works added to `03_catalog/catalog.yaml` (now 26 works); 213 stories merged into `catalog.yaml` + `story_index.yaml`. *(corpus_browser.html regen still TODO — cosmetic.)*
5. ✅ **Step 7 chunk + SoT:** `chunker.py` → 14,882 chunks; `build_corpus_manifest.py` → `CORPUS_CONTENTS.md` (flags embed-stale).
6. ⏸️ **STOPPED before Step 8 (embed)** per operator. Changelog entry added (`docs/CORPUS_CHANGELOG.md`); smoke-test plan drafted (scratchpad).

**Remaining:** (a) operator decision on 2c OCR engine, then re-OCR + structure those 3 works; (b) regenerate `corpus_browser.html`; (c) run embedder (`tools/embedder.py --restart`) + smoke-test — only after 2c is resolved or explicitly deferred.

## 5. Where things live
- Staging: `00_raw/drive_dump_2026-06-22/` — `_extracted/` (drafts), `_force/` (force-ocr PDFs), `_ocr/` (skip-text PDFs), `batch-triage.yaml` (full classification + resolutions). *(gitignored — local only.)*
- Tools: `tools/structure_batch_2026-06-22.py`, `tools/ocr_batch_2026-06-22*.sh`, `tools/ocr_force_2026-06-22.sh`, `tools/build_corpus_manifest.py`.
- SoT: `CORPUS_CONTENTS.md` (stale until Step 7 re-chunk).
