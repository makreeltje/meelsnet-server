# GitOps Controller

Pull-based deployment controller die GitHub pollt voor wijzigingen en automatisch de getroffen LXC containers deployt via Proxmox `pct`.

## Waarom?

De oude GitHub Actions workflow (`deploy.yml`) is **push-based**: GitHub heeft via Tailscale OAuth + SSH directe toegang tot de Proxmox server. Als iemand toegang krijgt tot de GitHub repo, heeft diegene ook toegang tot de server.

De GitOps controller draait **op de server zelf** en **haalt** wijzigingen op (pull-based). GitHub heeft geen enkele kennis van de server. Het enige dat nodig is, is een read-only deploy key op Proxmox.

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
│  Proxmox ──git fetch (read-only)──> GitHub                  │
│  Controller detecteert changes → deploy naar getroffen LXCs │
│  (pull-based, GitHub weet niets van de server)              │
└─────────────────────────────────────────────────────────────┘
```

## Hoe werkt het?

1. Systemd timer triggert elke 2 minuten `gitops-controller.sh sync`
2. Script doet `git fetch` en vergelijkt met de laatst gedeployde commit
3. Bij wijzigingen: bepaalt welke files zijn gewijzigd
4. Mapt gewijzigde files naar de juiste LXC container(s)
5. Deployt alleen de getroffen LXC's (`pct push` + `docker compose up -d`)
6. Slaat de gedeployde commit SHA op

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

### 4. .env bestanden op LXC's (eenmalig)

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

### 5. Eerste sync

```bash
# Test handmatig
/opt/gitops/gitops-controller.sh sync

# Check status
/opt/gitops/gitops-controller.sh status

# Start de timer
systemctl start gitops-controller.timer

# Controleer dat de timer actief is
systemctl list-timers gitops-controller.timer
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
# Controller logs
tail -f /var/log/gitops/gitops.log

# Systemd logs
journalctl -u gitops-controller.service -f
```

### Workflow: Renovate + auto-merge

1. Renovate opent een PR met een nieuwe image versie
2. PR wordt gemerged (handmatig of auto-merge voor patch/minor)
3. Binnen 2 minuten detecteert de controller de change op `main`
4. Alleen de getroffen LXC wordt gedeployed
5. Status is zichtbaar via `gitops-controller.sh status`

## Wat kan opgeruimd worden na migratie

Als je de GitOps controller gebruikt, zijn de volgende zaken in de GitHub repo **overbodig**:

### 1. GitHub Actions workflow verwijderen
```
.github/workflows/deploy.yml
```
De hele deploy workflow is vervangen door de controller.

### 2. GitHub Secrets verwijderen

Alle secrets in GitHub repo settings (Settings → Secrets and variables → Actions) kunnen verwijderd worden:

**Repository secrets:**
- `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET` (Tailscale)
- `PROXMOX_SSH_KEY` / `PROXMOX_SSH_HOST` (SSH)
- Alle per-environment secrets (prod-infra, prod-media, etc.)

Dit zijn alle wachtwoorden, API keys, en credentials die nu in GitHub staan. Na het verwijderen heeft GitHub geen enkele manier meer om bij je server te komen.

### 3. GitHub Environments verwijderen

De 7 deployment environments (Settings → Environments):
- `prod-infra`
- `prod-media`
- `prod-home`
- `prod-productivity`
- `prod-network`
- `prod-monitoring`
- `prod-utilities`

### 4. Tailscale OAuth client intrekken

De Tailscale OAuth client die voor GitHub Actions CI was aangemaakt kan ingetrokken worden in de Tailscale admin console. De `tag:ci` ACL regel kan ook verwijderd worden.

### 5. Optioneel: GitHub Actions validate workflow behouden

Je kunt een **uitgeklede** workflow behouden die alleen compose syntax valideert op PRs (zonder deploy):

```yaml
name: Validate
on:
  pull_request:
    paths: ['compose/**', 'lxc/**']
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          cp .env.example .env
          sed -i 's/=$/=dummy/g' .env
          docker compose config --quiet
```

Dit vereist geen secrets en is puur een syntax check.

## Bestanden

```
scripts/gitops/
├── gitops-controller.sh     # Hoofd-script (draait op Proxmox)
├── gitops-controller.service # systemd service unit
├── gitops-controller.timer   # systemd timer (elke 2 min)
├── config.env.example        # Configuratie template
└── setup.sh                  # Installatie script voor Proxmox
```
