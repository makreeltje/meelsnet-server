# Homelab Master Guide

*Single source of truth. Replaces `IMPLEMENTATION_GUIDE.md` and `MULTI_LXC_MIGRATION.md`.*
*Hardware: Intel i5-8600K (6c), 32 GB RAM, Intel UHD 630, 2 TB NVMe + 72 TB RAID-5, single Proxmox host.*

---

## Progress Overview

| Phase | Title | Status |
|-------|-------|--------|
| 1 | Proxmox Preparation | ✅ Done |
| 2 | LXC Creation & Docker Install | ✅ Done |
| 3 | Storage Coupling (RAID bind mounts) | ✅ Done |
| 4 | GPU & USB Passthrough | ✅ Done (through §4.3) |
| 5 | Verify Passthrough & Networking | ← **You are here** |
| 6 | Restructure Compose Files | Pending |
| 7 | Compose Fragments (DRY) | Pending |
| 8 | Fix Known Issues | Pending |
| 9 | Health Checks | Pending |
| 10 | Traefik Hardening | Pending |
| 11 | Authentik Hardening | Pending |
| 12 | Secrets & CI/CD (GitHub Actions) | Pending |
| 13 | Traefik Cross-LXC Routing | Pending |
| 14 | Migrate Services | Pending |
| 15 | Azure Backup | Pending |
| 16 | Renovate (Automated Updates) | Pending |

---

## Reference: LXC Layout

| LXC | Name | vmbr1 IP | vCPU | RAM | Services |
|-----|------|----------|------|-----|----------|
| 101 | infra | 10.10.0.10 | 2 | 4 GB | Traefik, Authentik, Postgres, Redis, MongoDB |
| 102 | media | 10.10.0.20 | 4 | 8 GB | Plex, *arr, SABnzbd, qBit+VPN [GPU] |
| 103 | home | 10.10.0.30 | 2 | 4 GB | HA, Frigate, Z2M, Mosquitto, Node-RED [GPU+USB] |
| 104 | productivity | 10.10.0.40 | 2 | 6 GB | Immich, Paperless, Nextcloud, n8n, Backrest |
| 105 | network | 10.10.0.50 | 1 | 1 GB | Pi-hole, Unifi |
| 106 | monitoring | 10.10.0.60 | 2 | 3 GB | Grafana, Prometheus, Loki, Promtail, exporters |
| 107 | utilities | 10.10.0.70 | 1 | 1 GB | Spoolman, OmniTools, Firefly |

---

## Phase 1 — Proxmox Preparation ✅

*(Already done — NVMe storage pool, vmbr1 bridge, RAID-5 mounted on host, Debian template downloaded.)*

---

## Phase 2 — LXC Creation & Docker Install ✅

*(Already done — LXCs 102–107 created with correct CPU/RAM/network config, Docker installed in each.)*

---

## Phase 3 — Storage Coupling ✅

*(Already done — RAID-5 bind-mounted into LXC 102 and 104 via `pct set` mp entries.)*

---

## Phase 4 — GPU & USB Passthrough ✅

*(Already done — Intel UHD 630 passthrough configured for LXC 102 and 103, Zigbee USB passthrough configured for LXC 103.)*

---

## Phase 5 — Verify Passthrough & Networking

### 5.1 Verify GPU inside LXC 102 and 103

```bash
# On Proxmox host — enter each LXC
pct enter 102

# Inside LXC 102 — check GPU devices exist
ls /dev/dri/
# Expected: card0 (or card1) and renderD128

# Test GPU is actually usable (install vainfo)
apt install -y vainfo
vainfo
# Expected output includes: VA-API version 1.x, VAEntrypointVLD etc.
# If you see "error: cannot open display" that's fine — no display needed

# Check Plex can see it (after Plex is migrated)
# docker exec plex ls -la /dev/dri/

exit
```

Repeat for LXC 103:
```bash
pct enter 103
ls /dev/dri/         # card0/card1 + renderD128
ls /dev/ttyUSB0      # Zigbee dongle
exit
```

> If `/dev/ttyUSB0` is missing: unplug and replug the Zigbee dongle on the Proxmox host, then check again.

### 5.2 Verify render group GID inside privileged LXCs

For privileged LXCs, the host GID maps 1:1 into the LXC. Check it matches:

```bash
# On Proxmox host
getent group render   # e.g. render:x:993:
getent group video    # e.g. video:x:44:

# Inside LXC 102 — same GIDs should appear
pct enter 102
getent group render
getent group video
exit
```

If the group is missing inside the LXC, create it with the same GID:
```bash
# Inside the LXC
groupadd -g 993 render   # use actual GID from host
```

### 5.3 Verify vmbr1 inter-LXC networking

Start all LXCs first:
```bash
# On Proxmox host
for id in 102 103 104 105 106 107; do pct start $id; done
```

Then test connectivity:
```bash
# From LXC 102 — can it reach LXC 101 (infra)?
pct enter 102
ping -c 3 10.10.0.10
exit

# From LXC 102 — can it reach LXC 104 (productivity)?
pct enter 102
ping -c 3 10.10.0.40
exit

# From LXC 101 — can it reach all others?
pct enter 101
for ip in 10.10.0.20 10.10.0.30 10.10.0.40 10.10.0.50 10.10.0.60 10.10.0.70; do
  ping -c 1 -W 1 $ip && echo "  $ip OK" || echo "  $ip FAIL"
done
exit
```

All should return OK. If any fail, check that vmbr1 is configured in the LXC's `/etc/pve/lxc/<ID>.conf` — it should have a line like:
```
net1: name=eth1,bridge=vmbr1,ip=10.10.0.X/24
```

### 5.4 Test that eth1 is configured inside each LXC

```bash
pct enter 102
ip addr show eth1
# Should show: inet 10.10.0.20/24
exit
```

If `eth1` has no IP, configure it statically inside the LXC:
```bash
# Inside the LXC — add to /etc/network/interfaces
cat >> /etc/network/interfaces << 'EOF'

auto eth1
iface eth1 inet static
    address 10.10.0.20
    netmask 255.255.255.0
EOF
ifup eth1
```

---

## Phase 6 — Restructure Compose Files

**Why now:** Services currently live under `compose/server/` (22 files, no grouping). The new structure maps directly to LXCs — you must reorganize before migrating, so the files are already in the right place when you rsync them over.

### 6.1 Create new directories and move files

```bash
cd /root/docker/compose

# Create new directories
mkdir -p database home-automation productivity network utilities fragments

# --- DATABASE ---
mv server/compose.postgres.yml database/
mv server/compose.redis.yml database/
mv server/compose.mongo.yml database/
mv server/compose.adminer.yml database/

# --- HOME AUTOMATION ---
mv server/compose.home-assistant.yml home-automation/
mv server/compose.music-assistant.yml home-automation/
mv server/compose.zigbee2mqtt.yml home-automation/
mv server/compose.mosquitto.yml home-automation/
mv server/compose.nodered.yml home-automation/
mv server/compose.hyperion.yml home-automation/
mv server/compose.frigate.yml home-automation/

# --- PRODUCTIVITY ---
mv server/compose.immich.yml productivity/
mv server/compose.paperless.yml productivity/
mv server/compose.nextcloud.yml productivity/
mv server/compose.n8n.yml productivity/
mv server/compose.firefly.yml productivity/
mv server/compose.backrest.yml productivity/

# --- NETWORK ---
mv server/compose.unifi.yml network/
mv server/compose.pihole.yml network/

# --- UTILITIES ---
mv server/compose.omni-tools.yml utilities/
mv server/compose.spoolman.yml utilities/
mv server/compose.printer-calculator.yml utilities/

# Verify server/ is now empty
ls server/
# Should be empty — then remove it
rmdir server/
```

### 6.2 Update `compose.yml` include block

Replace the entire `include:` section in `/root/docker/compose.yml`:

