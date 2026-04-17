#!/bin/bash
set -euo pipefail

SCRIPT_NAME="homeassistant"
CT_ID=103
HA_BACKUPS="/root/docker/appdata/homeassistant/config/backups"
DST="/mnt/backups/app-data/homeassistant"
RETENTION_DAYS=7

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

hc_ping "/start"

# Zoek nieuwste HA backup .tar
LATEST=$(pct exec "$CT_ID" -- bash -c "ls -t '${HA_BACKUPS}'/*.tar 2>/dev/null | head -1") \
    || fail "Geen HA backups gevonden in ${HA_BACKUPS}"

[[ -z "$LATEST" ]] && fail "Geen HA backups gevonden in ${HA_BACKUPS}"

FILENAME=$(basename "$LATEST")

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Kopieer HA backup: $FILENAME"
pct exec "$CT_ID" -- bash -c "
    set -e
    mkdir -p '${DST}'
    cp '${LATEST}' '${DST}/${FILENAME}'
    find '${DST}' -name '*.tar' -mtime +${RETENTION_DAYS} -delete
" || fail "Kopiëren HA backup mislukt"

hc_ping
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Home Assistant backup completed: $FILENAME"
