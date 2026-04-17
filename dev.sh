#!/usr/bin/env bash
# dev.sh — запуск всего dev-окружения
# Использование: ./dev.sh

set -e
cd "$(dirname "$0")"

echo "▶ Запуск Postgres + Redis..."
docker compose up -d db redis

echo "⏳ Ждём готовности БД..."
until docker compose exec -T db pg_isready -U humanizator -d humanizator >/dev/null 2>&1; do
  sleep 1
done

echo "▶ Миграции Alembic..."
(cd backend && source ../.venv/bin/activate && set -a && source ../.env && set +a && alembic upgrade head)

echo "▶ Запуск uvicorn (backend:8000)..."
(cd backend && source ../.venv/bin/activate && set -a && source ../.env && set +a && \
  uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/uvicorn.log 2>&1) &

echo "▶ Запуск Celery worker..."
(cd backend && source ../.venv/bin/activate && set -a && source ../.env && set +a && \
  celery -A async_tasks.celery_app worker --loglevel=info > /tmp/celery.log 2>&1) &

echo "▶ Запуск Next.js (frontend:3000)..."
(cd frontend && npm run dev > /tmp/nextdev.log 2>&1) &

echo ""
echo "✓ Всё запущено:"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  Логи: /tmp/uvicorn.log  /tmp/celery.log  /tmp/nextdev.log"
echo ""
echo "Для остановки: docker compose stop db redis && pkill -f 'uvicorn|celery|next'"
