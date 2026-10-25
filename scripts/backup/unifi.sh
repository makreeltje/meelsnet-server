#!/bin/bash
set -euo pipefail

CT_ID=105
SRC="/root/docker/appdata/unifi-os/var-lib-unifi/backup"
DST="/mnt/backups/app-data/unifi-os"
DATE=$(date +%Y-%m-%d)
RETENTION_DAYS=1

source /etc/default/backup-scripts
HC_URL="${HC_UNIFI:-}"

hc_ping() {
    local suffix="${1:-}"
    [[ -z "$HC_URL" ]] && return 0
    curl -fsS --retry 3 "${HC_URL}${suffix}" > /dev/null 2>&1 || true
}

fail() {
    logger -p user.err -t backup-unifi "ERROR: $*"
    hc_ping "/fail"
    exit 1
}

hc_ping "/start"

# Kopieer de nieuwste native UniFi OS .unf (autobackup of upgrade-backup).
# Geen tar van het volume: mongod en postgres draaien live in de container.
LATEST=$(pct exec "$CT_ID" -- bash -c "ls -t '${SRC}'/*.unf '${SRC}'/autobackup/*.unf 2>/dev/null | head -1") \
    || fail "Geen UniFi .unf backups gevonden in ${SRC}"

[[ -z "$LATEST" ]] && fail "Geen UniFi .unf backups gevonden in ${SRC}"

FILENAME=$(basename "$LATEST")

logger -t backup-unifi "Kopieer UniFi OS backup: $FILENAME"
pct exec "$CT_ID" -- bash -c "
    set -e
    mkdir -p '${DST}'
    cp '${LATEST}' '${DST}/${DATE}_${FILENAME}'
    find '${DST}' -name '*.unf' -mtime +${RETENTION_DAYS} -delete
" || fail "Kopiëren UniFi OS backup mislukt"

hc_ping
logger -t backup-unifi "UniFi OS backup completed: $FILENAME"
