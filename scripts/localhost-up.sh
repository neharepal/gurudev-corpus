#!/usr/bin/env bash
# localhost-up.sh — one command to check + revive both localhost services.
#
# Usage: bash scripts/localhost-up.sh
#
# What it does:
#   1. Checks backend (:8765/health).       Restarts if down.
#   2. Checks frontend (:3000).              Restarts (nuke + rebuild) if down.
#   3. Reports final status of both.
#
# Idempotent: run any time, in any state. If both are already up, no-op.
# If only one is down, it's brought back without touching the healthy one.
set -uo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URL="http://localhost:8765/health"
FRONTEND_URL="http://localhost:3000"

check_backend() {
  curl -sf --max-time 3 "$BACKEND_URL" >/dev/null 2>&1
}
check_frontend() {
  # Accept any 2xx or 3xx; frontend redirects to /gate when no cookie.
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$FRONTEND_URL" 2>/dev/null || echo "000")
  [[ "$code" =~ ^[23] ]]
}

start_backend() {
  echo "[localhost-up] backend down — restarting…"
  # Load API key from user's shell profile if not already exported.
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    # shellcheck disable=SC1090
    [[ -f "$HOME/.zshrc" ]] && source "$HOME/.zshrc" >/dev/null 2>&1
  fi
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "[localhost-up] ERROR: ANTHROPIC_API_KEY not set — cannot start backend"
    return 1
  fi
  lsof -ti tcp:8765 | xargs -r kill 2>/dev/null
  sleep 1
  cd "$REPO"
  ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" nohup "$REPO/.venv/bin/python" tools/server.py > /tmp/server.log 2>&1 &
  # Poll for ready — backend warmup is ~20-25s.
  for i in $(seq 1 40); do
    if check_backend; then
      echo "[localhost-up] backend ready ✓ (${i}s)"
      return 0
    fi
    sleep 1
  done
  echo "[localhost-up] backend did not become ready after 40s — tail /tmp/server.log"
  return 1
}

start_frontend() {
  echo "[localhost-up] frontend down — restarting…"
  bash "$REPO/chat-app/scripts/dev-restart.sh"
}

# ------------------------------------------------------------------
# main
echo "[localhost-up] checking backend + frontend…"

backend_ok=1
if check_backend; then
  echo "[localhost-up] backend ✓"
  backend_ok=0
else
  start_backend || true
  check_backend && backend_ok=0
fi

frontend_ok=1
if check_frontend; then
  echo "[localhost-up] frontend ✓"
  frontend_ok=0
else
  start_frontend
  check_frontend && frontend_ok=0
fi

echo
echo "[localhost-up] final: backend=$([[ $backend_ok -eq 0 ]] && echo up || echo DOWN)  frontend=$([[ $frontend_ok -eq 0 ]] && echo up || echo DOWN)"
[[ $backend_ok -eq 0 && $frontend_ok -eq 0 ]]
