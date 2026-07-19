#!/usr/bin/env bash
# Re-OCR the 15 garbled books with the LATEST Surya on the M4 (Apple Silicon / MPS).
# Run this from inside the AirDropped _surya_ocr_job/ folder:  bash run_ocr.sh
#
# Design: the slow OCR step writes cached JSON to out_raw/<work_id>/. The fast
# assemble.py step turns that into out/<work_id>.md. Re-running skips books whose
# JSON already exists, so it is safe to stop and resume.
set -uo pipefail
cd "$(dirname "$0")"

# Surya OCR-2's llamacpp backend spawns `llama-server` — installed via Homebrew
# under /opt/homebrew/bin on Apple Silicon. Neither `bash` nor a non-interactive
# `zsh -c` inherits that directory in $PATH by default, so the OCR step fails
# with "llama-server: command not found" partway through. Nityanemavali +
# Kakanchi runs hit this on 2026-07-18; pinning PATH here makes the script
# work stand-alone regardless of the caller's shell setup.
export PATH="/opt/homebrew/bin:${PATH}"

# 1) find a Python >= 3.10 (latest Surya needs it; system python3 on macOS may be too old)
PY=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)'; then
      PY=$(command -v "$c"); break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "Need Python >= 3.10. Install one:  brew install python@3.12"; exit 1
fi
echo "Using $PY ($("$PY" --version 2>&1))"

# 2) isolated venv + latest surya (pulls torch with MPS support on Apple Silicon)
[ -d venv ] || "$PY" -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q surya-ocr
./venv/bin/python -c "import torch; print('torch', torch.__version__, '| MPS available:', torch.backends.mps.is_available())"

# 3) OCR each PDF on the Apple GPU. Surya downloads its models on first run (needs internet).
export TORCH_DEVICE=mps
mkdir -p out_raw out
for pdf in pdfs/*.pdf; do
  wid=$(basename "$pdf" .pdf)
  if find "out_raw/$wid" -name results.json 2>/dev/null | grep -q .; then
    echo "== $wid : already OCR'd, skipping"; continue
  fi
  echo "== OCR $wid =="
  ./venv/bin/surya_ocr "$pdf" --output_dir "out_raw/$wid" \
    || echo "!! surya_ocr failed for $wid — check './venv/bin/surya_ocr --help' for current flags and adapt."
done

# 4) assemble JSON -> per-work markdown
./venv/bin/python assemble.py
echo
echo "OCR complete. Hand the ENTIRE out/ folder back to the main machine."
