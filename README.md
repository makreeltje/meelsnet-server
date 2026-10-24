# Meelsnet Server

Docker Compose homelab draaiend op Proxmox met meerdere LXC-containers, gescheiden stacks per functie, en GitOps-based deployment.

## Architectuur

Onderstaande plaat is gebaseerd op de actuele Proxmox/LXC- en Docker-structuur die nu draait.

![Meelsnet homelab architecture (light)](docs/assets/architecture-light.svg#gh-light-mode-only)
![Meelsnet homelab architecture (dark)](docs/assets/architecture-dark.svg#gh-dark-mode-only)

## Documentatie

| Document | Inhoud |
|---|---|
| [docs/SERVICES.md](docs/SERVICES.md) | Wat draait waar: services per LXC, hostnames, Authentik-bescherming, afhankelijkheden |
| [GITOPS.md](GITOPS.md) | Deploy-flow, controller, installatie op Proxmox |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Secrets, back-up/restore, handmatige stappen buiten de repo |

## Directorystructuur

```
.
├── .env.example                   # Environment variabelen template
├── .env.ci                        # Dummywaarden voor CI-validatie
├── renovate.json5                 # Renovate-configuratie
├── GITOPS.md                      # GitOps controller documentatie
│
├── compose/                       # Service-specifieke compose files
│   ├── fragments/                 # Herbruikbare base service definities
│   │   └── common-service.yml     #   common, common-host, common-lsio (+ ongebruikte *-db)
│   ├── reverse-proxy/             # Traefik, Authentik
│   ├── database/                  # PostgreSQL, Redis, MariaDB, Adminer
│   ├── media-server/              # Plex, Jellyfin, Arr-stack, Tracearr, ...
│   ├── home-automation/           # Home Assistant, Zigbee2MQTT, Frigate, Mosquitto, ...
│   ├── productivity/              # Immich, Paperless, n8n, Backrest, budget-tracker, ...
│   ├── network/                   # UniFi OS Server (Pi-hole staat uit)
│   ├── monitoring/                # Prometheus, Grafana, Loki, Alertmanager, exporters,
│   │                              #   plus cAdvisor en Alloy (draaien op elke LXC)
│   ├── utilities/                 # Losse tools (Portainer, IT-Tools, Spoolman, ...),
│   │                              #   verspreid geïncluded over meerdere LXC's
│   ├── archive/                   # Uitgeschakelde services (door Renovate genegeerd)
│   └── game-servers/              # Niet geïncludet (door Renovate genegeerd)
│
├── lxc/                           # Per-LXC entrypoint met de includes
│   ├── infra/compose.yml          # LXC 101 — Traefik, Authentik, databases, Portainer
│   ├── media/compose.yml          # LXC 102
│   ├── home/compose.yml           # LXC 103
│   ├── productivity/compose.yml   # LXC 104 — incl. de meeste utilities
│   ├── network/compose.yml        # LXC 105
│   └── monitoring/compose.yml     # LXC 106
│
├── traefik/                       # Traefik file-provider config (gesynct naar LXC 101)
│   ├── services/<groep>/          #   Eén router + service per app (hostname, chain, backend)
│   ├── chains/                    #   Middleware-chains (authentik, authentik-local, no-auth, ...)
│   ├── middlewares/               #   Losse middlewares
│   ├── inactive/                  #   Uitgecommentarieerde routes van uitgeschakelde apps
│   └── tls-opts.yml
│
├── scripts/
│   ├── gitops/                    # GitOps controller (draait op Proxmox)
│   ├── backup/                    # Back-upscripts (draaien op de Proxmox-host, zie docs/OPERATIONS.md)
│   ├── update-docker-hosts.sh     # Schrijft container-IP's naar /etc/hosts
│   ├── render-architecture-svg.py # Rendert docs/assets/architecture*.svg
│   └── check-docs.py              # CI-check: docs/SERVICES.md klopt met de compose-bestanden
│
├── docs/                          # SERVICES.md, OPERATIONS.md, architectuurplaat
│
└── .github/
    ├── workflows/                 # Validate (yamllint, shellcheck, compose), Security, Docs,
    │                              #   Render architecture
    └── pull_request_template.md
```

## Hoe het werkt

### LXC's

| LXC | Naam | IP | Stack |
|---|---|---|---|
| 101 | infra | 10.10.0.10 | Ingress, auth en gedeelde datastores |
| 102 | media | 10.10.0.20 | Streaming, downloads en Arr-ecosysteem |
| 103 | home | 10.10.0.30 | Home Assistant, MQTT, Frigate, domotica |
| 104 | productivity | 10.10.0.40 | Foto's, documenten, automatisering, back-up, tools |
| 105 | network | 10.10.0.50 | UniFi |
| 106 | monitoring | 10.10.0.60 | Metrics, logs, alerts, exporters |

Per service en hostname: zie [docs/SERVICES.md](docs/SERVICES.md). Er is geen aparte "utilities" LXC meer (was CT 107, opgegaan in productivity).

### Compose structuur

Elke service heeft zijn eigen compose file in `compose/<stack>/`. De `lxc/*/compose.yml` bestanden includen de bestanden die op die LXC draaien en zijn het entrypoint bij deployment. Een service uitzetten = de include uitcommentariëren (en de Traefik-route uitcommentariëren, zie hieronder).

Services erven van base templates in `compose/fragments/common-service.yml`:

```yaml
# compose/media-server/compose.sonarr.yml
services:
  sonarr:
    extends:
      file: ../fragments/common-service.yml
      service: common-lsio                    # Adds PUID, PGID, TZ, restart policy
    container_name: sonarr
    image: linuxserver/sonarr:<versie>        # altijd een vaste tag (Renovate werkt hem bij)
    profiles: [ "media", "all" ]
    volumes:
      - $CONF_DIR/sonarr/config:/config
      - $MEDIA_DIR:/media
```

### Routing en authenticatie (Traefik)

Traefik draait op LXC 101 en routeert **niet** via Docker-labels (behalve voor Traefik zelf en Authentik) maar via de file provider: elke app heeft een bestand in `traefik/services/<groep>/app-<naam>.yml` met hostname, middleware-chain en backend (`http://<LXC-IP>:<poort>`). De GitOps-controller synct `traefik/` naar LXC 101; Traefik herlaadt vanzelf.

De chain bepaalt de bescherming: `chain-authentik` (extern met Authentik-login), `chain-authentik-local` (alleen LAN + Authentik), `chain-local-only`, `chain-no-auth` (app heeft eigen login). Overzicht in [docs/SERVICES.md](docs/SERVICES.md#authentik-bescherming).

Er zijn twee domeinen in gebruik (`DOMAINNAME_1` = `meelsnet.nl`, `DOMAINNAME_2` = `meels.net`); welke app waar hangt staat in SERVICES.md. TLS-certificaten komen via de Cloudflare DNS-challenge.

### Deployment (GitOps)

Een webhook-based controller op de Proxmox-host deployt bij merge naar `main`. Zie [GITOPS.md](GITOPS.md).

1. Wijzig een bestand → open PR (Renovate doet dit automatisch voor image-updates)
2. CI valideert (yamllint, shellcheck, `docker compose config` per LXC, secret-scans, docs-check)
3. Review en merge naar `main`
4. GitHub stuurt een webhook naar Proxmox; een timer (elke 15 min) vangt gemiste webhooks op
5. De controller deployt alleen de getroffen LXC('s) en synct `traefik/` en de host-managed scripts

Wijzig nooit configuratie rechtstreeks op een server: de controller overschrijft die bij de volgende deploy.

### Image updates (Renovate)

[Renovate](https://docs.renovatebot.com/) opent PR's voor nieuwe image-versies in alle compose-bestanden (`renovate.json5`):

- **Patch en minor**: automerge (PR).
- **Major**: nooit automerge; labels `major-update` en `needs-review`.
- **Infra** (`compose/reverse-proxy/**`, `compose/database/**`): nooit automerge, label `infra`.
- **Groepen** in één PR: Portainer (server + agent), Immich (server + machine-learning), Authentik (server + worker), Arr-stack (minor/patch van Sonarr, Radarr, Prowlarr, Bazarr).
- **Tracearr** (draait DB-migraties bij start): nooit automerge. De **TimescaleDB-image van Tracearr** staat uit voor Renovate: een major-PG- of extensie-update vraagt een handmatige dump/restore of `ALTER EXTENSION UPDATE`.
- **Eigen apps** (`budget-tracker`, `prints-portal`, `3d-prints-calculator`) en `compose/archive/`, `compose/game-servers/` worden genegeerd.
- Images zonder versietag (`hyperion`, `pinchflat`) worden via digest (`@sha256`) gepind.

## Nieuwe service toevoegen

1. Compose file in de juiste stack-directory (`compose/<stack>/compose.<naam>.yml`), met een base template, vaste image-tag, `container_name`, volumes onder `$CONF_DIR/<naam>` en bij voorkeur een healthcheck (controleer dat het commando in de image bestaat; veel images hebben geen `curl`).
2. Include toevoegen in `lxc/<lxc>/compose.yml`.
3. Traefik-route: `traefik/services/<groep>/app-<naam>.yml` met de juiste chain. Kies bewust tussen `chain-authentik`, `chain-authentik-local`, `chain-local-only` of `chain-no-auth`.
4. Nieuwe variabelen in `.env.example` zetten én op de LXC in `.env` zetten vóór de merge.
5. **Rij toevoegen in [docs/SERVICES.md](docs/SERVICES.md)** (de docs-check in CI faalt anders).
6. PR openen; na merge deployt de controller.

## Base service templates

| Template | Gebruik |
|---|---|
| `common` | Standaard services (restart policy, t3_proxy network, TZ, log-rotatie) |
| `common-host` | Services met `network_mode: host` (Home Assistant, Hyperion) |
| `common-lsio` | LinuxServer.io images (voegt PUID/PGID toe) |
| `common-db`, `common-lsio-db` | Zoals `common`/`common-lsio` plus `depends_on` op een `postgres`- en `redis`-service in hetzelfde compose-project. Niet in gebruik: postgres en redis draaien op een andere LXC. |

## Secrets

Secrets staan **niet** in git. Ze staan op elke LXC in `/root/docker/.env` en `/root/docker/secrets/`. Zie `.env.example` en [docs/OPERATIONS.md](docs/OPERATIONS.md#secrets-en-env).
