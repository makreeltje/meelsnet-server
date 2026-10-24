#!/usr/bin/env python3
"""Check that docs/SERVICES.md matches the compose and Traefik config.

Checks:
  1. Per LXC: the container_names of all active includes in lxc/<name>/compose.yml
     equal the container names in the matching "## LXC <id> — <name>" section.
  2. Every active Traefik route in traefik/services/ has its hostname
     (`sub.`D1 or `sub.`D2) mentioned in docs/SERVICES.md.

Standard library only. Exit code 1 on any mismatch.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "SERVICES.md"
DOMAIN_ALIAS = {"DOMAINNAME_1": "D1", "DOMAINNAME_2": "D2"}


def active_includes(lxc_compose: Path):
    pat = re.compile(r"^\s+-\s+(compose/\S+\.ya?ml)\s*$")
    return [m.group(1) for line in lxc_compose.read_text().splitlines() if (m := pat.match(line))]


def compose_containers(lxc_compose: Path):
    names = set()
    for inc in active_includes(lxc_compose):
        text = (ROOT / inc).read_text()
        names.update(re.findall(r"^\s+container_name:\s*(\S+)", text, re.M))
    return names


def documented_containers(doc_text: str):
    sections = {}
    for m in re.finditer(r"^## LXC (\d+) — (\S+).*?$(.*?)(?=^## |\Z)", doc_text, re.M | re.S):
        names = set()
        for row in re.findall(r"^\|\s*([^|]+?)\s*\|", m.group(3), re.M):
            if row.startswith("`"):
                names.update(re.findall(r"`([^`]+)`", row))
        sections[m.group(2)] = names
    return sections


def route_hosts():
    hosts = {}
    pat = re.compile(r"Host\(`([a-z0-9-]+)\.\{\{env \"(DOMAINNAME_[12])\"\}\}`\)")
    for f in sorted((ROOT / "traefik" / "services").rglob("*.y*ml")):
        for line in f.read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue
            for sub, dom in pat.findall(line):
                hosts.setdefault(f"`{sub}.`{DOMAIN_ALIAS[dom]}", f.relative_to(ROOT))
    return hosts


def main():
    doc_text = DOC.read_text()
    documented = documented_containers(doc_text)
    errors = []

    for lxc_compose in sorted((ROOT / "lxc").glob("*/compose.yml")):
        lxc = lxc_compose.parent.name
        actual = compose_containers(lxc_compose)
        docs = documented.get(lxc)
        if docs is None:
            errors.append(f"{DOC.name}: no section '## LXC <id> — {lxc}'")
            continue
        for n in sorted(actual - docs):
            errors.append(f"{lxc}: container '{n}' is in lxc/{lxc}/compose.yml but not in {DOC.name}")
        for n in sorted(docs - actual):
            errors.append(f"{lxc}: '{n}' is in {DOC.name} but no longer in lxc/{lxc}/compose.yml")

    for token, src in route_hosts().items():
        if token not in doc_text:
            errors.append(f"{src}: hostname {token} is not mentioned in {DOC.name}")

    if errors:
        print("Docs are out of date:")
        for e in errors:
            print(f"  - {e}")
        print(f"\nUpdate docs/SERVICES.md (see 'Documentatie actueel houden' there).")
        return 1
    print("docs/SERVICES.md matches compose and Traefik config.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
