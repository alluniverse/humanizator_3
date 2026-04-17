#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE=/tmp/uvicorn.pid
LOG_FILE=/tmp/uvicorn.log

# Kill old process
if [[ -f "$PID_FILE" ]]; then
  kill -- "-$(cat "$PID_FILE")" 2>/dev/null || true
  kill "$(cat "$PID_FILE")" 2>/dev/null || true
  rm -f "$PID_FILE"
fi
# Also kill any stray uvicorn for this project
pkill -f "$ROOT/.venv/bin/uvicorn api.main:app" 2>/dev/null || true
pkill -f "uvicorn api.main:app" 2>/dev/null || true
sleep 0.5

cd "$ROOT/backend"
source "$ROOT/.venv/bin/activate"
set -a; source "$ROOT/.env"; set +a
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"

setsid uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload \
  </dev/null >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
echo "Backend PID=$(cat $PID_FILE) → $LOG_FILE"
