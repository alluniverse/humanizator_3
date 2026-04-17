#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE=/tmp/celery.pid
LOG_FILE=/tmp/celery.log

if [[ -f "$PID_FILE" ]]; then
  kill "$(cat "$PID_FILE")" 2>/dev/null || true
  rm -f "$PID_FILE"
fi
pkill -f "$ROOT/.venv/bin/celery" 2>/dev/null || true
sleep 0.5

cd "$ROOT/backend"
source "$ROOT/.venv/bin/activate"
set -a; source "$ROOT/.env"; set +a

setsid celery -A async_tasks.celery_app worker --loglevel=info \
  </dev/null >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
echo "Celery PID=$(cat $PID_FILE) → $LOG_FILE"
