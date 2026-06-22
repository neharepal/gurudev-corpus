#!/bin/bash
# Download Batch A — 16 PDFs from Wikimedia Commons ACPR category.
# Uses Special:FilePath redirect to fetch the actual file. Skips files already present.
# See RFC-009 §Step 2.
set -euo pipefail

OUT=/Users/neharepal/gurudev-corpus/00_raw/drive_dump_2026-06-17/wikimedia_acpr
mkdir -p "$OUT"

# Each file: source title on Commons (URL-encoded) | local filename
FILES=(
  "A_Constructive_Survey_of_Upanishadic_Philosophy_(Second_edition).pdf|constructive-survey-upanishadic-philosophy.pdf"
  "History_of_Indian_Philosophy_-_The_Creative_Period.pdf|creative-period.pdf"
  "Philosophical_%26_Other_Essays.pdf|philosophical-and-other-essays.pdf"
  "%E0%A4%95%E0%A4%A8%E0%A5%8D%E0%A4%A8%E0%A4%A1_%E0%A4%AA%E0%A4%B0%E0%A4%AE%E0%A4%BE%E0%A4%B0%E0%A5%8D%E0%A4%A5_%E0%A4%B8%E0%A5%8B%E0%A4%AA%E0%A4%BE%E0%A4%A8.pdf|kannad-parmarth-sopan-marathi.pdf"
  "%E0%A4%AA%E0%A4%B0%E0%A4%AE%E0%A4%BE%E0%A4%B0%E0%A5%8D%E0%A4%A5_%E0%A4%AE%E0%A4%82%E0%A4%A6%E0%A4%BF%E0%A4%B0.pdf|parmartha-mandir.pdf"
  "%E0%A4%B6%E0%A5%8D%E0%A4%B0%E0%A5%80_%E0%A4%AD%E0%A4%BE%E0%A4%89%E0%A4%B8%E0%A4%BE%E0%A4%B9%E0%A5%87%E0%A4%AC_%E0%A4%AE%E0%A4%B9%E0%A4%BE%E0%A4%B0%E0%A4%BE%E0%A4%9C_%E0%A4%89%E0%A4%AE%E0%A4%A6%E0%A5%80%E0%A4%95%E0%A4%B0_%E0%A4%AF%E0%A4%BE%E0%A4%82%E0%A4%9A%E0%A5%80_%E0%A4%9C%E0%A4%BE%E0%A4%B5%E0%A4%95_%E0%A4%AA%E0%A4%A4%E0%A5%8D%E0%A4%B0%E0%A5%87_%E0%A4%B5_%E0%A4%9F%E0%A4%BF%E0%A4%AA%E0%A4%A3%E0%A5%87.pdf|bhausaheb-maharaj-letters-and-notes.pdf"
  "Gurudev_R._D._Ranade_-_A_glance_at_his_Allahabad_University_days_and_other_essays.pdf|gurudev-allahabad-days-en.pdf"
  "%E0%A4%97%E0%A5%81%E0%A4%B0%E0%A5%81%E0%A4%A6%E0%A5%87%E0%A4%B5_%E0%A4%B0%E0%A4%BE._%E0%A4%A6._%E0%A4%B0%E0%A4%BE%E0%A4%A8%E0%A4%A1%E0%A5%87_-_%E0%A4%85%E0%A4%B2%E0%A4%BE%E0%A4%B9%E0%A4%BE%E0%A4%AC%E0%A4%BE%E0%A4%A6_%E0%A4%B5%E0%A4%BF%E0%A4%A6%E0%A5%8D%E0%A4%AF%E0%A4%BE%E0%A4%AA%E0%A5%80%E0%A4%A0%E0%A4%BE%E0%A4%A4%E0%A5%80%E0%A4%B2_%E0%A4%95%E0%A4%BE%E0%A4%B0%E0%A4%95%E0%A5%80%E0%A4%B0%E0%A5%8D%E0%A4%A6_%E0%A4%B5_%E0%A4%87%E0%A4%A4%E0%A4%B0_%E0%A4%B2%E0%A5%87%E0%A4%96.pdf|gurudev-allahabad-days-mr.pdf"
  "%E0%A4%AA%E0%A5%8D%E0%A4%B0%E0%A4%BE._%E0%A4%B0%E0%A4%BE._%E0%A4%A6._%E0%A4%B0%E0%A4%BE%E0%A4%A8%E0%A4%A1%E0%A5%87_%E0%A4%8F%E0%A4%95_%E0%A4%95%E0%A5%81%E0%A4%B6%E0%A4%B2_%E0%A4%AA%E0%A5%8D%E0%A4%B0%E0%A4%BE%E0%A4%A7%E0%A5%8D%E0%A4%AF%E0%A4%BE%E0%A4%AA%E0%A4%95_%E0%A4%B5_%E0%A4%A8%E0%A4%BE%E0%A4%AE%E0%A4%B5%E0%A4%82%E0%A4%A4_%E0%A4%97%E0%A5%8D%E0%A4%B0%E0%A4%82%E0%A4%A5%E0%A4%95%E0%A4%BE%E0%A4%B0_(2001).pdf|kushal-pradhyapak.pdf"
  "%E0%A4%B6%E0%A5%8D%E0%A4%B0%E0%A5%80_%E0%A4%97%E0%A5%81%E0%A4%B0%E0%A5%81%E0%A4%A6%E0%A5%87%E0%A4%B5_%E0%A4%B0%E0%A4%BE%E0%A4%A8%E0%A4%A1%E0%A5%87_%E0%A4%B5_%E0%A4%A4%E0%A5%8D%E0%A4%AF%E0%A4%BE%E0%A4%82%E0%A4%9A%E0%A5%80_%E0%A4%AA%E0%A4%BE%E0%A4%B0%E0%A4%AE%E0%A4%BE%E0%A4%B0%E0%A5%8D%E0%A4%A5%E0%A4%BF%E0%A4%95_%E0%A4%B6%E0%A4%BF%E0%A4%95%E0%A4%B5%E0%A4%A3.pdf|gurudev-paramarthik-shikvan.pdf"
  "%E0%A4%A8%E0%A4%BF%E0%A4%82%E0%A4%AC%E0%A4%B0%E0%A4%97%E0%A5%80_%E0%A4%B8%E0%A4%82%E0%A4%AA%E0%A5%8D%E0%A4%B0%E0%A4%A6%E0%A4%BE%E0%A4%AF%E0%A4%BE%E0%A4%9A%E0%A5%8D%E0%A4%AF%E0%A4%BE_%E0%A4%87%E0%A4%A4%E0%A4%BF%E0%A4%B9%E0%A4%BE%E0%A4%B8%E0%A4%BE%E0%A4%A4%E0%A5%80%E0%A4%B2_%E0%A4%B8%E0%A5%8B%E0%A4%A8%E0%A5%87%E0%A4%B0%E0%A5%80_%E0%A4%AA%E0%A4%BE%E0%A4%A8%E0%A5%87_(2000).pdf|sonari-pane-2000.pdf"
  "ACPR_Silver_Jubilee_Souvenir_(Volume_I).pdf|acpr-silver-jubilee-vol1.pdf"
  "Silver_Jubilee_Souvenir_(Volume_II).pdf|acpr-silver-jubilee-vol2.pdf"
  "Pathway_to_God_in_the_Vedas.pdf|pathway-to-god-in-the-vedas.pdf"
  "Critical_%26_Constructive_Aspects_of_Prof._R._D._Ranade%27s_Philosophy.pdf|critical-constructive-aspects.pdf"
  "Studies_In_Indian_Philosophy_(Edited_%26_Annotated).pdf|studies-in-indian-philosophy.pdf"
)

