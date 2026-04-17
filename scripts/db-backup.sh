#!/usr/bin/env bash
# Backup PostgreSQL database to local file

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/.env"

BACKUP_DIR="$ROOT/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/humanizator_${TIMESTAMP}.sql"

mkdir -p "$BACKUP_DIR"

echo "Creating backup: $BACKUP_FILE"
docker exec humanizator_3-db-1 pg_dump \
    -U "${POSTGRES_USER:-humanizator}" \
    -d "${POSTGRES_DB:-humanizator}" \
    --no-owner --no-privileges \
    > "$BACKUP_FILE"

echo "Backup complete: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
