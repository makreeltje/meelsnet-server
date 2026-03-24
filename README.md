# Meelsnet Server

Docker Compose homelab draaiend op Proxmox met 7 LXC containers, 40+ services, en GitOps-based deployment.

## Architectuur

```
┌──────────────────────────────────────────────────────┐
│                     Proxmox VE                       │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ LXC 101  │  │ LXC 102  │  │ LXC 103  │           │
│  │  infra   │  │  media   │  │  home    │           │
│  │ Traefik  │  │ Plex     │  │ HA       │           │
│  │ Authentik│  │ Sonarr   │  │ Zigbee   │           │
│  │ Postgres │  │ Radarr   │  │ Frigate  │           │
│  │ Redis    │  │ ...      │  │ ...      │           │
│  └──────────┘  └──────────┘  └──────────┘           │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ LXC 104  │  │ LXC 105  │  │ LXC 106  │           │
│  │producti- │  │ network  │  │monitoring│           │
│  │  vity    │  │ Pi-hole  │  │ Grafana  │           │
│  │ Immich   │  │ UniFi    │  │Prometheus│           │
│  │ Paperless│  │          │  │ Loki     │           │
│  └──────────┘  └──────────┘  └──────────┘           │
│                                                      │
│  ┌──────────┐                                        │
│  │ LXC 107  │       ┌─────────────────────┐          │
│  │utilities │       │  GitOps Controller  │          │
│  │ Spoolman │       │  Webhook + Deploy   │          │
│  └──────────┘       └─────────────────────┘          │
└──────────────────────────────────────────────────────┘
```

Elke LXC container draait een eigen Docker daemon met zijn eigen subset van services. Alle services worden beheerd via Docker Compose.

## Services

### LXC 101 — Infra

| Service | Beschrijving | Port |
|---|---|---|
| [Traefik](compose/reverse-proxy/compose.traefik.yml) | Reverse proxy + Let's Encrypt via Cloudflare DNS | 80, 443 |
| [Authentik](compose/reverse-proxy/compose.authentik.yml) | Identity provider / SSO | 9000 |
| [PostgreSQL](compose/database/compose.postgres.yml) | Gedeelde database | 5432 |
| [Redis](compose/database/compose.redis.yml) | Cache / message broker | 6379 |
| [MongoDB](compose/database/compose.mongo.yml) | Document database (UniFi) | 27017 |
| [Adminer](compose/database/compose.adminer.yml) | Database admin UI | 8080 |

### LXC 102 — Media

| Service | Beschrijving | Port |
|---|---|---|
| [Plex](compose/media-server/compose.plex.yml) | Media server | 32400 |
| [Jellyfin](compose/media-server/compose.jellyfin.yml) | Media server (open source) | 8096 |
| [Sonarr](compose/media-server/compose.sonarr.yml) | TV series management | 8989 |
| [Radarr](compose/media-server/compose.radarr.yml) | Film management | 7878 |
| [Prowlarr](compose/media-server/compose.prowlarr.yml) | Indexer manager | 9696 |
| [SABnzbd](compose/media-server/compose.sabnzbd.yml) | Usenet downloader | 8080 |
| [qBittorrent](compose/media-server/compose.qbittorrent.yml) | Torrent client (met VPN) | 8080 |
| [Bazarr](compose/media-server/compose.bazarr.yml) | Ondertiteling | 6767 |
| [Tautulli](compose/media-server/compose.tautulli.yml) | Plex monitoring | 8181 |
| [Seerr](compose/media-server/compose.seerr.yml) | Media requests | 5055 |
| [Notifiarr](compose/media-server/compose.notifiarr.yml) | Notificaties | 5454 |
| [Profilarr](compose/media-server/compose.profilarr.yml) | Profiel sync voor Sonarr/Radarr | 6868 |
| [Tracearr](compose/media-server/compose.tracearr.yml) | Arr monitoring | — |
| [Agregarr](compose/media-server/compose.agregarr.yml) | Arr aggregatie | — |
| [Watchstate](compose/media-server/compose.watchstate.yml) | Watch state sync | 8080 |

### LXC 103 — Home Automation

