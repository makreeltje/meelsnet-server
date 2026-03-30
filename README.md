# Meelsnet Server

Docker Compose homelab draaiend op Proxmox met meerdere LXC-containers, gescheiden stacks per functie, en GitOps-based deployment.

## Architectuur

Onderstaande plaat is gebaseerd op de actuele Proxmox/LXC- en Docker-structuur die nu draait, niet op een gok uit de README.

```mermaid
flowchart TB
  classDef prox fill:#111827,stroke:#374151,color:#f9fafb,stroke-width:2px
  classDef lxc fill:#1f2937,stroke:#60a5fa,color:#f9fafb,stroke-width:1.5px
  classDef svc fill:#0f172a,stroke:#94a3b8,color:#e2e8f0
  classDef core fill:#0b3b2e,stroke:#34d399,color:#ecfdf5,stroke-width:1.5px
  classDef media fill:#3b0764,stroke:#c084fc,color:#f5f3ff
  classDef home fill:#3f1d0d,stroke:#fb923c,color:#fff7ed
  classDef monitor fill:#082f49,stroke:#38bdf8,color:#e0f2fe
  classDef aux fill:#3f3f46,stroke:#a1a1aa,color:#fafafa

  Internet((Internet)):::aux
  GH[GitHub Webhook / GitOps]:::aux
  LAN[LAN 192.168.2.0/24]:::aux
  SVCNET[Service network 10.10.0.0/24]:::aux

  subgraph PVE[Proxmox host · srv-mn]
    direction TB

    subgraph CT101[LXC 101 · infra · 10.10.0.10]
      direction TB
      T[Traefik]:::core
      AK[Authentik + worker]:::core
      DB[(Postgres / Redis / MongoDB)]:::core
      ADM[Adminer / Mongo Express]:::svc
    end

    subgraph CT102[LXC 102 · media · 10.10.0.20]
      direction TB
      PLEX[Plex / Jellyfin]:::media
      ARR[Sonarr / Sonarr-4K<br/>Radarr / Radarr-4K<br/>Prowlarr / Bazarr]:::media
      DL[SABnzbd / qBittorrent]:::media
      MISC[Seerr / Tautulli / Notifiarr<br/>Profilarr / Tracearr / Agregarr / Watchstate]:::media
    end

    subgraph CT103[LXC 103 · home · 10.10.0.30]
      direction TB
      HA[Home Assistant]:::home
      MQTT[Mosquitto]:::home
      ZB[Zigbee2MQTT]:::home
      AUTO[Node-RED / Music Assistant<br/>Hyperion / Frigate]:::home
    end

    subgraph CT104[LXC 104 · productivity · 10.10.0.40]
      direction TB
      PROD[Immich / Paperless / Nextcloud<br/>Backrest / Firefly III]:::svc
    end

    subgraph CT105[LXC 105 · network · 10.10.0.50]
      direction TB
      NET[Pi-hole / UniFi Network Application]:::svc
    end

    subgraph CT106[LXC 106 · monitoring · 10.10.0.60]
      direction TB
      MON[Prometheus / Grafana / Alertmanager / cAdvisor]:::monitor
      EXP[Node / Smartctl / Mosquitto / Arr exporters]:::monitor
    end

    subgraph CT107[LXC 107 · utilities · 10.10.0.70]
      direction TB
      UTL[IT-Tools / Omni-Tools<br/>Spoolman / Printer Calculator]:::svc
    end

    subgraph CT108[LXC 108 · openclaw · 10.10.0.80]
      direction TB
      OC[OpenClaw / Lyra integration host]:::svc
    end

    subgraph CT109[LXC 109 · money · 10.10.0.90]
      direction TB
      MONEY[Finance stack]:::svc
    end
  end

  Internet --> T
  GH --> T
  GH --> CT101
  GH --> CT102
  GH --> CT103
  GH --> CT104
  GH --> CT105
  GH --> CT106
  GH --> CT107
  LAN --- PVE
  SVCNET --- PVE

  T --> CT102
  T --> CT103
  T --> CT104
  T --> CT105
  T --> CT106
  T --> CT107
  T --> CT108
  T --> CT109

  AK --> T
  DB --> AK
  DB --> CT104
  DB --> CT105
  MQTT --> ZB
  MQTT --> HA
  MQTT --> AUTO
  MON --> EXP
  EXP --> CT102
  EXP --> CT103
  EXP --> CT105

  class PVE prox
  class CT101,CT102,CT103,CT104,CT105,CT106,CT107,CT108,CT109 lxc
```

Hoofdlijn: Proxmox host met losse LXC-stacks per domein. `infra` levert ingress/auth/core-datastores, de overige containers draaien functionele stacks en `monitoring` leest mee over de rest heen.

## Services

### LXC 101 — Infra

| Service | Beschrijving |
|---|---|
| [Traefik](compose/reverse-proxy/compose.traefik.yml) | Reverse proxy + Let's Encrypt via Cloudflare DNS |
| [Authentik](compose/reverse-proxy/compose.authentik.yml) | Identity provider / SSO |
| [PostgreSQL](compose/database/compose.postgres.yml) | Gedeelde database |
| [Redis](compose/database/compose.redis.yml) | Cache / message broker |
| [MongoDB](compose/database/compose.mongo.yml) | Document database (UniFi) |
| [Adminer](compose/database/compose.adminer.yml) | Database admin UI |

