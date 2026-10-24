# Service-overzicht per LXC

Dit overzicht is de bron voor "wat draait waar". De lijst met containers wordt in CI vergeleken met de `include:`-regels in `lxc/<naam>/compose.yml` (zie [Documentatie actueel houden](#documentatie-actueel-houden)): staat er een service in een compose maar niet hier (of andersom), dan faalt de check.

Wat hier **niet** staat, omdat het te snel verloopt: image-versies (Renovate beheert die in de compose-bestanden) en secrets.

## Conventies

- **Domeinen.** Er zijn twee domeinen in gebruik, ingesteld in de `.env` van de infra-LXC: `DOMAINNAME_1` = `meelsnet.nl` en `DOMAINNAME_2` = `meels.net`. De migratie naar `meels.net` is gaande, dus een app staat onder het domein dat in `traefik/services/<groep>/app-<naam>.yml` staat. In de tabellen hieronder: **D1** = `meelsnet.nl`, **D2** = `meels.net`.
- **Routing.** Traefik (infra) routeert via de *file provider*, niet via Docker-labels. De regels staan in `traefik/services/`, de backend is steeds `http://<LXC-IP>:<host-poort>`. Alleen Traefik zelf en Authentik gebruiken labels.
- **Authenticatie.** De kolom *Chain* is de Traefik middleware-chain uit `traefik/chains/`, zie [Authentik-bescherming](#authentik-bescherming).
- **Netwerk.** Elke LXC heeft één bridge `t3_proxy`; alleen infra legt het subnet vast (`10.2.0.0/16`).
- **Standaardcontainers** op *elke* LXC: `alloy` (logs naar Loki), `cadvisor` (metrics, poort 8888) en `portainer-agent` (poort 9001, gebonden aan het LXC-IP). De Portainer-server draait alleen op infra.
- **Opslag.** Appdata staat in bind mounts onder `/root/docker/appdata/<app>` op de LXC. Media-, download-, foto-, paperless-, back-up- en archiefmounts komen van dezelfde opslagpool: vol-lopen raakt alles tegelijk.

## Authentik-bescherming

| Chain | Wat het doet | Gebruik |
|---|---|---|
| `chain-authentik` | rate-limit, secure headers, Authentik forward-auth | Extern bereikbaar met Authentik-login |
| `chain-authentik-local` | als hierboven, maar eerst `local-only` (alleen LAN-, thuis- en Docker-subnetten) | Beheer-UI's, alleen lokaal |
| `chain-local-only` | secure headers + local-only, geen login | Apps met eigen toegangsbeperking |
| `chain-no-auth` | rate-limit + secure headers | Apps met eigen login (Plex, Immich, HA, ...) of publieke endpoints |
| `chain-nextcloud` | rate-limit + Nextcloud-headers/redirects | Nextcloud (tijdelijk uitgeschakeld, security: php2shell) |
| `chain-basic-auth`, `chain-oauth`, `chain-unifi`, `chain-vgz-whitelist` | zie `traefik/chains/` | Nu door geen enkele actieve route gebruikt |

Authentik zelf (`authentik.$DOMAINNAME_1`) draait op `chain-no-auth`. Apps met eigen OIDC-login tegen Authentik (Paperless, budget-tracker) hebben geen Traefik-chain met Authentik nodig.

## LXC 101 — infra (10.10.0.10)

Ingress, authenticatie en gedeelde datastores. Entrypoint: `lxc/infra/compose.yml`.

| Container | Rol | Poorten (host) | Hostname | Chain |
|---|---|---|---|---|
| `traefik` | Reverse proxy, TLS via Cloudflare DNS-challenge | 80, 443 | `traefik.`D1 (label) | authentik-local |
| `authentik` | SSO / identity provider | intern 9000 | `authentik.`D1 (label) | no-auth |
| `authentik-worker` | Authentik achtergrondtaken (zelfde versie als `authentik`) | — | — | — |
| `postgres` | Gedeelde PostgreSQL (Immich-variant met vectorchord/pgvectors) | 5432 (LXC-IP) | — | — |
| `redis` | Gedeelde Redis | 6379 (LXC-IP) | — | — |
| `mariadb` | MariaDB | 3306 (LXC-IP) | — | — |
| `adminer` | DB-beheer-UI | 8083 (LXC-IP) | geen route | — |
| `portainer` | Portainer-server | 9000, 8000, 9443 | `portainer.`D1 | authentik-local |
| `cadvisor`, `alloy`, `portainer-agent` | standaardcontainers | | | |

**Afhankelijkheden**
- `authentik` en `authentik-worker` → `postgres` + `redis` (via compose-netwerk, `depends_on` healthy). Server en worker moeten dezelfde versie hebben; Renovate groepeert ze daarom ("Authentik Stack").
- `postgres` bedient andere LXC's: databases voor authentik, immich, paperless, n8n, budget_tracker, budget_tracker_demo, printer_calculator (en nextcloud, tijdelijk uitgeschakeld, en firefly, uitgeschakeld). `redis` wordt gebruikt door authentik, paperless en tracearr (db 7).
- Traefik-secrets via Docker secrets uit `/root/docker/secrets/` (`cf_dns_api_token`, `basic_auth_credentials`).
- De Traefik-regels uit `traefik/` worden door de GitOps-controller naar `/root/docker/appdata/traefik3/rules/meelsnet` op deze LXC gesynct; Traefik herlaadt zelf.
- Routes die op infra staan maar naar elders wijzen: `gitops.`D1 → Proxmox-host:9000 (webhook, `chain-no-auth`, authenticatie via HMAC) en `paperclip.`D2 (`chain-authentik`; alleen `/api` en `/mcp` op `chain-no-auth`).

## LXC 102 — media (10.10.0.20)

Streaming, downloads en Arr-ecosysteem. Entrypoint: `lxc/media/compose.yml`.

| Container | Rol | Poorten (host) | Hostname(s) | Chain |
|---|---|---|---|---|
| `plex` | Mediaserver | 32400 e.a. | `plex.`D1 | no-auth |
| `jellyfin` | Mediaserver | 8096 | `jellyfin.`D1 | no-auth |
| `sonarr` | Series | 8989 | `series.`D2 | authentik |
| `sonarr-anime` | Series (anime) | 8999 | `anime.`D2 | authentik-local |
| `radarr` | Films | 7878 | `radarr.`D1, `movies.`D1 | authentik |
| `radarr-4k` | Films 4K | 7879 | `movies-4k.`D2 | authentik-local |
| `prowlarr` | Indexer-beheer | 9696 | `prowlarr.`D1 | authentik-local |
| `jackett` | Indexer-proxy | 9117 (LXC-IP) | `jackett.`D2 | authentik-local |
| `sabnzbd` | Usenet-client | 8082 | `sab.`D1 | authentik-local |
| `qbittorrent` | Torrent-client (via VPN-image) | 8083 (UI) | `qbittorrent.`D1 | authentik-local |
| `bazarr` | Ondertitels | 6767 | `subtitles.`D2 | authentik-local |
| `seerr` | Aanvragen | 5055 | `request.`D1 | no-auth (eigen login) |
| `wizarr` | Uitnodigingen | 5690 | `invite.`D1 | no-auth |
| `tautulli` | Plex-statistieken | 8181 | `tautulli.`D1 | authentik-local |
| `tracearr` | Streaming-monitoring | 3000 | `tracearr.`D1 | authentik-local |
| `tracearr-db` | TimescaleDB voor tracearr | intern 5432 | — | — |
| `watchstate` | Watch-state sync | 8081 (LXC-IP) | `watchstate.`D1 | authentik-local |
| `profilarr` | Arr-profielbeheer | 6868 (LXC-IP) | `profilarr.`D1 | authentik-local |
| `agregarr` | Lijstbeheer | 7171 (LXC-IP) | `agregarr.`D2 | authentik-local |
| `notifiarr` | Notificaties | 5454 (LXC-IP) | `notifiarr.`D2 | authentik-local |
| `cadvisor`, `alloy`, `portainer-agent` | standaardcontainers | | | |

**Afhankelijkheden en paden**
- `tracearr` → `tracearr-db` (eigen TimescaleDB, data in `appdata/tracearr/timescale`) en Redis op infra (db 7). Praat met Plex en Jellyfin binnen `t3_proxy`. Draait DB-migraties bij start; daarom nooit automerge (zie Renovate).
- De Arr-apps gebruiken SQLite in hun config-map; de koppeling Arr → download-client staat in de Arr-databases, niet in de repo.
- Mounts: `/mnt/media` (bibliotheek) en `/mnt/downloads` zijn hetzelfde filesystem, nodig voor hardlinks. Plex- en Jellyfin-metadata staan deels op de gedeelde pool (`/mnt/media/appdata/...`), de rest lokaal.
- Pinchflat (`compose.pinchflat.yml`) is uitgeschakeld (include uitgecommentarieerd, route in `traefik/inactive/`).

## LXC 103 — home (10.10.0.30)

Domotica en MQTT. Entrypoint: `lxc/home/compose.yml`.

| Container | Rol | Poorten (host) | Hostname | Chain |
|---|---|---|---|---|
| `homeassistant` | Home Assistant (host-netwerk) | 8123 | `home.`D2 | no-auth (eigen login) |
| `zigbee2mqtt` | Zigbee-bridge | 8080 (LXC-IP) | `z2m.`D2 | authentik-local |
| `mosquitto` | MQTT-broker | 1883 (LXC-IP) | geen route | — |
| `frigate` | NVR / object detection | 5001→5000, 8554, 8555 | `frigate.`D2 | authentik |
| `nodered` | Node-RED | 1880 (LXC-IP) | `nodered.`D2 | authentik-local |
| `musicassistant` | Music Assistant | 8095 | `music.`D2 | no-auth |
| `hyperion` | Ambilight (host-netwerk) | 8090 | `hyperion.`D2 | authentik-local |
| `cadvisor`, `alloy`, `portainer-agent` | standaardcontainers | | | |

**Afhankelijkheden en paden**
- Clients van `mosquitto`: Zigbee2MQTT, Home Assistant, Frigate, Node-RED; `mosquitto-exporter` (monitoring-LXC) scrapet de broker.
- Frigate gebruikt de iGPU (`/dev/dri`, OpenVINO) en schrijft opnames naar `/mnt/frigate`; Home Assistant mount dezelfde map. Die mount en de USB-dongle voor Zigbee2MQTT worden op de Proxmox-host aan de LXC gegeven en staan **niet** in de repo (zie [Handmatige stappen](#handmatige-stappen-buiten-de-repo)).

## LXC 104 — productivity (10.10.0.40)

Foto's, documenten, automatisering, back-up en losse tools. Entrypoint: `lxc/productivity/compose.yml`.

| Container | Rol | Poorten (host) | Hostname(s) | Chain |
|---|---|---|---|---|
| `immich` | Foto's | 2283 | `photos.`D2 | no-auth (eigen login) |
| `immich-machine-learning` | Immich ML | — | — | — |
| `paperless` | Documentbeheer | 8000 (LXC-IP) | `paperless.`D1 | no-auth (eigen OIDC-login) |
| `n8n` | Workflows | 5678 (LXC-IP) | `n8n.`D2 | authentik |
| `backrest` | Back-ups (restic) | 9898 (LXC-IP) | `backup.`D2 | authentik-local |
| `budget-tracker` | Budget-app (eigen image) | 8090 | `budget.`D2 | local-only |
| `budget-tracker-demo` | Demo-instantie | 8091 | `budget-demo.`D2 | local-only |
| `spoolman` | Filament-beheer | 8001 | `spoolman.`D1 | authentik-local |
| `prints-portal-2` | Printportaal (eigen image) | 8004 (LXC-IP) | `printer.`D2, `printer-2.`D2 | no-auth |
| `convertx` | Bestandsconversie | 3000 (LXC-IP) | `convert.`D2 | authentik-local |
| `it-tools` | IT-Tools | 8082 | `it-tools.`D2 | authentik-local |
| `omni-tools` | Omni-Tools | 8083 | `tools.`D1 | authentik-local |
| `chromium` | Headless Chromium (browserless) | 3001 | geen route | — |
| `cadvisor`, `alloy`, `portainer-agent` | standaardcontainers | | | |

**Afhankelijkheden en paden**
- `paperless`, `n8n`, `budget-tracker` en `budget-tracker-demo` gebruiken PostgreSQL op infra (`LXC_INFRA_IP:5432`); `budget-tracker` en de demo hebben elk een eigen database en rol. `paperless` gebruikt ook Redis op infra. `immich` gebruikt via een env-file eveneens de gedeelde PostgreSQL (Immich-variant op infra).
- Opslag: Immich-bibliotheek op `/mnt/photos/library`; Paperless `consume` en `media` op `/mnt/paperless`, export naar `/mnt/backups/app-data/paperless/export`; `n8n` mount `/mnt/archive/ChronicleCore`; `prints-portal-2` leest uit `/mnt/cloud`.
- `backrest` mount `/root/docker` (alle compose en appdata) en `/mnt/backups`; zie [Back-up en restore](OPERATIONS.md#back-up-en-restore).
- **Nextcloud: tijdelijk uitgeschakeld (security, php2shell).** Bewust uitgezet vanwege de PHP-kwetsbaarheid "php2shell"; de eigenaar zet hem later weer aan. De include is daarom uitgecommentarieerd in `lxc/productivity/compose.yml`. De Traefik-route (`traefik/services/productivity/app-nextcloud.yml`, `cloud.`D1 en `cloud.`D2 → poort 8081) blijft **bewust** actief staan, zodat er bij heractivering niets aan routing hoeft te veranderen; zolang Nextcloud uit staat luistert er niets op die poort. Dit is geen drift en vraagt geen actie.
- Uitgeschakeld (include uitgecommentarieerd): **Firefly III**.

## LXC 105 — network (10.10.0.50)

Netwerkbeheer. Entrypoint: `lxc/network/compose.yml`.

| Container | Rol | Poorten (host) | Hostname | Chain |
|---|---|---|---|---|
| `unifi-os` | UniFi OS Server (bevat MongoDB) | o.a. 8080 (device inform), 8443, 11443→443, 3478/udp, 10001, 10003 | `unifi.`D1 (→ `https://<LXC>:11443`) | authentik-local |
| `pihole` | DNS voor Tailscale split DNS (wildcard D1 en D2 → Traefik op infra) | 53 tcp/udp en 80 (LXC-IP en LAN-adres) | geen route | — |
| `cadvisor`, `alloy`, `portainer-agent` | standaardcontainers | | | |

- **Pi-hole** is alleen DNS voor Tailscale-apparaten (split DNS); de Experia Box blijft DNS voor de rest van het huis. Het LAN-adres van de LXC en het LAN-adres van infra (`LXC_LAN_IP`, `LXC_INFRA_LAN_IP`) staan alleen in de `.env`, niet in de repo. De web-UI (poort 80) luistert op het service-net en op het LAN-adres van de LXC; de route `traefik/services/network/app-pihole.yml` is bewust volledig uitgecommentarieerd (niet verwijderen: de controller haalt verwijderde bestanden niet van de LXC, zie [GITOPS.md](../GITOPS.md#traefik-regels)).
- De oude losse UniFi Network Application staat alleen nog in `compose/archive/compose.unifi.yml`.

## LXC 106 — monitoring (10.10.0.60)

Metrics, dashboards, logs en alerts. Entrypoint: `lxc/monitoring/compose.yml`.

| Container | Rol | Poorten (host) | Hostname | Chain |
|---|---|---|---|---|
| `prometheus` | Metrics (retentie op grootte, 25 GB) | 9090 (LXC-IP) | `prometheus.`D1 | authentik-local |
| `grafana` | Dashboards | 3000 | `grafana.`D2 | authentik-local |
| `loki` | Logs | 3100 (LXC-IP) | geen route | — |
| `alertmanager` | Alerts | 9093 (LXC-IP) | geen route | — |
| `node-exporter` | Host-metrics van deze LXC | 9100 (LXC-IP) | — | — |
| `sonarr-exporter`, `radarr-exporter`, `prowlarr-exporter`, `sabnzbd-exporter` | Exportarr (poorten 9707, 9708, 9710, 9711) | LXC-IP | — | — |
| `mosquitto-exporter` | Scrapet Mosquitto op LXC 103 | 9234 (LXC-IP) | — | — |
| `cadvisor`, `alloy`, `portainer-agent` | standaardcontainers | | | |

- De scrape-config (`prometheus.yml`), alert-regels en Alertmanager-config staan in `appdata/` op de LXC, niet in deze repo. Externe targets: Backrest op `10.10.0.40:9898` en een smartctl-exporter op de Proxmox-host (`10.10.0.1:9633`, hostzijdig beheerd).

## Niet-actieve onderdelen in de repo

| Pad | Status |
|---|---|
| `compose/archive/` | Uitgeschakelde services (EMQX, Firefly III, Homarr, mdns-repeater, Mongo, Mydia, Ollama, OpenChat, Tdarr, UniFi Network Application). Renovate negeert dit pad. |
| `compose/game-servers/` | Minecraft-server, niet geïncludet. Renovate negeert dit pad. |
| `compose/media-server/compose.pinchflat.yml` | Uitgecommentarieerd in `lxc/media`; route in `traefik/inactive/`. |
| `compose/productivity/compose.nextcloud.yml` | **Tijdelijk uitgeschakeld** (security, php2shell); uitgecommentarieerd in `lxc/productivity`, route blijft actief. Wordt weer aangezet. |
| `compose/productivity/compose.firefly.yml` | Uitgecommentarieerd in `lxc/productivity`. |
| `compose/monitoring/compose.promtail.yml` | Niet geïncludet; vervangen door `alloy`. |
| `compose/utilities/compose.prints-portal.yml` | Niet geïncludet; `prints-portal-2` is de actieve variant. |
| `traefik/inactive/` | Routes voor Firefly III en Pinchflat, uitgecommentarieerd. |

## Documentatie actueel houden

- Bij elke PR die een service toevoegt, verwijdert of een route/chain wijzigt: pas deze pagina aan. De PR-template heeft hier een checkbox voor.
- `scripts/check-docs.py` (draait in CI, workflow *Docs*, bij wijzigingen in `compose/`, `lxc/` en `traefik/`) controleert dat elke `container_name` uit de geïncludete compose-bestanden in de juiste LXC-sectie hierboven staat, dat er geen container in staat die niet meer bestaat, en dat elke actieve Traefik-route in `traefik/services/` een hostnaam-vermelding in dit document heeft. Lokaal draaien: `python3 scripts/check-docs.py`.
