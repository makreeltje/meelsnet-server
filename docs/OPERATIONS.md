# Operations: secrets, back-up en handmatige stappen

De repo is de bron van waarheid; wijzigingen op een server worden door de GitOps-controller overschreven. Deze pagina beschrijft wat *niet* uit de repo komt. Het service-overzicht staat in [SERVICES.md](SERVICES.md), de deploy-flow in [GITOPS.md](../GITOPS.md).

## Secrets en `.env`

- Niet in git: `.env`, `secrets/` en `appdata/` staan in `.gitignore`. Variabelen en hun betekenis staan in `.env.example`; `.env.ci` bevat alleen dummywaarden voor de CI-validatie.
- Per LXC: `/root/docker/.env` (variabelen) en `/root/docker/secrets/` (Docker secrets). Nieuwe variabele in een compose-bestand? Voeg hem toe aan `.env.example` **en** zet hem handmatig in de `.env` van de betreffende LXC vóór de merge, anders start de container niet.
- Docker secrets: alleen op infra (`cf_dns_api_token`, `basic_auth_credentials`). Overige tokens (zoals `PLEX_CLAIM_TOKEN`) staan als variabele in de `.env`.
- Rechten: `.env` hoort `600` te zijn.
- CI scant de werkboom (Trivy) en de volledige git-historie (gitleaks) op secrets, bij elke push/PR en wekelijks op maandag.

## Back-up en restore

### Wat wordt er geback-upt

| Wat | Mechanisme | Waar |
|---|---|---|
| PostgreSQL (alle databases) en MariaDB | `scripts/backup/postgres.sh`, `mariadb.sh` op de Proxmox-host (dumps uit LXC 101) | `/mnt/pve/data/backups/databases/{postgres,mariadb}/<datum>_<db>.sql`, lokaal 1 dag bewaard |
| Paperless | `scripts/backup/paperless.sh` (document_exporter) | `/mnt/backups/app-data/paperless/export` (binnen LXC 104) |
| Home Assistant, Frigate | `scripts/backup/homeassistant.sh`, `frigate.sh` | `/mnt/backups/app-data/{homeassistant,frigate}`, 1 dag lokaal |
| Immich-bibliotheek | `scripts/backup/immich.sh` (bestandskopie) | `/mnt/pve/data/backups/app-data/immich/library` |
| Nextcloud | `scripts/backup/nextcloud.sh` (uitgeschakelde service; script bestaat nog) | `/mnt/pve/data/backups/app-data/nextcloud` |
| Alle appdata + compose van LXC 104, plus `/mnt/backups` | Backrest (restic) in `backrest`, naar Azure Blob | Plannen en retentie in de Backrest-UI (`backup.`$DOMAINNAME_2); de databasedumps gaan met het plan *databases* mee (keep-last-3 snapshots, volgens de scriptcommentaar) |

Alle scripts melden start/succes/fout aan healthchecks.io als de bijbehorende `HC_*`-variabele in `/etc/default/backup-scripts` op de Proxmox-host staat; zonder variabele draait de back-up gewoon zonder ping. Fouten komen in de journal: `journalctl -t backup-<naam> -p err`.

De scripts in `scripts/backup/` worden door de GitOps-controller naar `/root/scripts/backup/` op de host gekopieerd. **De cron-regels die ze starten staan niet in de repo** (zie hieronder).

### Restore

Een uitgeschreven, geteste restore-procedure bestaat nog niet in de repo. De uitgangspunten, afgeleid van de scripts:

1. De compose-configuratie herstelt zichzelf: `deploy <lxc>` via de controller zet de repo-staat terug. Alleen `.env` en `secrets/` moeten uit een eigen kopie komen (die staan bewust niet in git of in de dumps).
2. Databases: de `.sql`-dumps zijn per database; terugzetten gaat met `psql`/`mariadb` in de `postgres`/`mariadb`-container op infra.
3. Appdata per app: uit de Backrest-snapshot (restic restore via de Backrest-UI) of uit de lokale kopieën hierboven.

> **Open punt:** de restore-stappen per app zijn niet getest of vastgelegd; zie de PR-beschrijving.

## Handmatige stappen buiten de repo

Dit staat op de Proxmox-host of in de LXC's en wordt **niet** door GitOps beheerd. Wijzigingen hieraan gaan dus ook niet via een PR.

| Onderdeel | Waar | Opmerking |
|---|---|---|
| Cron-regels voor `scripts/backup/*` | Proxmox-host | Schema niet in repo |
| `/etc/default/backup-scripts` (healthchecks.io-URL's) | Proxmox-host | Bevat URL's; niet committen |
| `/etc/gitops/config.env` (incl. `WEBHOOK_SECRET`) | Proxmox-host | Template: `scripts/gitops/config.env.example` |
| Deploy key (read-only) en webhook in GitHub | Proxmox-host / GitHub | Zie GITOPS.md |
| LXC-resources, bind mounts (`/mnt/...`) en device passthrough (iGPU, USB-dongle Zigbee, `/mnt/frigate`) | Proxmox LXC-config | Niet in compose zichtbaar |
| `.env` en `secrets/` per LXC | elke LXC | Zie boven |
| Cloudflare DNS en tokens | Cloudflare | DNS-challenge voor wildcard-certificaten |
| Authentik-configuratie (applicaties, providers, flows) | Authentik-UI | Zit in de database, niet in de repo |
| Prometheus-, Alertmanager- en Loki-configuratie | `appdata/` op LXC 106 | Niet in de repo |
| smartctl-exporter | Proxmox-host (`:9633`) | Gescrapet door Prometheus |
| `guides/` en `CLAUDE.md` | infra-LXC | Staan in `.gitignore`, niet in de repo |
