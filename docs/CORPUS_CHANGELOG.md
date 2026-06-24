# Corpus Changelog

Per RFC-009 §Step 10. Authoritative answer to "what's in the corpus as of date X" and
"when did we add work Y."

## v.2026-06-23 — Batch drive_dump_2026-06-22 (Drive "Dump 3")

10 new works + 1 upgrade + 213 athvani recollection stories segmented from 3 anthologies.
Chunked (14,882 total chunks). **Embeddings NOT yet regenerated — Step 8 paused per
operator;** `CORPUS_CONTENTS.md` flags the chunk/embed mismatch until the rebuild.

Added (canonical):
- herakleitos (gurudev_ranade, en) — 27 chunks
- evolution-of-my-own-thought (gurudev_ranade, en) — 47 chunks
- vindication-of-indian-philosophy (gurudev_ranade, en) — 32 chunks
- gandhi-and-other-indian-saints (gurudev_ranade, en) — 242 chunks
- sadhakbodh (kakasaheb_tulpule, mr, letters) — 150 chunks — **completes the 2026-06-11 failed stub**

Added (biography):
- ranade-and-his-spiritual-lineage (about_gurudev_ranade, en) — 446 chunks
- kannada-sahityatil-punyasmruti (about_gurudev_ranade, mr) — 129 chunks
- jivandarshan-deshpande (about_gurudev_ranade, mr) — 546 chunks
- nimbargi-maharaj-biography-en (about_nimbargi_maharaj, en) — 81 chunks
- nimbargi-maharaj-charitra-athavani-mr (about_nimbargi_maharaj, mr) — 67 chunks

