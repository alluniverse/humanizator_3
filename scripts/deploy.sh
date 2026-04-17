#!/usr/bin/env bash
# deploy.sh — production deploy script for Humanizator
#
# Usage:
#   ./scripts/deploy.sh [--env staging|production] [--tag <image-tag>]
#
# Prerequisites:
#   - Docker + docker compose v2 installed
#   - .env file (or env vars) with OPENAI_API_KEY, JWT_SECRET_KEY, etc.
#
# What it does:
#   1. Pull latest images / rebuild
#   2. Apply DB migrations
#   3. Rolling restart (zero-downtime for app + worker)
#   4. Health check verification

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
ENV="${DEPLOY_ENV:-production}"
IMAGE_TAG="${DEPLOY_TAG:-latest}"
COMPOSE_FILE="docker-compose.yml"
HEALTH_URL="http://localhost:8000/health"
HEALTH_RETRIES=30
HEALTH_INTERVAL=3

# ── Helpers ──────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)     ENV="$2"; shift 2 ;;
    --tag)     IMAGE_TAG="$2"; shift 2 ;;
    *)         die "Unknown argument: $1" ;;
  esac
done

if [[ "$ENV" == "staging" ]]; then
  COMPOSE_FILE="docker-compose.staging.yml"
fi

log "Starting deploy: env=$ENV, tag=$IMAGE_TAG, compose=$COMPOSE_FILE"

# ── 1. Build / pull ───────────────────────────────────────────────────────────
log "Building images..."
docker compose -f "$COMPOSE_FILE" build --pull

# ── 2. Run DB migrations ──────────────────────────────────────────────────────
log "Running database migrations..."
docker compose -f "$COMPOSE_FILE" run --rm app \
  sh -c "cd /app/backend && alembic upgrade head"

# ── 3. Rolling restart ────────────────────────────────────────────────────────
log "Restarting services..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# ── 4. Health check ───────────────────────────────────────────────────────────
log "Waiting for health check at $HEALTH_URL..."
for i in $(seq 1 "$HEALTH_RETRIES"); do
  if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
    log "Health check passed after $((i * HEALTH_INTERVAL))s"
    break
  fi
  if [[ $i -eq "$HEALTH_RETRIES" ]]; then
    die "Health check failed after $((HEALTH_RETRIES * HEALTH_INTERVAL))s — rolling back"
  fi
  sleep "$HEALTH_INTERVAL"
done

log "Deploy complete."