### LXC 102 — Media

| Service | Beschrijving |
|---|---|
| [Plex](compose/media-server/compose.plex.yml) | Media server |
| [Jellyfin](compose/media-server/compose.jellyfin.yml) | Media server (open source) |
| [Sonarr](compose/media-server/compose.sonarr.yml) | TV series management |
| [Radarr](compose/media-server/compose.radarr.yml) | Film management |
| [Prowlarr](compose/media-server/compose.prowlarr.yml) | Indexer manager |
| [SABnzbd](compose/media-server/compose.sabnzbd.yml) | Usenet downloader | 
| [qBittorrent](compose/media-server/compose.qbittorrent.yml) | Torrent client (met VPN) |
| [Bazarr](compose/media-server/compose.bazarr.yml) | Ondertiteling |
| [Tautulli](compose/media-server/compose.tautulli.yml) | Plex monitoring |
| [Seerr](compose/media-server/compose.seerr.yml) | Media requests |
| [Notifiarr](compose/media-server/compose.notifiarr.yml) | Notificaties |
| [Profilarr](compose/media-server/compose.profilarr.yml) | Profiel sync voor Sonarr/Radarr |
| [Tracearr](compose/media-server/compose.tracearr.yml) | Arr monitoring |
| [Agregarr](compose/media-server/compose.agregarr.yml) | Arr aggregatie |
| [Watchstate](compose/media-server/compose.watchstate.yml) | Watch state sync |

### LXC 103 — Home Automation

| Service | Beschrijving |
|---|---|---|
| [Home Assistant](compose/home-automation/compose.home-assistant.yml) | Domotica platform |
| [Zigbee2MQTT](compose/home-automation/compose.zigbee2mqtt.yml) | Zigbee bridge |
| [Mosquitto](compose/home-automation/compose.mosquitto.yml) | MQTT broker |
| [Node-RED](compose/home-automation/compose.nodered.yml) | Flow-based automation |
| [Music Assistant](compose/home-automation/compose.music-assistant.yml) | Multi-room audio |
| [Hyperion](compose/home-automation/compose.hyperion.yml) | Ambilight / LED control |
| [Frigate](compose/home-automation/compose.frigate.yml) | NVR met AI detectie |

### LXC 104 — Productivity

| Service | Beschrijving |
|---|---|
| [Immich](compose/productivity/compose.immich.yml) | Foto/video management |
| [Paperless-NGX](compose/productivity/compose.paperless.yml) | Document management |
| [Nextcloud](compose/productivity/compose.nextcloud.yml) | Cloud opslag / office |
| [Backrest](compose/productivity/compose.backrest.yml) | Backup UI voor restic |
| Firefly III | Persoonlijke financiën / administratie |

### LXC 105 — Network

| Service | Beschrijving | Port |
|---|---|---|
| [Pi-hole](compose/network/compose.pihole.yml) | DNS ad-blocker | 53, 80 |
| [UniFi Controller](compose/network/compose.unifi.yml) | Netwerk management | 8443 |

### LXC 106 — Monitoring

| Service | Beschrijving |
|---|---|
| [Prometheus](compose/monitoring/compose.prometheus.yml) | Metrics verzameling |
| [Grafana](compose/monitoring/compose.grafana.yml) | Dashboards / visualisatie |
| Alertmanager | Alert routing |
| cAdvisor | Container metrics |
| Node Exporter | Host metrics |
| Smartctl Exporter | Disk / SMART metrics |
| Mosquitto Exporter | MQTT metrics |
| Arr Exporters | Prometheus exporters voor Sonarr, Radarr, Prowlarr en SABnzbd |

### LXC 107 — Utilities

| Service | Beschrijving |
|---|---|
| IT-Tools | Kleine self-hosted utility toolbox |
| [Omni-tools](compose/utilities/compose.omni-tools.yml) | File conversie tools |
| [Spoolman](compose/utilities/compose.spoolman.yml) | 3D print filament tracker |
| [Printer Calculator](compose/utilities/compose.printer-calculator.yml) | 3D print cost calculator |

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

Elke service heeft zijn eigen compose file in `compose/<stack>/`. De actieve productie-indeling op dit moment is:

- `infra` → ingress, auth en gedeelde datastores
- `media` → streaming, downloads en Arr-ecosysteem
- `home` → Home Assistant, MQTT en domotica
- `productivity` → documenten, foto's, cloud en finance
- `network` → DNS en UniFi
- `monitoring` → metrics, alerts en exporters
- `utilities` → kleine losse tools
- aparte LXC's voor `openclaw` en `money`

Services erven van base templates in `compose/fragments/common-service.yml`:

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

## Netwerk

Alle services binnen een LXC communiceren via het `t3_proxy` bridge network. Traefik (LXC 101) routeert extern verkeer naar de juiste services via Docker labels.

TLS certificaten worden automatisch verkregen via Cloudflare DNS challenge (wildcard `*.domein.nl`).

Authenticatie gaat via Authentik SSO, geconfigureerd als Traefik middleware (`chain-authentik@file`).

## Secrets

Secrets worden **niet** in git opgeslagen. Ze staan direct op elke LXC container:

- **`.env`** — Environment variabelen per LXC (`~/docker/.env`)
- **Docker secrets** — Gevoelige bestanden (`~/docker/secrets/`)

Zie `.env.example` voor een overzicht van alle variabelen.
