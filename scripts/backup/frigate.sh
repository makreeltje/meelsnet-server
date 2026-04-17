#!/bin/bash
set -euo pipefail

SCRIPT_NAME="frigate"
CT_ID=103
SRC="/root/docker/appdata/frigate"
DST="/mnt/backups/app-data/frigate"
DATE=$(date +%Y-%m-%d)
RETENTION_DAYS=7

source /etc/default/backup-scripts
HC_URL="${HC_FRIGATE:-}"

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

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Tar Frigate config+DB: $SRC"
pct exec "$CT_ID" -- bash -c "
    set -e
    mkdir -p '${DST}'
    tar czf '${DST}/${DATE}_frigate.tar.gz' -C '$(dirname "$SRC")' '$(basename "$SRC")'
    find '${DST}' -name '*_frigate.tar.gz' -mtime +${RETENTION_DAYS} -delete
" || fail "Frigate tar failed"

hc_ping
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Frigate backup completed"