```yaml
include:
  # =========================================================
  # REVERSE PROXY STACK (LXC 101: infra)
  # =========================================================
  - compose/reverse-proxy/compose.traefik.yml
  - compose/reverse-proxy/compose.oauth.yml
  - compose/reverse-proxy/compose.authentik.yml

  # =========================================================
  # DATABASE STACK (LXC 101: infra)
  # =========================================================
  - compose/database/compose.postgres.yml
  - compose/database/compose.redis.yml
  - compose/database/compose.mongo.yml
  - compose/database/compose.adminer.yml

  # =========================================================
  # MEDIA SERVER STACK (LXC 102: media)
  # =========================================================
  - compose/media-server/compose.plex.yml
  - compose/media-server/compose.jellyfin.yml
  - compose/media-server/compose.overseerr.yml
  - compose/media-server/compose.sonarr.yml
  - compose/media-server/compose.radarr.yml
  - compose/media-server/compose.prowlarr.yml
  - compose/media-server/compose.sabnzbd.yml
  - compose/media-server/compose.qbittorrent.yml
  - compose/media-server/compose.bazarr.yml
  - compose/media-server/compose.tautulli.yml
  - compose/media-server/compose.huntarr.yml
  - compose/media-server/compose.notifiarr.yml
  - compose/media-server/compose.profilarr.yml
  - compose/media-server/compose.maintainerr.yml
  - compose/media-server/compose.plex-rewind.yml
  - compose/media-server/compose.tracearr.yml
  - compose/media-server/compose.agregarr.yml
  - compose/media-server/compose.lingarr.yml
  - compose/media-server/compose.watchstate.yml

  # =========================================================
  # HOME AUTOMATION STACK (LXC 103: home)
  # =========================================================
  - compose/home-automation/compose.home-assistant.yml
  - compose/home-automation/compose.zigbee2mqtt.yml
  - compose/home-automation/compose.mosquitto.yml
  - compose/home-automation/compose.nodered.yml
  - compose/home-automation/compose.music-assistant.yml
  - compose/home-automation/compose.hyperion.yml
  - compose/home-automation/compose.frigate.yml

  # =========================================================
  # PRODUCTIVITY STACK (LXC 104: productivity)
  # =========================================================
  - compose/productivity/compose.immich.yml
  - compose/productivity/compose.paperless.yml
  - compose/productivity/compose.nextcloud.yml
  - compose/productivity/compose.n8n.yml
  - compose/productivity/compose.firefly.yml
  - compose/productivity/compose.backrest.yml

  # =========================================================
  # NETWORK STACK (LXC 105: network)
  # =========================================================
  - compose/network/compose.unifi.yml
  - compose/network/compose.pihole.yml

  # =========================================================
  # MONITORING STACK (LXC 106: monitoring)
  # =========================================================
  - compose/monitoring/compose.exporters.yml
  - compose/monitoring/compose.grafana.yml
  - compose/monitoring/compose.loki.yml
  - compose/monitoring/compose.promtail.yml
  - compose/monitoring/compose.prometheus.yml
  - compose/monitoring/compose.diun.yml

  # =========================================================
  # UTILITIES STACK (LXC 107: utilities)
  # =========================================================
  - compose/utilities/compose.omni-tools.yml
  - compose/utilities/compose.spoolman.yml
  - compose/utilities/compose.printer-calculator.yml
```

> Remove any entries for files that don't exist in your setup. Only include files that are actually present.

### 6.3 Update profiles in moved service files

Services moved out of `server/` need their profile updated. Open each moved file and replace `"other"` with the stack-appropriate profile:

| Directory | Profile |
|-----------|---------|
| `database/` | `["database", "all"]` |
| `home-automation/` | `["home", "all"]` |
| `productivity/` | `["productivity", "all"]` |
| `network/` | `["network", "all"]` |
| `utilities/` | `["utilities", "all"]` |

Example for `compose.postgres.yml`:
```yaml
# Before:
profiles: ["other", "database", "all"]

# After:
profiles: ["database", "all"]
```

### 6.4 Verify the restructure works

```bash
cd /root/docker

# Dry-run config validation — does NOT start containers
docker compose config --quiet && echo "Config valid!"

# Check for errors
docker compose config 2>&1 | grep -i error
```

Fix any path errors before continuing. The most common cause is a service file listed in `include:` that doesn't exist.

### 6.5 Commit

```bash
cd /root/docker
git add -A
git commit -m "refactor: split server/ into database, home-automation, productivity, network, utilities stacks"
git push
```

---

## Phase 7 — Compose Fragments (DRY)

Eliminate repeated `restart`, `networks`, `TZ`, `PUID/PGID` blocks across service files using `extends`.

### 7.1 Create `compose/fragments/common-service.yml`

```yaml
# compose/fragments/common-service.yml
# Shared service templates — referenced via 'extends' in service files.
# YAML anchors do NOT work across files; extends does.

services:

  # Base for non-LSIO containers (immich, authentik, frigate, exporters, etc.)
  common:
    restart: unless-stopped
    networks:
      - t3_proxy
    environment:
      TZ: ${TZ}

  # Base for LinuxServer.io containers (adds PUID/PGID)
  common-lsio:
    restart: unless-stopped
    networks:
      - t3_proxy
    environment:
      PUID: ${PUID}
      PGID: ${PGID}
      TZ: ${TZ}

  # Base for non-LSIO containers that depend on postgres + redis
  common-db:
    restart: unless-stopped
    networks:
      - t3_proxy
    environment:
      TZ: ${TZ}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  # Base for LSIO containers that depend on postgres + redis (rare)
  common-lsio-db:
    restart: unless-stopped
    networks:
      - t3_proxy
    environment:
      PUID: ${PUID}
      PGID: ${PGID}
      TZ: ${TZ}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  # Base for all exportarr Prometheus exporters
  exportarr-base:
    image: ghcr.io/onedr0p/exportarr:v2.0.1
    restart: unless-stopped
    profiles: ["monitoring", "all"]
    networks:
      - t3_proxy
    environment:
      TZ: ${TZ}
```

### 7.2 Refactor exporters (biggest win — removes 4× repeated config)

Replace `compose/monitoring/compose.exporters.yml` with:

```yaml
services:
  sonarr-exporter:
    extends:
      file: ../fragments/common-service.yml
      service: exportarr-base
    container_name: sonarr-exporter
    command: ["sonarr"]
    environment:
      PORT: "9707"
      URL: http://sonarr:8989
      APIKEY: $SONARR_API_KEY
    ports:
      - "9707:9707"

  radarr-exporter:
    extends:
      file: ../fragments/common-service.yml
      service: exportarr-base
    container_name: radarr-exporter
    command: ["radarr"]
    environment:
      PORT: "9708"
      URL: http://radarr:7878
      APIKEY: $RADARR_API_KEY
    ports:
      - "9708:9708"

  prowlarr-exporter:
    extends:
      file: ../fragments/common-service.yml
      service: exportarr-base
    container_name: prowlarr-exporter
    command: ["prowlarr"]
    environment:
      PORT: "9710"
      URL: http://prowlarr:9696
      APIKEY: $PROWLARR_API_KEY
    ports:
      - "9710:9710"

  sabnzbd-exporter:
    extends:
      file: ../fragments/common-service.yml
      service: exportarr-base
    container_name: sabnzbd-exporter
    command: ["sabnzbd"]
    environment:
      PORT: "9711"
      URL: http://sabnzbd:8080
      APIKEY: $SABNZBD_API_KEY
    ports:
      - "9711:9711"

  mosquitto-exporter:
    extends:
      file: ../fragments/common-service.yml
      service: common
    container_name: mosquitto-exporter
    image: sapcc/mosquitto-exporter:0.8.0
    profiles: ["monitoring", "all"]
    command:
      - --endpoint=tcp://mosquitto:1883
      - --user=$MOSQUITTO_USER
      - --pass=$MOSQUITTO_PASS
      - --client-id=mosquitto-exporter

  smartctl-exporter:
    extends:
      file: ../fragments/common-service.yml
      service: common
    container_name: smartctl-exporter
    image: prometheuscommunity/smartctl-exporter:v0.12.0
    profiles: ["monitoring", "all"]
    privileged: true
    user: root
    ports:
      - "9633:9633"
```

### 7.3 Apply extends to other service files

For every LSIO service (sonarr, radarr, bazarr, prowlarr, sabnzbd, tautulli, unifi, etc.), add `extends` and remove the duplicate boilerplate. Example for bazarr:

```yaml
# compose/media-server/compose.bazarr.yml
services:
  bazarr:
    extends:
      file: ../fragments/common-service.yml
      service: common-lsio          # ← replaces restart + networks + TZ + PUID/PGID
    container_name: bazarr
    image: lscr.io/linuxserver/bazarr:1.5.3
    profiles: ["media", "all"]
    volumes:
      - $CONF_DIR/bazarr/config:/config
      - $MEDIA_DIR/movies:/movies
      - $MEDIA_DIR/tv-shows:/tv
    expose:
      - 6767
    labels:
      - "traefik.enable=true"
      # ... rest of labels unchanged
```

For non-LSIO services, use `service: common` or `service: common-db`.

---

## Phase 8 — Fix Known Issues

### 8.1 Remove PUID/PGID from non-LSIO containers

These images ignore `PUID`/`PGID` — remove them (they create a false sense of user control):

| File | Service(s) |
|------|-----------|
| `reverse-proxy/compose.authentik.yml` | `authentik`, `authentik-worker` |
| `productivity/compose.immich.yml` | `immich`, `immich-machine-learning` |
| `home-automation/compose.frigate.yml` | `frigate` |
| `home-automation/compose.mosquitto.yml` | `mosquitto` |
| `database/compose.mongo.yml` | `mongo`, `mongo-express` |
| `monitoring/compose.grafana.yml` | `grafana` |
| `monitoring/compose.loki.yml` | `loki` |
| `monitoring/compose.promtail.yml` | `promtail` |
| `monitoring/compose.exporters.yml` | all exporters |
| `media-server/compose.seerr.yml` | `seerr` |
| `media-server/compose.watchstate.yml` | `watchstate` |
| `media-server/compose.tracearr.yml` | `tracearr` |

