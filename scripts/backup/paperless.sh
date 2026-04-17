#!/bin/bash
set -euo pipefail

SCRIPT_NAME="paperless"
CT_ID=104
CONTAINER="paperless"

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

hc_ping "/start"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Paperless document_exporter"
pct exec "$CT_ID" -- docker exec "$CONTAINER" \
    document_exporter ../export \
    || fail "document_exporter failed"

hc_ping
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Paperless export completed"