| Service | Beschrijving | Port |
|---|---|---|
| [Home Assistant](compose/home-automation/compose.home-assistant.yml) | Domotica platform | 8123 |
| [Zigbee2MQTT](compose/home-automation/compose.zigbee2mqtt.yml) | Zigbee bridge | 8080 |
| [Mosquitto](compose/home-automation/compose.mosquitto.yml) | MQTT broker | 1883 |
| [Node-RED](compose/home-automation/compose.nodered.yml) | Flow-based automation | 1880 |
| [Music Assistant](compose/home-automation/compose.music-assistant.yml) | Multi-room audio | 8095 |
| [Hyperion](compose/home-automation/compose.hyperion.yml) | Ambilight / LED control | 8090 |
| [Frigate](compose/home-automation/compose.frigate.yml) | NVR met AI detectie | 5000 |

### LXC 104 — Productivity

| Service | Beschrijving | Port |
|---|---|---|
| [Immich](compose/productivity/compose.immich.yml) | Foto/video management | 2283 |
| [Paperless-NGX](compose/productivity/compose.paperless.yml) | Document management | 8000 |
| [Nextcloud](compose/productivity/compose.nextcloud.yml) | Cloud opslag / office | 443 |
| [Backrest](compose/productivity/compose.backrest.yml) | Backup UI voor restic | 9898 |

### LXC 105 — Network

| Service | Beschrijving | Port |
|---|---|---|
| [Pi-hole](compose/network/compose.pihole.yml) | DNS ad-blocker | 53, 80 |
| [UniFi Controller](compose/network/compose.unifi.yml) | Netwerk management | 8443 |

### LXC 106 — Monitoring

| Service | Beschrijving | Port |
|---|---|---|
| [Prometheus](compose/monitoring/compose.prometheus.yml) | Metrics verzameling | 9090 |
| [Grafana](compose/monitoring/compose.grafana.yml) | Dashboards / visualisatie | 3000 |
| [Loki](compose/monitoring/compose.loki.yml) | Log aggregatie | 3100 |
| [Promtail](compose/monitoring/compose.promtail.yml) | Log collector voor Loki | — |
| [Exporters](compose/monitoring/compose.exporters.yml) | Prometheus exporters (Sonarr, Radarr, etc.) | — |

### LXC 107 — Utilities

| Service | Beschrijving | Port |
|---|---|---|
| [Omni-tools](compose/utilities/compose.omni-tools.yml) | File conversie tools | 8080 |
| [Spoolman](compose/utilities/compose.spoolman.yml) | 3D print filament tracker | 7912 |
| [Printer Calculator](compose/utilities/compose.printer-calculator.yml) | 3D print cost calculator | 3000 |

## Directorystructuur

```
.
├── compose.yml                    # Root compose (alle services, voor validatie)
├── .env.example                   # Environment variabelen template
├── GITOPS.md                      # GitOps controller documentatie
│
├── compose/                       # Service-specifieke compose files
│   ├── fragments/                 # Herbruikbare base service definities
│   │   └── common-service.yml     #   common, common-lsio, common-db, etc.
│   ├── reverse-proxy/             # Traefik, Authentik
│   ├── database/                  # PostgreSQL, Redis, MongoDB, Adminer
│   ├── media-server/              # Plex, Sonarr, Radarr, ...
│   ├── home-automation/           # Home Assistant, Zigbee2MQTT, ...
│   ├── productivity/              # Immich, Paperless, Nextcloud, ...
│   ├── network/                   # Pi-hole, UniFi
│   ├── monitoring/                # Prometheus, Grafana, Loki, ...
│   ├── utilities/                 # Spoolman, Printer Calculator, ...
│   └── archive/                   # Uitgeschakelde services
│
├── lxc/                           # Per-LXC container orchestratie
│   ├── infra/compose.yml          # LXC 101 — includes reverse-proxy + database
│   ├── media/compose.yml          # LXC 102 — includes media-server
│   ├── home/compose.yml           # LXC 103 — includes home-automation
│   ├── productivity/compose.yml   # LXC 104 — includes productivity
│   ├── network/compose.yml        # LXC 105 — includes network
│   ├── monitoring/compose.yml     # LXC 106 — includes monitoring
│   └── utilities/compose.yml      # LXC 107 — includes utilities
│
├── scripts/
│   ├── gitops/                    # GitOps controller (draait op Proxmox)
│   │   ├── gitops-controller.sh   #   Deploy logica
│   │   ├── gitops-webhook.py      #   Webhook listener
│   │   ├── gitops-webhook.service #   systemd service
│   │   ├── config.env.example     #   Configuratie template
│   │   └── setup.sh               #   Installatie script
│   └── update-docker-hosts.sh     # Update /etc/hosts in containers
│
└── .github/
    └── workflows/
        └── deploy.yml             # PR compose syntax validatie
```

