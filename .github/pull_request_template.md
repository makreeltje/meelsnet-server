## Wat en waarom

<!-- Korte omschrijving van de wijziging -->

## Checklist

- [ ] Docs bijgewerkt (`docs/SERVICES.md`, README/GITOPS.md waar relevant) — of: geen docs-impact
- [ ] Nieuwe variabelen staan in `.env.example` én in de `.env` van de betreffende LXC
- [ ] Nieuwe of gewijzigde Traefik-route heeft bewust de juiste chain (authentik / authentik-local / local-only / no-auth)
- [ ] Geen secrets in de diff
