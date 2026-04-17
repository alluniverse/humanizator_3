#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE=/tmp/nextdev.pid
LOG_FILE=/tmp/nextdev.log

if [[ -f "$PID_FILE" ]]; then
  kill "$(cat "$PID_FILE")" 2>/dev/null || true
  rm -f "$PID_FILE"
fi
pkill -f "$ROOT/frontend/node_modules/.bin/next" 2>/dev/null || true
sleep 0.5

cd "$ROOT/frontend"

setsid npm run dev \
  </dev/null >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
echo "Frontend PID=$(cat $PID_FILE) → $LOG_FILE"
