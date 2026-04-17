#!/bin/bash
set -euo pipefail

SCRIPT_NAME="homeassistant"
CT_ID=103
SRC="/root/docker/appdata/homeassistant"
DST="/mnt/backups/app-data/homeassistant/data"

source /etc/default/backup-scripts
HC_URL="${HC_HOMEASSISTANT:-}"

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

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Rsync HA config via pct exec: $SRC -> $DST"
run pct exec "$CT_ID" -- bash -c "
    mkdir -p '${DST}'
    rsync -a --delete '${SRC}/' '${DST}/'
"

hc_ping
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Home Assistant backup completed"