## Hoe het werkt

### Compose structuur

Elke service heeft zijn eigen compose file in `compose/<stack>/`. Services erven van base templates in `compose/fragments/common-service.yml`:

```yaml
# compose/media-server/compose.sonarr.yml
services:
  sonarr:
    extends:
      file: ../fragments/common-service.yml
      service: common-lsio                    # Adds PUID, PGID, TZ, restart policy
    container_name: sonarr
    image: linuxserver/sonarr:4.0.16
    profiles: [ "media", "all" ]
    volumes:
      - $CONF_DIR/sonarr/config:/config
      - $MEDIA_DIR:/media
```

De `lxc/*/compose.yml` bestanden bevatten de includes voor hun specifieke stack en worden gebruikt als entrypoint bij deployment:

```bash
docker compose -f lxc/media/compose.yml up -d
```

### Deployment (GitOps)

Deployment gaat via een webhook-based GitOps controller die op Proxmox draait. Zie [GITOPS.md](GITOPS.md) voor volledige documentatie.

**Kort samengevat:**

1. Wijzig een compose file → open PR (of Renovate doet dit automatisch)
2. Merge naar `main`
3. GitHub stuurt webhook → Proxmox controller detecteert welke files zijn gewijzigd
4. Controller deployt alleen de getroffen LXC container(s)

### Image updates (Renovate)

[Renovate](https://docs.renovatebot.com/) monitort alle compose files voor nieuwe Docker image versies en opent automatisch PRs. Patch en minor updates kunnen automatisch gemerged worden.

## Nieuwe service toevoegen

1. Maak een compose file aan in de juiste stack directory:

```bash
# Voorbeeld: nieuwe service in de media stack
touch compose/media-server/compose.nieuwe-service.yml
```

2. Gebruik een van de base templates uit `compose/fragments/common-service.yml`:

```yaml
services:
  nieuwe-service:
    extends:
      file: ../fragments/common-service.yml
      service: common          # of common-lsio, common-db, etc.
    container_name: nieuwe-service
    image: vendor/image:tag
    profiles: [ "media", "all" ]
    volumes:
      - $CONF_DIR/nieuwe-service:/config
    ports:
      - 1234:1234
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:1234/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

3. Voeg de include toe aan `lxc/<stack>/compose.yml`:

```yaml
include:
  - compose/media-server/compose.nieuwe-service.yml
```

4. Voeg de include ook toe aan de root `compose.yml` (voor validatie).

5. Commit, push, en merge. De GitOps controller deployt automatisch naar de juiste LXC.

## Base service templates

| Template | Gebruik |
|---|---|
| `common` | Standaard services (restart policy, t3_proxy network, TZ) |
| `common-host` | Services met `network_mode: host` |
| `common-lsio` | LinuxServer.io images (voegt PUID/PGID toe) |
| `common-db` | Services die postgres + redis nodig hebben |
| `common-lsio-db` | LSIO images met database dependencies |
| `exportarr-base` | Prometheus exporters voor *arr services |

## Netwerk

Alle services binnen een LXC communiceren via het `t3_proxy` bridge network. Traefik (LXC 101) routeert extern verkeer naar de juiste services via Docker labels.

TLS certificaten worden automatisch verkregen via Cloudflare DNS challenge (wildcard `*.domein.nl`).

Authenticatie gaat via Authentik SSO, geconfigureerd als Traefik middleware (`chain-authentik@file`).

## Secrets

Secrets worden **niet** in git opgeslagen. Ze staan direct op elke LXC container:

- **`.env`** — Environment variabelen per LXC (`~/docker/.env`)
- **Docker secrets** — Gevoelige bestanden (`~/docker/secrets/`)
  - `cf_dns_api_token` — Cloudflare API token (LXC 101)
  - `basic_auth_credentials` — Traefik basic auth (LXC 101)
  - `plex_claim_token` — Plex claim token (LXC 102)

Zie `.env.example` voor een overzicht van alle variabelen.
