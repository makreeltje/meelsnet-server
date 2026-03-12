# Docker Infrastructure Improvement Guide

*Tailored to your Proxmox + Docker Compose + Traefik + Authentik setup*

---

## Table of Contents

1. [What You're Doing Well](#1-what-youre-doing-well)
2. [Audit: Concrete Issues Found in Your Files](#2-audit-concrete-issues-found-in-your-files)
3. [Reducing Repetition with Compose Extensions](#3-reducing-repetition-with-compose-extensions)
4. [Hosting on GitHub — Repository Structure](#4-hosting-on-github--repository-structure)
5. [Secrets Management for Git](#5-secrets-management-for-git)
6. [Renovate for Automated Image Updates](#6-renovate-for-automated-image-updates)
7. [CI/CD and Deployment Pipeline](#7-cicd-and-deployment-pipeline)
8. [Image Pinning Strategy](#8-image-pinning-strategy)
9. [Environment File Hygiene](#9-environment-file-hygiene)
10. [Compose File Structural Improvements](#10-compose-file-structural-improvements)
11. [Backup and Disaster Recovery](#11-backup-and-disaster-recovery)
12. [Preparing for Multi-Node (Future Proxmox Split)](#12-preparing-for-multi-node)
13. [Recommended Migration Order](#13-recommended-migration-order)

---

## 1. What You're Doing Well

Before diving into improvements, it's worth acknowledging the things your setup already does right:

- **Split compose files with `include`** — This is the modern, clean way to organize Docker Compose. Many people still cram everything into a single 2,000-line file. Your category-based split (reverse-proxy, media-server, monitoring, server) is logical and maintainable.
- **Environment variables** for paths ($DOCKER_DIR, $CONF_DIR, $MEDIA_DIR) — Makes the setup portable.
- **Profiles** ("media", "all") — Lets you selectively start groups of services.
- **File-based Docker secrets** — Better than hardcoding credentials in compose files.
- **Consistent naming convention** — `compose.<service>.yml` is clean and predictable.
- **Traefik with Authentik** — Solid choice for reverse proxy + SSO.
- **Pinned image versions** (e.g., `bazarr:1.5.3`) — Critical for reproducibility and Renovate compatibility.

So the foundation is strong. The improvements below are about taking it to the next level.

---

## 2. Audit: Concrete Issues Found in Your Files

After reviewing bazarr, immich, mosquitto, frigate, authentik, and your exporters file, here are the specific issues worth fixing.

### 2.1 PUID/PGID applied to containers that don't use them

`PUID` and `PGID` are a **LinuxServer.io convention**. Only images from `lscr.io/linuxserver/` actually read these variables. You're setting them on containers that completely ignore them:

| Container | Image | Uses PUID/PGID? |
|-----------|-------|-----------------|
| bazarr | `lscr.io/linuxserver/bazarr` | Yes (LSIO) |
| sonarr, radarr, prowlarr, etc. | `lscr.io/linuxserver/*` | Yes (LSIO) |
| immich | `ghcr.io/immich-app/immich-server` | **No** |
| immich-machine-learning | `ghcr.io/immich-app/immich-machine-learning` | **No** |
| mosquitto | `eclipse-mosquitto` | **No** |
| frigate | `ghcr.io/blakeblackshear/frigate` | **No** |
| authentik | `ghcr.io/goauthentik/server` | **No** |
| exportarr instances | `ghcr.io/onedr0p/exportarr` | **No** |
| smartctl-exporter | `prometheuscommunity/smartctl-exporter` | **No** |
| mosquitto-exporter | `sapcc/mosquitto-exporter` | **No** |

This isn't breaking anything — the containers just ignore the variables — but it adds clutter and gives a false impression that you're controlling the user mapping. It matters when you're debugging permission issues: you might think you've set the UID/GID, but non-LSIO containers run as whatever user is baked into the image (usually root, or a service-specific user).

**Fix:** Only include PUID/PGID on LinuxServer.io containers. For non-LSIO containers that need user mapping, use Docker's `user:` directive instead:

```yaml
# LSIO container — uses PUID/PGID
bazarr:
  environment:
    - PUID=$PUID
    - PGID=$PGID
    - TZ=$TZ

# Non-LSIO container — only needs TZ (or nothing)
immich:
  environment:
    - TZ=$TZ
  # If you need to control the user:
  # user: "${PUID}:${PGID}"
```

This is exactly why the `extends` fragments should have separate base services (`common-lsio` vs `common-base`), covered in section 3.

### 2.2 `expose` + `ports` redundancy

In your immich file:
```yaml
expose:
  - 2283
ports:
  - 2283:2283
```

The `ports` directive already makes the port available to other containers on the same network AND publishes it to the host. The `expose` line is completely redundant here. Same applies to your frigate config (`expose: 5000` alongside `ports: 5001:5000`).

**Rule of thumb:**
- **Behind Traefik only:** Use just `expose` (no `ports`). Traefik reaches the container on the Docker network. This is the bazarr pattern — correct.
- **Needs direct host access:** Use just `ports`. Drop `expose`.
- **Both Traefik AND direct access needed:** Use just `ports`. Traefik can still reach it on the Docker network.

**Fix for immich** — Immich is behind Traefik (`traefik.enable=true` in labels) but also has `ports: 2283:2283`. Ask yourself: do you actually need direct port access to Immich, or is it always accessed through Traefik? If always through Traefik, remove the `ports` mapping. If the mobile app connects directly (bypassing Traefik), keep `ports` but remove `expose`.

**Fix for frigate** — The ports for RTSP (8554) and WebRTC (8555) genuinely need direct host access for camera streams. The web UI on port 5000 goes through Traefik. So this is reasonable, but drop the `expose: 5000`:
```yaml
# Frigate — cleaned up
ports:
  - 5001:5000       # Web UI direct access (if needed alongside Traefik)
  - 8554:8554       # RTSP
  - 8555:8555/tcp   # WebRTC TCP
  - 8555:8555/udp   # WebRTC UDP
# No 'expose' needed
```

### 2.3 Duplicated image versions for multi-container services

Your immich and authentik compose files each define the same image version twice:

```yaml
# Immich — same version on two services
immich:
  image: ghcr.io/immich-app/immich-server:v2.5.3
immich-machine-learning:
  image: ghcr.io/immich-app/immich-machine-learning:v2.5.3

# Authentik — same version on two services
authentik:
  image: ghcr.io/goauthentik/server:2025.8.1
authentik-worker:
  image: ghcr.io/goauthentik/server:2025.8.1
```

If you update one and forget the other, you'll have a version mismatch. For immich this can cause database migration failures; for authentik the worker and server must always match.

**Fix — use a YAML anchor within the same file:**
```yaml
x-immich-version: &immich-version "v2.5.3"

services:
  immich:
    image: ghcr.io/immich-app/immich-server:${IMMICH_VERSION:-v2.5.3}
  immich-machine-learning:
    image: ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION:-v2.5.3}
```

Or even simpler, use an environment variable in `.env`:
```bash
IMMICH_VERSION=v2.5.3
AUTHENTIK_VERSION=2025.8.1
```

```yaml
services:
  immich:
    image: ghcr.io/immich-app/immich-server:${IMMICH_VERSION}
  immich-machine-learning:
    image: ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION}
```

**Important Renovate note:** Renovate can detect and update environment variables in `.env` files when they follow the pattern `_VERSION=`. You'll need to add a `regexManagers` config for this (see section 6 for the Renovate config addition).

Alternatively, if you keep the versions inline, Renovate will naturally create PRs that update both image lines, since it bumps by package name. But the env var approach is cleaner for readability.

### 2.4 Exporters are the #1 candidate for `extends`

Your exporters file is the poster child for DRY improvement. Four exportarr instances are virtually identical:

```yaml
# The pattern repeats 4 times, only these values change:
#   command:  [sonarr] / [radarr] / [prowlarr] / [sabnzbd]
#   PORT:     9707 / 9708 / 9710 / 9711
#   URL:      http://sonarr:8989 / http://radarr:7878 / ...
#   APIKEY:   $SONARR_API_KEY / $RADARR_API_KEY / ...
```

**Fix — create an exportarr base service in your fragments:**

`compose/fragments/common-service.yml` (add to existing):
```yaml
services:
  # ... existing common and common-lsio ...

  exportarr-base:
    image: ghcr.io/onedr0p/exportarr:v2.0.1
    restart: unless-stopped
    profiles: ["monitoring", "all"]
    networks:
      - t3_proxy
    environment:
      TZ: ${TZ}
```

Then your exporters file becomes:
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
      - 9707:9707

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

  # These two are different images, so they don't extend exportarr-base
  mosquitto-exporter:
    extends:
      file: ../fragments/common-service.yml
      service: common
    container_name: mosquitto-exporter
    image: sapcc/mosquitto-exporter:0.8.0  # PIN THIS VERSION
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
    image: prometheuscommunity/smartctl-exporter:v0.12.0  # PIN THIS VERSION
    profiles: ["monitoring", "all"]
    privileged: true
    user: root
    ports:
      - "9633:9633"
```

This cuts the exporters file roughly in half and — critically — means updating the exportarr image version only needs to happen in one place (the fragment).

### 2.5 Unversioned images

Two images have no version tags:

```yaml
image: sapcc/mosquitto-exporter          # No version
image: prometheuscommunity/smartctl-exporter  # No version
```

This means you're pulling `latest` every time, which is unpredictable. Pin these:

```yaml
image: sapcc/mosquitto-exporter:0.8.0
image: prometheuscommunity/smartctl-exporter:v0.12.0
```

Check Docker Hub for the current versions of these images. Without pinned versions, Renovate also cannot track or update them.

### 2.6 Inconsistent Traefik label patterns

Across your services, the Traefik labels have inconsistencies:

| Service | Has `tls=true`? | Has bypass route? | Auth middleware |
|---------|----------------|-------------------|-----------------|
| bazarr | No | Yes (bypass key) | chain-authentik@file |
| immich | Yes | No | chain-no-auth@file |
| frigate | Yes | No | chain-authentik@file |
| authentik | Yes | No | chain-no-auth@file |

Observations:
- Some services have `traefik.http.routers.X.tls=true` and some don't. If your Traefik entrypoint `websecure` already enforces TLS (which it almost certainly does if it's on port 443), the `tls=true` label is redundant. Pick one approach and use it everywhere.
- The bypass route pattern (bazarr) with `TRAEFIK_AUTH_BYPASS_KEY` is useful for API access. Consider whether other services (sonarr, radarr, prowlarr) also need this for webhook/API callbacks and apply consistently.

**Fix:** Standardize on one pattern. If using file-based Traefik dynamic config (recommended in section 3), you can define middleware chains once and reference them consistently.

### 2.7 What's actually good in these files

Worth calling out the positive patterns too:

- **Authentik's `depends_on` with health check conditions** — This is the gold standard. Apply this pattern to every service that needs a database (immich, paperless, nextcloud, n8n, etc.).
- **Immich's `env_file` approach** — Using `$CONF_DIR/immich/.env` for service-specific config is clean. Keeps the compose file from being polluted with 20 Immich-specific variables. Consider this pattern for other services with many config variables (Authentik, Frigate, Paperless).
- **Frigate's hardware passthrough** — The `devices`, `shm_size`, and `tmpfs` config is correct and well-done. Just note that this pins Frigate to a specific host with Intel GPU, which will matter when you split nodes.
- **Consistent use of profiles** — Every service has a profile assigned, which is great for selective startup.

---

## 3. Reducing Repetition with Compose Extensions

This is probably the single biggest quick win. Looking at your bazarr example, every service likely repeats the same pattern:

```yaml
restart: unless-stopped
networks:
  - t3_proxy
environment:
  - PGID=$PGID
  - PUID=$PUID
  - TZ=$TZ
```

And the Traefik labels follow a highly predictable template. Docker Compose supports **extension fields** (the `x-` prefix) that let you define reusable fragments.

### 2.1 Create a shared extensions file

Create a new file: `compose/fragments/x-common.yml`

```yaml
# Common service defaults
x-common: &common
  restart: unless-stopped
  networks:
    - t3_proxy

# Common environment variables for LinuxServer.io containers
x-lsio-env: &lsio-env
  PGID: ${PGID}
  PUID: ${PUID}
  TZ: ${TZ}

# For containers that only need TZ
x-base-env: &base-env
  TZ: ${TZ}
```

### 2.2 Refactor a service file to use extensions

**Before** (your current bazarr):
```yaml
services:
  bazarr:
    container_name: bazarr
    image: lscr.io/linuxserver/bazarr:1.5.3
    restart: unless-stopped
    profiles: ["media", "all"]
    networks:
      - t3_proxy
    environment:
      - PGID=$PGID
      - PUID=$PUID
      - TZ=$TZ
    volumes:
      - $CONF_DIR/bazarr/config:/config
      - $MEDIA_DIR/movies:/movies
      - $MEDIA_DIR/tv-shows:/tv
    expose:
      - 6767
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.bazarr-rtr-bypass.entrypoints=websecure"
      - "traefik.http.routers.bazarr-rtr-bypass.rule=Host(`subtitles.$DOMAINNAME_1`) && Header(`traefik-auth-bypass-key`, `$TRAEFIK_AUTH_BYPASS_KEY`)"
      - "traefik.http.routers.bazarr-rtr-bypass.priority=100"
      - "traefik.http.routers.bazarr-rtr.entrypoints=websecure"
      - "traefik.http.routers.bazarr-rtr.rule=Host(`subtitles.$DOMAINNAME_1`)"
      - "traefik.http.routers.bazarr-rtr.priority=99"
      - "traefik.http.routers.bazarr-rtr-bypass.middlewares=chain-no-auth@file"
      - "traefik.http.routers.bazarr-rtr.middlewares=chain-authentik@file"
      - "traefik.http.routers.bazarr-rtr.service=bazarr-svc"
      - "traefik.http.routers.bazarr-rtr-bypass.service=bazarr-svc"
      - "traefik.http.services.bazarr-svc.loadbalancer.server.port=6767"
```

**After** (using extensions):
```yaml
services:
  bazarr:
    <<: *common
    container_name: bazarr
    image: lscr.io/linuxserver/bazarr:1.5.3
    profiles: ["media", "all"]
    environment:
      <<: *lsio-env
    volumes:
      - $CONF_DIR/bazarr/config:/config
      - $MEDIA_DIR/movies:/movies
      - $MEDIA_DIR/tv-shows:/tv
    expose:
      - 6767
    labels:
      <<: *traefik-labels
      # Only the unique parts:
      traefik.http.routers.bazarr-rtr.rule: "Host(`subtitles.$DOMAINNAME_1`)"
      traefik.http.routers.bazarr-rtr-bypass.rule: "Host(`subtitles.$DOMAINNAME_1`) && Header(`traefik-auth-bypass-key`, `$TRAEFIK_AUTH_BYPASS_KEY`)"
      traefik.http.services.bazarr-svc.loadbalancer.server.port: "6767"
```

### 2.3 Traefik label templates

The Traefik labels are the most repetitive part. Unfortunately, YAML anchors can't do string interpolation (you can't template the service name into labels). There are two approaches:

**Option A: Accept some repetition, but use a consistent template.** Create a documented label template in your repo that you copy-paste when adding new services. This is the simplest approach and what most people do.

**Option B: Use a script or templating tool.** For example, a small Python or bash script that generates the compose file from a simpler config:

```yaml
# services.yml (your simplified input)
bazarr:
  image: lscr.io/linuxserver/bazarr:1.5.3
  subdomain: subtitles
  port: 6767
  auth: authentik  # or "none", "oauth", "basic"
  profiles: ["media", "all"]
  type: lsio  # implies PUID/PGID/TZ
  volumes:
    - $CONF_DIR/bazarr/config:/config
    - $MEDIA_DIR/movies:/movies
    - $MEDIA_DIR/tv-shows:/tv
```

The script would generate the full compose file with all the Traefik labels. This is more work upfront but pays off when you have 30+ services with the same label pattern.

**Option C: Move Traefik configuration to file-based dynamic config** instead of labels. In your Traefik `rules/` directory, define routers and services in YAML files. This separates routing from container definitions and makes the compose files much shorter. Example:

```yaml
# traefik3/rules/bazarr.yml
http:
  routers:
    bazarr-rtr:
      entryPoints:
        - websecure
      rule: "Host(`subtitles.{{env "DOMAINNAME_1"}}`)"
      middlewares:
        - chain-authentik@file
      service: bazarr-svc
      priority: 99
    bazarr-rtr-bypass:
      entryPoints:
        - websecure
      rule: "Host(`subtitles.{{env "DOMAINNAME_1"}}`) && Header(`traefik-auth-bypass-key`, `{{env "TRAEFIK_AUTH_BYPASS_KEY"}}`)"
      middlewares:
        - chain-no-auth@file
      service: bazarr-svc
      priority: 100
  services:
    bazarr-svc:
      loadBalancer:
        servers:
          - url: "http://bazarr:6767"
```

Then your compose file for bazarr becomes just:
```yaml
services:
  bazarr:
    <<: *common
    container_name: bazarr
    image: lscr.io/linuxserver/bazarr:1.5.3
    profiles: ["media", "all"]
    environment:
      <<: *lsio-env
    volumes:
      - $CONF_DIR/bazarr/config:/config
      - $MEDIA_DIR/movies:/movies
      - $MEDIA_DIR/tv-shows:/tv
    labels:
      - "traefik.enable=true"
```

This is the cleanest approach and is especially nice when routing rules get complex.

### 2.4 How to make extensions work with `include`

There's a catch: YAML anchors don't work across files with Docker Compose `include`. Each included file is parsed independently. You have two options:

**Option 1: Define extensions in your root `compose.yml` and reference them.** Unfortunately, this doesn't work with `include` either — extensions in the parent aren't available to included files.

**Option 2: Use `extends` (Docker Compose v2.24.6+).** This is the proper Compose-native way:

Create `compose/fragments/common-service.yml`:
```yaml
services:
  # Base: just restart policy, network, and timezone
  # Use for: non-LSIO containers (immich, frigate, authentik, exporters, etc.)
  common:
    restart: unless-stopped
    networks:
      - t3_proxy
    environment:
      TZ: ${TZ}

  # LSIO: adds PUID/PGID for LinuxServer.io containers
  # Use for: bazarr, sonarr, radarr, prowlarr, sabnzbd, tautulli, etc.
  common-lsio:
    restart: unless-stopped
    networks:
      - t3_proxy
    environment:
      PGID: ${PGID}
      PUID: ${PUID}
      TZ: ${TZ}

  # DB-dependent: common + depends_on for database services
  # Use for: immich, authentik, paperless, nextcloud, n8n, etc.
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

  # Exportarr base: shared config for all *arr Prometheus exporters
  exportarr-base:
    image: ghcr.io/onedr0p/exportarr:v2.0.1
    restart: unless-stopped
    profiles: ["monitoring", "all"]
    networks:
      - t3_proxy
    environment:
      TZ: ${TZ}
```

Then in each service file:
```yaml
# LSIO container (bazarr, sonarr, radarr, etc.)
services:
  bazarr:
    extends:
      file: ../fragments/common-service.yml
      service: common-lsio
    container_name: bazarr
    image: lscr.io/linuxserver/bazarr:1.5.3
    # ... rest of config

# Non-LSIO container (immich, frigate, etc.)
services:
  immich:
    extends:
      file: ../fragments/common-service.yml
      service: common-db       # Gets depends_on for postgres + redis
    container_name: immich
    image: ghcr.io/immich-app/immich-server:${IMMICH_VERSION}
    # ... rest of config

# Exporter (sonarr-exporter, radarr-exporter, etc.)
services:
  sonarr-exporter:
    extends:
      file: ../fragments/common-service.yml
      service: exportarr-base  # Gets image, restart, profile, network
    container_name: sonarr-exporter
    command: ["sonarr"]
    environment:
      PORT: "9707"
      URL: http://sonarr:8989
      APIKEY: $SONARR_API_KEY
```

This is the recommended approach for your multi-file setup. Having distinct base services ensures PUID/PGID only goes where it belongs, database dependencies are consistently declared, and exportarr config lives in one place.

---

## 4. Hosting on GitHub — Repository Structure

### 3.1 Recommended repo layout

```
docker-server/
├── .github/
│   ├── renovate.json5          # Renovate configuration
│   └── workflows/
│       └── deploy.yml          # GitHub Actions deployment
├── compose/
│   ├── fragments/
│   │   └── common-service.yml  # Shared service templates
│   ├── media-server/
│   ├── monitoring/
│   ├── reverse-proxy/
│   └── server/
├── traefik3/
│   └── rules/                  # Traefik dynamic config (if using file provider)
├── scripts/
│   ├── deploy.sh               # Deployment script
│   └── update-docker-hosts.sh
├── .env.example                # Template with all required variables (no values)
├── .gitignore
├── .sops.yaml                  # SOPS configuration (for encrypted secrets)
├── compose.yml
├── secrets.enc.env             # Encrypted secrets (safe to commit)
└── README.md
```

### 3.2 What goes in .gitignore

```gitignore
# Environment and secrets (unencrypted)
.env
secrets/

# Application data (NEVER commit this)
appdata/

# Logs
logs/
*.log

# Traefik ACME certificates
traefik3/acme/

# Temporary files
*.tmp
*.bak
```

### 3.3 What to commit vs. what to keep out

| Commit | Do NOT commit |
|--------|--------------|
| All compose files | `.env` file |
| Traefik rules (dynamic config) | `secrets/` directory |
| Scripts | `appdata/` (container data) |
| `.env.example` (template) | `traefik3/acme/` (certificates) |
| Encrypted secrets (SOPS) | Logs |
| Renovate config | Backup files |
| CI/CD workflows | |

---

## 5. Secrets Management for Git

Your current file-based secrets are fine for local use, but you can't commit them to Git. Here are your options, ranked by practicality:

### 4.1 SOPS + age (Recommended)

**Mozilla SOPS** encrypts files so they're safe to commit. **age** is a simple, modern encryption tool (easier than GPG).

Setup:
```bash
# Install on your server
apt install age
# Download sops binary from GitHub releases

# Generate an age key
age-keygen -o ~/.config/sops/age/keys.txt
# This outputs a public key like: age1xxxxxxxxxx...
```

Create `.sops.yaml` in your repo root:
```yaml
creation_rules:
  - path_regex: \.enc\.env$
    age: "age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  - path_regex: secrets/.*\.enc$
    age: "age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Encrypt your secrets:
```bash
# Encrypt entire .env file
sops --encrypt .env > .env.enc

# Or encrypt individual secret files
sops --encrypt secrets/cf_dns_api_token > secrets/cf_dns_api_token.enc
```

In your deployment script, decrypt before starting:
```bash
sops --decrypt .env.enc > .env
sops --decrypt secrets/cf_dns_api_token.enc > secrets/cf_dns_api_token
```

**Why this is the best option:** Simple, no external service dependency, encrypted files are safe to commit, and the age private key only needs to exist on your server (and in a secure backup).

### 4.2 Alternative: GitHub Secrets + CI/CD

Store secrets in GitHub's encrypted secrets and inject them during deployment. Good if you're fully committing to GitHub Actions for deployment, but means your secrets are tied to GitHub.

### 4.3 Alternative: HashiCorp Vault or Infisical

Overkill for a homelab, but worth mentioning. Only consider if you're running 50+ services or have a team.

---

## 6. Renovate for Automated Image Updates

Renovate is perfect for your setup. It will scan your compose files, detect Docker image versions, check for updates, and create pull requests.

### 5.1 Basic Renovate configuration

Create `.github/renovate.json5`:
```json5
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

  // Group updates to reduce PR noise
  "packageRules": [
    {
      // Group all LinuxServer.io updates together
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["^lscr\\.io/linuxserver/"],
      "groupName": "LinuxServer.io containers",
      "schedule": ["every weekend"]
    },
    {
      // Auto-merge patch updates (e.g., 1.5.3 -> 1.5.4)
      "matchDatasources": ["docker"],
      "matchUpdateTypes": ["patch"],
      "automerge": true,
      "automergeType": "pr",
      "schedule": ["every weekend"]
    },
    {
      // Hold major updates for manual review
      "matchDatasources": ["docker"],
      "matchUpdateTypes": ["major"],
      "labels": ["major-update"],
      "automerge": false
    },
    {
      // Group monitoring stack updates
      "matchDatasources": ["docker"],
      "matchPackagePatterns": ["grafana", "prom", "loki"],
      "groupName": "Monitoring stack",
      "schedule": ["every weekend"]
    },
    {
      // Pin specific containers that break often
      "matchDatasources": ["docker"],
      "matchPackageNames": ["postgres"],
      "allowedVersions": "!/^17/",  // Example: stay on PG16
      "enabled": true
    }
  ],

  // Limit open PRs to avoid overwhelming
  "prConcurrentLimit": 5,
  "prHourlyLimit": 2,

  // Labels for organization
  "labels": ["renovate", "dependencies"]
}
```

### 5.2 Important: Pin ALL images for Renovate to work

Renovate needs version tags to detect updates. Go through your compose files and make sure every image has a pinned version, not `latest` or no tag. For example:

```yaml
# BAD - Renovate can't track this
image: postgres
image: postgres:latest

# GOOD - Renovate will detect updates
image: postgres:16.4
image: lscr.io/linuxserver/bazarr:1.5.3

# BEST - Pin to digest for maximum reproducibility
image: postgres:16.4@sha256:abc123...
```

### 6.3 Handling version variables in .env files

If you adopt the env var approach for multi-container services (like `IMMICH_VERSION=v2.5.3` in `.env`), add a regex manager so Renovate can detect and update these:

```json5
  "customManagers": [
    {
      "customType": "regex",
      "fileMatch": ["(^|/)\\.env$", "(^|/)\\.env\\.example$"],
      "matchStrings": [
        "# renovate: datasource=docker depName=(?<depName>[^\\s]+)\\n[A-Z_]+=(?<currentValue>.+)"
      ],
      "datasourceTemplate": "docker"
    }
  ]
```

Then annotate your `.env` file with comments Renovate can parse:
```bash
# renovate: datasource=docker depName=ghcr.io/immich-app/immich-server
IMMICH_VERSION=v2.5.3

# renovate: datasource=docker depName=ghcr.io/goauthentik/server
AUTHENTIK_VERSION=2025.8.1
```

Renovate will now create PRs to bump these version variables automatically.

### 6.4 Install Renovate

Go to [github.com/apps/renovate](https://github.com/apps/renovate) and install it on your repository. It's free for public and private repos.

---

## 7. CI/CD and Deployment Pipeline

### 6.1 Deployment strategy

The simplest reliable approach for a homelab:

```
GitHub (merge PR) → GitHub Actions → SSH to server → git pull + docker compose up -d
```

### 6.2 GitHub Actions workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy Docker Stack

on:
  push:
    branches: [main]
    paths:
      - 'compose/**'
      - 'compose.yml'
      - 'traefik3/rules/**'
      - 'scripts/**'

  # Allow manual trigger
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /path/to/your/docker-server
            git pull origin main

            # Decrypt secrets if using SOPS
            sops --decrypt .env.enc > .env

            # Pull new images and recreate changed containers
            docker compose pull
            docker compose up -d --remove-orphans

            # Prune old images
            docker image prune -f

            # Health check (optional)
            sleep 10
            docker compose ps --format json | jq -r '.[] | select(.State != "running") | .Name' > /tmp/failed_containers
            if [ -s /tmp/failed_containers ]; then
              echo "WARNING: Some containers are not running:"
              cat /tmp/failed_containers
              exit 1
            fi
```

### 6.3 Setting up SSH access

On your Proxmox container:
```bash
# Create a deploy user with limited permissions
useradd -m deploy
usermod -aG docker deploy

# Generate SSH keypair on the server (or use an existing one)
su - deploy
ssh-keygen -t ed25519 -C "github-actions-deploy"

# Add the public key to authorized_keys
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
```

Add the **private key** as a GitHub secret (`SERVER_SSH_KEY`), along with your server's IP (`SERVER_HOST`) and the username (`SERVER_USER`).

### 6.4 Alternative: Webhook-based deployment (simpler)

If you don't want GitHub Actions SSH access, run a lightweight webhook listener on your server:

```bash
# Install webhook
apt install webhook

# Create webhook config
cat > /etc/webhook.conf << 'EOF'
[
  {
    "id": "deploy-docker",
    "execute-command": "/opt/docker-server/scripts/deploy.sh",
    "command-working-directory": "/opt/docker-server",
    "trigger-rule": {
      "match": {
        "type": "payload-hmac-sha256",
        "secret": "your-webhook-secret",
        "parameter": {
          "source": "header",
          "name": "X-Hub-Signature-256"
        }
      }
    }
  }
]
EOF
```

Then add a GitHub webhook pointing to `https://deploy.yourdomain.com/hooks/deploy-docker`. You can even route this through Traefik.

---

## 8. Image Pinning Strategy

You're already pinning some images (good!). Here's a consistent strategy:

### 7.1 Pin to minor or patch

For most services, pin to the **patch version**:
```yaml
image: lscr.io/linuxserver/bazarr:1.5.3    # Patch
image: postgres:16.4                         # Patch
```

This lets Renovate suggest updates while keeping your stack stable.

### 7.2 Special cases

- **Databases (Postgres, MongoDB, Redis):** Pin to **major** version. Database major upgrades need manual migration.
  ```yaml
  image: postgres:16    # Major pin — upgrade manually
  image: mongo:7        # Major pin
  image: redis:7        # Major pin
  ```
  Configure Renovate to only suggest minor/patch updates for these.

- **Frigate, Home Assistant:** These can have breaking changes in minor versions. Pin to patch and review PRs carefully.

- **Traefik:** Pin to minor at minimum (`traefik:3.2`). Traefik occasionally introduces breaking changes in minor versions.

---

## 9. Environment File Hygiene

### 8.1 Create a comprehensive .env.example

This serves as documentation and a template for new setups:

```bash
# ===== PATHS =====
DOCKER_DIR=/opt/docker-server
CONF_DIR=/opt/docker-server/appdata
MEDIA_DIR=/mnt/media
LOG_DIR=/opt/docker-server/logs

# ===== USER =====
PUID=1000
PGID=1000
TZ=Europe/Amsterdam  # Change to your timezone

# ===== DOMAINS =====
DOMAINNAME_1=example.com

# ===== TRAEFIK =====
TRAEFIK_AUTH_BYPASS_KEY=  # Generate: openssl rand -hex 32

# ===== DATABASE =====
POSTGRES_USER=
POSTGRES_PASSWORD=  # Generate: openssl rand -base64 32

# ===== AUTHENTIK =====
AUTHENTIK_SECRET_KEY=  # Generate: openssl rand -hex 50
AUTHENTIK_POSTGRESQL_PASSWORD=

# ... etc for each service that needs credentials
```

### 8.2 Consider splitting .env files

For a setup this size, a single `.env` can get unwieldy. Consider:

```
.env                    # Common variables (paths, PUID, TZ, domain)
.env.authentik          # Authentik-specific
.env.databases          # Database credentials
.env.immich             # Immich-specific
```

Then in your compose files, use `env_file`:
```yaml
services:
  authentik:
    env_file:
      - ../../.env
      - ../../.env.authentik
```

---

## 10. Compose File Structural Improvements

### 9.1 Use `expose` consistently (you're already doing this)

You're correctly using `expose` instead of `ports` for services behind Traefik. Keep doing this. Only use `ports` for services that need direct access (e.g., Pi-hole DNS on port 53, Unifi on specific UDP ports).

### 9.2 Add health checks

Health checks let Docker (and monitoring) know if a service is actually working:

```yaml
services:
  bazarr:
    # ... existing config ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6767/api/system/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

Not every service supports a health endpoint, but most *arr apps and databases do. At minimum, add health checks to:
- Postgres (`pg_isready`)
- Redis (`redis-cli ping`)
- MongoDB (`mongosh --eval "db.runCommand('ping')"`)
- Traefik (`traefik healthcheck`)

### 9.3 Add resource limits

Prevent any single container from eating all your RAM:

```yaml
services:
  plex:
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 2G

  bazarr:
    deploy:
      resources:
        limits:
          memory: 512M
```

Especially important for: Plex (transcoding), Frigate (video processing), Immich (ML), databases, and n8n (workflow automation can spike).

### 9.4 Add `depends_on` with conditions

For services that need databases:

```yaml
services:
  immich:
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
```

This prevents services from crashing during startup because their database isn't ready yet.

### 9.5 Consolidate your profiles

Consider expanding your profiles system:

```yaml
profiles: ["media", "all"]           # Media stack
profiles: ["monitoring", "all"]      # Monitoring
profiles: ["home", "all"]            # Home automation
profiles: ["infra", "all"]           # Infrastructure (Traefik, DBs)
profiles: ["productivity", "all"]    # Paperless, Nextcloud, etc.
```

This lets you do things like:
```bash
docker compose --profile media up -d      # Just media stack
docker compose --profile infra up -d      # Just infrastructure
docker compose --profile all up -d        # Everything
```

---

## 11. Backup and Disaster Recovery

### 10.1 What to back up

You already have Backrest listed — good. Make sure you're backing up:

1. **`appdata/` directory** — This is the most critical. Container configs, databases, etc.
2. **Your compose repo** — Handled by Git.
3. **`.env` file and secrets** — Handled by SOPS if you adopt it.
4. **Database dumps** (not just the data directory) — File-level Postgres backups can be inconsistent. Schedule `pg_dumpall` as a cron job:

```bash
# scripts/backup-databases.sh
#!/bin/bash
BACKUP_DIR="/opt/backups/databases"
DATE=$(date +%Y%m%d_%H%M%S)

# Postgres
docker exec postgres pg_dumpall -U $POSTGRES_USER > "$BACKUP_DIR/postgres_$DATE.sql"

# MongoDB
docker exec mongo mongodump --archive > "$BACKUP_DIR/mongo_$DATE.archive"

# Cleanup old backups (keep 7 days)
find "$BACKUP_DIR" -name "*.sql" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.archive" -mtime +7 -delete
```

### 10.2 Test your restores

A backup that hasn't been tested is not a backup. Schedule a quarterly test where you spin up a fresh LXC container and try to restore everything.

---

## 12. Preparing for Multi-Node (Future Proxmox Split)

You mentioned eventually splitting across multiple containers/VMs. Here's how to prepare now:

### 11.1 Decouple databases early

Your Postgres, MongoDB, and Redis are shared infrastructure. When you split, these should be on their own node. Prepare by:

- Making sure all services connect to databases via **container name or environment variable**, not `localhost`.
- Using a dedicated Docker network for database connections.
- Consider adding a separate `db` network:

```yaml
networks:
  t3_proxy:   # For services behind Traefik
  db:         # For database connections
    internal: true  # No external access
```

### 11.2 Consider Docker Swarm (lightweight) or keep it simple

When you split, you have options:

- **Keep it simple:** Run separate `docker compose` stacks on each node, with databases on one node and services connecting over the Proxmox network. This is the easiest path.
- **Docker Swarm:** Built into Docker, minimal overhead over compose. Good if you want service discovery and load balancing across nodes.
- **Kubernetes (k3s):** Only if you want to learn it. Massive overkill for a homelab, but educational.

For most homelabs, the "separate compose stacks" approach works fine. Your current repo structure already supports this — just split the `include` list across multiple `compose.yml` files on different nodes.

### 11.3 Split candidates

Natural groupings for separate nodes:

| Node | Services | Why |
|------|----------|-----|
| **Infra** | Traefik, Authentik, Postgres, Redis, Mongo, Pi-hole | Core infrastructure, should be most stable |
| **Media** | Plex, *arrs, qBittorrent, SABnzbd, Tautulli | Heavy I/O and CPU (transcoding) |
| **Home** | Home Assistant, Z2M, Mosquitto, Frigate, Hyperion | IoT, needs hardware access (USB for Zigbee, GPU for Frigate) |
| **Productivity** | Paperless, Nextcloud, Immich, n8n | User-facing apps |
| **Monitoring** | Grafana, Prometheus, Loki, Promtail | Observability |

---

## 13. Recommended Migration Order

Don't try to do everything at once. Here's a suggested order:

### Phase 1: Git Foundation (1-2 hours)
1. Initialize a Git repo in your docker directory.
2. Create `.gitignore` (use the template from section 3.2).
3. Create `.env.example`.
4. Make your first commit.
5. Push to a **private** GitHub repo.

### Phase 2: Reduce Repetition (2-3 hours)
1. Create the common service fragment file using `extends`.
2. Refactor 2-3 services to use it (start with simple ones like bazarr, sonarr, radarr).
3. Test that everything still starts correctly.
4. Gradually refactor the rest.

### Phase 3: Secrets in Git (1-2 hours)
1. Install SOPS and age on your server.
2. Generate an age key.
3. Encrypt your `.env` and `secrets/` directory.
4. Add encrypted files to Git, remove unencrypted from tracking.
5. Update your deployment process to decrypt on deploy.

### Phase 4: Renovate (30 minutes)
1. Ensure all images have pinned versions.
2. Add `renovate.json5` to your repo.
3. Install the Renovate GitHub App.
4. Review and merge the initial onboarding PR.

### Phase 5: CI/CD (1-2 hours)
1. Set up SSH keys for deployment.
2. Create the GitHub Actions workflow.
3. Test with a small change (e.g., bump a version manually).
4. Enable auto-merge for Renovate patch updates.

### Phase 6: Polish (ongoing)
1. Add health checks to critical services.
2. Add resource limits.
3. Consider moving Traefik config to file-based dynamic config.
4. Improve monitoring and alerting.
5. Document your setup in the repo README.

---

## Quick Reference: Tools Mentioned

| Tool | Purpose | Link |
|------|---------|------|
| **SOPS** | Encrypt secrets for Git | github.com/getsops/sops |
| **age** | Modern encryption (simpler than GPG) | github.com/FiloSottile/age |
| **Renovate** | Automated dependency updates | github.com/apps/renovate |
| **Backrest** | Backup (you already use this) | — |
| **GitHub Actions** | CI/CD | github.com/features/actions |

---

*This guide is tailored to your current setup. The recommendations are ordered by impact — phases 1-3 give you the biggest improvements with the least effort. If you have questions about any section or want me to generate specific config files, just ask.*