For containers that actually need a specific user, use Docker's `user:` directive:
```yaml
user: "${PUID}:${PGID}"
```

### 8.2 Fix expose + ports redundancy

**Immich** — keep `ports` only (mobile app connects directly, not through Traefik):
```yaml
# Remove: expose: 2283
ports:
  - "2283:2283"
```

**Frigate** — keep `ports` only:
```yaml
# Remove: expose: 5000
ports:
  - "5001:5000"     # Direct access
  - "8554:8554"     # RTSP
  - "8555:8555/tcp" # WebRTC
  - "8555:8555/udp"
```

### 8.3 Pin multi-container versions via env vars

Add to `.env` and `.env.example`:
```bash
IMMICH_VERSION=v2.5.3
AUTHENTIK_VERSION=2025.8.1
```

Update `compose/productivity/compose.immich.yml`:
```yaml
immich:
  image: ghcr.io/immich-app/immich-server:${IMMICH_VERSION}

immich-machine-learning:
  image: ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION}
```

Update `compose/reverse-proxy/compose.authentik.yml`:
```yaml
authentik:
  image: ghcr.io/goauthentik/server:${AUTHENTIK_VERSION}

authentik-worker:
  image: ghcr.io/goauthentik/server:${AUTHENTIK_VERSION}
```

### 8.4 Pin unversioned images

```yaml
# compose/monitoring/compose.exporters.yml
mosquitto-exporter:
  image: sapcc/mosquitto-exporter:0.8.0        # was: no version

smartctl-exporter:
  image: prometheuscommunity/smartctl-exporter:v0.12.0   # was: no version
```

Check Docker Hub for latest stable version before pinning.

### 8.5 Commit

```bash
git add -A
git commit -m "fix: PUID/PGID on non-LSIO images, pin versions, remove expose+ports redundancy"
git push
```

---

## Phase 9 — Health Checks

Add health checks to every service. This enables Docker to restart broken containers (not just stopped ones) and makes `depends_on: condition: service_healthy` work correctly.

### 9.1 Templates

**HTTP — curl available:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:<PORT>/<PATH>"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**HTTP — wget only (smaller images):**
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:<PORT>/<PATH>"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

**TCP port check (no HTTP endpoint):**
```yaml
healthcheck:
  test: ["CMD-SHELL", "nc -z localhost <PORT> || exit 1"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 10s
```

### 9.2 Health check per service

**Traefik** — enable ping in command flags first:
```yaml
# In compose.traefik.yml, add to command:
- --ping=true
- --ping.entrypoint=traefik
```
Then:
```yaml
healthcheck:
  test: ["CMD", "traefik", "healthcheck", "--ping"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 10s
```

