#!/usr/bin/env bash
# Restore PostgreSQL database from backup file

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/.env"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file.sql>"
    echo "Available backups:"
    ls -1t "$ROOT/backups/"*.sql 2>/dev/null | head -10 || echo "  (none)"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "Restoring from: $BACKUP_FILE"
echo "WARNING: This will overwrite existing data!"

# Restore into the running container
docker exec -i humanizator_3-db-1 psql \
    -U "${POSTGRES_USER:-humanizator}" \
    -d "${POSTGRES_DB:-humanizator}" \
    < "$BACKUP_FILE"

echo "Restore complete."
