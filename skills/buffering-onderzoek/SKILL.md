---
name: buffering-onderzoek
description: Vaste werkwijze voor klachten over haperen/bufferen bij Plex of Jellyfin. Gebruik bij elke buffer-/streamingklacht van een kijker. Marlijn routeert (Forel, daarna Snoek), Forel en Snoek voeren hun stap uit, Marlijn schrijft één conclusie voor Rick.
---

# Buffering-onderzoek (Plex/Jellyfin)

Doel: elke klacht over haperen/bufferen wordt op dezelfde manier onderzocht en eindigt in één conclusie:
**server, uplink, pad naar provider, of kant van de kijker** (thuisnetwerk/apparaat).
Referentie-onderzoeken: MEE-488 (ankem1), MEE-542 (m.swinn).

## Regels (voor iedereen)
- Alles alleen lezen. Niets herstarten, aanpassen of verwijderen tijdens het onderzoek.
- Altijd met vergelijking: een externe kijker die niet buffert (liefst bij dezelfde provider), of een avond zonder buffering.
- Cijfers altijd met drempel/context erbij (bijv. "md5-busy max 0,84, drempel 0,9"; "68 Mbps = 6,8% van de lijn"). Nooit "lijkt prima".
- Tijden in UTC én NL-tijd.
- Ruwe data (sessielijsten, vensters) als document op de eigen subtask, niet in een comment.
- Geen credentials of volledige IP-adressen van kijkers in comments; IP's alleen in het document dat Snoek nodig heeft.

## Rol Marlijn: routeren
1. Maak subtask **stap 1 voor Forel** (zie hieronder), alleen lezen, met de naam van de kijker en eerdere bufferende kijkers ter vergelijking.
2. Maak subtask **stap 2 voor Snoek**, geblokkeerd door stap 1 (`blockedByIssueIds`), zodat Snoek pas start met de vensters en het IP van Forel.
3. Zet de parent op blocked op beide subtasks en meld Rick kort wat er loopt ("voor jou nu niets").
4. Na stap 2: schrijf de conclusie (stap 3).

## Stap 1 — Forel (media-LXC): sessies en server
1. Alle sessies van de kijker over de laatste 30 dagen (Tautulli/Plex): apparaat, player, locatie/IP, provider, bitrate, kwaliteit, direct play / direct stream / transcode, ingebrande ondertitels, aantal en duur van buffermeldingen.
2. Buffervensters (start/eind, UTC + NL) als document `<kijker>-buffervensters`; sessies als `<kijker>-sessies-30d`.
3. **Kerntest:** keken andere externe kijkers tegelijk, en buffereden die ook? Rapporteer als "x van y vensters schoon voor anderen".
4. Server in die vensters: transcoder-belasting, CPU/IO, OOM-kills, Plex-herstarts.
5. Overlap met eerdere bufferende kijkers (vensters naast elkaar).
6. Patroon: tijdstip van de dag, apparaat (wifi-telefoon vs. TV/kabel), haperingen per uur kijktijd, % sessies met zware buffering.
7. Lever op: IP + provider van de kijker en van een niet-bufferende vergelijkingskijker (zelfde provider als het kan), voor Snoek.

## Stap 2 — Snoek (netwerk/monitoring/host), start na stap 1
Met de buffervensters en IP's uit stap 1:
1. Uitgaand WAN-verkeer tijdens de vensters vs. avonden zonder buffering (Prometheus/UniFi), piek in Mbps en % van de lijn.
2. mtr naar het IP van de kijker én naar de vergelijkingskijker: latency (gem./max) en verlies per hop, vooral de laatste hop.
3. Uploadtest van onze lijn.
4. Interfacefouten (UniFi WAN/switch/AP, host-NIC).
5. Host tijdens de vensters: RAID-drukte (md5-busy vs. drempel, MediaRaidBusy), swap, openstaande/pending alerts.
6. Optioneel: langere ping-meting in de avondpiek als het patroon op piekuren wijst (stopt vanzelf, alleen lezen).

## Stap 3 — Marlijn: conclusie voor Rick (op de parent)
- Kop: in één zin waar het ligt.
- **Wat er mis is**, en hoe ernstig (% sessies, vergelijking met eerdere kijkers).
- **Bewijs per laag:** server / host / uplink / pad / patroon, telkens met cijfers en drempel.
- **Wat je eraan kunt doen**, genummerd, met wie het moet doen (kijker, provider, Rick).
- Of er PR's uit komen. Moet er config veranderen: subtask voor Botje, PR voor Rick.
- Losse bevindingen apart onder **"Losse punten, geen actie voor nu"**.
- Verwijs naar de subtasks en documenten met details. Sluit daarna de parent.