**Authentik** (port 9000):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:9000/-/health/ready/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Authentik Worker:**
```yaml
healthcheck:
  test: ["CMD-SHELL", "ak healthcheck || exit 1"]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**OAuth (traefik-forward-auth):**
```yaml
healthcheck:
  test: ["CMD-SHELL", "nc -z localhost 4181 || exit 1"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 10s
```

**MongoDB:**
```yaml
healthcheck:
  test: ["CMD-SHELL", "mongosh --quiet --eval \"db.runCommand('ping').ok\" || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 5
  start_period: 30s
```

**Sonarr** (port 8989):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8989/api/v3/system/status?apikey=$SONARR_API_KEY"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Radarr** (port 7878):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:7878/api/v3/system/status?apikey=$RADARR_API_KEY"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Prowlarr** (port 9696):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:9696/api/v1/system/status?apikey=$PROWLARR_API_KEY"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**SABnzbd** (port 8080):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8080/api?mode=version&output=json&apikey=$SABNZBD_API_KEY"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**qBittorrent** (port 8080):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8080/api/v2/app/version"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s   # VPN takes time to connect
```

**Plex** (port 32400):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:32400/identity"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Jellyfin** (port 8096):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8096/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Overseerr** (port 5055):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:5055/api/v1/status"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Tautulli** (port 8181):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8181/status"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Bazarr** (port 6767):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:6767/api/system/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Maintainerr** (port 6246):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:6246/"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

**Notifiarr** (port 5454):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:5454/api/v1/healthcheck/"]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Watchstate** (port 8080):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:8080/"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

**Home Assistant** (port 8123):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8123/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Frigate** (port 5000):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:5000/api/stats"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Mosquitto** (MQTT on port 1883):
```yaml
healthcheck:
  test: ["CMD-SHELL", "mosquitto_sub -h localhost -t '$$SYS/#' -C 1 -u $MOSQUITTO_USER -P $MOSQUITTO_PASS -W 3 || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

**Zigbee2MQTT** (port 8080):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:8080/"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

**Node-RED** (port 1880):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:1880/"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

**Music Assistant** (port 8095):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8095/"]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Immich** (port 2283):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:2283/api/server-info/ping"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Immich Machine Learning** (port 3003):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:3003/ping"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Paperless** (port 8000):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8000/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Nextcloud** (port 80):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:80/status.php"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**n8n** (port 5678):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:5678/healthz"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

**Firefly** (port 8080):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8080/login"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Backrest** (port 9898):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:9898/"]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 20s
```

**Unifi** (HTTPS on port 8443):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "--insecure", "https://localhost:8443/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Pi-hole** (port 80):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:80/admin/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 20s
```

**Grafana** (port 3000):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:3000/api/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

**Prometheus** (port 9090):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:9090/-/healthy"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

**Loki** (port 3100):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:3100/ready"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

**Promtail** (port 9080):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:9080/ready"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

**OmniTools** (port 80):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:80/"]
  interval: 60s
  timeout: 5s
  retries: 3
  start_period: 10s
```

**Spoolman** (port 8000):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:8000/api/v1/info"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

**Adminer** (port 8080):
```yaml
healthcheck:
  test: ["CMD-SHELL", "nc -z localhost 8080 || exit 1"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 10s
```

### 9.3 Add MongoDB health check dependency to Unifi

Once MongoDB has a health check, update Unifi:
```yaml
# compose/network/compose.unifi.yml
depends_on:
  mongo:
    condition: service_healthy
```

### 9.4 Commit

```bash
git add -A
git commit -m "feat: add health checks to all services"
git push
```

---

## Phase 10 — Traefik Hardening

### 10.1 Security headers + rate limiting middleware

Create or update `appdata/traefik3/rules/$HOSTNAME/middlewares.yml`:

```yaml
http:
  middlewares:
    # Security headers — apply to all services
    security-headers:
      headers:
        customResponseHeaders:
          X-Robots-Tag: "none,noarchive,nosnippet,notranslate,noimageindex"
          Server: ""
          X-Powered-By: ""
        sslProxyHeaders:
          X-Forwarded-Proto: "https"
        hostsProxyHeaders:
          - "X-Forwarded-Host"
        customRequestHeaders:
          X-Forwarded-Proto: "https"
        contentTypeNosniff: true
        browserXssFilter: true
        referrerPolicy: "strict-origin-when-cross-origin"
        forceSTSHeader: true
        stsIncludeSubdomains: true
        stsPreload: true
        stsSeconds: 31536000
        frameDeny: true
        contentSecurityPolicy: "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; img-src 'self' data: blob:; worker-src blob:;"

    # General rate limit
    rate-limit:
      rateLimit:
        average: 100
        burst: 50
        period: 1s

    # Stricter rate limit for auth endpoints
    rate-limit-auth:
      rateLimit:
        average: 10
        burst: 20
        period: 1m

    # Local-only allowlist — for admin services (Adminer, Prometheus)
    local-only:
      ipAllowList:
        sourceRange:
          - "127.0.0.1/32"
          - "10.0.0.0/8"
          - "192.168.0.0/16"
          - "172.16.0.0/12"

    # Authentik forward auth
    middlewares-authentik:
      forwardAuth:
        address: "http://authentik:9000/outpost.goauthentik.io/auth/traefik"
        trustForwardHeader: true
        authResponseHeaders:
          - X-authentik-username
          - X-authentik-groups
          - X-authentik-email
          - X-authentik-name
          - X-authentik-uid
          - X-authentik-jwt
          - X-authentik-meta-jwks
          - X-authentik-meta-outpost
          - X-authentik-meta-provider
          - X-authentik-meta-app
          - X-authentik-meta-version

    # Nextcloud CalDAV/CardDAV redirect
    nextcloud-redirect:
      redirectRegex:
        permanent: true
        regex: "https://(.*)/.well-known/(?:card|cal)dav"
        replacement: "https://${1}/remote.php/dav"
```

### 10.2 Update middleware chains

Update `appdata/traefik3/rules/$HOSTNAME/middlewares-chains.yml`:

```yaml
http:
  middlewares:
    chain-no-auth:
      chain:
        middlewares:
          - security-headers
          - rate-limit

    chain-oauth:
      chain:
        middlewares:
          - security-headers
          - rate-limit
          - oauth@docker

    chain-authentik:
      chain:
        middlewares:
          - security-headers
          - rate-limit
          - middlewares-authentik@file

    chain-local-only:
      chain:
        middlewares:
          - security-headers
          - local-only

    chain-nextcloud:
      chain:
        middlewares:
          - security-headers
          - nextcloud-redirect
```

### 10.3 TLS hardening

Create `appdata/traefik3/rules/$HOSTNAME/tls-opts.yml`:

```yaml
tls:
  options:
    tls-opts:
      minVersion: VersionTLS12
      cipherSuites:
        - TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256
        - TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
        - TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384
        - TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
        - TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305
        - TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305
      sslStrict: true
      curvePreferences:
        - CurveP521
        - CurveP384
```

Add to Traefik command flags in `compose/reverse-proxy/compose.traefik.yml`:
```yaml
command:
  # ... existing flags ...
  - --ping=true
  - --ping.entrypoint=traefik
  - --accessLog.filters.statusCodes=400-599
  - --entrypoints.websecure.http.tls.options=tls-opts@file
```

### 10.4 Restrict admin services to local-only

Update Adminer and Prometheus labels:
```yaml
# compose/database/compose.adminer.yml
labels:
  - "traefik.http.routers.adminer-rtr.middlewares=chain-local-only@file"

# compose/monitoring/compose.prometheus.yml
labels:
  - "traefik.http.routers.prometheus-rtr.middlewares=chain-local-only@file"
```

---

## Phase 11 — Authentik Hardening

Replace `compose/reverse-proxy/compose.authentik.yml` with this corrected version:

```yaml
services:
  authentik:
    container_name: authentik
    image: ghcr.io/goauthentik/server:${AUTHENTIK_VERSION}
    restart: unless-stopped
    profiles: ["reverse-proxy", "all"]
    networks:
      - t3_proxy
    command: server
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      # No PUID/PGID — authentik is not a LinuxServer.io image
      TZ: ${TZ}
      AUTHENTIK_POSTGRESQL__HOST: postgres
      AUTHENTIK_POSTGRESQL__NAME: ${AUTHENTIK_DBNAME}
      AUTHENTIK_POSTGRESQL__PASSWORD: ${AUTHENTIK_DBPASS}
      AUTHENTIK_POSTGRESQL__USER: ${AUTHENTIK_DBUSER}
      AUTHENTIK_REDIS__HOST: redis
      AUTHENTIK_SECRET_KEY: ${AUTHENTIK_SECRET}
      AUTHENTIK_ERROR_REPORTING__ENABLED: "false"
      AUTHENTIK_LOG_LEVEL: info
    volumes:
      - $CONF_DIR/authentik/media:/media
      - $CONF_DIR/authentik/custom-templates:/templates
    expose:
      - 9000
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9000/-/health/ready/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.authentik-rtr.entrypoints=websecure"
      - "traefik.http.routers.authentik-rtr.rule=Host(`authentik.$DOMAINNAME_1`)"
      - "traefik.http.routers.authentik-rtr.middlewares=chain-no-auth@file"
      - "traefik.http.routers.authentik-rtr.service=authentik-svc"
      - "traefik.http.services.authentik-svc.loadbalancer.server.port=9000"

  authentik-worker:
    container_name: authentik-worker
    image: ghcr.io/goauthentik/server:${AUTHENTIK_VERSION}
    restart: unless-stopped
    profiles: ["reverse-proxy", "all"]
    user: root    # Intentional — worker needs Docker socket access
    networks:
      - t3_proxy
    command: worker
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      authentik:
        condition: service_healthy
    environment:
      TZ: ${TZ}
      AUTHENTIK_POSTGRESQL__HOST: postgres
      AUTHENTIK_POSTGRESQL__NAME: ${AUTHENTIK_DBNAME}
      AUTHENTIK_POSTGRESQL__PASSWORD: ${AUTHENTIK_DBPASS}
      AUTHENTIK_POSTGRESQL__USER: ${AUTHENTIK_DBUSER}
      AUTHENTIK_REDIS__HOST: redis
      AUTHENTIK_SECRET_KEY: ${AUTHENTIK_SECRET}
      AUTHENTIK_ERROR_REPORTING__ENABLED: "false"
      AUTHENTIK_LOG_LEVEL: info
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - $CONF_DIR/authentik/certs:/certs
      - $CONF_DIR/authentik/media:/media
      - $CONF_DIR/authentik/custom-templates:/templates
    healthcheck:
      test: ["CMD-SHELL", "ak healthcheck || exit 1"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s
```

### Commit phases 8–11

```bash
git add -A
git commit -m "feat: Traefik hardening, Authentik fixes, security headers, TLS options"
git push
```

---

## Phase 12 — Secrets & CI/CD (GitHub Actions)

**Goal:** No secrets ever touch Git. All secrets live in GitHub Actions Secrets and are written to each LXC's `.env` file at deploy time.

### 12.1 Update .gitignore

```gitignore
# Secrets and environment — NEVER commit
.env
secrets/

# Application data
appdata/

# Logs
logs/
*.log

# Traefik certificates
appdata/traefik3/acme/

# Backups
*.bak
*.tmp
```

### 12.2 Create `.env.example`

This file IS committed — it documents every variable name with no values:

```bash
cat > /root/docker/.env.example << 'EOF'
# ============================================================
# PATHS
# ============================================================
DOCKER_DIR=/root/docker
CONF_DIR=/root/docker/appdata
MEDIA_DIR=/mnt/media
PHOTOS_DIR=/mnt/photos
LOG_DIR=/root/docker/logs

# ============================================================
# USER & TIMEZONE
# ============================================================
PUID=1000
PGID=1000
TZ=Europe/Amsterdam

# ============================================================
# NETWORKING
# ============================================================
DOMAINNAME_1=example.com
HOSTNAME=docker
CLOUDFLARE_IPS=173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,104.24.0.0/14,172.64.0.0/13,131.0.72.0/22
LOCAL_IPS=127.0.0.1/32,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12

# ============================================================
# TRAEFIK
# ============================================================
TRAEFIK_AUTH_BYPASS_KEY=   # openssl rand -hex 32

# ============================================================
# DATABASES
# ============================================================
PSQL_DBUSER=postgres
PSQL_DBPASS=               # openssl rand -base64 32
AUTHENTIK_DBNAME=authentik
AUTHENTIK_DBUSER=authentik
AUTHENTIK_DBPASS=
PAPERLESS_DBNAME=paperless
PAPERLESS_DBUSER=paperless
PAPERLESS_DBPASS=
NEXTCLOUD_DBNAME=nextcloud
NEXTCLOUD_DBUSER=nextcloud
NEXTCLOUD_DBPASS=
N8N_DBNAME=n8n
N8N_DBUSER=n8n
N8N_DBPASS=
MONGO_ROOT_USER=admin
MONGO_ROOT_PASS=

# ============================================================
# AUTHENTIK
# ============================================================
AUTHENTIK_SECRET=          # openssl rand -hex 50
# renovate: datasource=docker depName=ghcr.io/goauthentik/server
AUTHENTIK_VERSION=2025.8.1

# ============================================================
# IMMICH
# ============================================================
# renovate: datasource=docker depName=ghcr.io/immich-app/immich-server
IMMICH_VERSION=v2.5.3

# ============================================================
# MEDIA
# ============================================================
PLEX_ADVERTISE_IP=         # https://<your-ip>:32400/
VPN_USER=
VPN_PASS=
VPN_PROV=
VPN_INPUT_PORTS=
VPN_OUTPUT_PORTS=

# ============================================================
# ARR API KEYS
# ============================================================
SONARR_API_KEY=
RADARR_API_KEY=
PROWLARR_API_KEY=
SABNZBD_API_KEY=

# ============================================================
# HOME AUTOMATION
# ============================================================
MOSQUITTO_USER=
MOSQUITTO_PASS=
FRIGATE_RTSP_PASSWORD=

# ============================================================
# NETWORK
# ============================================================
PIHOLE_WEB_PASS=

# ============================================================
# PRODUCTIVITY
# ============================================================
NEXTAUTH_SECRET=           # openssl rand -hex 32

# ============================================================
# NOTIFICATIONS
# ============================================================
DN_API_KEY=

# ============================================================
# AZURE BACKUP (Phase 15)
# ============================================================
AZURE_ACCOUNT_NAME=
AZURE_ACCOUNT_KEY=
AZURE_BACKUP_CONTAINER=homelab-backups
EOF
```

### 12.3 Create GitHub Environments

Go to your GitHub repo → **Settings → Environments** → create one per LXC:

| Environment | LXC |
|-------------|-----|
| `prod-infra` | 101 |
| `prod-media` | 102 |
| `prod-home` | 103 |
| `prod-productivity` | 104 |
| `prod-network` | 105 |
| `prod-monitoring` | 106 |
| `prod-utilities` | 107 |

### 12.4 Generate secrets and add to GitHub

Generate values locally:
```bash
openssl rand -hex 32    # → TRAEFIK_AUTH_BYPASS_KEY, NEXTAUTH_SECRET
openssl rand -base64 32 # → PSQL_DBPASS, AUTHENTIK_DBPASS, etc.
openssl rand -hex 50    # → AUTHENTIK_SECRET
```

**Repository-level secrets** (Settings → Secrets and variables → Actions → New repository secret):
```
PROXMOX_SSH_HOST          = <Proxmox Tailscale IP or MagicDNS hostname>
PROXMOX_SSH_KEY           = <private deploy key — see §12.5>
TS_OAUTH_CLIENT_ID        = <Tailscale OAuth client ID — see §12.5>
TS_OAUTH_SECRET           = <Tailscale OAuth client secret — see §12.5>
```

These are repo-level (not per-environment) because all deploy jobs SSH to the same Proxmox host. The per-environment secrets below are for service-specific values only.

SSH happens over Tailscale — no port is exposed to the public internet. The GitHub Actions runner joins your tailnet ephemerally for the duration of each workflow run via the `tailscale/github-action` step.

Add to each GitHub environment:

**`prod-infra` secrets:**
```
TRAEFIK_AUTH_BYPASS_KEY
PSQL_DBPASS
AUTHENTIK_SECRET
AUTHENTIK_DBPASS
MONGO_ROOT_PASS
CF_DNS_API_TOKEN        (written to secrets/cf_dns_api_token file)
BASIC_AUTH_CREDS        (written to secrets/basic_auth_credentials)
OAUTH_SECRET            (written to secrets/oauth_secrets)
```

**`prod-media` secrets:**
```
TRAEFIK_AUTH_BYPASS_KEY
PLEX_CLAIM_TOKEN        (written to secrets/plex_claim_token)
VPN_USER
VPN_PASS
VPN_PROV
SONARR_API_KEY
RADARR_API_KEY
PROWLARR_API_KEY
SABNZBD_API_KEY
PLEX_ADVERTISE_IP
```

**`prod-home` secrets:**
```
TRAEFIK_AUTH_BYPASS_KEY
FRIGATE_RTSP_PASSWORD
MOSQUITTO_USER
MOSQUITTO_PASS
```

**`prod-productivity` secrets:**
```
TRAEFIK_AUTH_BYPASS_KEY
IMMICH_VERSION
PAPERLESS_DBPASS
NEXTCLOUD_DBPASS
N8N_DBPASS
NEXTAUTH_SECRET
AZURE_ACCOUNT_KEY
```

**`prod-network` secrets:**
```
PIHOLE_WEB_PASS
```

**`prod-monitoring` secrets:**
```
SONARR_API_KEY
RADARR_API_KEY
PROWLARR_API_KEY
SABNZBD_API_KEY
MOSQUITTO_USER
MOSQUITTO_PASS
```

**`prod-utilities` secrets:**
```
(none — add here if utilities services ever need secrets)
```

### 12.5 Set up SSH deploy key and Tailscale access

GitHub Actions SSHs into the **Proxmox host only** — not individual LXCs. The connection goes over **Tailscale**, so no port is ever exposed to the public internet. Each workflow run joins your tailnet ephemerally via a Tailscale OAuth client, SSHs to Proxmox's Tailscale IP, then uses `pct push`/`pct exec` to operate inside LXCs.

**Step 1 — SSH keypair:**
```bash
# One keypair for Proxmox — not per LXC
ssh-keygen -t ed25519 -C "github-deploy-proxmox" -f ~/.ssh/deploy_proxmox -N ""

# Add public key to the Proxmox host's authorized_keys
ssh root@<proxmox-tailscale-ip> "cat >> ~/.ssh/authorized_keys" < ~/.ssh/deploy_proxmox.pub

# Add to GitHub repo-level secrets:
#   PROXMOX_SSH_HOST = <proxmox tailscale IP or MagicDNS name, e.g. proxmox.your-tailnet.ts.net>
#   PROXMOX_SSH_KEY  = (contents of deploy_proxmox private key)
cat ~/.ssh/deploy_proxmox   # copy into GitHub → repo secrets → PROXMOX_SSH_KEY
```

**Step 2 — Tailscale OAuth client** (allows runners to join your tailnet without a pre-generated key):

1. Go to [Tailscale admin → Settings → OAuth clients](https://login.tailscale.com/admin/settings/oauth) → Generate new client
2. Scope: `devices:write` (so it can create ephemeral nodes)
3. Tag it `tag:ci` (create the tag in your ACL first if it doesn't exist)
4. Add to GitHub repo-level secrets:
   - `TS_OAUTH_CLIENT_ID` — the client ID
   - `TS_OAUTH_SECRET` — the client secret

Each workflow run will spin up an ephemeral Tailscale node tagged `tag:ci`, use it to SSH into Proxmox, then automatically remove it when the job completes.

### 12.6 Create deployment workflow

**Design:** The GitHub Actions runner is the only place that ever holds the full repository. It packages a minimal compose slice for each LXC, writes `.env` and secret files locally, and `scp`s everything to Proxmox. Proxmox then uses `pct push` to inject files into each LXC and `pct exec` to run Docker Compose. **No git is needed inside any LXC.**

Per-LXC compose slices (only these directories are transferred to each LXC):

| LXC | Directories in tarball |
|-----|------------------------|
| 101 infra | `lxc/infra/` + `compose/reverse-proxy/` + `compose/database/` |
| 102 media | `lxc/media/` + `compose/media-server/` |
| 103 home | `lxc/home/` + `compose/home-automation/` |
| 104 productivity | `lxc/productivity/` + `compose/productivity/` |
| 105 network | `lxc/network/` + `compose/network/` |
| 106 monitoring | `lxc/monitoring/` + `compose/monitoring/` |
| 107 utilities | `lxc/utilities/` + `compose/utilities/` |

Each deploy job has two steps after checkout + Tailscale + SSH setup:

1. **Build deploy package** (runs on the runner): write `.env`, write Docker secret files, `tar` the compose slice, `scp` everything to Proxmox `/tmp/`
2. **Deploy into LXC** (runs on Proxmox over SSH): `pct push` files into the LXC, `pct exec` to extract the tarball and run `docker compose up`

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to LXCs

on:
  push:
    branches: [main]
    paths:
      - 'compose/**'
      - 'lxc/**'
      - 'compose.yml'
      - 'scripts/**'
  workflow_dispatch:
    inputs:
      target:
        description: 'Target LXC (all / infra / media / home / productivity / network / monitoring / utilities)'
        default: 'all'
        required: true

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate compose syntax
        run: |
          sudo apt-get install -y docker-compose-plugin
          cp .env.example .env
          sed -i 's/=$/=dummy/g' .env
          docker compose config --quiet && echo "Compose config valid"

  deploy-infra:
    needs: validate
    if: ${{ github.event.inputs.target == 'all' || github.event.inputs.target == 'infra' || github.event_name == 'push' }}
    runs-on: ubuntu-latest
    environment: prod-infra
    steps:
      - uses: actions/checkout@v4

      - name: Connect to Tailscale
        uses: tailscale/github-action@v2
        with:
          oauth-client-id: ${{ secrets.TS_OAUTH_CLIENT_ID }}
          oauth-secret: ${{ secrets.TS_OAUTH_SECRET }}
          tags: tag:ci

      - name: Set up SSH key
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.PROXMOX_SSH_KEY }}

      - name: Trust Proxmox host key
        run: ssh-keyscan -H "${{ secrets.PROXMOX_SSH_HOST }}" >> ~/.ssh/known_hosts

      - name: Build deploy package for LXC 101 (infra)
        env:
          TRAEFIK_AUTH_BYPASS_KEY: ${{ secrets.TRAEFIK_AUTH_BYPASS_KEY }}
          PSQL_DBPASS: ${{ secrets.PSQL_DBPASS }}
          AUTHENTIK_SECRET: ${{ secrets.AUTHENTIK_SECRET }}
          AUTHENTIK_DBPASS: ${{ secrets.AUTHENTIK_DBPASS }}
          MONGO_ROOT_PASS: ${{ secrets.MONGO_ROOT_PASS }}
          CF_DNS_API_TOKEN: ${{ secrets.CF_DNS_API_TOKEN }}
          BASIC_AUTH_CREDS: ${{ secrets.BASIC_AUTH_CREDS }}
          OAUTH_SECRET: ${{ secrets.OAUTH_SECRET }}
        run: |
          # Write .env locally on the runner — secrets expand from env: block above
          cat > /tmp/lxc101.env << EOF
          DOCKER_DIR=/root/docker
          CONF_DIR=/root/docker/appdata
          LOG_DIR=/root/docker/logs
          TZ=Europe/Amsterdam
          PUID=1000
          PGID=1000
          DOMAINNAME_1=example.com
          HOSTNAME=infra
          AUTHENTIK_VERSION=2025.8.1
          TRAEFIK_AUTH_BYPASS_KEY=${TRAEFIK_AUTH_BYPASS_KEY}
          PSQL_DBUSER=postgres
          PSQL_DBPASS=${PSQL_DBPASS}
          AUTHENTIK_DBNAME=authentik
          AUTHENTIK_DBUSER=authentik
          AUTHENTIK_DBPASS=${AUTHENTIK_DBPASS}
          AUTHENTIK_SECRET=${AUTHENTIK_SECRET}
          MONGO_ROOT_USER=admin
          MONGO_ROOT_PASS=${MONGO_ROOT_PASS}
          EOF

          # Write Docker secret files locally on the runner
          printf '%s' "${CF_DNS_API_TOKEN}" > /tmp/lxc101.cf_dns_api_token
          printf '%s' "${BASIC_AUTH_CREDS}"  > /tmp/lxc101.basic_auth_credentials
          printf '%s' "${OAUTH_SECRET}"       > /tmp/lxc101.oauth_secrets

          # Package only the compose slice this LXC needs — not the whole repo
          tar -czf /tmp/lxc101-compose.tar.gz \
            lxc/infra/ \
            compose/reverse-proxy/ \
            compose/database/

          # Transfer all files to Proxmox in one scp call
          scp /tmp/lxc101.env \
              /tmp/lxc101.cf_dns_api_token \
              /tmp/lxc101.basic_auth_credentials \
              /tmp/lxc101.oauth_secrets \
              /tmp/lxc101-compose.tar.gz \
              root@${{ secrets.PROXMOX_SSH_HOST }}:/tmp/

      - name: Deploy into LXC 101 via Proxmox
        run: |
          ssh root@${{ secrets.PROXMOX_SSH_HOST }} << 'SCRIPT'
          set -e

          # Push .env and secrets into LXC 101
          pct push 101 /tmp/lxc101.env /root/docker/.env
          pct exec 101 -- mkdir -p /root/docker/secrets
          pct push 101 /tmp/lxc101.cf_dns_api_token       /root/docker/secrets/cf_dns_api_token
          pct push 101 /tmp/lxc101.basic_auth_credentials /root/docker/secrets/basic_auth_credentials
          pct push 101 /tmp/lxc101.oauth_secrets          /root/docker/secrets/oauth_secrets
          pct exec 101 -- chmod 600 /root/docker/secrets/

          # Push and extract the compose slice — no git pull needed inside the LXC
          pct push 101 /tmp/lxc101-compose.tar.gz /tmp/compose.tar.gz
          pct exec 101 -- bash -c "tar -xzf /tmp/compose.tar.gz -C /root/docker && rm /tmp/compose.tar.gz"

          # Bring services up
          pct exec 101 -- bash -c "
            cd /root/docker
            docker compose -f lxc/infra/compose.yml pull --quiet
            docker compose -f lxc/infra/compose.yml up -d --remove-orphans
            docker image prune -f
          "

          # Clean up Proxmox temp files
          rm -f /tmp/lxc101.*
          SCRIPT

  deploy-media:
    needs: validate
    if: ${{ github.event.inputs.target == 'all' || github.event.inputs.target == 'media' || github.event_name == 'push' }}
    runs-on: ubuntu-latest
    environment: prod-media
    steps:
      - uses: actions/checkout@v4

      - name: Connect to Tailscale
        uses: tailscale/github-action@v2
        with:
          oauth-client-id: ${{ secrets.TS_OAUTH_CLIENT_ID }}
          oauth-secret: ${{ secrets.TS_OAUTH_SECRET }}
          tags: tag:ci

      - name: Set up SSH key
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.PROXMOX_SSH_KEY }}

      - name: Trust Proxmox host key
        run: ssh-keyscan -H "${{ secrets.PROXMOX_SSH_HOST }}" >> ~/.ssh/known_hosts

      - name: Build deploy package for LXC 102 (media)
        env:
          TRAEFIK_AUTH_BYPASS_KEY: ${{ secrets.TRAEFIK_AUTH_BYPASS_KEY }}
          VPN_USER: ${{ secrets.VPN_USER }}
          VPN_PASS: ${{ secrets.VPN_PASS }}
          VPN_PROV: ${{ secrets.VPN_PROV }}
          SONARR_API_KEY: ${{ secrets.SONARR_API_KEY }}
          RADARR_API_KEY: ${{ secrets.RADARR_API_KEY }}
          PROWLARR_API_KEY: ${{ secrets.PROWLARR_API_KEY }}
          SABNZBD_API_KEY: ${{ secrets.SABNZBD_API_KEY }}
          PLEX_ADVERTISE_IP: ${{ secrets.PLEX_ADVERTISE_IP }}
          PLEX_CLAIM_TOKEN: ${{ secrets.PLEX_CLAIM_TOKEN }}
        run: |
          cat > /tmp/lxc102.env << EOF
          DOCKER_DIR=/root/docker
          CONF_DIR=/root/docker/appdata
          MEDIA_DIR=/mnt/media
          DOWNLOAD_DIR=/mnt/downloads
          TZ=Europe/Amsterdam
          PUID=1000
          PGID=1000
          DOMAINNAME_1=example.com
          HOSTNAME=media
          POSTGRES_HOST=10.10.0.10
          REDIS_HOST=10.10.0.10
          TRAEFIK_AUTH_BYPASS_KEY=${TRAEFIK_AUTH_BYPASS_KEY}
          VPN_USER=${VPN_USER}
          VPN_PASS=${VPN_PASS}
          VPN_PROV=${VPN_PROV}
          SONARR_API_KEY=${SONARR_API_KEY}
          RADARR_API_KEY=${RADARR_API_KEY}
          PROWLARR_API_KEY=${PROWLARR_API_KEY}
          SABNZBD_API_KEY=${SABNZBD_API_KEY}
          PLEX_ADVERTISE_IP=${PLEX_ADVERTISE_IP}
          EOF

          printf '%s' "${PLEX_CLAIM_TOKEN}" > /tmp/lxc102.plex_claim_token

          tar -czf /tmp/lxc102-compose.tar.gz \
            lxc/media/ \
            compose/media-server/

          scp /tmp/lxc102.env \
              /tmp/lxc102.plex_claim_token \
              /tmp/lxc102-compose.tar.gz \
              root@${{ secrets.PROXMOX_SSH_HOST }}:/tmp/

      - name: Deploy into LXC 102 via Proxmox
        run: |
          ssh root@${{ secrets.PROXMOX_SSH_HOST }} << 'SCRIPT'
          set -e

          pct push 102 /tmp/lxc102.env /root/docker/.env
          pct exec 102 -- mkdir -p /root/docker/secrets
          pct push 102 /tmp/lxc102.plex_claim_token /root/docker/secrets/plex_claim_token
          pct exec 102 -- chmod 600 /root/docker/secrets/

          pct push 102 /tmp/lxc102-compose.tar.gz /tmp/compose.tar.gz
          pct exec 102 -- bash -c "tar -xzf /tmp/compose.tar.gz -C /root/docker && rm /tmp/compose.tar.gz"

          pct exec 102 -- bash -c "
            cd /root/docker
            docker compose -f lxc/media/compose.yml pull --quiet
            docker compose -f lxc/media/compose.yml up -d --remove-orphans
            docker image prune -f
          "

          rm -f /tmp/lxc102.*
          SCRIPT

  # deploy-home (103), deploy-productivity (104), deploy-network (105),
  # deploy-monitoring (106), deploy-utilities (107) follow the same pattern:
  #
  # Compose slices per LXC:
  #   103 home:         lxc/home/         + compose/home-automation/
  #   104 productivity: lxc/productivity/ + compose/productivity/
  #   105 network:      lxc/network/      + compose/network/
  #   106 monitoring:   lxc/monitoring/   + compose/monitoring/
  #   107 utilities:    lxc/utilities/    + compose/utilities/
  #
  # Steps per job:
  #   1. actions/checkout@v4
  #   2. tailscale/github-action@v2       — join tailnet ephemerally
  #   3. webfactory/ssh-agent@v0.9.0      — load deploy key
  #   4. ssh-keyscan                      — trust Proxmox host key
  #   5. Build deploy package:
  #      a. write .env locally with only the vars this LXC needs
  #      b. write any Docker secret files locally (printf '%s')
  #      c. tar the compose slice (lxc/<name>/ + compose/<category>/)
  #      d. scp all files to Proxmox /tmp/
  #   6. Deploy into LXC:
  #      a. pct push .env → /root/docker/.env
  #      b. pct push secrets → /root/docker/secrets/
  #      c. pct push tarball → /tmp/compose.tar.gz
  #      d. pct exec tar extract → /root/docker/
  #      e. pct exec docker compose pull + up --remove-orphans + image prune
  #      f. rm -f /tmp/lxcNNN.* on Proxmox