cd "$OUT"
SUMMARY=download-summary.txt
: > "$SUMMARY"

for entry in "${FILES[@]}"; do
  src="${entry%%|*}"
  dst="${entry##*|}"
  if [[ -f "$dst" ]]; then
    size=$(stat -f%z "$dst")
    echo "skip (exists): $dst ($size bytes)" | tee -a "$SUMMARY"
    continue
  fi
  url="https://commons.wikimedia.org/wiki/Special:FilePath/${src}"
  echo "↓ $dst"
  if curl -sSL -A "GurudevCorpus-ingest/1.0 (https://github.com/example)" -o "$dst" "$url"; then
    size=$(stat -f%z "$dst")
    if [[ "$size" -lt 10000 ]]; then
      echo "FAIL (too small, $size bytes): $dst" | tee -a "$SUMMARY"
      rm -f "$dst"
    else
      sha=$(shasum -a 256 "$dst" | awk '{print $1}')
      echo "OK: $dst ($size bytes) sha256=$sha" | tee -a "$SUMMARY"
    fi
  else
    echo "FAIL (curl): $dst" | tee -a "$SUMMARY"
  fi
done

echo "---" | tee -a "$SUMMARY"
echo "Total files in dir:" | tee -a "$SUMMARY"
ls -la "$OUT" | tee -a "$SUMMARY"
