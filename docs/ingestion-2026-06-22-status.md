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

### 2c. OCR path for the failures (see benchmark)
amrutavalli, hindi-parmarth-sopan, pawanbhumi-jamkhandi can't be done with tesseract. Pick: Surya local (works but slow on this Intel Mac), Google Cloud Vision (best, needs your GCP key), or vision-LLM for top works.

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

## 4. Next steps (after your calls — all before the embed pause)
1. Apply upgrade decisions (2a); promote `.force.md` lectures+mahayudhacha after a quality eyeball.
2. Re-OCR amrutavalli / hindi / pawanbhumi with chosen engine (2c).
3. Structure athvani books per (2b); structure the re-OCR'd works (generator: `tools/structure_batch_2026-06-22.py`).
4. **Step 6 catalog:** add to `03_catalog/catalog.yaml` (works + stories), `story_index.yaml`; regenerate `tools/corpus_browser.html`.
5. **Step 7 chunk:** `python tools/chunker.py`; then regenerate SoT: `python tools/build_corpus_manifest.py`.
6. **STOP before Step 8 (embed)** — hand back smoke-test plan + `docs/CORPUS_CHANGELOG.md` draft.

## 5. Where things live
- Staging: `00_raw/drive_dump_2026-06-22/` — `_extracted/` (drafts), `_force/` (force-ocr PDFs), `_ocr/` (skip-text PDFs), `batch-triage.yaml` (full classification + resolutions). *(gitignored — local only.)*
- Tools: `tools/structure_batch_2026-06-22.py`, `tools/ocr_batch_2026-06-22*.sh`, `tools/ocr_force_2026-06-22.sh`, `tools/build_corpus_manifest.py`.
- SoT: `CORPUS_CONTENTS.md` (stale until Step 7 re-chunk).
