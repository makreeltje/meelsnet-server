#!/bin/bash
set -euo pipefail

DATA_SRC="/mnt/pve/data/photos"
DATA_DST="/mnt/pve/data/backups/app-data/immich/library"

source /etc/default/backup-scripts
HC_URL="${HC_IMMICH:-}"

hc_ping() {
    local suffix="${1:-}"
    [[ -z "$HC_URL" ]] && return 0
    curl -fsS --retry 3 "${HC_URL}${suffix}" > /dev/null 2>&1 || true
}

fail() {
    logger -p user.err -t backup-immich "ERROR: $*"
    hc_ping "/fail"
    exit 1
}

run() {
    "$@" || fail "Command failed: $*"
}

hc_ping "/start"

logger -t backup-immich "Rsync Immich library: $DATA_SRC -> $DATA_DST"
mkdir -p "$DATA_DST"
run rsync -a --delete "$DATA_SRC/" "$DATA_DST/"

hc_ping
logger -t backup-immich "Immich backup completed"
