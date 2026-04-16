#!/bin/bash
# mongo.sh — application-consistent dump van alle MongoDB databases in CT 101
#
# Output: /mnt/pve/data/backups/databases/mongo/<date>_<dbname>.archive
# Local retention: 7 dagen (Backrest doet long-term naar Azure via 'databases' plan)
#
# Output policy: silent on success. Bij failure: full log via
# `logger -p user.err -t mongo-backup`. Bekijk failures met:
#   journalctl -t mongo-backup -p err
#
# Monitoring: pingt healthchecks.io (start/success/fail) als HC_MONGO_BACKUP
# is gedefinieerd in /etc/default/backup-scripts. Graceful degradation:
# ontbrekende file of lege variabele = geen pings, backup draait nog wel.
#
# Auth: gebruikt $MONGO_INITDB_ROOT_USERNAME en $MONGO_INITDB_ROOT_PASSWORD
# env vars die al in de container beschikbaar zijn. Geen secrets op de host.

set -uo pipefail

# Healthchecks.io ping URL (optional, graceful degradation)
if [ -f /etc/default/backup-scripts ]; then
  # shellcheck disable=SC1091
  source /etc/default/backup-scripts
fi
HC_URL="${HC_MONGO_BACKUP:-}"

hc_ping() {
  local endpoint="${1:-}"
  local body="${2:-}"
  [ -z "$HC_URL" ] && return 0
  if [ -n "$body" ]; then
    curl -fsS -m 10 --retry 3 --data-raw "$body" -o /dev/null "${HC_URL}${endpoint}" || true
  else
    curl -fsS -m 10 --retry 3 -o /dev/null "${HC_URL}${endpoint}" || true
  fi
}

CTID=101
CONTAINER=mongo
BACKUP_DIR=/mnt/pve/data/backups/databases/mongo
DATE=$(date +%Y-%m-%d)
RETENTION_DAYS=7

# System databases to skip. admin/config/local are MongoDB internals.
SKIP_DBS="admin|config|local"

LOG=$(mktemp)
cleanup() { rm -f "$LOG"; }
trap cleanup EXIT

fail() {
  local msg="$1"
  {
    echo "FAILED: $msg"
    echo "--- log ---"
    cat "$LOG" 2>/dev/null || true
  } | logger -p user.err -t mongo-backup
  hc_ping "/fail" "$(tail -n 50 "$LOG" 2>/dev/null || echo "$msg")"
  exit 1
}

run() {
  local desc="$1"
  shift
  echo ">>> $desc" >> "$LOG"
  if ! "$@" >> "$LOG" 2>&1; then
    fail "$desc"
  fi
}

hc_ping "/start"

mkdir -p "$BACKUP_DIR" || fail "mkdir $BACKUP_DIR"

# Auto-discover alle databases, filter systeem-DBs
DBLIST=$(pct exec $CTID -- docker exec $CONTAINER bash -c \
  'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "db.adminCommand({listDatabases:1}).databases.map(d=>d.name).join(\"\n\")"' \
  2>> "$LOG") || fail "database discovery"

# Filter system databases
DBLIST=$(echo "$DBLIST" | grep -Ev "^(${SKIP_DBS})$" | grep -v '^$')

if [ -z "$DBLIST" ]; then
  echo "no databases discovered" >> "$LOG"
  fail "empty database list"
fi

mapfile -t DATABASES <<< "$DBLIST"
echo "Discovered ${#DATABASES[@]} databases: ${DATABASES[*]}" >> "$LOG"

# Per-database dumps using --archive (single binary file per DB)
# No --gzip: Restic handles compression + dedup
for db in "${DATABASES[@]}"; do
  OUTFILE="$BACKUP_DIR/${DATE}_${db}.archive"
  echo ">>> dump $db (-> $OUTFILE)" >> "$LOG"
  if ! pct exec $CTID -- docker exec $CONTAINER bash -c \
    "mongodump -u \"\$MONGO_INITDB_ROOT_USERNAME\" -p \"\$MONGO_INITDB_ROOT_PASSWORD\" --authenticationDatabase admin --db \"$db\" --archive" \
    > "$OUTFILE" 2>> "$LOG"; then
    fail "dump $db"
  fi
done

# Local retention
run "cleanup old dumps" \
  find "$BACKUP_DIR" -name "*.archive" -type f -mtime +$RETENTION_DAYS -delete

# Sanity check
EXPECTED_FILES=${#DATABASES[@]}
ACTUAL_FILES=$(find "$BACKUP_DIR" -name "${DATE}_*.archive" -type f -size +0c 2>/dev/null | wc -l)

if [ "$ACTUAL_FILES" -ne "$EXPECTED_FILES" ]; then
  echo "expected $EXPECTED_FILES files, found $ACTUAL_FILES" >> "$LOG"
  fail "file count mismatch"
fi

# Success: nothing to stdout, nothing to logger, cleanup trap removes $LOG
hc_ping
exit 0
