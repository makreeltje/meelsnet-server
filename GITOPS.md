# GitOps Controller

Webhook-based deployment controller die luistert naar GitHub push events en automatisch de getroffen LXC containers deployt via Proxmox `pct`.

## Waarom?

De oude GitHub Actions workflow (`deploy.yml`) is **push-based**: GitHub heeft via Tailscale OAuth + SSH directe toegang tot de Proxmox server. Als iemand toegang krijgt tot de GitHub repo, heeft diegene ook toegang tot de server.

De GitOps controller draait **op Proxmox zelf** en ontvangt alleen een webhook notificatie. GitHub heeft geen SSH, geen Tailscale, en geen credentials. Het enige dat GitHub kent is een webhook URL met een gedeeld HMAC secret.

```
┌─────────────────────────────────────────────────────────────┐
│                         VOORHEEN                            │
│                                                             │
│  GitHub Actions ──tailscale──> SSH ──> Proxmox ──> LXCs    │
│  (push-based, GitHub heeft server-toegang)                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                          NU                                 │
│                                                             │
│  GitHub ──webhook (HMAC signed)──> Proxmox webhook listener │
│  Listener triggert controller → git pull → deploy naar LXCs │
│  (GitHub kent alleen de webhook URL, geen server-toegang)   │
└─────────────────────────────────────────────────────────────┘
```

## Hoe werkt het?

1. PR wordt gemerged naar `main` (handmatig of via Renovate auto-merge)
2. GitHub stuurt een push webhook naar de Proxmox webhook listener
3. Listener verifieert de HMAC-SHA256 signature en accepteert het event
4. Controller doet `git fetch` + `git diff` om gewijzigde files te bepalen
5. Mapt gewijzigde files naar de juiste LXC container(s)
6. Deployt alleen de getroffen LXC's (`pct push` + `docker compose up -d`)

### Path → LXC mapping

| Gewijzigd pad | LXC | Container |
|---|---|---|
| `compose/reverse-proxy/*`, `compose/database/*` | 101 | infra |
| `compose/media-server/*` | 102 | media |
| `compose/home-automation/*` | 103 | home |
| `compose/productivity/*` | 104 | productivity |
| `compose/network/*` | 105 | network |
| `compose/monitoring/*` | 106 | monitoring |
| `compose/utilities/*` | 107 | utilities |
| `lxc/<name>/*` | bijbehorende LXC | |
| `compose/fragments/*` | **ALLE** | shared dependency |

## Installatie op Proxmox

### 1. Setup script draaien

```bash
# Kopieer de scripts/gitops/ map naar Proxmox (eenmalig)
scp -r scripts/gitops/ root@proxmox:/tmp/gitops-setup/

# Op Proxmox:
bash /tmp/gitops-setup/setup.sh
```

Het setup script:
- Installeert de controller + webhook listener in `/opt/gitops/`
- Maakt config aan in `/etc/gitops/config.env`
- Genereert automatisch een webhook secret
- Installeert de systemd service

### 2. Deploy key aanmaken (read-only)

```bash
# Op Proxmox
ssh-keygen -t ed25519 -f /root/.ssh/github_deploy_key -N '' -C 'gitops-proxmox'
cat /root/.ssh/github_deploy_key.pub
```

Voeg de public key toe aan GitHub: **Repo → Settings → Deploy keys → Add deploy key** (vink **NIET** "Allow write access" aan).

### 3. SSH configureren

```bash
cat >> /root/.ssh/config << 'EOF'
Host github.com
  IdentityFile /root/.ssh/github_deploy_key
  IdentitiesOnly yes
EOF
```

### 4. GitHub webhook configureren

Ga naar **Repo → Settings → Webhooks → Add webhook**:

| Veld | Waarde |
|---|---|
| Payload URL | `https://<proxmox-ip-of-domein>:9000/webhook` |
| Content type | `application/json` |
| Secret | Kopieer uit `/etc/gitops/config.env` (`WEBHOOK_SECRET`) |
| Events | **Just the push event** |

> **Tip:** Als Proxmox niet direct bereikbaar is vanuit GitHub, kun je de webhook via Traefik routeren of Cloudflare Tunnel gebruiken.

### 5. .env bestanden op LXC's (eenmalig)

De `.env` bestanden met secrets staan nu direct op elke LXC (niet meer in GitHub). Als je ze nog niet hebt, maak ze eenmalig aan:

