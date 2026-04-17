SHELL   := /bin/bash
CURDIR  := $(shell pwd)
VENV    := $(CURDIR)/.venv/bin
BACKEND := $(CURDIR)/backend
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
	cd $(BACKEND) && source $(VENV)/activate && \
	  set -a && source $(CURDIR)/.env && set +a && \
	  alembic upgrade head

# ── App processes ─────────────────────────────────────────────────────────────

backend-start:
	@bash scripts/start-backend.sh

worker-start:
	@bash scripts/start-worker.sh

frontend-start:
	@bash scripts/start-frontend.sh

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
	@kill $$(cat $(LOGS)/uvicorn.pid 2>/dev/null) 2>/dev/null || true
	@kill $$(cat $(LOGS)/celery.pid 2>/dev/null) 2>/dev/null || true
	@kill $$(cat $(LOGS)/nextdev.pid 2>/dev/null) 2>/dev/null || true
	@rm -f $(LOGS)/uvicorn.pid $(LOGS)/celery.pid $(LOGS)/nextdev.pid
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