```

### 12.7 Create per-LXC compose files

Create the `lxc/` directory structure. Each LXC has its own root compose file that includes only the services for that LXC:

```bash
mkdir -p /root/docker/lxc/{infra,media,home,productivity,network,monitoring,utilities}
```

**`lxc/infra/compose.yml`:**
```yaml
networks:
  t3_proxy:
    name: t3_proxy
    driver: bridge
    ipam:
      config:
        - subnet: 10.2.0.0/16
  default:
    driver: bridge

secrets:
  basic_auth_credentials:
    file: $DOCKER_DIR/secrets/basic_auth_credentials
  cf_dns_api_token:
    file: $DOCKER_DIR/secrets/cf_dns_api_token
  oauth_secrets:
    file: $DOCKER_DIR/secrets/oauth_secrets

include:
  - ../../compose/reverse-proxy/compose.traefik.yml
  - ../../compose/reverse-proxy/compose.oauth.yml
  - ../../compose/reverse-proxy/compose.authentik.yml
  - ../../compose/database/compose.postgres.yml
  - ../../compose/database/compose.redis.yml
  - ../../compose/database/compose.mongo.yml
  - ../../compose/database/compose.adminer.yml
```

**`lxc/media/compose.yml`:**
```yaml
networks:
  t3_proxy:
    name: t3_proxy
    driver: bridge

