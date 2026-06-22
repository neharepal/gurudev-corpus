#!/bin/bash
# Batch OCR all PDFs in the Wikimedia ACPR batch.
# Strategy: serial across PDFs, parallel across pages within each PDF.
# Multi-language tesseract config (eng+mar+hin+san) covers all expected scripts.
# Outputs:
#   - <ocr_dir>/<file>.pdf — OCR'd PDF with invisible text layer
#   - <ocr_dir>/<file>.txt — extracted text via pdftotext -layout
#   - ocr-log.txt           — per-file timing + status
# Skips files that already have a .txt output.

set -uo pipefail

SRC=/Users/neharepal/gurudev-corpus/00_raw/drive_dump_2026-06-17/wikimedia_acpr
OUT="$SRC/ocr"
LOG="$SRC/ocr-log.txt"
mkdir -p "$OUT"

cd "$SRC"

start=$(date +%s)
echo "=== OCR batch start: $(date -u +%FT%TZ) ===" | tee -a "$LOG"
echo "Languages: eng+mar+hin+san  ·  parallel pages per PDF: 4" | tee -a "$LOG"
echo "" | tee -a "$LOG"

for f in *.pdf; do
  [[ -f "$f" ]] || continue
  base="${f%.pdf}"
  pdf_out="$OUT/${base}.pdf"
  txt_out="$OUT/${base}.txt"

  if [[ -f "$txt_out" && -s "$txt_out" ]]; then
    chars=$(wc -c < "$txt_out" | tr -d ' ')
    echo "skip (already done): $f  ·  ${chars} chars" | tee -a "$LOG"
    continue
  fi

  pages=$(/usr/local/bin/pdfinfo "$f" 2>/dev/null | awk -F: '/^Pages/ {gsub(/ /,"",$2); print $2}')
  echo "[$(date -u +%FT%TZ)] OCR start: $f  ($pages pages)" | tee -a "$LOG"
  t0=$(date +%s)

  # --skip-text: don't re-OCR pages that already have text (defensive).
  # --output-type pdf: standard PDF; smaller than pdfa.
  # --jobs 4: four parallel pages.
  # --quiet: minimal output (errors still print).
  # --rotate-pages: detect and fix rotation per page.
  /usr/local/bin/ocrmypdf \
    -l eng+mar+hin+san \
    --skip-text \
    --output-type pdf \
    --jobs 4 \
    --quiet \
    --rotate-pages \
    "$f" "$pdf_out" 2>>"$LOG"
  rc=$?

  if [[ $rc -ne 0 ]]; then
    echo "FAIL ($rc): $f" | tee -a "$LOG"
    continue
  fi

  /usr/local/bin/pdftotext -layout "$pdf_out" "$txt_out" 2>>"$LOG"
  txt_chars=$(wc -c < "$txt_out" | tr -d ' ')
  t1=$(date +%s)
  elapsed=$((t1 - t0))
  echo "[$(date -u +%FT%TZ)] OCR done: $f  ·  ${elapsed}s  ·  ${txt_chars} text chars" | tee -a "$LOG"
done

end=$(date +%s)
total=$((end - start))
echo "" | tee -a "$LOG"
echo "=== OCR batch end: $(date -u +%FT%TZ)  ·  total ${total}s ===" | tee -a "$LOG"
ls -la "$OUT" | tee -a "$LOG"
