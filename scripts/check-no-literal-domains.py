#!/usr/bin/env python3
"""Fail when a literal public domain appears in a tracked file.

This is a public repo: domains come from .env (DOMAINNAME_1, DOMAINNAME_2),
never from literals. The domains are built from fragments below so that this
script does not contain them itself.

Files in ALLOWLIST may still contain them (pre-existing, to be cleaned up).
Standard library only. Exit code 1 on any hit.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile("|".join(re.escape(d) for d in ("meels" + ".net", "meelsnet" + ".nl")), re.I)
ALLOWLIST = {
    "README.md",  # pre-existing literals, pending a decision by the owner
}


def main():
    files = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.decode().split("\0")
    hits = []
    for name in filter(None, files):
        if name in ALLOWLIST:
            continue
        path = ROOT / name
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                hits.append(f"{name}:{n}")
    if hits:
        print("Literal domain found (use DOMAINNAME_1 / DOMAINNAME_2 from .env instead):")
        for h in hits:
            print(f"  - {h}")
        return 1
    print("No literal domains outside the allowlist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