secrets:
  plex_claim_token:
    file: $DOCKER_DIR/secrets/plex_claim_token

include:
  - ../../compose/media-server/compose.plex.yml
  - ../../compose/media-server/compose.sonarr.yml
  - ../../compose/media-server/compose.radarr.yml
  - ../../compose/media-server/compose.prowlarr.yml
  - ../../compose/media-server/compose.sabnzbd.yml
  - ../../compose/media-server/compose.qbittorrent.yml
  - ../../compose/media-server/compose.bazarr.yml
  - ../../compose/media-server/compose.tautulli.yml
  - ../../compose/media-server/compose.overseerr.yml
  - ../../compose/media-server/compose.jellyfin.yml
  - ../../compose/media-server/compose.huntarr.yml
  - ../../compose/media-server/compose.notifiarr.yml
  - ../../compose/media-server/compose.profilarr.yml
  - ../../compose/media-server/compose.maintainerr.yml
  - ../../compose/media-server/compose.plex-rewind.yml
  - ../../compose/media-server/compose.tracearr.yml
  - ../../compose/media-server/compose.agregarr.yml
  - ../../compose/media-server/compose.lingarr.yml
  - ../../compose/media-server/compose.watchstate.yml
```

**`lxc/home/compose.yml`:**
```yaml
networks:
  t3_proxy:
    name: t3_proxy
    driver: bridge

