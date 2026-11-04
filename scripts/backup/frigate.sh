#!/bin/bash
set -euo pipefail

CT_ID=103
SRC="/root/docker/appdata/frigate"
DST="/mnt/backups/app-data/frigate"
DATE=$(date +%Y-%m-%d)
RETENTION_DAYS=1

source /etc/default/backup-scripts
HC_URL="${HC_FRIGATE:-}"

hc_ping() {
    local suffix="${1:-}"
    [[ -z "$HC_URL" ]] && return 0
    curl -fsS --retry 3 "${HC_URL}${suffix}" > /dev/null 2>&1 || true
}

fail() {
    logger -p user.err -t backup-frigate "ERROR: $*"
    hc_ping "/fail"
    exit 1
}

hc_ping "/start"

logger -t backup-frigate "Tar Frigate config+DB: $SRC"
# Archive goes to a .tmp file first and is only moved into place after it
# verified OK, so a failed run never leaves a truncated *_frigate.tar.gz.
# --warning=no-file-changed: frigate.db is written to while we read it; tar
# would otherwise exit 1 for that. Any other tar error still fails.
pct exec "$CT_ID" -- bash -c "
    set -e
    OUT='${DST}/${DATE}_frigate.tar.gz'
    TMP=\"\$OUT.tmp\"
    trap 'rm -f \"\$TMP\"' EXIT
    mkdir -p '${DST}'
    tar --warning=no-file-changed -czf \"\$TMP\" -C '$(dirname "$SRC")' '$(basename "$SRC")'
    gzip -t \"\$TMP\"
    tar -tzf \"\$TMP\" > /dev/null
    mv -f \"\$TMP\" \"\$OUT\"
    find '${DST}' -name '*_frigate.tar.gz' -mtime +${RETENTION_DAYS} -delete
" || fail "Frigate tar failed"

hc_ping
logger -t backup-frigate "Frigate backup completed"
