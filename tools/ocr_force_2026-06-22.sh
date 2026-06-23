#!/bin/bash
# Rescue pass: --force-ocr (ignore any existing/garbage text layer, OCR the rasterized
# images). Targets works that failed the --skip-text pass: mahayudhacha (non-Unicode font
# mojibake text layer), hindi-parmarth-sopan (failed OCR), and the thin lecture volumes.
# Non-destructive: writes _extracted/<slug>.force.md alongside the originals for comparison.
set -uo pipefail
BATCH=/Users/neharepal/gurudev-corpus/00_raw/drive_dump_2026-06-22
SRC="$BATCH/Neha 2"; OCR="$BATCH/_force"; EXT="$BATCH/_extracted"; LOG="$BATCH/ocr-log-force.txt"
mkdir -p "$OCR"
MAP=(
  "Copy of Gurudev Mahayudhacha Sankshipt Itihas .pdf::mahayudhacha-sankshipt-itihas"
  "Copy of परमार्थपर व्याख्याने १.pdf::parmarthapar-vyakhyane-01"
  "Copy of परमार्थपर व्याख्याने २.pdf::parmarthapar-vyakhyane-02"
  "Copy of परमार्थपर व्याख्याने ३.pdf::parmarthapar-vyakhyane-03"
  "Copy of परमार्थपर व्याख्याने ४.pdf::parmarthapar-vyakhyane-04"
  "Copy of परमार्थपर व्याख्याने ५.pdf::parmarthapar-vyakhyane-05"
  "Copy of परमार्थपर व्याख्याने ६.pdf::parmarthapar-vyakhyane-06"
  "Copy of परमार्थपर व्याख्याने ७.pdf::parmarthapar-vyakhyane-07"
  "Copy of हिंदी परमार्थ सोपान_.pdf::hindi-parmarth-sopan"
)
start=$(date +%s)
echo "=== FORCE-OCR rescue start: $(date -u +%FT%TZ)  ·  ${#MAP[@]} files ===" | tee -a "$LOG"
for entry in "${MAP[@]}"; do
  src="${entry%%::*}"; slug="${entry##*::}"
  in="$SRC/$src"; pdf_out="$OCR/${slug}.pdf"; txt_out="$EXT/${slug}.force.md"
  [[ -f "$in" ]] || { echo "MISSING: $src" | tee -a "$LOG"; continue; }
  [[ -f "$txt_out" && -s "$txt_out" ]] && { echo "skip (done): $slug" | tee -a "$LOG"; continue; }
  pages=$(/usr/local/bin/pdfinfo "$in" 2>/dev/null | awk -F: '/^Pages/ {gsub(/ /,"",$2); print $2}')
  echo "[$(date -u +%FT%TZ)] FORCE start: $slug ($pages pp)" | tee -a "$LOG"; t0=$(date +%s)
  /usr/local/bin/ocrmypdf -l eng+mar+hin+san --force-ocr --oversample 300 --output-type pdf \
    --jobs 4 --quiet --rotate-pages --clean "$in" "$pdf_out" 2>>"$LOG"
  [[ $? -ne 0 ]] && { echo "FAIL: $slug" | tee -a "$LOG"; continue; }
  /usr/local/bin/pdftotext -layout "$pdf_out" "$txt_out" 2>>"$LOG"
  echo "[$(date -u +%FT%TZ)] FORCE done: $slug · $(($(date +%s)-t0))s · $(wc -c <"$txt_out"|tr -d ' ') chars" | tee -a "$LOG"
done
echo "=== FORCE-OCR end: $(date -u +%FT%TZ) · total $(($(date +%s)-start))s ===" | tee -a "$LOG"
