#!/bin/bash
# mariadb.sh — application-consistent dump van alle MariaDB databases in CT 101
#
# Output: /mnt/pve/data/backups/databases/mariadb/<date>_<dbname>.sql
# Local retention: 7 dagen (Backrest doet long-term naar Azure via 'databases' plan)
#
# Output policy: silent on success. Bij failure: full log via
# `logger -p user.err -t mariadb-backup`. Bekijk failures met:
#   journalctl -t mariadb-backup -p err
#
# Monitoring: pingt healthchecks.io (start/success/fail) als HC_MARIADB_BACKUP
# is gedefinieerd in /etc/default/backup-scripts. Graceful degradation:
# ontbrekende file of lege variabele = geen pings, backup draait nog wel.
#
# Auth: gebruikt $MARIADB_ROOT_PASSWORD env var die al in de container
# beschikbaar is. Geen wachtwoord op de host nodig.

set -uo pipefail

# Healthchecks.io ping URL (optional, graceful degradation)
if [ -f /etc/default/backup-scripts ]; then
  # shellcheck disable=SC1091
  source /etc/default/backup-scripts
fi
HC_URL="${HC_MARIADB_BACKUP:-}"

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
CONTAINER=mariadb
BACKUP_DIR=/mnt/pve/data/backups/databases/mariadb
DATE=$(date +%Y-%m-%d)
RETENTION_DAYS=7

# System databases to skip (information_schema, performance_schema, sys are
# virtual and cannot/should not be dumped). The 'mysql' database IS included
# because it contains user accounts, grants and privileges — the MariaDB
# equivalent of Postgres globals.
SKIP_DBS="information_schema|performance_schema|sys"

LOG=$(mktemp)
cleanup() { rm -f "$LOG"; }
trap cleanup EXIT

fail() {
  local msg="$1"
  {
    echo "FAILED: $msg"
    echo "--- log ---"
    cat "$LOG" 2>/dev/null || true
  } | logger -p user.err -t mariadb-backup
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

# Auto-discover alle databases, filter systeem-DBs
DBLIST=$(pct exec $CTID -- docker exec $CONTAINER bash -c \
  'mariadb -u root -p"$MARIADB_ROOT_PASSWORD" -BNe "SHOW DATABASES;"' \
  2>> "$LOG") || fail "database discovery"

# Filter system databases
DBLIST=$(echo "$DBLIST" | grep -Ev "^(${SKIP_DBS})$")

if [ -z "$DBLIST" ]; then
  echo "no databases discovered" >> "$LOG"
  fail "empty database list"
fi

mapfile -t DATABASES <<< "$DBLIST"
echo "Discovered ${#DATABASES[@]} databases: ${DATABASES[*]}" >> "$LOG"

# Per-database dumps
# --single-transaction: consistent snapshot without table locks (InnoDB)
# --routines: include stored procedures and functions
# --events: include scheduled events
# --triggers: include triggers (default, explicit for clarity)
# --quick: row-by-row retrieval for large tables (default in mariadb-dump)
for db in "${DATABASES[@]}"; do
  run_capture "dump $db" "$BACKUP_DIR/${DATE}_${db}.sql" \
    pct exec $CTID -- docker exec $CONTAINER bash -c \
    "mariadb-dump -u root -p\"\$MARIADB_ROOT_PASSWORD\" --single-transaction --routines --events --triggers \"$db\""
done

# Local retention
run "cleanup old dumps" \
  find "$BACKUP_DIR" -name "*.sql" -type f -mtime +$RETENTION_DAYS -delete

# Sanity check
EXPECTED_FILES=${#DATABASES[@]}
ACTUAL_FILES=$(find "$BACKUP_DIR" -name "${DATE}_*.sql" -type f -size +0c 2>/dev/null | wc -l)

if [ "$ACTUAL_FILES" -ne "$EXPECTED_FILES" ]; then
  echo "expected $EXPECTED_FILES files, found $ACTUAL_FILES" >> "$LOG"
  fail "file count mismatch"
fi

# Success: nothing to stdout, nothing to logger, cleanup trap removes $LOG
hc_ping
exit 0