```bash
# Voorbeeld voor LXC 101 (infra)
pct exec 101 -- bash -c "cat > ~/docker/.env << 'EOF'
DOCKER_DIR=~/docker
CONF_DIR=~/docker/appdata
TZ=Europe/Amsterdam
PUID=1000
PGID=1000
DOMAINNAME_1=jouwdomein.nl
HOSTNAME=infra
PSQL_DBPASS=<wachtwoord>
AUTHENTIK_DBNAME=authentik
AUTHENTIK_DBUSER=authentik
AUTHENTIK_DBPASS=<wachtwoord>
AUTHENTIK_SECRET=<secret>
CLOUDFLARE_IPS=173.245.48.0/20,...
LOCAL_IPS=127.0.0.1/32,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12
MONGO_DBUSER=<user>
MONGO_DBPASS=<wachtwoord>
EOF"
```

Herhaal voor elke LXC met de juiste variabelen (zie `.env.example` en de oude `deploy.yml` voor welke variabelen elke LXC nodig heeft).

Docker secrets (`~/docker/secrets/`) moeten ook eenmalig op de juiste LXC staan:
- **LXC 101**: `cf_dns_api_token`, `basic_auth_credentials`
- **LXC 102**: `plex_claim_token`

### 6. Eerste sync en starten

```bash
# Test handmatig
/opt/gitops/gitops-controller.sh sync

# Check status
/opt/gitops/gitops-controller.sh status

# Start de webhook listener
systemctl start gitops-webhook.service

# Controleer dat de service draait
systemctl status gitops-webhook.service
```

## Dagelijks gebruik

### Status bekijken

```bash
/opt/gitops/gitops-controller.sh status
```

### Handmatig deployen

```bash
# Eén specifieke LXC
/opt/gitops/gitops-controller.sh deploy media
/opt/gitops/gitops-controller.sh deploy 102

# Alles
/opt/gitops/gitops-controller.sh deploy all
```

### Logs bekijken

```bash
# Webhook logs
tail -f /var/log/gitops/webhook.log

# Controller logs
tail -f /var/log/gitops/gitops.log

# Systemd logs
journalctl -u gitops-webhook.service -f
```

### Workflow: Renovate + auto-merge

1. Renovate opent een PR met een nieuwe image versie
2. PR wordt gemerged (handmatig of auto-merge voor patch/minor)
3. GitHub stuurt een webhook → controller deployt de getroffen LXC
4. Status is zichtbaar via `gitops-controller.sh status`

## Wat kan opgeruimd worden na migratie

Als je de GitOps controller gebruikt, zijn de volgende zaken **overbodig**:

### 1. GitHub Actions deploy workflow

Het bestand `.github/workflows/deploy.yml` is al vervangen door een validate-only workflow die alleen compose syntax checkt op PRs (geen secrets nodig).

### 2. GitHub Secrets verwijderen

Alle secrets in GitHub repo settings (Settings → Secrets and variables → Actions):

**Repository/environment secrets:**
- `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET` (Tailscale)
- `PROXMOX_SSH_KEY` / `PROXMOX_SSH_HOST` (SSH)
- Alle wachtwoorden, API keys, database credentials per environment

Dit zijn alle credentials die nu in GitHub staan. Na het verwijderen heeft GitHub geen enkele manier meer om bij je server te komen.

### 3. GitHub Environments verwijderen

De 7 deployment environments (Settings → Environments):
- `prod-infra`, `prod-media`, `prod-home`, `prod-productivity`, `prod-network`, `prod-monitoring`, `prod-utilities`

### 4. Tailscale OAuth client intrekken

De Tailscale OAuth client die voor GitHub Actions CI was aangemaakt kan ingetrokken worden in de Tailscale admin console. De `tag:ci` ACL regel kan ook verwijderd worden.

## Endpoints

| Endpoint | Methode | Beschrijving |
|---|---|---|
| `/webhook` | POST | GitHub webhook ontvanger |
| `/health` | GET | Health check (voor monitoring) |

## Bestanden

```
scripts/gitops/
├── gitops-controller.sh      # Deploy logica (draait op Proxmox)
├── gitops-webhook.py          # Webhook listener (Python, geen dependencies)
├── gitops-webhook.service     # systemd service voor webhook listener
├── config.env.example         # Configuratie template
└── setup.sh                   # Installatie script voor Proxmox
```
