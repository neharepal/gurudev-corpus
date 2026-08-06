#!/usr/bin/env bash
# dev-restart.sh — nuke the Next.js dev server and its cache, start a fresh one.
#
# Use this whenever localhost:3000 returns 500 with ENOENT on missing
# _buildManifest.js.tmp.* files, or after a batch of file edits leaves the
# dev cache wedged. Both symptoms come from incremental-bundler tmp-file
# races and clear cleanly with a full restart.
#
# Usage:  npm run dev:restart
#
# Runs the standard webpack dev server (npm run dev). If you want the
# experimental turbopack build instead, run `npm run dev:turbo` manually.
set -uo pipefail

# Move to chat-app root regardless of where this was invoked from.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[dev-restart] killing any running next-dev/next-server processes…"
pkill -f "next dev" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
sleep 2

# Wait for port 3000 to free up (in case a straggler holds it briefly).
for i in $(seq 1 10); do
  if ! lsof -ti tcp:3000 >/dev/null 2>&1; then break; fi
  sleep 1
done

if lsof -ti tcp:3000 >/dev/null 2>&1; then
  echo "[dev-restart] port 3000 still held after 10s — force-killing holder"
  lsof -ti tcp:3000 | xargs -r kill -9
  sleep 1
fi

echo "[dev-restart] purging .next cache…"
rm -rf "$ROOT/.next"

echo "[dev-restart] starting fresh dev server (webpack)…"
LOG_FILE="/tmp/next-dev.log"
: > "$LOG_FILE"
nohup "$ROOT/node_modules/.bin/next" dev > "$LOG_FILE" 2>&1 &
PID=$!
echo "[dev-restart] pid=$PID log=$LOG_FILE"

# Poll for Ready — up to 30s.
for i in $(seq 1 30); do
  if grep -q "Ready in" "$LOG_FILE" 2>/dev/null; then
    echo "[dev-restart] ready ✓ (took ${i}s)"
    exit 0
  fi
  sleep 1
done

echo "[dev-restart] warning: did not see 'Ready in' after 30s — tailing log:"
tail -20 "$LOG_FILE"
exit 1