include:
  - ../../compose/home-automation/compose.home-assistant.yml
  - ../../compose/home-automation/compose.zigbee2mqtt.yml
  - ../../compose/home-automation/compose.mosquitto.yml
  - ../../compose/home-automation/compose.nodered.yml
  - ../../compose/home-automation/compose.music-assistant.yml
  - ../../compose/home-automation/compose.hyperion.yml
  - ../../compose/home-automation/compose.frigate.yml
```

**`lxc/productivity/compose.yml`:**
```yaml
networks:
  t3_proxy:
    name: t3_proxy
    driver: bridge

include:
  - ../../compose/productivity/compose.immich.yml
  - ../../compose/productivity/compose.paperless.yml
  - ../../compose/productivity/compose.nextcloud.yml
  - ../../compose/productivity/compose.n8n.yml
  - ../../compose/productivity/compose.firefly.yml
  - ../../compose/productivity/compose.backrest.yml
```

**`lxc/network/compose.yml`:**
```yaml
networks:
  t3_proxy:
    name: t3_proxy
    driver: bridge

include:
  - ../../compose/network/compose.unifi.yml
  - ../../compose/network/compose.pihole.yml
```

**`lxc/monitoring/compose.yml`:**
```yaml
networks:
  t3_proxy:
    name: t3_proxy
    driver: bridge

include:
  - ../../compose/monitoring/compose.exporters.yml
  - ../../compose/monitoring/compose.grafana.yml
  - ../../compose/monitoring/compose.loki.yml
  - ../../compose/monitoring/compose.promtail.yml
  - ../../compose/monitoring/compose.prometheus.yml
  - ../../compose/monitoring/compose.diun.yml
```

**`lxc/utilities/compose.yml`:**
```yaml
networks:
  t3_proxy:
    name: t3_proxy
    driver: bridge

include:
  - ../../compose/utilities/compose.omni-tools.yml
  - ../../compose/utilities/compose.spoolman.yml
  - ../../compose/utilities/compose.printer-calculator.yml
```

### 12.8 Commit

```bash
git add -A
git commit -m "feat: GitHub Actions multi-LXC deploy workflow, per-LXC compose files"
git push
```

> **Before the first GitHub Actions deploy:** run `docker compose up -d` manually on LXC 101 using the existing setup. Once CI/CD is working, subsequent changes deploy automatically.

---

## Phase 13 — Traefik Cross-LXC Routing

When a service moves to a new LXC, Traefik (on LXC 101) can no longer see its Docker labels. Instead, you create a YAML file in `appdata/traefik3/rules/` that points directly to the LXC's vmbr1 IP and port. Traefik watches this directory and picks up changes without restart.

### 13.1 File-based routing template

For a service on LXC 102 (10.10.0.20) port 8989:

```yaml
# appdata/traefik3/rules/<HOSTNAME>/sonarr.yml
http:
  routers:
    sonarr-rtr:
      entryPoints:
        - websecure
      rule: "Host(`sonarr.example.com`)"
      middlewares:
        - chain-authentik@file
      service: sonarr-svc
      priority: 99

    sonarr-rtr-bypass:
      entryPoints:
        - websecure
      rule: "Host(`sonarr.example.com`) && Header(`traefik-auth-bypass-key`, `YOUR_BYPASS_KEY`)"
      middlewares:
        - chain-no-auth@file
      service: sonarr-svc
      priority: 100

  services:
    sonarr-svc:
      loadBalancer:
        servers:
          - url: "http://10.10.0.20:8989"
```

Create one file per service as you migrate it. Use hardcoded domain names (simpler than Go template env vars).

### 13.2 Port binding pattern on destination LXCs

When a service moves to a new LXC, change its compose file from `expose` (Docker-internal) to `ports` bound to the vmbr1 interface:

```yaml
# Before (LXC 101, labels-based routing):
expose:
  - 8989
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.sonarr-rtr.rule=Host(`sonarr.example.com`)"
  # ...

# After (LXC 102, file-based routing):
ports:
  - "10.10.0.20:8989:8989"   # Bind ONLY to vmbr1 — not exposed on internet
# No traefik labels needed
```

Binding to `10.10.0.20` means only Traefik and other LXCs on vmbr1 can reach it. If you use `"8989:8989"` without the IP, it binds to all interfaces including vmbr0 (internet).

### 13.3 Database connection updates

Services on LXC 102–107 cannot reach `postgres` by container name — they must use the LXC 101 vmbr1 IP:

```bash
# In each LXC's .env (written by GitHub Actions deploy):
POSTGRES_HOST=10.10.0.10
REDIS_HOST=10.10.0.10
```

Update service environment vars to use `${POSTGRES_HOST}` instead of `postgres`.

---

## Phase 14 — Migrate Services

### 14.1 Recommended migration order

| Step | LXC | Services | Why this order |
|------|-----|----------|----------------|
| 1 | 101 (infra) | Traefik, Authentik, Postgres, Redis, MongoDB | Already there — just clean up and test |
| 2 | 103 (home) | HA, Frigate, Z2M, Mosquitto, Node-RED | No Postgres dependency; GPU+USB already configured |
| 3 | 102 (media) | Plex, *arr, SABnzbd, qBit | Stateless-ish; easy rollback; GPU already configured |
| 4 | 104 (productivity) | Immich, Paperless, Nextcloud, n8n | Needs Postgres on 101 — confirm 101 is stable first |
| 5 | 105 (network) | Pi-hole, Unifi | Time carefully — Pi-hole outage = DNS outage |
| 6 | 106 (monitoring) | Grafana, Prometheus, Loki | Update scrape targets to 10.10.0.x IPs after move |
| 7 | 107 (utilities) | Spoolman, OmniTools | Last — least critical |

### 14.2 Service move playbook

Follow this for every service:

```bash
# --- On SOURCE LXC (101) ---

SERVICE=sonarr
DATE=$(date +%Y%m%d)

# Step 1: Backup appdata
tar czf /tmp/${SERVICE}_backup_${DATE}.tar.gz -C /root/docker/appdata/$SERVICE .

# Step 2: Copy to destination LXC
DEST_IP=10.10.0.20
scp /tmp/${SERVICE}_backup_${DATE}.tar.gz root@$DEST_IP:/tmp/

# --- On DESTINATION LXC (102) ---

mkdir -p /root/docker/appdata/$SERVICE
tar xzf /tmp/${SERVICE}_backup_${DATE}.tar.gz -C /root/docker/appdata/$SERVICE

# Step 3: Ensure the destination's .env has correct values
# (Written by GitHub Actions or manually via bootstrap)

# Step 4: Update service compose file — change expose to ports bound to vmbr1
# (Edit compose/media-server/compose.sonarr.yml)

# Step 5: Create Traefik routing file on LXC 101
# (Create appdata/traefik3/rules/$HOSTNAME/sonarr.yml)

# --- On SOURCE LXC (101) ---

# Step 6: Stop service on source
docker compose stop $SERVICE

# --- On DESTINATION LXC (102) ---

# Step 7: Start service on destination
docker compose -f lxc/media/compose.yml up -d $SERVICE

