# Docker Infrastructure Implementation Guide

*Comprehensive, phased implementation plan for a solid, GitHub-managed, multi-LXC-ready homelab setup.*

---

## Table of Contents

1. [Current State Assessment](#current-state-assessment)
2. [Phase 1 — Git Foundation & Repository Setup](#phase-1--git-foundation--repository-setup)
3. [Phase 2 — Secrets Management (GitHub Actions Secrets)](#phase-2--secrets-management-github-actions-secrets)
4. [Phase 3 — Stack Separation & Directory Restructure](#phase-3--stack-separation--directory-restructure)
5. [Phase 4 — Compose Fragments (DRY)](#phase-4--compose-fragments-dry)
6. [Phase 5 — Fix Known Issues](#phase-5--fix-known-issues)
7. [Phase 6 — Health Checks for All Services](#phase-6--health-checks-for-all-services)
8. [Phase 7 — Traefik Hardening](#phase-7--traefik-hardening)
9. [Phase 8 — Authentik Hardening](#phase-8--authentik-hardening)
10. [Phase 9 — Azure Backup Setup](#phase-9--azure-backup-setup)
11. [Phase 10 — Renovate (Automated Updates)](#phase-10--renovate-automated-updates)
12. [Phase 11 — CI/CD with GitHub Actions](#phase-11--cicd-with-github-actions)
13. [Appendix A — Multi-LXC Architecture](#appendix-a--multi-lxc-architecture)
14. [Appendix B — Intel iGPU Passthrough in Proxmox LXC](#appendix-b--intel-igpu-passthrough-in-proxmox-lxc)
15. [Appendix C — Environment Variable Reference](#appendix-c--environment-variable-reference)

---

## Current State Assessment

### What works well (keep as-is)
- Split compose files with `include` — modern and clean
- `t3_proxy` bridge network with Traefik at static IP `10.2.0.254`
- File-based Docker secrets for Cloudflare token, basic auth, OAuth, Plex claim
- Auth bypass header pattern for *arr apps (`traefik-auth-bypass-key`)
- Postgres and Redis already have health checks with correct `service_healthy` conditions in Authentik
- Image versions pinned on most services (good for Renovate)
- Profiles system (`media`, `monitoring`, `all`, etc.)

### Critical problems to fix
| Problem | Impact | Fix phase |
|---------|--------|-----------|
| `server/` has 22 files — no logical grouping | Hard to maintain, can't split to LXCs | Phase 3 |
| PUID/PGID on non-LSIO images (immich, authentik, frigate, etc.) | False sense of user control | Phase 5 |
| `expose` + `ports` together on immich, frigate | Redundant config, confusing | Phase 5 |
| Immich + authentik duplicate versions | Version mismatch risk | Phase 5 |
| `sapcc/mosquitto-exporter` and `prometheuscommunity/smartctl-exporter` unversioned | Unpredictable pulls | Phase 5 |
| ~45 services with no health check | No automatic recovery | Phase 6 |
| No Git repo → no history, CI/CD impossible | Can't use GitHub, Renovate | Phase 1 |
| Secrets in plaintext files → can't commit | No disaster recovery via Git | Phase 2 |
| Traefik missing security headers, rate limiting | Security gaps | Phase 7 |
| Authentik PUID/PGID, no healthcheck, same image version not enforced | Reliability issues | Phase 8 |

### Services requiring Intel iGPU (`/dev/dri`)
- **Plex** — hardware transcoding (QuickSync)
- **Frigate** — OpenVINO object detection (i965 driver, 128MB shm, 1GB tmpfs)

Both must always share the same LXC when on separate hardware.

---

## Phase 1 — Git Foundation & Repository Setup

### 1.1 Initialize the repository

```bash
cd /root/docker
git init
git branch -M main
```

### 1.2 Create `.gitignore`

```bash
cat > /root/docker/.gitignore << 'EOF'
# Secrets and environment (never commit unencrypted)
.env
secrets/
!secrets/*.example

# Encrypted secrets are safe to commit
# *.enc and *.age files are added explicitly

# Application data (NEVER — container state)
appdata/

# Logs
logs/
*.log

# Traefik ACME certificates (auto-renewed)
appdata/traefik3/acme/

# Backup files
*.bak
*.tmp

# OS noise
.DS_Store
Thumbs.db
EOF
```

### 1.3 Create `.env.example`

This file IS committed — it documents every variable with no values.

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
# DATABASES — Shared PostgreSQL
# ============================================================
PSQL_DBUSER=postgres
PSQL_DBPASS=              # openssl rand -base64 32

# Per-service database credentials
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

PRINTER_CALCULATOR_DBNAME=printer_calculator
PRINTER_CALCULATOR_DBUSER=printer_calc
PRINTER_CALCULATOR_DBPASS=

# ============================================================
# DATABASES — MongoDB
# ============================================================
MONGO_ROOT_USER=admin
MONGO_ROOT_PASS=

# ============================================================
# AUTHENTIK
# ============================================================
AUTHENTIK_SECRET=          # openssl rand -hex 50
AUTHENTIK_VERSION=2025.8.1

# ============================================================
# IMMICH
# ============================================================
IMMICH_VERSION=v2.5.3

# ============================================================
# MEDIA
# ============================================================
PLEX_ADVERTISE_IP=         # https://<your-ip>:32400/

# VPN (qBittorrent)
VPN_USER=
VPN_PASS=
VPN_PROV=               # pia / airvpn / mullvad etc
VPN_INPUT_PORTS=
VPN_OUTPUT_PORTS=

# ============================================================
# ARR API KEYS (for exportarr Prometheus exporters)
# ============================================================
SONARR_API_KEY=
RADARR_API_KEY=
PROWLARR_API_KEY=
SABNZBD_API_KEY=

# ============================================================
# MONITORING
# ============================================================
MOSQUITTO_USER=
MOSQUITTO_PASS=

# ============================================================
# HOME AUTOMATION
# ============================================================
FRIGATE_RTSP_PASSWORD=

# ============================================================
# NOTIFICATIONS
# ============================================================
DN_API_KEY=     # Notifiarr

# ============================================================
# PIHOLE
# ============================================================
PIHOLE_WEB_PASS=

# ============================================================
# NEXTCLOUD
# ============================================================
NEXTAUTH_SECRET=          # openssl rand -hex 32

# ============================================================
# FIREFLY
# ============================================================
# Firefly uses its own .env file at $CONF_DIR/firefly/.env

# ============================================================
# AZURE BACKUP (Phase 9)
# ============================================================
AZURE_ACCOUNT_NAME=
AZURE_ACCOUNT_KEY=
AZURE_BACKUP_CONTAINER=homelab-backups
EOF
```

### 1.4 Create the GitHub repository

1. Go to [github.com/new](https://github.com/new)
2. Create a **private** repository named `docker-homelab` (or similar)
3. Do NOT initialize with a README (you already have files)

```bash
cd /root/docker

# Add the remote (replace with your actual URL)
git remote add origin git@github.com:YOURUSERNAME/docker-homelab.git

# Stage everything except what's in .gitignore
git add .

# Review what will be committed — check NO secrets are included
git status

# Make first commit
git commit -m "chore: initial commit — existing docker compose setup"

# Push
git push -u origin main
```

> **Before pushing**: Run `git diff --cached` and verify no `.env`, no `secrets/`, no `appdata/` appears in the diff.

---

## Phase 2 — Secrets Management (GitHub Actions Secrets)

> **Decision**: No secrets — not even encrypted ones — are stored in the Git repository. All sensitive values live exclusively in GitHub Actions Secrets (encrypted at rest by GitHub) and are written to each server at deploy time by the CI/CD workflow. The `.env` file on each server is ephemeral: regenerated on every deployment.

### Why not SOPS/age?

SOPS is a valid approach but requires managing an age private key: if you lose it, all encrypted secrets in the repo are permanently unrecoverable. GitHub Actions Secrets avoids this entirely — GitHub manages the encryption and you manage access through your GitHub account.

The trade-off: if your GitHub account is compromised, secrets are exposed. Mitigate this with 2FA + hardware key on your GitHub account and a local password manager backup of all secret values (1Password, Bitwarden, etc.).

### 2.1 What goes where

| Location | What's stored |
|----------|---------------|
| Git repo (committed) | `.env.example`, compose files, scripts, Traefik rules, `CLOUDFLARE_IPS`, `LOCAL_IPS`, non-secret config |
| GitHub Actions Secrets | All passwords, API keys, tokens, auth secrets |
| Server `.env` | Written at deploy time from GH secrets — never committed |
| Server `secrets/` | Written at deploy time from GH secrets — never committed |

### 2.2 Update `.gitignore`

```gitignore
# Secrets and environment — NEVER commit
.env
secrets/
!secrets/*.example

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

> Remove `.sops.yaml` and any `.env.enc` / `*.enc` files if you had them from a previous SOPS setup:
> ```bash
> git rm --cached .sops.yaml .env.enc secrets/*.enc 2>/dev/null || true
> ```

### 2.3 Commit non-secret config directly in `.env.example`

The `.env.example` doubles as documentation. Leave all values that aren't secrets in it — they'll be hardcoded into the deploy workflow script:

```bash
# Values safe to commit in .env.example (not secrets):
DOCKER_DIR=/root/docker
CONF_DIR=/root/docker/appdata
TZ=Europe/Amsterdam
PUID=1000
PGID=1000
DOMAINNAME_1=example.com
HOSTNAME=docker
CLOUDFLARE_IPS=173.245.48.0/20,103.21.244.0/22,...
LOCAL_IPS=127.0.0.1/32,10.0.0.0/8,...

# Values that ARE secrets — placeholder only:
TRAEFIK_AUTH_BYPASS_KEY=   # → GitHub Secret: TRAEFIK_AUTH_BYPASS_KEY
PSQL_DBPASS=               # → GitHub Secret: PSQL_DBPASS
AUTHENTIK_SECRET=          # → GitHub Secret: AUTHENTIK_SECRET
CF_DNS_API_TOKEN=          # → GitHub Secret: CF_DNS_API_TOKEN (written to secrets/ file)
```

### 2.4 Add secrets to GitHub

1. Go to your GitHub repository → **Settings → Secrets and variables → Actions**
2. For single-LXC setups: add all secrets as **Repository secrets**
3. For multi-LXC setups (see `MULTI_LXC_MIGRATION.md`): use **Environments** to scope secrets per LXC

Secrets to add:
```
TRAEFIK_AUTH_BYPASS_KEY    openssl rand -hex 32
PSQL_DBPASS                openssl rand -base64 32
AUTHENTIK_SECRET           openssl rand -hex 50
AUTHENTIK_DBPASS           openssl rand -base64 32
MONGO_ROOT_PASS            openssl rand -base64 32
CF_DNS_API_TOKEN           from Cloudflare dashboard
BASIC_AUTH_CREDS           htpasswd -nb user password
OAUTH_SECRET               from your OAuth provider
PLEX_CLAIM_TOKEN           from plex.tv/claim
VPN_USER / VPN_PASS        from your VPN provider
SONARR_API_KEY             from Sonarr settings
RADARR_API_KEY             from Radarr settings
PROWLARR_API_KEY           from Prowlarr settings
SABNZBD_API_KEY            from SABnzbd settings
SERVER_SSH_KEY             private key of deploy keypair
SERVER_HOST                IP of your server/LXC
```

### 2.5 Set up SSH deploy key

```bash
# On your server — generate a deploy keypair
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/deploy_key -N ""

# Add public key to authorized_keys
cat ~/.ssh/deploy_key.pub >> ~/.ssh/authorized_keys

# Print private key — paste this as GitHub Secret: SERVER_SSH_KEY
cat ~/.ssh/deploy_key
```

### 2.6 Deployment workflow

The workflow writes `.env` and `secrets/` from GitHub Secrets on every deploy. See Phase 11 (CI/CD) for the full workflow. The key pattern is:

```yaml
- name: Deploy
  uses: appleboy/ssh-action@v1
  env:
    PSQL_DBPASS: ${{ secrets.PSQL_DBPASS }}
    CF_DNS_API_TOKEN: ${{ secrets.CF_DNS_API_TOKEN }}
    # ... all secrets passed as env vars
  with:
    host: ${{ secrets.SERVER_HOST }}
    key: ${{ secrets.SERVER_SSH_KEY }}
    username: root
    envs: PSQL_DBPASS,CF_DNS_API_TOKEN,...
    script: |
      cd /root/docker
      git pull origin main

      # Write .env from injected variables
      cat > .env << EOF
      DOCKER_DIR=/root/docker
      CONF_DIR=/root/docker/appdata
      TZ=Europe/Amsterdam
      PSQL_DBPASS=${PSQL_DBPASS}
      # ... all variables
      EOF

      # Write Docker file secrets
      mkdir -p secrets
      echo -n "${CF_DNS_API_TOKEN}" > secrets/cf_dns_api_token
      chmod 600 secrets/*

      docker compose pull --quiet
      docker compose up -d --remove-orphans
      docker image prune -f
```

### 2.7 Local `.env` bootstrap (for manual use)

When you need to run `docker compose` manually on the server without triggering GitHub Actions, keep a local bootstrap script that you run once after provisioning:

```bash
cat > /root/docker/scripts/bootstrap-env.sh << 'SCRIPT'
#!/bin/bash
# Run this manually after provisioning a fresh server.
# Fill in values from your password manager.
set -e

cat > /root/docker/.env << 'EOF'
DOCKER_DIR=/root/docker
CONF_DIR=/root/docker/appdata
TZ=Europe/Amsterdam
PUID=1000
PGID=1000
DOMAINNAME_1=FILL_IN
TRAEFIK_AUTH_BYPASS_KEY=FILL_IN
PSQL_DBPASS=FILL_IN
# ... etc
EOF

mkdir -p /root/docker/secrets
echo -n "FILL_IN" > /root/docker/secrets/cf_dns_api_token
echo -n "FILL_IN" > /root/docker/secrets/basic_auth_credentials
chmod 600 /root/docker/secrets/*

echo "Done. Edit /root/docker/.env with real values, then run: docker compose up -d"
SCRIPT
chmod +x /root/docker/scripts/bootstrap-env.sh
```

Add `bootstrap-env.sh` to Git (with `FILL_IN` placeholders, not real values). You fill it in manually on each new server.

---

## Phase 3 — Stack Separation & Directory Restructure

### 3.1 Target directory structure

The `server/` directory has 22 services with no logical grouping. The new structure maps directly to future LXC containers.

```
compose/
├── reverse-proxy/     → LXC 1 (infra)     — unchanged
├── database/          → LXC 1 (infra)     — NEW, split from server/
├── media-server/      → LXC 2 (media)     — unchanged
├── home-automation/   → LXC 3 (home)      — NEW, split from server/
├── productivity/      → LXC 4 (productivity) — NEW, split from server/
├── network/           → LXC 5 (network)   — NEW, split from server/
├── monitoring/        → LXC 6 (monitoring) — unchanged
├── utilities/         → LXC 7 (utilities)  — NEW, split from server/
├── fragments/         → shared templates   — NEW
└── archive/           → disabled services  — unchanged
```

### 3.2 Create new directories and move files

```bash
cd /root/docker/compose

# Create new directories
mkdir -p database home-automation productivity network utilities fragments

# --- DATABASE stack ---
mv server/compose.postgres.yml database/
mv server/compose.redis.yml database/
mv server/compose.mongo.yml database/
mv server/compose.adminer.yml database/

# --- HOME AUTOMATION stack ---
mv server/compose.home-assistant.yml home-automation/
mv server/compose.music-assistant.yml home-automation/
mv server/compose.zigbee2mqtt.yml home-automation/
mv server/compose.mosquitto.yml home-automation/
mv server/compose.nodered.yml home-automation/
mv server/compose.hyperion.yml home-automation/
mv server/compose.frigate.yml home-automation/

# --- PRODUCTIVITY stack ---
mv server/compose.immich.yml productivity/
mv server/compose.paperless.yml productivity/
mv server/compose.nextcloud.yml productivity/
mv server/compose.n8n.yml productivity/
mv server/compose.firefly.yml productivity/
mv server/compose.backrest.yml productivity/

# --- NETWORK stack ---
mv server/compose.unifi.yml network/
mv server/compose.pihole.yml network/

# --- UTILITIES stack ---
mv server/compose.omni-tools.yml utilities/
mv server/compose.spoolman.yml utilities/
mv server/compose.printer-calculator.yml utilities/

# Verify server/ is now empty (it should be)
ls server/
# Should show nothing (or just an empty dir)
rmdir server/
```

### 3.3 Update `compose.yml`

Replace the entire `include:` block with the reorganized structure:

```yaml
##### NETWORKS #####
networks:
  default:
    driver: bridge
  t3_proxy:
    name: t3_proxy
    driver: bridge
    ipam:
      config:
        - subnet: 10.2.0.0/16

##### SECRETS #####
secrets:
  basic_auth_credentials:
    file: $DOCKER_DIR/secrets/basic_auth_credentials
  cf_dns_api_token:
    file: $DOCKER_DIR/secrets/cf_dns_api_token
  oauth_secrets:
    file: $DOCKER_DIR/secrets/oauth_secrets
  plex_claim_token:
    file: $DOCKER_DIR/secrets/plex_claim_token

include:
  # =========================================================
  # REVERSE PROXY STACK (LXC 1: infra)
  # =========================================================
  - compose/reverse-proxy/compose.traefik.yml
  - compose/reverse-proxy/compose.oauth.yml
  - compose/reverse-proxy/compose.authentik.yml

  # =========================================================
  # DATABASE STACK (LXC 1: infra)
  # =========================================================
  - compose/database/compose.postgres.yml
  - compose/database/compose.redis.yml
  - compose/database/compose.mongo.yml
  - compose/database/compose.adminer.yml

  # =========================================================
  # MEDIA SERVER STACK (LXC 2: media — needs GPU)
  # =========================================================
  - compose/media-server/compose.plex.yml
  - compose/media-server/compose.jellyfin.yml
  - compose/media-server/compose.overseerr.yml
  - compose/media-server/compose.seerr.yml
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
  - compose/media-server/compose.bazarr.yml
  - compose/media-server/compose.lingarr.yml
  - compose/media-server/compose.watchstate.yml

  # =========================================================
  # HOME AUTOMATION STACK (LXC 3: home — needs GPU for Frigate)
  # =========================================================
  - compose/home-automation/compose.home-assistant.yml
  - compose/home-automation/compose.zigbee2mqtt.yml
  - compose/home-automation/compose.mosquitto.yml
  - compose/home-automation/compose.nodered.yml
  - compose/home-automation/compose.music-assistant.yml
  - compose/home-automation/compose.hyperion.yml
  - compose/home-automation/compose.frigate.yml

  # =========================================================
  # PRODUCTIVITY STACK (LXC 4: productivity)
  # =========================================================
  - compose/productivity/compose.immich.yml
  - compose/productivity/compose.paperless.yml
  - compose/productivity/compose.nextcloud.yml
  - compose/productivity/compose.n8n.yml
  - compose/productivity/compose.firefly.yml
  - compose/productivity/compose.backrest.yml

  # =========================================================
  # NETWORK STACK (LXC 5: network)
  # =========================================================
  - compose/network/compose.unifi.yml
  - compose/network/compose.pihole.yml

  # =========================================================
  # MONITORING STACK (LXC 6: monitoring)
  # =========================================================
  - compose/monitoring/compose.exporters.yml
  - compose/monitoring/compose.grafana.yml
  - compose/monitoring/compose.loki.yml
  - compose/monitoring/compose.promtail.yml
  - compose/monitoring/compose.prometheus.yml
  - compose/monitoring/compose.diun.yml

  # =========================================================
  # UTILITIES STACK (LXC 7: utilities)
  # =========================================================
  - compose/utilities/compose.omni-tools.yml
  - compose/utilities/compose.spoolman.yml
  - compose/utilities/compose.printer-calculator.yml
```

### 3.4 Update profiles to match new stack names

Add new profile names to services. Keep backward compat by also keeping `all`. The goal is: each stack has a profile matching its directory name.

| Directory | Profile tag to use |
|-----------|-------------------|
| reverse-proxy | `reverse-proxy` |
| database | `database` |
| media-server | `media` |
| home-automation | `home` |
| productivity | `productivity` |
| network | `network` |
| monitoring | `monitoring` |
| utilities | `utilities` |

Update each moved service file to replace `"other"` profile with the appropriate stack profile. Example for `compose.postgres.yml`:

```yaml
# Before:
profiles: ["other", "database", "all"]

# After:
profiles: ["database", "all"]
```

Do this for all moved files:
- database/ services: `["database", "all"]`
- home-automation/ services: `["home", "all"]`
- productivity/ services: `["productivity", "all"]`
- network/ services: `["network", "all"]`
- utilities/ services: `["utilities", "all"]`

### 3.5 Verify the restructure works

```bash
cd /root/docker

# Validate compose config (dry run — does not start containers)
docker compose config --quiet && echo "Config valid!"

# Check for any broken paths
docker compose config 2>&1 | grep -i error
```

### 3.6 Commit

```bash
git add -A
git commit -m "refactor: split server/ into database, home-automation, productivity, network, utilities stacks"
git push
```

---

## Phase 4 — Compose Fragments (DRY)

Create shared base service definitions that all services can `extend`. This eliminates the repeated `restart`, `networks`, `TZ`, `PUID/PGID` blocks.

> **Note**: Docker Compose `extends` works across files and IS compatible with `include`. Each included file can reference the fragments file.

### 4.1 Create `compose/fragments/common-service.yml`

```yaml
# compose/fragments/common-service.yml
# Shared service templates — referenced via 'extends' in service files
# YAML anchors do NOT work across files; use 'extends' instead.

services:

  # Base: restart policy, t3_proxy network, TZ
  # Use for: non-LSIO containers — immich, authentik, frigate, exporters, etc.
  common:
    restart: unless-stopped
    networks:
      - t3_proxy
    environment:
      TZ: ${TZ}

  # LSIO base: adds PUID/PGID for LinuxServer.io containers
  # Use for: bazarr, sonarr, radarr, prowlarr, sabnzbd, tautulli, unifi, etc.
  common-lsio:
    restart: unless-stopped
    networks:
      - t3_proxy
    environment:
      PUID: ${PUID}
      PGID: ${PGID}
      TZ: ${TZ}

  # DB-dependent: extends common, adds depends_on for postgres + redis
  # Use for: paperless, nextcloud, n8n, firefly (if postgres-backed)
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

  # DB-dependent LSIO: LSIO + postgres + redis depends_on
  # Use for: LSIO containers that need a database (rare)
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

  # Exportarr base: shared config for all *arr Prometheus exporters
  # Use for: sonarr-exporter, radarr-exporter, prowlarr-exporter, sabnzbd-exporter
  exportarr-base:
    image: ghcr.io/onedr0p/exportarr:v2.0.1
    restart: unless-stopped
    profiles: ["monitoring", "all"]
    networks:
      - t3_proxy
    environment:
      TZ: ${TZ}
```

### 4.2 Refactor exporters file (biggest win)

Replace `compose/monitoring/compose.exporters.yml` with:

```yaml
## Prometheus exporters for *arr apps and infrastructure

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
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9707/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

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
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9708/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

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
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9710/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

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
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9711/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

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
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9633/metrics"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 15s
```

### 4.3 Refactor bazarr as a reference example

```yaml
# compose/media-server/compose.bazarr.yml
services:
  bazarr:
    extends:
      file: ../fragments/common-service.yml
      service: common-lsio
    container_name: bazarr
    image: lscr.io/linuxserver/bazarr:1.5.3
    profiles: ["media", "all"]
    volumes:
      - $CONF_DIR/bazarr/config:/config
      - $MEDIA_DIR/movies:/movies
      - $MEDIA_DIR/tv-shows:/tv
    expose:
      - 6767
    healthcheck:
      test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:6767/api/system/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.bazarr-rtr-bypass.entrypoints=websecure"
      - "traefik.http.routers.bazarr-rtr-bypass.rule=Host(`subtitles.$DOMAINNAME_1`) && Header(`traefik-auth-bypass-key`, `$TRAEFIK_AUTH_BYPASS_KEY`)"
      - "traefik.http.routers.bazarr-rtr-bypass.priority=100"
      - "traefik.http.routers.bazarr-rtr-bypass.middlewares=chain-no-auth@file"
      - "traefik.http.routers.bazarr-rtr-bypass.service=bazarr-svc"
      - "traefik.http.routers.bazarr-rtr.entrypoints=websecure"
      - "traefik.http.routers.bazarr-rtr.rule=Host(`subtitles.$DOMAINNAME_1`)"
      - "traefik.http.routers.bazarr-rtr.priority=99"
      - "traefik.http.routers.bazarr-rtr.middlewares=chain-authentik@file"
      - "traefik.http.routers.bazarr-rtr.service=bazarr-svc"
      - "traefik.http.services.bazarr-svc.loadbalancer.server.port=6767"
```

Apply the same `extends` pattern to all LSIO services (sonarr, radarr, prowlarr, sabnzbd, tautulli, etc.) and `extends: common` for non-LSIO services.

---

## Phase 5 — Fix Known Issues

### 5.1 Fix PUID/PGID on non-LSIO containers

Remove `PUID` and `PGID` from these services (they ignore it):

| File | Service(s) |
|------|-----------|
| `compose.authentik.yml` | `authentik` (keep off worker — already correct) |
| `productivity/compose.immich.yml` | `immich`, `immich-machine-learning` |
| `home-automation/compose.frigate.yml` | `frigate` |
| `home-automation/compose.mosquitto.yml` | `mosquitto` |
| `database/compose.mongo.yml` | `mongo`, `mongo-express` |
| `monitoring/compose.exporters.yml` | all exportarr, mosquitto-exporter, smartctl-exporter |
| `monitoring/compose.grafana.yml` | `grafana` |
| `monitoring/compose.loki.yml` | `loki` |
| `monitoring/compose.promtail.yml` | `promtail` |
| `media-server/compose.seerr.yml` | `seerr` |
| `media-server/compose.watchstate.yml` | `watchstate` |
| `media-server/compose.tracearr.yml` | `tracearr` |

For containers that actually need a specific user, use Docker's `user:` directive instead:
```yaml
# Example for immich (runs as uid 1000 inside image)
user: "${PUID}:${PGID}"
```

### 5.2 Fix `expose` + `ports` redundancy

**Immich** — choose one. Since mobile app connects directly (not through Traefik), keep `ports` only:
```yaml
# Remove: expose: 2283
ports:
  - "2283:2283"
# (expose is redundant when ports is set)
```

**Frigate** — web UI goes through Traefik, RTSP goes direct:
```yaml
# Remove: expose: 5000
ports:
  - "5001:5000"     # Direct access backup
  - "8554:8554"     # RTSP
  - "8555:8555/tcp" # WebRTC
  - "8555:8555/udp"
```

### 5.3 Pin multi-container service versions via env vars

**Add to `.env` (and `.env.example`):**
```bash
IMMICH_VERSION=v2.5.3
AUTHENTIK_VERSION=2025.8.1
```

**Update `compose/productivity/compose.immich.yml`:**
```yaml
immich:
  image: ghcr.io/immich-app/immich-server:${IMMICH_VERSION}

immich-machine-learning:
  image: ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION}
```

**Update `compose/reverse-proxy/compose.authentik.yml`:**
```yaml
authentik:
  image: ghcr.io/goauthentik/server:${AUTHENTIK_VERSION}

authentik-worker:
  image: ghcr.io/goauthentik/server:${AUTHENTIK_VERSION}
```

### 5.4 Pin unversioned images

```yaml
# compose/monitoring/compose.exporters.yml
mosquitto-exporter:
  image: sapcc/mosquitto-exporter:0.8.0    # Was: sapcc/mosquitto-exporter

smartctl-exporter:
  image: prometheuscommunity/smartctl-exporter:v0.12.0   # Was: no version
```

Check Docker Hub for latest versions before pinning.

---

## Phase 6 — Health Checks for All Services

Add health checks to every service that doesn't have one. This enables:
- Docker to restart containers that are running but broken (not just stopped)
- `depends_on: condition: service_healthy` to work correctly
- Better visibility in `docker compose ps`

### 6.1 Health check templates by service type

**HTTP services (curl available):**
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:<PORT>/<PATH>"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**HTTP services (wget only — smaller images):**
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

### 6.2 Health check reference per service

Apply these to each service file:

#### Reverse Proxy

**Traefik** — enable the ping endpoint first:
Add to Traefik command flags in `compose.traefik.yml`:
```yaml
command:
  # ... existing flags ...
  - --ping=true
  - --ping.entrypoint=traefik
```
Then add healthcheck:
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

**Authentik Worker** (no HTTP, check worker process):
```yaml
healthcheck:
  test: ["CMD-SHELL", "ak healthcheck || exit 1"]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**OAuth (traefik-forward-auth)**:
```yaml
healthcheck:
  test: ["CMD-SHELL", "nc -z localhost 4181 || exit 1"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 10s
```

#### Databases

**MongoDB** (missing healthcheck):
```yaml
healthcheck:
  test: ["CMD-SHELL", "mongosh --quiet --eval \"db.runCommand('ping').ok\" || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 5
  start_period: 30s
```

#### Media Server

**Radarr** (port 7878):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:7878/api/v3/system/status?apikey=$RADARR_API_KEY"]
  interval: 30s
  timeout: 10s
  retries: 3
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

**Agregarr** (port 7171):
```yaml
healthcheck:
  test: ["CMD", "wget", "-qO-", "http://localhost:7171/"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

**Lingarr** (port 9876):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:9876/health"]
  interval: 30s
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

#### Home Automation

**Home Assistant** (network_mode: host, port 8123):
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

**Mosquitto** (MQTT TCP on 1883):
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

**Music Assistant** (network_mode: host, port 8095):
```yaml
healthcheck:
  test: ["CMD", "curl", "-fsSo", "/dev/null", "http://localhost:8095/"]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 30s
```

#### Productivity

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

#### Network

**Unifi** (HTTP management on 8080):
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

#### Monitoring

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

#### Utilities

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

### 6.3 Add MongoDB health check dependency

Once MongoDB has a health check, update Unifi to depend on it:
```yaml
# compose/network/compose.unifi.yml
depends_on:
  mongo:
    condition: service_healthy
```

---

## Phase 7 — Traefik Hardening

### 7.1 Add security headers middleware

Create `appdata/traefik3/rules/$HOSTNAME/middlewares.yml` (add to existing or create):

```yaml
http:
  middlewares:
    # =========================================================
    # SECURITY HEADERS — Apply to all services
    # =========================================================
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

    # =========================================================
    # RATE LIMITING — General purpose
    # =========================================================
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

    # =========================================================
    # IP ALLOWLIST — Admin/internal services only
    # =========================================================
    local-only:
      ipAllowList:
        sourceRange:
          - "127.0.0.1/32"
          - "10.0.0.0/8"
          - "192.168.0.0/16"
          - "172.16.0.0/12"

    # =========================================================
    # REDIRECT
    # =========================================================
    redirect-to-https:
      redirectScheme:
        scheme: https
        permanent: true

    # =========================================================
    # NEXTCLOUD — Special middleware chain
    # =========================================================
    nextcloud-redirect:
      redirectRegex:
        permanent: true
        regex: "https://(.*)/.well-known/(?:card|cal)dav"
        replacement: "https://${1}/remote.php/dav"
```

### 7.2 Update middleware chains

Update `appdata/traefik3/rules/$HOSTNAME/middlewares-chains.yml` (keep existing, add security-headers):

```yaml
http:
  middlewares:
    # Public — no auth, but with security headers
    chain-no-auth:
      chain:
        middlewares:
          - security-headers
          - rate-limit

    # OAuth — Google OAuth via traefik-forward-auth
    chain-oauth:
      chain:
        middlewares:
          - security-headers
          - rate-limit
          - oauth@docker

    # Authentik — SSO forward auth
    chain-authentik:
      chain:
        middlewares:
          - security-headers
          - rate-limit
          - middlewares-authentik@file

    # Nextcloud — special chain with redirect
    chain-nextcloud:
      chain:
        middlewares:
          - security-headers
          - nextcloud-redirect

    # Admin services — add local-only restriction
    chain-local-only:
      chain:
        middlewares:
          - security-headers
          - local-only
```

### 7.3 Add Authentik forward auth middleware definition

In `appdata/traefik3/rules/$HOSTNAME/middlewares.yml`, add:

```yaml
    # =========================================================
    # AUTHENTIK FORWARD AUTH
    # =========================================================
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
```

### 7.4 Update Traefik compose — add ping + stricter config

Add to `compose/reverse-proxy/compose.traefik.yml` command flags:

```yaml
command:
  # ... existing flags ...

  # Enable ping endpoint for health checks
  - --ping=true
  - --ping.entrypoint=traefik

  # Stricter log filtering
  - --accessLog.filters.statusCodes=400-599

  # Disable TLS 1.0 and 1.1
  - --entrypoints.websecure.http.tls.options=tls-opts@file
```

### 7.5 TLS options file

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

### 7.6 Apply `local-only` to sensitive admin services

Update labels for Adminer, Prometheus, and Alertmanager to use `chain-local-only@file` instead of `chain-oauth@file`. These services should only be accessible from your LAN, not the public internet:

```yaml
# compose/database/compose.adminer.yml
labels:
  - "traefik.http.routers.adminer-rtr.middlewares=chain-local-only@file"

# compose/monitoring/compose.prometheus.yml
labels:
  - "traefik.http.routers.prometheus-rtr.middlewares=chain-local-only@file"
```

---

## Phase 8 — Authentik Hardening

### 8.1 Complete revised `compose.authentik.yml`

Replace the existing file with this corrected version:

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
      # NO PUID/PGID — authentik is not a LinuxServer.io image
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
    # user: root is intentionally kept — worker needs Docker socket access
    user: root
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
```

### 8.2 Authentik outpost configuration

Authentik uses an "embedded outpost" for its forward auth. To ensure it works correctly with Traefik, verify in the Authentik UI:

1. Go to **Admin** → **Applications** → **Providers**
2. For each provider, ensure **Authentication flow** is set correctly
3. Go to **System** → **Outposts** → edit the embedded outpost
4. In the configuration, set:
   ```yaml
   log_level: info
   docker_labels:
     traefik.enable: "false"
   ```

---

## Phase 9 — Azure Backup Setup

### 9.1 Azure resources to create

**Required Azure resources (all in same resource group):**

| Resource | Type | Tier | Est. monthly cost |
|----------|------|------|-------------------|
| `homelab-rg` | Resource Group | — | Free |
| `homelabstorage<unique>` | Storage Account | Standard LRS | ~$0.018/GB |
| `homelab-backups` | Blob Container | Cool tier | ~$0.01/GB |

**Cost estimate for your setup:**
- Config/appdata (~50GB): ~$0.90/month (Cool tier)
- Database dumps (~5GB): ~$0.09/month
- **Total: well under $10/month** — leaves $130+ for compute if needed

### 9.2 Create Azure resources

```bash
# Install Azure CLI if not present
curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Login
az login

# Create resource group (choose your region)
az group create \
  --name homelab-rg \
  --location westeurope

# Create storage account (name must be globally unique, 3-24 lowercase alphanumeric)
STORAGE_ACCOUNT="homelabstorage$(openssl rand -hex 4)"
echo "Storage account name: $STORAGE_ACCOUNT"

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

# Get the account key (for restic/Backrest)
az storage account keys list \
  --resource-group homelab-rg \
  --account-name "$STORAGE_ACCOUNT" \
  --query "[0].value" \
  --output tsv
```

Save the output values to your `.env` file:
```bash
AZURE_ACCOUNT_NAME=homelabstorage<your-unique-suffix>
AZURE_ACCOUNT_KEY=<key-from-above>
AZURE_BACKUP_CONTAINER=homelab-backups
```

### 9.3 Configure Backrest for Azure

Backrest (which uses restic internally) supports Azure Blob Storage natively.

**Update `compose/productivity/compose.backrest.yml`** to add Azure env vars:

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
      # Azure Blob Storage for restic backend
      AZURE_ACCOUNT_NAME: ${AZURE_ACCOUNT_NAME}
      AZURE_ACCOUNT_KEY: ${AZURE_ACCOUNT_KEY}
    volumes:
      - $CONF_DIR/backrest/data:/data
      - $CONF_DIR/backrest/config:/config
      - $CONF_DIR/backrest/cache:/cache
      # Mount paths to back up (read-only where possible)
      - $CONF_DIR:/mnt/conf:ro
      - $DOCKER_DIR/compose:/mnt/compose:ro
      - $DOCKER_DIR/.env.enc:/mnt/env-enc:ro
      - $DOCKER_DIR/secrets:/mnt/secrets-enc:ro
    expose:
      - 9898
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9898/"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 20s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.backrest-rtr.entrypoints=websecure"
      - "traefik.http.routers.backrest-rtr.rule=Host(`backup.$DOMAINNAME_1`)"
      - "traefik.http.routers.backrest-rtr.middlewares=chain-authentik@file"
      - "traefik.http.routers.backrest-rtr.service=backrest-svc"
      - "traefik.http.services.backrest-svc.loadbalancer.server.port=9898"
```

### 9.4 Configure Backrest repositories in the UI

Access Backrest at `https://backup.$DOMAINNAME_1` and create repositories:

**Repository 1: Config Backup (daily)**
- **Name**: `azure-config`
- **URI**: `azure:homelab-backups:/config`
- **Password**: Generate with `openssl rand -hex 32` (store in your password manager)
- **Schedules**:
  - Backup: `0 3 * * *` (3 AM daily)
  - Prune: `0 4 * * 0` (Sunday 4 AM weekly)
- **Retention**: 30 daily, 12 weekly, 3 monthly
- **Paths to include**: `/mnt/conf` (all appdata)

**Repository 2: Database Dumps (daily)**
- **Name**: `azure-databases`
- **URI**: `azure:homelab-backups:/databases`
- **Password**: Different password from above
- **Schedules**:
  - Backup: `0 2 * * *` (2 AM daily — before config backup)
  - Prune: `0 4 * * 0`
- **Retention**: 30 daily, 8 weekly

**Repository 3: Compose Files + Encrypted Secrets (daily)**
- **Name**: `azure-compose`
- **URI**: `azure:homelab-backups:/compose`
- **Paths**: `/mnt/compose`, `/mnt/env-enc`, `/mnt/secrets-enc`

### 9.5 Database dump script

Create a pre-backup hook or a companion container for database dumps:

```bash
cat > /root/docker/scripts/backup-databases.sh << 'SCRIPT'
#!/bin/bash
# backup-databases.sh — Run before Backrest backup
# Creates dumps of all databases into a directory Backrest can read
set -euo pipefail

DUMP_DIR="/root/docker/appdata/backrest/db-dumps"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$DUMP_DIR"

echo "[$(date)] Starting database dumps..."

# PostgreSQL — full dump of all databases
echo "Dumping PostgreSQL..."
docker exec postgres pg_dumpall \
  -U "${PSQL_DBUSER:-postgres}" \
  --clean \
  --if-exists \
  > "$DUMP_DIR/postgres_${DATE}.sql"
gzip "$DUMP_DIR/postgres_${DATE}.sql"
echo "  PostgreSQL: done ($(du -sh "$DUMP_DIR/postgres_${DATE}.sql.gz" | cut -f1))"

# MongoDB — full dump
echo "Dumping MongoDB..."
docker exec mongo mongodump \
  --username "${MONGO_ROOT_USER:-admin}" \
  --password "${MONGO_ROOT_PASS}" \
  --authenticationDatabase admin \
  --archive \
  > "$DUMP_DIR/mongo_${DATE}.archive"
echo "  MongoDB: done ($(du -sh "$DUMP_DIR/mongo_${DATE}.archive" | cut -f1))"

# Keep only last 7 days of dumps locally (Backrest handles long-term retention)
find "$DUMP_DIR" -name "postgres_*.sql.gz" -mtime +7 -delete
find "$DUMP_DIR" -name "mongo_*.archive" -mtime +7 -delete

echo "[$(date)] Database dumps complete."
SCRIPT

chmod +x /root/docker/scripts/backup-databases.sh
```

Schedule it via cron (runs before Backrest backup at 2 AM):
```bash
crontab -e
# Add:
0 1 * * * /root/docker/scripts/backup-databases.sh >> /root/docker/logs/db-backup.log 2>&1
```

**Add the dump directory to Backrest's database repository path**: `/mnt/conf/backrest/db-dumps`

### 9.6 What NOT to back up to Azure

Configure Backrest exclusion patterns:
```
*.log
*.tmp
*.bak
traefik3/acme/
# Large media — use separate backup strategy (NAS, external HDD)
```

---

## Phase 10 — Renovate (Automated Updates)

### 10.1 Install Renovate GitHub App

1. Go to [github.com/apps/renovate](https://github.com/apps/renovate)
2. Install on your `docker-homelab` repository
3. Merge the initial onboarding PR Renovate creates

### 10.2 Create `.github/renovate.json5`

```bash
mkdir -p /root/docker/.github
```

```json5
// .github/renovate.json5
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": [
    "config:recommended",
    "docker:enableMajor"
  ],

  // Scan all compose files
  "docker-compose": {
    "fileMatch": [
      "(^|/)compose\\..*\\.ya?ml$",
      "(^|/)compose\\.ya?ml$"
    ]
  },

  // Track version variables in .env files
  "customManagers": [
    {
      "customType": "regex",
      "fileMatch": ["(^|/)\\.env\\.example$"],
      "matchStrings": [
        // Matches: # renovate: datasource=docker depName=image/name\nVAR_VERSION=v1.2.3
        "# renovate: datasource=(?<datasource>[^\\s]+) depName=(?<depName>[^\\s]+)\\n[A-Z_]+=(?<currentValue>.+)"
      ],
      "datasourceTemplate": "{{datasource}}"
    }
  ],

  "packageRules": [
    // Group LinuxServer.io updates (they release frequently)
    {
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["^lscr\\.io/linuxserver/"],
      "groupName": "LinuxServer.io containers",
      "schedule": ["every weekend"]
    },

    // Group monitoring stack
    {
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["grafana/", "prom/", "gcr.io/cadvisor"],
      "groupName": "Monitoring stack",
      "schedule": ["every weekend"]
    },

    // Group *arr media apps
    {
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["linuxserver/sonarr", "linuxserver/radarr", "linuxserver/prowlarr", "linuxserver/sabnzbd"],
      "groupName": "Arr media stack",
      "schedule": ["every weekend"]
    },

    // Group Immich (server + ml must update together)
    {
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["ghcr.io/immich-app/"],
      "groupName": "Immich",
      "schedule": ["every weekend"]
    },

    // Group Authentik (server + worker must update together)
    {
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["ghcr.io/goauthentik/server"],
      "groupName": "Authentik",
      "schedule": ["every weekend"]
    },

    // Database major versions — require manual review
    {
      "matchDatasources": ["docker"],
      "matchPackageNames": [
        "postgres",
        "ghcr.io/immich-app/postgres",
        "mongo",
        "redis"
      ],
      "matchUpdateTypes": ["major"],
      "enabled": false,
      "description": "Database major versions require manual migration — disabled"
    },

    // Auto-merge patch updates for low-risk services
    {
      "matchDatasources": ["docker"],
      "matchUpdateTypes": ["patch"],
      "matchPackagePatterns": [
        "lscr.io/linuxserver/",
        "grafana/loki",
        "grafana/promtail",
        "prom/node-exporter"
      ],
      "automerge": true,
      "automergeType": "pr",
      "schedule": ["every weekend"]
    },

    // Flag major updates with a label
    {
      "matchDatasources": ["docker"],
      "matchUpdateTypes": ["major"],
      "labels": ["major-update", "needs-review"],
      "automerge": false
    }
  ],

  // Prevent PR spam
  "prConcurrentLimit": 5,
  "prHourlyLimit": 2,
  "labels": ["renovate", "dependencies"]
}
```

### 10.3 Annotate `.env.example` for Renovate tracking

```bash
# In .env.example, add renovate comments above version variables:

# renovate: datasource=docker depName=ghcr.io/immich-app/immich-server
IMMICH_VERSION=v2.5.3

# renovate: datasource=docker depName=ghcr.io/goauthentik/server
AUTHENTIK_VERSION=2025.8.1
```

---

## Phase 11 — CI/CD with GitHub Actions

### 11.1 Create a deploy user on the LXC

```bash
# On your Docker LXC
useradd -m -s /bin/bash deploy
usermod -aG docker deploy

# Generate SSH key for GitHub Actions
su - deploy
ssh-keygen -t ed25519 -C "github-actions-deploy" -N "" -f ~/.ssh/github_deploy

cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys

# Display the private key to add to GitHub Secrets
cat ~/.ssh/github_deploy
# COPY THIS — goes into GitHub Secret: SERVER_SSH_KEY
```

### 11.2 Add GitHub repository secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret name | Value |
|-------------|-------|
| `SERVER_HOST` | Your server's IP or hostname |
| `SERVER_USER` | `deploy` |
| `SERVER_SSH_KEY` | Contents of `~/.ssh/github_deploy` (private key) |
| `DOCKER_DIR` | `/root/docker` |

### 11.3 Create `.github/workflows/deploy.yml`

```yaml
name: Deploy Docker Stack

on:
  push:
    branches: [main]
    paths:
      - 'compose/**'
      - 'compose.yml'
      - '.env.enc'
      - 'secrets/*.enc'
      - 'scripts/**'

  workflow_dispatch:
    inputs:
      force_recreate:
        description: 'Force recreate all containers'
        required: false
        default: 'false'
        type: boolean

jobs:
  validate:
    name: Validate compose files
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Docker Compose
        run: |
          sudo apt-get install -y docker-compose-plugin

      - name: Validate compose syntax
        run: |
          # Create a dummy .env for validation
          cp .env.example .env
          # Replace empty values with dummy values to pass validation
          sed -i 's/=$/=dummy/g' .env
          docker compose config --quiet && echo "Compose config is valid"

  deploy:
    name: Deploy to server
    runs-on: ubuntu-latest
    needs: validate
    environment: production
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          timeout: 120s
          script: |
            set -euo pipefail
            cd ${{ secrets.DOCKER_DIR }}

            echo "=== Pulling latest config ==="
            git pull origin main

            echo "=== Decrypting secrets ==="
            bash scripts/decrypt-secrets.sh

            echo "=== Pulling new images ==="
            docker compose pull --quiet

            echo "=== Applying changes ==="
            if [ "${{ github.event.inputs.force_recreate }}" = "true" ]; then
              docker compose up -d --force-recreate --remove-orphans
            else
              docker compose up -d --remove-orphans
            fi

            echo "=== Pruning old images ==="
            docker image prune -f

            echo "=== Checking container health ==="
            sleep 15
            UNHEALTHY=$(docker compose ps --format json | \
              python3 -c "
            import json, sys
            data = [json.loads(line) for line in sys.stdin if line.strip()]
            unhealthy = [c['Name'] for c in data if c.get('Health') == 'unhealthy']
            print('\n'.join(unhealthy))
            ")
            if [ -n "$UNHEALTHY" ]; then
              echo "WARNING: Unhealthy containers:"
              echo "$UNHEALTHY"
              # Don't fail the deploy — just warn (some start slowly)
            fi

            echo "=== Deploy complete ==="
```

### 11.4 Protect the main branch

In GitHub → **Settings** → **Branches** → **Add rule** for `main`:
- ✅ Require a pull request before merging
- ✅ Require status checks (add the `validate` job)
- ✅ Require branches to be up to date

This means Renovate PRs get validated before merging, and you can review all changes.

---

## Appendix A — Multi-LXC Architecture

> **This is now the primary goal.** The full, hardware-tailored multi-LXC migration guide has been moved to its own document:
>
> **`guides/MULTI_LXC_MIGRATION.md`**

That guide covers everything you need, specific to your hardware (i5-8600K, 32 GB RAM, Intel UHD 630, 2 TB NVMe + 72 TB RAID-5):

- LXC design and resource allocation (CPU/RAM/disk per LXC)
- Proxmox setup: vmbr1 internal bridge, NVMe storage pool, RAID-5 mounting
- LXC creation commands with exact flags
- Storage coupling via Proxmox bind mounts (RAID-5 → multiple LXCs)
- Intel UHD 630 GPU passthrough to both LXC 102 (Plex) and LXC 103 (Frigate) simultaneously
- USB passthrough for Zigbee coordinator into LXC 103
- Traefik cross-LXC routing via file-based dynamic config (no Docker labels across hosts)
- GitHub Actions multi-environment deployment with per-LXC secrets scoping
- Migration order and step-by-step service move playbook

### Quick summary: 7-LXC design

| LXC | Name | vCPU | RAM | Services |
|-----|------|------|-----|----------|
| 101 | infra | 2 | 4 GB | Traefik, Authentik, Postgres, Redis, MongoDB |
| 102 | media | 4 | 8 GB | Plex, *arr, SABnzbd, qBit+VPN [GPU] |
| 103 | home | 2 | 4 GB | HA, Frigate, Z2M, Mosquitto, Node-RED [GPU+USB] |
| 104 | productivity | 2 | 6 GB | Immich, Paperless, Nextcloud, n8n, Backrest |
| 105 | network | 1 | 1 GB | Pi-hole, Unifi |
| 106 | monitoring | 2 | 3 GB | Grafana, Prometheus, Loki, Promtail, exporters |
| 107 | utilities | 1 | 1 GB | Spoolman, OmniTools, Firefly |

Networking: `vmbr0` (internet) + `vmbr1` (10.10.0.0/24, LXC-internal only).
Traefik on LXC 101 routes to other LXCs via file-based dynamic config pointing to `10.10.0.X:PORT`.
GitHub Actions Environments (`prod-infra`, `prod-media`, etc.) scope secrets per LXC.

---

## Appendix B — Intel iGPU Passthrough in Proxmox LXC

Both Plex and Frigate need `/dev/dri`. Since they're currently in the same LXC (media + home-automation combined), or will be on separate LXCs when you split, here's how to configure GPU passthrough on each.

### B.1 Check host GPU devices

```bash
# On Proxmox host
ls -la /dev/dri/
# Expected output:
# card0 → main display
# renderD128 → render node (for hardware acceleration)
```

### B.2 Configure LXC for GPU access

Edit the LXC configuration file on the Proxmox host:

```bash
# On Proxmox host — replace <LXC_ID> with your LXC ID (e.g., 100)
nano /etc/pve/lxc/<LXC_ID>.conf
```

Add these lines:
```
# Intel iGPU passthrough
lxc.cgroup2.devices.allow: c 226:0 rwm
lxc.cgroup2.devices.allow: c 226:128 rwm
lxc.cgroup2.devices.allow: c 29:0 rwm
lxc.mount.entry: /dev/dri dev/dri none bind,optional,create=dir 0 0
lxc.mount.entry: /dev/dri/renderD128 dev/dri/renderD128 none bind,optional,create=file 0 0
```

> **If using privileged LXC**: The above is sufficient.
> **If using unprivileged LXC**: You also need to add the GID of the `render` and `video` groups:

```bash
# On Proxmox host — check GIDs
getent group render   # Usually GID 104
getent group video    # Usually GID 44

# In the LXC config, add:
# lxc.idmap: u 0 100000 65536
# lxc.idmap: g 0 100000 44
# lxc.idmap: g 44 44 1        <- video group passthrough
# lxc.idmap: g 45 100045 104  <- adjust to avoid gap
# lxc.idmap: g 104 104 1      <- render group passthrough
# lxc.idmap: g 105 100105 65431
```

For simplicity, use a **privileged LXC** for any LXC that needs GPU access.

### B.3 Verify inside the LXC

```bash
# Inside the LXC
ls -la /dev/dri/
# Should show card0 and renderD128

# Install vainfo to test
apt install -y vainfo
vainfo
# Should show: VA-API version 1.x.x, VAEntrypointVLD, etc.

# Plex and Frigate should now have GPU access
docker exec plex ls /dev/dri
```

### B.4 GPU considerations when splitting

| LXC | Needs GPU? | Services |
|-----|-----------|---------|
| LXC 2 (media) | Yes | Plex (QuickSync HW transcoding), Jellyfin (optional) |
| LXC 3 (home) | Yes | Frigate (OpenVINO object detection, i965 driver) |
| All others | No | — |

You will need to configure GPU passthrough on **both** LXC 2 and LXC 3 when you split. Each LXC gets independent access to the same iGPU. This is fine for Intel iGPU — unlike discrete GPUs, Intel iGPUs support concurrent access from multiple LXCs.

---

## Appendix C — Environment Variable Reference

Complete reference of all variables used across the stack.

```bash
# ============================================================
# PATHS
# ============================================================
DOCKER_DIR=/root/docker          # Repo root
CONF_DIR=/root/docker/appdata    # Container config data
MEDIA_DIR=/mnt/media             # Media files (movies, TV)
PHOTOS_DIR=/mnt/photos           # Photos (Immich)
LOG_DIR=/root/docker/logs        # Log files

# ============================================================
# USER
# ============================================================
PUID=1000    # User ID for LSIO containers
PGID=1000    # Group ID for LSIO containers
TZ=Europe/Amsterdam

# ============================================================
# NETWORKING
# ============================================================
DOMAINNAME_1=yourdomain.com
HOSTNAME=docker                  # Scopes traefik rules path
CLOUDFLARE_IPS=...               # Cloudflare IP ranges (see .env.example)
LOCAL_IPS=127.0.0.1/32,...       # Local IP ranges

# ============================================================
# TRAEFIK
# ============================================================
TRAEFIK_AUTH_BYPASS_KEY=<hex32>  # API bypass key for *arr apps

# ============================================================
# DATABASES
# ============================================================
PSQL_DBUSER=postgres
PSQL_DBPASS=<strong-password>
AUTHENTIK_DBNAME=authentik
AUTHENTIK_DBUSER=authentik
AUTHENTIK_DBPASS=<password>
PAPERLESS_DBNAME=paperless
PAPERLESS_DBUSER=paperless
PAPERLESS_DBPASS=<password>
NEXTCLOUD_DBNAME=nextcloud
NEXTCLOUD_DBUSER=nextcloud
NEXTCLOUD_DBPASS=<password>
N8N_DBNAME=n8n
N8N_DBUSER=n8n
N8N_DBPASS=<password>
PRINTER_CALCULATOR_DBNAME=printer_calculator
PRINTER_CALCULATOR_DBUSER=printer_calc
PRINTER_CALCULATOR_DBPASS=<password>
MONGO_ROOT_USER=admin
MONGO_ROOT_PASS=<password>

# ============================================================
# AUTHENTIK
# ============================================================
AUTHENTIK_SECRET=<hex50>         # openssl rand -hex 50
AUTHENTIK_VERSION=2025.8.1       # Renovate-tracked

# ============================================================
# IMMICH
# ============================================================
IMMICH_VERSION=v2.5.3            # Renovate-tracked

# ============================================================
# MEDIA
# ============================================================
PLEX_ADVERTISE_IP=https://<ip>:32400/
SONARR_API_KEY=
RADARR_API_KEY=
PROWLARR_API_KEY=
SABNZBD_API_KEY=
VPN_USER=
VPN_PASS=
VPN_PROV=
VPN_INPUT_PORTS=
VPN_OUTPUT_PORTS=
DN_API_KEY=

# ============================================================
# HOME AUTOMATION
# ============================================================
FRIGATE_RTSP_PASSWORD=
MOSQUITTO_USER=
MOSQUITTO_PASS=

# ============================================================
# NETWORK
# ============================================================
PIHOLE_WEB_PASS=

# ============================================================
# AZURE BACKUP
# ============================================================
AZURE_ACCOUNT_NAME=
AZURE_ACCOUNT_KEY=
AZURE_BACKUP_CONTAINER=homelab-backups
```

---

## Implementation Checklist

Use this to track progress:

- [ ] **Phase 1**: Git repo created, `.gitignore` in place, first commit pushed
- [ ] **Phase 2**: SOPS + age installed, `.env.enc` and `secrets/*.enc` committed
- [ ] **Phase 3**: Directories restructured, `compose.yml` updated, `docker compose config` passes
- [ ] **Phase 4**: `fragments/common-service.yml` created, exporters refactored
- [ ] **Phase 5**: PUID/PGID removed from non-LSIO, expose/ports fixed, versions pinned
- [ ] **Phase 6**: Health checks added to all services, `docker compose ps` shows health status
- [ ] **Phase 7**: Security headers, rate limiting, TLS opts, Traefik ping endpoint active
- [ ] **Phase 8**: Authentik versions via env var, healthcheck working, worker depends_on server
- [ ] **Phase 9**: Azure Storage created, Backrest configured for Azure, cron for DB dumps
- [ ] **Phase 10**: Renovate installed, `renovate.json5` committed, initial PRs reviewed
- [ ] **Phase 11**: Deploy user created, GitHub secrets set, Actions workflow tested
- [ ] **Appendix A**: Multi-LXC plan documented and understood
- [ ] **Appendix B**: GPU passthrough verified (vainfo shows GPU inside LXC)