Added (athvani — story segmentation):
- 213 individual athvani recollection stories (366 chunks) segmented into
  `02_aggregated/athvani/about_gurudev_ranade/stories/`, each with `meta.yaml` + a
  verbatim variant file; merged into `story_index.yaml` and `catalog.yaml`.
  - smruti-sangam (mr+en; compiler Rajendra Chauhan) — 110 stories (`smruti-*`)
  - santsabha-sittings-vamanrao-kulkarni (mr) — 77 stories (`santsabha-*`)
  - dada-tendulkar-shesh-ruperi-pane (mr) — 26 stories (`dada-tendulkar-*`)
  - Fixed a line-numbering bug in `tools/structure_athvani_2026-06-22.py` before
    finalizing (`str.splitlines` broke on form-feed page-break chars, desyncing slice
    boundaries from the segmentation agents' `\n`-based line numbers).

Upgraded:
- studies-in-indian-philosophy (other_authors / ed. B. R. Kulkarni, en) — 199 chunks
  (was 477) — replaced the noisy Wikimedia Commons OCR (opened with pure garbage) with a
  clean text-layer extraction from the Dump 3 source. Same work_id; text.md + meta.yaml.

Declined upgrade:
- creative-period (gurudev_ranade, en) — existing kept; new source near-identical (both
  clean, ~22.5K lines), replacement judged destructive for marginal benefit.

Verified-against: no public source — flagged (verified=false) on all new works.

Re-OCR'd + added (2c — engine chosen per root-cause diagnosis):
- amrutavalli (about_other_devotees, mr) — 141 chunks — **Surya** re-OCR (tesseract failed
  on the 150 DPI scan). Memoir of Dadasaheb Deshpande (Inchageri lineage) by Rama Inamdar.
- pawanbhumi-jamkhandi (about_gurudev_ranade, en/mr/kn) — 14 chunks — **vision-LLM (Claude)**
  transcription of the 12pp trilingual souvenir brochure (tesseract failed on the layout).

Pending (2c — still in flight):
- **hindi-parmarth-sopan** (539pp, historical Devanagari typeface) — vision-LLM pass
  underway/queued (pages rendered). Clean scan; tesseract fails on the old typeface.

## v.2026-06-17 — Batch wikimedia_acpr_2026-06-17

16 books ingested from Wikimedia Commons ACPR-scanned category.

Added (canonical):
- constructive-survey-of-upanishadic-philosophy (gurudev_ranade, en) — 715 chunks
- creative-period (gurudev_ranade, en) — 813 chunks
- philosophical-and-other-essays (gurudev_ranade, en) — 277 chunks
- kannad-parmarth-sopan (gurudev_ranade, mr) — 312 chunks
- parmartha-mandir (gurudev_ranade, mr) — 289 chunks
- javak-patre-tipane (bhausaheb_maharaj, mr, letters) — 482 chunks
- gurudev-paramarthik-shikvan (kakasaheb_tulpule, mr) — 302 chunks
- pathway-to-god-in-the-vedas (other_authors / K. D. Sangoram, en) — 555 chunks
- critical-constructive-aspects (other_authors / B. R. Kulkarni, en) — 277 chunks
- studies-in-indian-philosophy (other_authors / ed. B. R. Kulkarni, en) — 477 chunks

Added (biography):
- allahabad-days-en (about_gurudev_ranade, en) — 235 chunks
- allahabad-days-mr (about_gurudev_ranade, mr) — 193 chunks
- kushal-pradhyapak (about_gurudev_ranade, mr) — 224 chunks
- sonari-pane-2000 (about_other_devotees, mr) — 147 chunks
- acpr-silver-jubilee-vol1 (about_other_devotees, en) — 523 chunks
- acpr-silver-jubilee-vol2 (about_other_devotees, en) — 282 chunks

Verified-against: no public source — flagged (verified=false, reason=ocr_only_from_wikimedia_commons_scan)
Chunks added: 6,103 (corpus total: 13,027 — was 6,924)
Embedding mode: **DEFERRED — full --restart rebuild required**
Smoke-test: **DEFERRED — pending embedder rebuild**
Source: https://commons.wikimedia.org/wiki/Category:Books_scanned_by_ACPR

### Row-stability check result: FAIL

Per RFC-009 §Risks §1, the chunker uses unsorted `iterdir()`. New folders landed
mid-stream rather than at the alphabetic end on this APFS volume. Of 86 pre-existing
work segments, only 3 retained their original row index in `chunks.jsonl`; the rest
shifted by 302 to 6,103 rows. The embedder's row-keyed resume cannot handle this —
running `tools/embedder.py` without `--restart` would corrupt existing embeddings
because the `.npy` file rows would no longer correspond to the right chunks.

The 14-hour full rebuild was deferred per the operator's "no-go right now" rule.

To complete this batch:
```bash
/Users/neharepal/opt/anaconda3/bin/python tools/embedder.py --restart
```
Then re-run the Step 9 smoke tests below.

### Step 5 / 6 status

- 16 `text.md` files placed verbatim from OCR.
- 16 `meta.yaml` files written with full provenance (raw_path, SHA-256, batch tag, OCR method).
- `03_catalog/catalog.yaml` `works:` list populated with all 16 entries (was `[]`).

### Per-source chunk counts (from chunker stderr)

```
canonical: 9,310 chunks (was 5,861 → +3,449)
biography: 2,564 chunks (was 1,260 → +1,304 — wait: actually +1,604; see below)
athvani-variants: 24 chunks
athvani-raw: 1,074 chunks
periodicals: 0 chunks
reference: 55 chunks
Total: 13,027 chunks (was 6,924 → +6,103)
By language: en 7,803 | mr 5,121 | mixed 103
```

### Smoke-test phrases (to run after `--restart` completes)

Pick one distinctive phrase per work and run `tools/retrieve.py "<phrase>" --show-text`.
Per RFC-009 §Step 9 spot-check rule, 5 of 16 is sufficient. Suggested coverage:
- EN canonical: `constructive-survey-of-upanishadic-philosophy` or `creative-period`
- MR canonical: `kannad-parmarth-sopan` or `gurudev-paramarthik-shikvan`
- MR letters:   `javak-patre-tipane`
- EN biography: `allahabad-days-en` or `acpr-silver-jubilee-vol1`
- MR biography: `kushal-pradhyapak` or `sonari-pane-2000`

Confirm cos ≥ 0.55 (RFC-009 floor) for the chosen phrase landing in the new work's chunks.
