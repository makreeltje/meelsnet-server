#!/bin/bash
# nextcloud.sh — Application-consistent backup: Nextcloud
# Laag 2 backup: maintenance mode + rsync data + config tar
# Draait op de Proxmox host als root via cron

set -euo pipefail

SCRIPT_NAME="nextcloud"
CT_ID=104
NC_CONTAINER="nextcloud"
DATA_SRC="/mnt/pve/data/cloud"
DATA_DST="/mnt/pve/data/backups/app-data/nextcloud/data"
CONFIG_DST_DIR="/mnt/backups/app-data/nextcloud"  # pad binnen CT 104
CONFIG_SRC="/root/docker/appdata/nextcloud/config"
CONFIG_RETENTION_DAYS=7
DATE=$(date +%Y-%m-%d)

# --- Healthchecks.io ---
source /etc/default/backup-scripts
HC_URL="${HC_NEXTCLOUD:-}"

hc_ping() {
    local suffix="${1:-}"
    [[ -z "$HC_URL" ]] && return 0
    curl -fsS --retry 3 "${HC_URL}${suffix}" > /dev/null 2>&1 || true
}

fail() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
    # Maintenance mode uitzetten als het aanstond
    pct exec "$CT_ID" -- docker exec "$NC_CONTAINER" \
        php occ maintenance:mode --off 2>/dev/null || true
    hc_ping "/fail"
    exit 1
}

run() {
    "$@" || fail "Command failed: $*"
}

# --- Start ---
hc_ping "/start"

# 1. Maintenance mode aan
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Nextcloud maintenance mode ON"
run pct exec "$CT_ID" -- docker exec "$NC_CONTAINER" \
    php occ maintenance:mode --on

# 2. Rsync data (direct op host, --delete spiegelt huidige staat)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Rsync data: $DATA_SRC -> $DATA_DST"
mkdir -p "$DATA_DST"
run rsync -a --delete \
    --exclude=".DS_Store" \
    --exclude="*._.DS_Store" \
    "$DATA_SRC/" "$DATA_DST/"

# 3. Config tar (via pct exec zodat rootfs bereikbaar is)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Config tar -> $CONFIG_DST_DIR"
pct exec "$CT_ID" -- bash -c "
    set -e
    mkdir -p '${CONFIG_DST_DIR}'
    tar czf '${CONFIG_DST_DIR}/${DATE}_config.tar.gz' -C /root/docker/appdata/nextcloud config
    find '${CONFIG_DST_DIR}' -name '*_config.tar.gz' -mtime +${CONFIG_RETENTION_DAYS} -delete
"  || fail "Config tar failed"

# 4. Maintenance mode uit
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Nextcloud maintenance mode OFF"
run pct exec "$CT_ID" -- docker exec "$NC_CONTAINER" \
    php occ maintenance:mode --off

# --- Done ---
hc_ping
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Nextcloud backup completed"
