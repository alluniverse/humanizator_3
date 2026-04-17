VENV    := .venv/bin
BACKEND := backend
LOGS    := /tmp

# ── Infra (Docker) ────────────────────────────────────────────────────────────

infra-up:
	docker compose up -d db redis
	@echo "Waiting for Postgres..."
	@until docker compose exec -T db pg_isready -U humanizator -d humanizator >/dev/null 2>&1; do sleep 1; done
	@echo "Postgres ready."

infra-stop:
	docker compose stop db redis

infra-down:
	docker compose down

# ── Migrations ────────────────────────────────────────────────────────────────

migrate:
	cd $(BACKEND) && source ../$(VENV)/activate && \
	  set -a && source ../.env && set +a && \
	  alembic upgrade head

# ── App processes ─────────────────────────────────────────────────────────────

backend-start:
	@pkill -f "uvicorn api.main:app" 2>/dev/null || true
	cd $(BACKEND) && source ../$(VENV)/activate && \
	  set -a && source ../.env && set +a && \
	  uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload \
	  > $(LOGS)/uvicorn.log 2>&1 & \
	echo "Backend PID=$$! → $(LOGS)/uvicorn.log"

worker-start:
	@pkill -f "celery.*async_tasks" 2>/dev/null || true
	cd $(BACKEND) && source ../$(VENV)/activate && \
	  set -a && source ../.env && set +a && \
	  celery -A async_tasks.celery_app worker --loglevel=info \
	  > $(LOGS)/celery.log 2>&1 & \
	echo "Celery PID=$$! → $(LOGS)/celery.log"

frontend-start:
	@pkill -f "next dev" 2>/dev/null || true
	cd frontend && npm run dev > $(LOGS)/nextdev.log 2>&1 & \
	echo "Frontend PID=$$! → $(LOGS)/nextdev.log"

# ── Composite targets ─────────────────────────────────────────────────────────

up: infra-up migrate backend-start worker-start frontend-start
	@echo ""
	@echo "All services started:"
	@echo "  Backend:  http://localhost:8000"
	@echo "  Frontend: http://localhost:3000"

restart: backend-start worker-start frontend-start
	@echo ""
	@echo "App processes restarted (infra untouched):"
	@echo "  Backend:  http://localhost:8000"
	@echo "  Frontend: http://localhost:3000"

stop:
	@pkill -f "uvicorn api.main:app" 2>/dev/null || true
	@pkill -f "celery.*async_tasks" 2>/dev/null || true
	@pkill -f "next dev" 2>/dev/null || true
	$(MAKE) infra-stop
	@echo "All services stopped."

# ── Logs ──────────────────────────────────────────────────────────────────────

logs-backend:
	tail -f $(LOGS)/uvicorn.log

logs-worker:
	tail -f $(LOGS)/celery.log

logs-frontend:
	tail -f $(LOGS)/nextdev.log

# ── Status ────────────────────────────────────────────────────────────────────

status:
	@echo "=== Docker ==="
	@docker compose ps db redis
	@echo ""
	@echo "=== Ports ==="
	@ss -tlnp | grep -E "8000|3000" || echo "(none)"
	@echo ""
	@echo "=== Processes ==="
	@pgrep -af "uvicorn|celery.*async_tasks|next dev" 2>/dev/null | grep -v grep || echo "(none)"

.PHONY: infra-up infra-stop infra-down migrate \
        backend-start worker-start frontend-start \
        up restart stop \
        logs-backend logs-worker logs-frontend status
