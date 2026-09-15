#!/bin/bash
set -euo pipefail

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
    logger -p user.err -t backup-paperless "ERROR: $*"
    hc_ping "/fail"
    exit 1
}

hc_ping "/start"

logger -t backup-paperless "Running Paperless document_exporter"
pct exec "$CT_ID" -- docker exec "$CONTAINER" \
    document_exporter ../export \
    || fail "document_exporter failed"

hc_ping
logger -t backup-paperless "Paperless export completed"
