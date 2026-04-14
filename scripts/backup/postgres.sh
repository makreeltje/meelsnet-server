#!/bin/bash
# postgres.sh — application-consistent dump van alle Postgres databases in CT 101
#
# Output: /mnt/pve/data/backups/databases/postgres/<date>_<dbname>.sql
# Local retention: 7 dagen (Backrest doet long-term naar Azure via 'databases' plan)
#
# Output policy: silent on success. Bij failure: full log via
# `logger -p user.err -t postgres-backup`. Bekijk failures met:
#   journalctl -t postgres-backup -p err
#
# Monitoring: pingt healthchecks.io (start/success/fail) als HC_POSTGRES_BACKUP
# is gedefinieerd in /etc/default/backup-scripts. Graceful degradation:
# ontbrekende file of lege variabele = geen pings, backup draait nog wel.

set -uo pipefail

# Healthchecks.io ping URL (optional, graceful degradation)
# Sourced from /etc/default/backup-scripts if present.
if [ -f /etc/default/backup-scripts ]; then
  # shellcheck disable=SC1091
  source /etc/default/backup-scripts
fi
HC_URL="${HC_POSTGRES_BACKUP:-}"

hc_ping() {
  local endpoint="${1:-}"  # "", "/start", or "/fail"
  local body="${2:-}"
  [ -z "$HC_URL" ] && return 0
  if [ -n "$body" ]; then
    curl -fsS -m 10 --retry 3 --data-raw "$body" -o /dev/null "${HC_URL}${endpoint}" || true
  else
    curl -fsS -m 10 --retry 3 -o /dev/null "${HC_URL}${endpoint}" || true
  fi
}

CTID=101
CONTAINER=postgres
BACKUP_DIR=/mnt/pve/data/backups/databases/postgres
DATE=$(date +%Y-%m-%d)
RETENTION_DAYS=7

LOG=$(mktemp)
cleanup() { rm -f "$LOG"; }
trap cleanup EXIT

fail() {
  local msg="$1"
  {
    echo "FAILED: $msg"
    echo "--- log ---"
    cat "$LOG" 2>/dev/null || true
  } | logger -p user.err -t postgres-backup
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

run_capture() {
  local desc="$1"
  local outfile="$2"
  shift 2
  echo ">>> $desc (-> $outfile)" >> "$LOG"
  if ! "$@" > "$outfile" 2>> "$LOG"; then
    fail "$desc"
  fi
}

hc_ping "/start"

mkdir -p "$BACKUP_DIR" || fail "mkdir $BACKUP_DIR"

# Auto-discover alle non-template databases
DBLIST=$(pct exec $CTID -- docker exec $CONTAINER \
  psql -U postgres -tAc \
  "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;" \
  2>> "$LOG") || fail "database discovery"

if [ -z "$DBLIST" ]; then
  echo "no databases discovered" >> "$LOG"
  fail "empty database list"
fi

mapfile -t DATABASES <<< "$DBLIST"
echo "Discovered ${#DATABASES[@]} databases: ${DATABASES[*]}" >> "$LOG"

# Globals
run_capture "dump globals" "$BACKUP_DIR/${DATE}_globals.sql" \
  pct exec $CTID -- docker exec $CONTAINER pg_dumpall -U postgres --globals-only

# Per-database dumps
for db in "${DATABASES[@]}"; do
  run_capture "dump $db" "$BACKUP_DIR/${DATE}_${db}.sql" \
    pct exec $CTID -- docker exec $CONTAINER pg_dump -U postgres --clean --if-exists "$db"
done

# Local retention
run "cleanup old dumps" \
  find "$BACKUP_DIR" -name "*.sql" -type f -mtime +$RETENTION_DAYS -delete

# Sanity check
EXPECTED_FILES=$((${#DATABASES[@]} + 1))
ACTUAL_FILES=$(find "$BACKUP_DIR" -name "${DATE}_*.sql" -type f -size +0c 2>/dev/null | wc -l)

if [ "$ACTUAL_FILES" -ne "$EXPECTED_FILES" ]; then
  echo "expected $EXPECTED_FILES files, found $ACTUAL_FILES" >> "$LOG"
  fail "file count mismatch"
fi

# Success: nothing to stdout, nothing to logger, cleanup trap removes $LOG
hc_ping
exit 0