# Step 8: Verify
curl -IL https://sonarr.yourdomain.com
docker compose -f lxc/media/compose.yml logs -f $SERVICE

# Step 9: If OK — remove from source LXC's compose.yml include list
# If NOT OK — restart on source (rollback):
docker compose start $SERVICE   # on source
```

### 14.3 Checklist per service migration

- [ ] appdata backed up and copied to destination LXC
- [ ] compose file: `expose` replaced with `ports: ["10.10.0.X:PORT:PORT"]`
- [ ] compose file: Traefik labels removed (or `traefik.enable=false`)
- [ ] Traefik file-based routing rule created on LXC 101
- [ ] Database connection updated to `10.10.0.10` (if applicable)
- [ ] Service started on destination and verified working
- [ ] Entry removed from source LXC's include list
- [ ] Old container stopped/removed on source

### 14.4 Update Prometheus scrape targets after migration

```yaml
# appdata/prometheus/prometheus.yml
scrape_configs:
  - job_name: 'sonarr-exporter'
    static_configs:
      - targets: ['10.10.0.20:9707']   # Was: sonarr-exporter:9707

  - job_name: 'radarr-exporter'
    static_configs:
      - targets: ['10.10.0.20:9708']

  - job_name: 'node-home'
    static_configs:
      - targets: ['10.10.0.30:9100']   # node-exporter on LXC 103
```

---

## Phase 15 — Azure Backup

### 15.1 Create Azure resources

```bash
# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | bash
az login

# Create resource group
az group create --name homelab-rg --location westeurope

# Create storage account (name must be globally unique)
STORAGE_ACCOUNT="homelabstorage$(openssl rand -hex 4)"
echo "Storage account: $STORAGE_ACCOUNT"

az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group homelab-rg \
  --location westeurope \
  --sku Standard_LRS \
  --kind StorageV2 \
  --access-tier Cool \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false

# Create the backup container
az storage container create \
  --name homelab-backups \
  --account-name "$STORAGE_ACCOUNT" \
  --public-access off

# Get the account key
az storage account keys list \
  --resource-group homelab-rg \
  --account-name "$STORAGE_ACCOUNT" \
  --query "[0].value" \
  --output tsv
```

Save the output to your password manager. Add `AZURE_ACCOUNT_NAME` and `AZURE_ACCOUNT_KEY` as GitHub secrets in the `prod-productivity` environment.

### 15.2 Configure Backrest for Azure

Update `compose/productivity/compose.backrest.yml`:

```yaml
services:
  backrest:
    container_name: backrest
    image: garethgeorge/backrest:v1.9.2
    restart: unless-stopped
    profiles: ["productivity", "all"]
    networks:
      - t3_proxy
    environment:
      TZ: ${TZ}
      XDG_CACHE_HOME: /cache
      BACKREST_CONFIG: /config/config.json
      BACKREST_DATA: /data
      AZURE_ACCOUNT_NAME: ${AZURE_ACCOUNT_NAME}
      AZURE_ACCOUNT_KEY: ${AZURE_ACCOUNT_KEY}
    volumes:
      - $CONF_DIR/backrest/data:/data
      - $CONF_DIR/backrest/config:/config
      - $CONF_DIR/backrest/cache:/cache
      - $CONF_DIR:/mnt/conf:ro
      - $DOCKER_DIR/compose:/mnt/compose:ro
    expose:
      - 9898
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.backrest-rtr.entrypoints=websecure"
      - "traefik.http.routers.backrest-rtr.rule=Host(`backup.$DOMAINNAME_1`)"
      - "traefik.http.routers.backrest-rtr.middlewares=chain-authentik@file"
      - "traefik.http.routers.backrest-rtr.service=backrest-svc"
      - "traefik.http.services.backrest-svc.loadbalancer.server.port=9898"
```

### 15.3 Configure Backrest repositories in the UI

Access Backrest at `https://backup.yourdomain.com` and create:

**Repository: Config (daily)**
- URI: `azure:homelab-backups:/config`
- Password: `openssl rand -hex 32` (store in password manager)
- Backup schedule: `0 3 * * *`
- Prune schedule: `0 4 * * 0`
- Retention: 30 daily, 12 weekly, 3 monthly
- Paths: `/mnt/conf`

**Repository: Compose files (daily)**
- URI: `azure:homelab-backups:/compose`
- Paths: `/mnt/compose`

### 15.4 Database dump script

```bash
cat > /root/docker/scripts/backup-databases.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

DUMP_DIR="/root/docker/appdata/backrest/db-dumps"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$DUMP_DIR"

echo "[$(date)] Starting database dumps..."

# PostgreSQL
docker exec postgres pg_dumpall \
  -U "${PSQL_DBUSER:-postgres}" \
  --clean --if-exists \
  > "$DUMP_DIR/postgres_${DATE}.sql"
gzip "$DUMP_DIR/postgres_${DATE}.sql"
echo "  PostgreSQL done"

# MongoDB
docker exec mongo mongodump \
  --username "${MONGO_ROOT_USER:-admin}" \
  --password "${MONGO_ROOT_PASS}" \
  --authenticationDatabase admin \
  --archive \
  > "$DUMP_DIR/mongo_${DATE}.archive"
echo "  MongoDB done"

# Keep only last 7 days locally
find "$DUMP_DIR" -name "postgres_*.sql.gz" -mtime +7 -delete
find "$DUMP_DIR" -name "mongo_*.archive" -mtime +7 -delete

echo "[$(date)] Done."
SCRIPT

chmod +x /root/docker/scripts/backup-databases.sh
```

Schedule via cron on LXC 101 (runs before Backrest backup at 3 AM):
```bash
crontab -e
# Add:
0 2 * * * /root/docker/scripts/backup-databases.sh >> /root/docker/logs/db-backup.log 2>&1
```

---

## Phase 16 — Renovate (Automated Updates)

### 16.1 Install Renovate GitHub App

1. Go to [github.com/apps/renovate](https://github.com/apps/renovate)
2. Install on your `docker-homelab` repo
3. Merge the initial onboarding PR it creates

### 16.2 Create `.github/renovate.json5`

```bash
mkdir -p /root/docker/.github
```

```json5
// .github/renovate.json5
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended", "docker:enableMajor"],

  "docker-compose": {
    "fileMatch": [
      "(^|/)compose\\..*\\.ya?ml$",
      "(^|/)compose\\.ya?ml$",
      "(^|/)lxc/.*/compose\\.ya?ml$"
    ]
  },

  "customManagers": [
    {
      "customType": "regex",
      "fileMatch": ["(^|/)\\.env\\.example$"],
      "matchStrings": [
        "# renovate: datasource=(?<datasource>[^\\s]+) depName=(?<depName>[^\\s]+)\\n[A-Z_]+=(?<currentValue>.+)"
      ],
      "datasourceTemplate": "{{datasource}}"
    }
  ],

  "packageRules": [
    {
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["^lscr\\.io/linuxserver/"],
      "groupName": "LinuxServer.io containers",
      "schedule": ["every weekend"]
    },
    {
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["grafana/", "prom/"],
      "groupName": "Monitoring stack",
      "schedule": ["every weekend"]
    },
    {
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["ghcr.io/immich-app/"],
      "groupName": "Immich",
      "schedule": ["every weekend"]
    },
    {
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["ghcr.io/goauthentik/server"],
      "groupName": "Authentik",
      "schedule": ["every weekend"]
    },
    {
      "matchDatasources": ["docker"],
      "matchPackageNames": [
        "postgres", "ghcr.io/immich-app/postgres", "mongo", "redis"
      ],
      "matchUpdateTypes": ["major"],
      "enabled": false,
      "description": "Database major versions require manual migration"
    },
    {
      "matchDatasources": ["docker"],
      "matchUpdateTypes": ["patch"],
      "matchPackagePatterns": ["lscr.io/linuxserver/", "prom/node-exporter"],
      "automerge": true,
      "automergeType": "pr",
      "schedule": ["every weekend"]
    },
    {
      "matchDatasources": ["docker"],
      "matchUpdateTypes": ["major"],
      "labels": ["major-update", "needs-review"],
      "automerge": false
    }
  ],

  "prConcurrentLimit": 5,
  "prHourlyLimit": 2,
  "labels": ["renovate", "dependencies"]
}
```

### 16.3 Annotate `.env.example` for Renovate tracking

These comments tell Renovate where to find the version for env-var-pinned images:

```bash
# In .env.example:

# renovate: datasource=docker depName=ghcr.io/immich-app/immich-server
IMMICH_VERSION=v2.5.3

# renovate: datasource=docker depName=ghcr.io/goauthentik/server
AUTHENTIK_VERSION=2025.8.1
```

### 16.4 Protect main branch

GitHub → **Settings → Branches → Add rule** for `main`:
- ✅ Require pull request before merging
- ✅ Require status checks (add the `validate` job)
- ✅ Require branches to be up to date

Renovate PRs will be validated by CI before you merge them.

---

*All phases complete. The stack is now split across 7 LXCs, fully automated, secured, and monitored.*
