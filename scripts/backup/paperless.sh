#!/bin/bash
set -euo pipefail

SCRIPT_NAME="paperless"
DATA_SRC="/mnt/pve/data/paperless"
DATA_DST="/mnt/pve/data/backups/app-data/paperless/data"

source /etc/default/backup-scripts
HC_URL="${HC_PAPERLESS:-}"

hc_ping() {
    local suffix="${1:-}"
    [[ -z "$HC_URL" ]] && return 0
    curl -fsS --retry 3 "${HC_URL}${suffix}" > /dev/null 2>&1 || true
}

fail() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
    hc_ping "/fail"
    exit 1
}

run() {
    "$@" || fail "Command failed: $*"
}

hc_ping "/start"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Rsync Paperless data: $DATA_SRC -> $DATA_DST"
mkdir -p "$DATA_DST"
run rsync -a --delete "$DATA_SRC/" "$DATA_DST/"

hc_ping
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Paperless backup completed"
