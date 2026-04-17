#!/usr/bin/env bash
# Reset database: drop all tables, recreate schema via alembic

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/.env"

echo "WARNING: This will DELETE ALL DATA in the database!"
echo "Database: ${POSTGRES_DB:-humanizator}"

# Drop and recreate database
docker exec humanizator_3-db-1 psql \
    -U "${POSTGRES_USER:-humanizator}" \
    -d postgres \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB:-humanizator};" \
    -c "CREATE DATABASE ${POSTGRES_DB:-humanizator};"

echo "Database recreated. Running migrations..."

# Run alembic migrations
cd "$ROOT/backend"
source "$ROOT/.venv/bin/activate"
set -a; source "$ROOT/.env"; set +a
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"

alembic upgrade head

echo "Database reset complete."
