#!/bin/bash
# RFC-009 Step 3 — OCR the now-resolved TBD files from batch drive_dump_2026-06-22.
# Classifications confirmed by operator 2026-06-22 (see batch-triage.yaml resolutions:).
# Runs --jobs 2 to stay gentle alongside the main batch (ocr_batch_2026-06-22.sh, --jobs 4).
# Gandhi (clean EN text layer) and Smruti Sangam (.docx) were extracted separately, not here.

set -uo pipefail
BATCH=/Users/neharepal/gurudev-corpus/00_raw/drive_dump_2026-06-22
SRC="$BATCH/Neha 2"; OCR="$BATCH/_ocr"; EXT="$BATCH/_extracted"; LOG="$BATCH/ocr-log-tbd.txt"
mkdir -p "$OCR" "$EXT"

MAP=(
  "Copy of A Vindication Of Indian Philosophy_.pdf::vindication-of-indian-philosophy"
  "Copy of साधक - बोध-993.pdf::sadhak-bodh"
  "Copy of अमृतवल्ली_.pdf::amrutavalli"
  "Copy of Pawanbhumi_Jamkhandi_v2.pdf::pawanbhumi-jamkhandi"
  "Copy of Gurudev Mahayudhacha Sankshipt Itihas .pdf::mahayudhacha-sankshipt-itihas"
)

start=$(date +%s)
echo "=== TBD OCR batch start: $(date -u +%FT%TZ)  ·  ${#MAP[@]} files ===" | tee -a "$LOG"
for entry in "${MAP[@]}"; do
  src="${entry%%::*}"; slug="${entry##*::}"
  in="$SRC/$src"; pdf_out="$OCR/${slug}.pdf"; txt_out="$EXT/${slug}.md"
  [[ -f "$in" ]] || { echo "MISSING: $src" | tee -a "$LOG"; continue; }
  [[ -f "$txt_out" && -s "$txt_out" ]] && { echo "skip (done): $slug" | tee -a "$LOG"; continue; }
  pages=$(/usr/local/bin/pdfinfo "$in" 2>/dev/null | awk -F: '/^Pages/ {gsub(/ /,"",$2); print $2}')
  echo "[$(date -u +%FT%TZ)] OCR start: $slug  ($pages pages)" | tee -a "$LOG"
  t0=$(date +%s)
  /usr/local/bin/ocrmypdf -l eng+mar+hin+san --skip-text --output-type pdf --jobs 2 --quiet --rotate-pages \
    "$in" "$pdf_out" 2>>"$LOG"
  [[ $? -ne 0 ]] && { echo "FAIL: $slug" | tee -a "$LOG"; continue; }
  /usr/local/bin/pdftotext -layout "$pdf_out" "$txt_out" 2>>"$LOG"
  echo "[$(date -u +%FT%TZ)] OCR done:  $slug  ·  $(($(date +%s) - t0))s  ·  $(wc -c < "$txt_out" | tr -d ' ') chars" | tee -a "$LOG"
done
echo "=== TBD OCR batch end: $(date -u +%FT%TZ)  ·  total $(($(date +%s) - start))s ===" | tee -a "$LOG"
