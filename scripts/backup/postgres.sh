#!/bin/bash
# postgres.sh — application-consistent dump van alle Postgres databases in CT 101
#
# Output: /mnt/pve/data/backups/databases/postgres/<date>_<dbname>.sql
# Local retention: 7 dagen (Backrest doet long-term naar Azure via 'databases' plan)
#
# Auto-discover: queries pg_database at runtime, filtert system templates weg.
# Nieuwe databases worden automatisch opgepakt — geen script-onderhoud bij nieuwe services.
#
# Run schedule: dagelijks 04:00 via /etc/cron.d/homelab-backups op Proxmox host.

set -euo pipefail

CTID=101
CONTAINER=postgres
BACKUP_DIR=/mnt/pve/data/backups/databases/postgres
DATE=$(date +%Y-%m-%d)
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

# Auto-discover alle non-template databases
mapfile -t DATABASES < <(
  pct exec $CTID -- docker exec $CONTAINER \
    psql -U postgres -tAc \
    "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;"
)

if [ ${#DATABASES[@]} -eq 0 ]; then
  echo "ERROR: no databases discovered — connection or permission issue?" >&2
  exit 1
fi

echo "Discovered ${#DATABASES[@]} databases: ${DATABASES[*]}"

# Globals (rollen, tablespaces, ACLs)
echo "Dumping globals..."
pct exec $CTID -- docker exec $CONTAINER \
  pg_dumpall -U postgres --globals-only \
  > "$BACKUP_DIR/${DATE}_globals.sql"

# Per-database dumps
for db in "${DATABASES[@]}"; do
  echo "Dumping $db..."
  pct exec $CTID -- docker exec $CONTAINER \
    pg_dump -U postgres --clean --if-exists "$db" \
    > "$BACKUP_DIR/${DATE}_${db}.sql"
done

# Local retention: verwijder dumps ouder dan RETENTION_DAYS
find "$BACKUP_DIR" -name "*.sql" -type f -mtime +$RETENTION_DAYS -delete

# Sanity check
EXPECTED_FILES=$((${#DATABASES[@]} + 1))
ACTUAL_FILES=$(find "$BACKUP_DIR" -name "${DATE}_*.sql" -type f -size +0c | wc -l)

if [ "$ACTUAL_FILES" -ne "$EXPECTED_FILES" ]; then
  echo "ERROR: expected $EXPECTED_FILES files, found $ACTUAL_FILES" >&2
  exit 1
fi

echo "OK: $ACTUAL_FILES dumps written to $BACKUP_DIR"