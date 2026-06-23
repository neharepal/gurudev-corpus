#!/bin/bash
# RFC-009 Step 3 — OCR the confident-classification subset of batch drive_dump_2026-06-22.
# Held back (TBD / low-confidence in batch-triage.yaml): A Vindication, Gandhi and other
# Hindi Saints, Gurudev Mahayudhacha, Pawanbhumi Jamkhandi, Amrutavalli, Sadhak-bodh,
# Smruti Sangam(.docx) — ingest once the operator resolves their classification.
#
# Strategy mirrors tools/ocr_wikimedia_batch.sh: ocrmypdf eng+mar+hin+san, --skip-text,
# 4 parallel pages, then pdftotext -layout. Ordered smallest->largest for early progress.
# Outputs:  _ocr/<slug>.pdf  (text-layer PDF)   _extracted/<slug>.md  (extracted text)
# Idempotent: skips any slug whose _extracted/<slug>.md already exists and is non-empty.

set -uo pipefail

BATCH=/Users/neharepal/gurudev-corpus/00_raw/drive_dump_2026-06-22
SRC="$BATCH/Neha 2"
OCR="$BATCH/_ocr"
EXT="$BATCH/_extracted"
LOG="$BATCH/ocr-log.txt"
mkdir -p "$OCR" "$EXT"

# "source filename::output slug"  (smallest file first)
MAP=(
  "Copy of The Evolution Of My Own Thought 1.pdf::evolution-of-my-own-thought"
  "Copy of Studies in Indian Philosophy.pdf::studies-in-indian-philosophy-NEW"
  "Copy of Nimbargi Maharaj Biography_.pdf::nimbargi-maharaj-biography-en"
  "Copy of परमार्थपर व्याख्याने ३.pdf::parmarthapar-vyakhyane-03"
  "Copy of परमार्थपर व्याख्याने ७.pdf::parmarthapar-vyakhyane-07"
  "Copy of परमार्थपर व्याख्याने ४.pdf::parmarthapar-vyakhyane-04"
  "Copy of परमार्थपर व्याख्याने १.pdf::parmarthapar-vyakhyane-01"
  "Copy of परमार्थपर व्याख्याने २.pdf::parmarthapar-vyakhyane-02"
  "Copy of दादा तेंडुलकर आठवणी शेष रुपेरी पाने.pdf::dada-tendulkar-shesh-ruperi-pane"
  "Copy of परमार्थपर व्याख्याने ५.pdf::parmarthapar-vyakhyane-05"
  "Copy of परमार्थपर व्याख्याने ६.pdf::parmarthapar-vyakhyane-06"
  "Copy of Date Spiritual Lineage 2015.117278.R-D-Ranade-And-His-Spiritual-Lineage.pdf::ranade-and-his-spiritual-lineage"
  "Copy of हिंदी परमार्थ सोपान_.pdf::hindi-parmarth-sopan"
  "Copy of The Creative Period.pdf::creative-period-NEW"
  "Copy of कन्नड साहित्यातील गुरुदेव रानडे यांच्या पुण्यस्मृती.pdf::kannada-sahityatil-punyasmruti"
  "Copy of गुरुदेव रानडे-जीवनदर्शन ले-शा-नी-देशपांडे 28-Jan-2022 13-14-24.pdf::jivandarshan-deshpande"
  "Copy of संतसभा परमपूज्य गुरुदेवांच्या सीटींग्ज, वामनराव कुलकर्णी.pdf::santsabha-sittings-vamanrao-kulkarni"
)

start=$(date +%s)
echo "=== OCR batch drive_dump_2026-06-22 start: $(date -u +%FT%TZ) ===" | tee -a "$LOG"
echo "Languages: eng+mar+hin+san  ·  4 parallel pages  ·  ${#MAP[@]} files" | tee -a "$LOG"

for entry in "${MAP[@]}"; do
  src="${entry%%::*}"
  slug="${entry##*::}"
  in="$SRC/$src"
  pdf_out="$OCR/${slug}.pdf"
  txt_out="$EXT/${slug}.md"

  if [[ ! -f "$in" ]]; then
    echo "MISSING SOURCE: $src" | tee -a "$LOG"; continue
  fi
  if [[ -f "$txt_out" && -s "$txt_out" ]]; then
    echo "skip (done): $slug" | tee -a "$LOG"; continue
  fi

  pages=$(/usr/local/bin/pdfinfo "$in" 2>/dev/null | awk -F: '/^Pages/ {gsub(/ /,"",$2); print $2}')
  echo "[$(date -u +%FT%TZ)] OCR start: $slug  ($pages pages)" | tee -a "$LOG"
  t0=$(date +%s)

  /usr/local/bin/ocrmypdf \
    -l eng+mar+hin+san \
    --skip-text \
    --output-type pdf \
    --jobs 4 \
    --quiet \
    --rotate-pages \
    "$in" "$pdf_out" 2>>"$LOG"
  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "FAIL ($rc): $slug" | tee -a "$LOG"; continue
  fi

  /usr/local/bin/pdftotext -layout "$pdf_out" "$txt_out" 2>>"$LOG"
  chars=$(wc -c < "$txt_out" | tr -d ' ')
  t1=$(date +%s)
  echo "[$(date -u +%FT%TZ)] OCR done:  $slug  ·  $((t1 - t0))s  ·  ${chars} chars" | tee -a "$LOG"
done

echo "=== OCR batch end: $(date -u +%FT%TZ)  ·  total $(($(date +%s) - start))s ===" | tee -a "$LOG"
