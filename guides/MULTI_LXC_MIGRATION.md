# Multi-LXC Migration Guide

*Tailored to your hardware: Intel i5-8600K (6 cores), 32 GB RAM, Intel UHD 630, 2 TB NVMe + 72 TB RAID-5, single Proxmox host.*

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Critical Pre-Migration Checks](#2-critical-pre-migration-checks)
3. [Phase 1 — Proxmox Preparation](#3-phase-1--proxmox-preparation)
4. [Phase 2 — LXC Creation & Resource Allocation](#4-phase-2--lxc-creation--resource-allocation)
5. [Phase 3 — Storage Coupling](#5-phase-3--storage-coupling)
6. [Phase 4 — GPU & Hardware Passthrough](#6-phase-4--gpu--hardware-passthrough)
7. [Phase 5 — Networking (vmbr1 Internal Bridge)](#7-phase-5--networking-vmbr1-internal-bridge)
8. [Phase 6 — Secrets via GitHub Actions](#8-phase-6--secrets-via-github-actions)
9. [Phase 7 — Traefik Cross-LXC Routing](#9-phase-7--traefik-cross-lxc-routing)
10. [Phase 8 — Migration Order & Service Move Playbook](#10-phase-8--migration-order--service-move-playbook)
11. [Appendix — Per-LXC compose.yml Templates](#appendix--per-lxc-composeyml-templates)

---

## 1. Architecture Overview

### Target LXC Layout

```
┌──────────────────────────────────────────────────────────────────┐
│                Proxmox Host (i5-8600K, 32 GB RAM)                │
│                                                                  │
│  ┌──────────────────┐   ┌───────────────────┐                    │
│  │  LXC 101 — infra │   │  LXC 102 — media  │                    │
│  │  2 vCPU / 4 GB   │   │  4 vCPU / 8 GB    │                    │
│  │  vmbr0 + vmbr1   │   │  vmbr0 + vmbr1    │                    │
│  │                  │   │  [Intel UHD 630]  │                    │
│  │  Traefik         │   │  Plex             │                    │
│  │  Authentik       │   │  *arr apps        │                    │
│  │  Postgres        │   │  SABnzbd          │                    │
│  │  Redis           │   │  qBittorrent+VPN  │                    │
│  │  MongoDB         │   │  Tautulli         │                    │
│  └──────────────────┘   └───────────────────┘                    │
│                                                                  │
│  ┌──────────────────┐   ┌───────────────────┐                    │
│  │  LXC 103 — home  │   │  LXC 104 — prod   │                    │
│  │  2 vCPU / 4 GB   │   │  2 vCPU / 6 GB    │                    │
│  │  vmbr0 + vmbr1   │   │  vmbr0 + vmbr1    │                    │
│  │  [Intel UHD 630] │   │                   │                    │
│  │  [USB: Zigbee]   │   │  Immich           │                    │
│  │                  │   │  Paperless        │                    │
│  │  Home Assistant  │   │  Nextcloud        │                    │
│  │  Zigbee2MQTT     │   │  n8n              │                    │
│  │  Mosquitto       │   │  Firefly          │                    │
│  │  Frigate         │   │  Backrest         │                    │
│  │  Node-RED        │   └───────────────────┘                    │
│  │  Music Assistant │                                            │
│  └──────────────────┘                                            │
│                                                                  │
│  ┌──────────────────┐   ┌──────────────────┐   ┌─────────────┐   │
│  │  LXC 105 — net   │   │  LXC 106 — mon   │   │  LXC 107    │   │
│  │  1 vCPU / 1 GB   │   │  2 vCPU / 3 GB   │   │  utilities  │   │
│  │  vmbr0 + vmbr1   │   │  vmbr0 + vmbr1   │   │  1 vCPU/1GB │   │
│  │                  │   │                  │   │  vmbr0+vmbr1│   │
│  │  Pi-hole         │   │  Grafana         │   │             │   │
│  │  Unifi           │   │  Prometheus      │   │  Spoolman   │   │
│  │                  │   │  Loki            │   │  OmniTools  │   │
│  │                  │   │  Promtail        │   │  Printer-   │   │
│  │                  │   │  Exporters       │   │  Calculator │   │
│  └──────────────────┘   └──────────────────┘   └─────────────┘   │
│                                                                  │
│  ════════════════════ vmbr0 (internet) ══════════════════════    │
│  ════════════════════ vmbr1 (10.10.0.0/24) ══════════════════    │
│  ════════════════════ NVMe (LXC root disks) ═════════════════    │
│  ════════════════════ RAID-5 (media/data) ═══════════════════    │
└──────────────────────────────────────────────────────────────────┘
```

### IP Address Plan

| LXC | Name | vmbr0 (internet) | vmbr1 (internal) |
|-----|------|------------------|------------------|
| 101 | infra | your-current-ip | 10.10.0.10 |
| 102 | media | DHCP or static | 10.10.0.20 |
| 103 | home | DHCP or static | 10.10.0.30 |
| 104 | productivity | DHCP or static | 10.10.0.40 |
| 105 | network | DHCP or static | 10.10.0.50 |
| 106 | monitoring | DHCP or static | 10.10.0.60 |
| 107 | utilities | DHCP or static | 10.10.0.70 |

vmbr1 has no gateway — it is LAN-only, not routed to the internet. Only Proxmox host and LXCs are on it.

### Resource Budget

| LXC | vCPU | RAM | NVMe Disk | RAID-5 Mounts |
|-----|------|-----|-----------|---------------|
| 101 infra | 2 | 4 GB | 32 GB | — |
| 102 media | 4 | 8 GB | 32 GB | `/mnt/media` |
| 103 home | 2 | 4 GB | 20 GB | — |
| 104 productivity | 2 | 6 GB | 32 GB | `/mnt/photos`, `/mnt/media` (read) |
| 105 network | 1 | 1 GB | 8 GB | — |
| 106 monitoring | 2 | 3 GB | 80 GB | — |
| 107 utilities | 1 | 1 GB | 8 GB | — |
| **Total** | **14** | **27 GB** | **212 GB** | |

Notes:
- vCPU overcommit (14 vCPU on 6 physical cores) is normal and safe for LXCs — they time-share under load.
- 5 GB reserved for Proxmox host overhead (27 + 5 = 32 GB total).
- Monitoring gets 80 GB disk because Prometheus metrics + Loki logs accumulate over time.
- 212 GB NVMe for LXC disks + 96 GB existing OS = 308 GB total. NVMe is 2 TB, so you have ~1.7 TB spare for growth.

---

## 2. Critical Pre-Migration Checks

**Do these before creating any new LXCs.**

### 2.1 CPU Temperature — CRITICAL

Your CPU is currently running at **96°C** with a Tjunction max of 100°C. This is thermal throttling territory and needs to be addressed before adding more LXC load.

```bash
# Check current temps on Proxmox host
sensors
# Look for "Package id 0" and "Core X" lines

# Monitor over time
watch -n 2 sensors
```

**Actions required:**
1. Clean CPU cooler fan and heatsink (dust accumulation over 37+ days of uptime)
2. Replace thermal paste — after years of use it dries out
3. Check case airflow (ITX form factor = tight space, add fan if possible)
4. After cleaning, temps should drop to 60-80°C under load

> Running migrations at 96°C risks thermal shutdown mid-migration. Fix cooling first.

### 2.2 Swap Usage

Your swap is 100% full (8 GB). This means containers are actively using swap, which causes slowdowns and can cause OOM kills when starting new LXCs.

```bash
# See what's using swap
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  swap=$(cat /proc/$pid/status 2>/dev/null | grep VmSwap | awk '{print $2}')
  if [ -n "$swap" ] && [ "$swap" -gt "0" ]; then
    name=$(cat /proc/$pid/comm 2>/dev/null)
    echo "$swap kB - $name (PID $pid)"
  fi
done | sort -n -r | head -20
```

You may want to increase swap to 16 GB before migrating:
```bash
# On Proxmox host — resize swap LV (adjust LV name to yours)
lvextend -L 16G /dev/pve/swap
swapoff /dev/pve/swap
mkswap /dev/pve/swap
swapon /dev/pve/swap
```

### 2.3 Check Current Storage Mount Setup

Before migrating storage, find out how the RAID-5 is currently attached to LXC 101:

```bash
# On Proxmox host
cat /proc/mdstat            # Verify md5 RAID is healthy
cat /etc/pve/lxc/101.conf   # See how storage is passed to the LXC

# Check if RAID is mounted on the Proxmox host
mount | grep md5
ls /mnt/
```

You will see one of two situations:

**Case A** — RAID is mounted on Proxmox host and bind-mounted into LXC 101:
```
# In 101.conf you'll see something like:
mp0: /mnt/data/media,mp=/mnt/media
```
Good. Just add the same `mp` lines to the new LXCs.

**Case B** — RAID device is passed directly to LXC 101 (raw device passthrough):
```
# In 101.conf you'll see something like:
dev0: /dev/md5,mode=rw
```
You need to mount it on the Proxmox host first (see Phase 3).

---

## 3. Phase 1 — Proxmox Preparation

### 1.1 Add NVMe as a Proxmox storage pool (if not already)

LXC root disks should live on the NVMe for speed. Check current storage:

```bash
pvesm status
# Look for a storage pool pointing to the NVMe
```

If the NVMe is already the `local-lvm` pool, you're set. If not, add it via Proxmox web UI:
- Datacenter → Storage → Add → LVM-Thin
- Base storage: `/dev/nvme0n1` (or the appropriate partition)
- ID: `nvme-fast`

### 1.2 Create vmbr1 internal bridge

This is the backbone for inter-LXC communication. Do this on the Proxmox host.

**Via Proxmox web UI:**
1. Node → Network → Create → Linux Bridge
2. Name: `vmbr1`
3. IPv4/CIDR: `10.10.0.1/24` (Proxmox host gets .1)
4. Leave "Gateway" blank — this is internal only, not routed
5. Comment: `LXC internal bridge`
6. Apply configuration

**Or via CLI:**
```bash
# Edit /etc/network/interfaces — add this block
cat >> /etc/network/interfaces << 'EOF'

auto vmbr1
iface vmbr1 inet static
    address 10.10.0.1/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
    comment LXC internal bridge
EOF

# Apply without reboot
ifreload -a
```

### 1.3 Mount RAID-5 on the Proxmox host

If you are in **Case B** above (raw device in LXC), do this first. If Case A, skip.

```bash
# Find the RAID array mount point or filesystem
blkid /dev/md5

# Create mount point on Proxmox host
mkdir -p /mnt/pve/media
mkdir -p /mnt/pve/photos
mkdir -p /mnt/pve/downloads

# Add to /etc/fstab (adjust filesystem type — probably ext4 or xfs)
echo "/dev/md5  /mnt/pve/data  ext4  defaults,nofail  0  2" >> /etc/fstab
mount -a

# Verify
ls /mnt/pve/data/
```

> The RAID must be mounted on the Proxmox **host** for bind-mounting into multiple LXCs. It cannot be mounted in two LXCs at once as a device.

### 1.4 Download Debian template

```bash
# On Proxmox host — download Debian 12 (bookworm) template
pveam update
pveam available | grep debian-12
pveam download local debian-12-standard_12.12-1_amd64.tar.zst
```

---

## 4. Phase 2 — LXC Creation & Resource Allocation

Create each LXC using `pct create`. Replace `local-lvm` with your NVMe storage pool name if different.

### LXC 101 — infra (existing, reconfigure)

LXC 101 already exists. After migrating services out, resize it down:
```bash
# After migration, reduce resources on Proxmox host
pct set 101 --memory 4096 --cores 2
```

### LXC 102 — media

```bash
pct create 102 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname media \
  --cores 4 \
  --memory 8192 \
  --swap 2048 \
  --rootfs local-lvm:32 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --net1 name=eth1,bridge=vmbr1,ip=10.10.0.20/24 \
  --unprivileged 0 \
  --features nesting=1 \
  --onboot 1 \
  --start 0

# Note: unprivileged=0 (privileged) required for GPU passthrough
```

### LXC 103 — home

```bash
pct create 103 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname home \
  --cores 2 \
  --memory 4096 \
  --swap 1024 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --net1 name=eth1,bridge=vmbr1,ip=10.10.0.30/24 \
  --unprivileged 0 \
  --features nesting=1 \
  --onboot 1 \
  --start 0

# Privileged required for: GPU passthrough + USB (Zigbee dongle)
```

### LXC 104 — productivity

```bash
pct create 104 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname productivity \
  --cores 2 \
  --memory 6144 \
  --swap 2048 \
  --rootfs local-lvm:32 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --net1 name=eth1,bridge=vmbr1,ip=10.10.0.40/24 \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1 \
  --start 0
```

### LXC 105 — network

```bash
pct create 105 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname network \
  --cores 1 \
  --memory 1024 \
  --swap 512 \
  --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --net1 name=eth1,bridge=vmbr1,ip=10.10.0.50/24 \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1 \
  --start 0
```

### LXC 106 — monitoring

```bash
pct create 106 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname monitoring \
  --cores 2 \
  --memory 3072 \
  --swap 1024 \
  --rootfs local-lvm:80 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --net1 name=eth1,bridge=vmbr1,ip=10.10.0.60/24 \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1 \
  --start 0
```

### LXC 107 — utilities

```bash
pct create 107 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname utilities \
  --cores 1 \
  --memory 1024 \
  --swap 512 \
  --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --net1 name=eth1,bridge=vmbr1,ip=10.10.0.70/24 \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1 \
  --start 0
```

### Install Docker in each new LXC

Run this inside each new LXC after starting it (`pct start <ID> && pct enter <ID>`):

```bash
# Install Docker (official method — works in privileged and unprivileged LXCs)
apt update && apt install -y curl ca-certificates
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify
docker compose version
```

---

## 5. Phase 3 — Storage Coupling

### How it works

The Proxmox host mounts the RAID-5 array and then bind-mounts specific directories into each LXC via `mp` (mount point) entries in the LXC config file. This means:

- One RAID mount on the Proxmox host
- Any number of LXCs can access subdirectories simultaneously
- No NFS required — it's a kernel-level bind mount, very efficient
- Each LXC only gets the subdirectories it actually needs

### Assumed directory structure on RAID-5

```
/mnt/pve/data/
├── media/
│   ├── movies/
│   ├── tv-shows/
│   ├── music/
│   └── downloads/
│       ├── incomplete/
│       └── complete/
├── photos/
│   └── library/
├── backups/
│   ├── restic/
│   └── database-dumps/
└── paperless/
    └── media/
```

Adjust these paths to match your actual RAID layout.

### appdata directory — stays on NVMe

All container config/data (`appdata/`) stays on the **NVMe** inside each LXC's root disk. Only large media files come from the RAID. This is intentional: database files, Prometheus data, and config files need the low-latency NVMe, not spinning RAID.

### Add bind mounts to each LXC config

**Do this on the Proxmox host** after stopping each LXC (or while it's running for some filesystems, but stopping is safer):

```bash
# LXC 102 — media (needs read+write access to media + downloads)
pct set 102 \
  --mp0 /mnt/pve/data/media,mp=/mnt/media \
  --mp1 /mnt/pve/data/media/downloads,mp=/mnt/downloads

# LXC 103 — home (no large storage needed unless you backup camera footage)
# Add only if Frigate records to RAID:
# pct set 103 --mp0 /mnt/pve/data/frigate-recordings,mp=/mnt/frigate

# LXC 104 — productivity (read access to media for Immich, full access for photos)
pct set 104 \
  --mp0 /mnt/pve/data/photos,mp=/mnt/photos \
  --mp1 /mnt/pve/data/paperless,mp=/mnt/paperless \
  --mp2 /mnt/pve/data/backups,mp=/mnt/backups

# LXC 106 — monitoring (optionally log to RAID for long retention)
# Usually not needed if 80 GB NVMe disk is enough

# LXC 107 — utilities (no media access needed)
```

> **Unprivileged LXC note**: If using unprivileged LXCs (104, 105, 106, 107), you may need to map UIDs. Add `--mp0 ...,ro=0` and ensure the Proxmox host directory has correct ownership. If you hit permission errors, the simplest fix is `chmod 777 /mnt/pve/data/<dir>` temporarily, then tighten later.

### Verify inside the LXC

```bash
# Inside LXC 102
pct enter 102
ls /mnt/media/movies   # Should see your movies
ls /mnt/downloads/     # Should see downloads directory
```

---

## 6. Phase 4 — GPU & Hardware Passthrough

Both LXC 102 (Plex) and LXC 103 (Frigate) need the Intel UHD 630. In LXC, this is **device file passthrough** — not exclusive like VM GPU passthrough. Multiple LXCs can share the same `/dev/dri` simultaneously.

### 6.1 Check GPU devices on Proxmox host

```bash
ls -la /dev/dri/
# card0 or card1 → main DRM device (card1 is normal if a virtual framebuffer grabbed minor 0 first)
# renderD128     → render node (used by both Plex QuickSync and Frigate OpenVINO)

# Get device major:minor numbers — output is hex, convert to decimal for cgroup2 lines
stat -c '%t %T' /dev/dri/card0      # or card1 — use whatever ls showed
stat -c '%t %T' /dev/dri/renderD128
# Example output: "e2 0" and "e2 80"
# e2 hex = 226 decimal, 80 hex = 128 decimal → so these are 226:0 and 226:128
# If you got "e2 1" for card1, that is 226:1 — just use that number

# Also check for render group GID
getent group render  # e.g. render:x:993:
getent group video   # e.g. video:x:44:
```

### 6.2 Configure LXC 102 and 103 for GPU

**On Proxmox host** — edit each LXC config file:

```bash
nano /etc/pve/lxc/102.conf
```

Add these lines (adjust card0/card1 and major:minor numbers from the stat output above):

```ini
# GPU passthrough — Intel UHD 630
# Replace 226:0 with your card's actual decimal major:minor from stat output
# e.g. "e2 0" → 226:0   or   "e2 1" → 226:1   (e2 hex = 226 decimal)
# renderD128 is almost always 226:128 (e2 80 → 226:128)
lxc.cgroup2.devices.allow: c 226:0 rwm
lxc.cgroup2.devices.allow: c 226:128 rwm
lxc.mount.entry: /dev/dri/card0 dev/dri/card0 none bind,optional,create=file
lxc.mount.entry: /dev/dri/renderD128 dev/dri/renderD128 none bind,optional,create=file
```

> **If you have `card1` instead of `card0`**: use `226:1` and `card1` in the lines above. `card1` is normal when a virtual framebuffer device registers before the Intel GPU and takes minor 0.

> **render group inside the LXC**: After the LXC boots, run `getent group render` inside it. If the group is missing or has a different GID than the Proxmox host, create it: `groupadd -g <HOST_GID> render`. For privileged LXCs, UIDs/GIDs map 1:1 so the host's render GID should carry through automatically.

Do the same for `/etc/pve/lxc/103.conf`.

### 6.3 USB Passthrough for Zigbee dongle (LXC 103)

Find your Zigbee coordinator on the Proxmox host:

```bash
ls -la /dev/serial/by-id/
# Example: usb-ITEAD_SONOFF_Zigbee_3.0_USB_Dongle_Plus_...-if00-port0 -> ../../ttyUSB0

# Get device numbers
stat -c '%t %T' /dev/ttyUSB0
```

Add to `/etc/pve/lxc/103.conf`:

```ini
# Zigbee USB dongle — adjust 188:0 to your actual major:minor
lxc.cgroup2.devices.allow: c 188:0 rwm
lxc.mount.entry: /dev/ttyUSB0 dev/ttyUSB0 none bind,optional,create=file
```

> **Tip**: Use `by-id` path in Home Assistant and Zigbee2MQTT configs, not `/dev/ttyUSB0`, so it survives reboots and reconnects.

### 6.4 Verify inside the LXC

```bash
pct enter 102
ls /dev/dri/          # Should show card0 and renderD128
# For Plex: check that the plex user can access it
docker exec plex ls -la /dev/dri/
```

---

## 7. Phase 5 — Networking (vmbr1 Internal Bridge)

### How services talk across LXCs

```
Internet → vmbr0 → Traefik (LXC 101) → vmbr1 → Service (LXC 102-107)
                                               ↑
                                         file-based routing rules
                                         pointing to 10.10.0.x:PORT
```

Each LXC has two network interfaces:
- `eth0` on `vmbr0` — for internet access (DNS updates, image pulls, external traffic)
- `eth1` on `vmbr1` — for backend-to-backend communication (Traefik → services, services → databases)

### What this means for services

**Services on LXC 2-7 that Traefik routes to:**
- Expose their port on the `eth1` interface (`10.10.0.x` address)
- Do this with Docker `ports` bound to the vmbr1 IP: `"10.10.0.20:8989:8989"`
- Drop `expose` (pointless when using `ports`)

**Database connections from other LXCs:**
- Services use `POSTGRES_HOST=10.10.0.10` instead of container name `postgres`
- Add these to the per-LXC `.env` file

**Firewall (optional but recommended):**

```bash
# On Proxmox host — allow vmbr1 traffic between LXCs
# Add to /etc/network/interfaces vmbr1 block:
#   post-up iptables -I FORWARD -i vmbr1 -j ACCEPT
#   post-up iptables -I FORWARD -o vmbr1 -j ACCEPT
```

Or use Proxmox's built-in firewall:
- Datacenter → Firewall → Options → Enable Firewall: Yes
- Add rules to allow TCP traffic on vmbr1 between LXC IPs

### Verify inter-LXC connectivity

```bash
# From LXC 102, ping infra LXC
ping 10.10.0.10

# From LXC 102, test Postgres port (after migration)
nc -zv 10.10.0.10 5432
# Should say: Connection to 10.10.0.10 5432 port [tcp/postgresql] succeeded!

# From LXC 101, test a service on LXC 102
nc -zv 10.10.0.20 8989   # Sonarr
```

---

## 8. Phase 6 — Secrets via GitHub Actions

The goal: **no secrets ever touch the Git repository**. Secrets live only in GitHub Actions Secrets and on the servers themselves. The deployment workflow writes `.env` files to each LXC at deploy time.

### 8.1 Repository structure for secrets

```
.env.example        ← committed — all variable NAMES, no secret values
.env.infra.example  ← committed — infra-specific variable names
.env.media.example  ← committed — media-specific variable names
...                 ← one per LXC

# NOT committed (generated by GitHub Actions on deploy):
.env                ← on each LXC, written by deploy workflow
secrets/            ← on LXC 101, written by deploy workflow
```

### 8.2 Split `.env` by LXC

Each LXC only needs the variables for its own services. This limits the blast radius if one LXC is compromised.

**LXC 101 (infra) — `.env`:**
```bash
# Paths
DOCKER_DIR=/root/docker
CONF_DIR=/root/docker/appdata
LOG_DIR=/root/docker/logs
TZ=Europe/Amsterdam
PUID=1000
PGID=1000
DOMAINNAME_1=example.com
HOSTNAME=docker
CLOUDFLARE_IPS=...
LOCAL_IPS=...

# Secrets (written by GitHub Actions)
TRAEFIK_AUTH_BYPASS_KEY=<from GH secret>
PSQL_DBUSER=postgres
PSQL_DBPASS=<from GH secret>
AUTHENTIK_SECRET=<from GH secret>
AUTHENTIK_DBPASS=<from GH secret>
AUTHENTIK_VERSION=2025.8.1
MONGO_ROOT_PASS=<from GH secret>
```

**LXC 102 (media) — `.env`:**
```bash
DOCKER_DIR=/root/docker
CONF_DIR=/root/docker/appdata
MEDIA_DIR=/mnt/media
DOWNLOAD_DIR=/mnt/downloads
TZ=Europe/Amsterdam
PUID=1000
PGID=1000
DOMAINNAME_1=example.com
HOSTNAME=docker
TRAEFIK_AUTH_BYPASS_KEY=<from GH secret>

# Media-specific
PLEX_ADVERTISE_IP=<from GH secret>
VPN_USER=<from GH secret>
VPN_PASS=<from GH secret>
VPN_PROV=<from GH secret>
SONARR_API_KEY=<from GH secret>
RADARR_API_KEY=<from GH secret>
PROWLARR_API_KEY=<from GH secret>
SABNZBD_API_KEY=<from GH secret>

# Database — point to LXC 101
POSTGRES_HOST=10.10.0.10
```

**LXC 103 (home) — `.env`:**
```bash
DOCKER_DIR=/root/docker
CONF_DIR=/root/docker/appdata
TZ=Europe/Amsterdam
DOMAINNAME_1=example.com
HOSTNAME=docker
TRAEFIK_AUTH_BYPASS_KEY=<from GH secret>

FRIGATE_RTSP_PASSWORD=<from GH secret>
MOSQUITTO_USER=<from GH secret>
MOSQUITTO_PASS=<from GH secret>
```

**LXC 104 (productivity) — `.env`:**
```bash
DOCKER_DIR=/root/docker
CONF_DIR=/root/docker/appdata
PHOTOS_DIR=/mnt/photos
PAPERLESS_DIR=/mnt/paperless
TZ=Europe/Amsterdam
PUID=1000
PGID=1000
DOMAINNAME_1=example.com
HOSTNAME=docker
TRAEFIK_AUTH_BYPASS_KEY=<from GH secret>

IMMICH_VERSION=v2.5.3
PAPERLESS_DBPASS=<from GH secret>
NEXTCLOUD_DBPASS=<from GH secret>
N8N_DBPASS=<from GH secret>
NEXTAUTH_SECRET=<from GH secret>
AZURE_ACCOUNT_KEY=<from GH secret>

# Database — point to LXC 101
POSTGRES_HOST=10.10.0.10
REDIS_HOST=10.10.0.10
```

### 8.3 GitHub Actions Environments

Create one environment per LXC in GitHub:
- **GitHub repo → Settings → Environments**
- Create: `prod-infra`, `prod-media`, `prod-home`, `prod-productivity`, `prod-network`, `prod-monitoring`, `prod-utilities`
- Each environment has its own **environment secrets** (scoped only to that LXC)

**Secrets to add per environment:**

`prod-infra` secrets:
```
SSH_HOST          = <LXC 101 IP>
SSH_KEY           = <private deploy key for LXC 101>
TRAEFIK_AUTH_BYPASS_KEY
PSQL_DBPASS
AUTHENTIK_SECRET
AUTHENTIK_DBPASS
MONGO_ROOT_PASS
CF_DNS_API_TOKEN    ← also write to secrets/cf_dns_api_token file
BASIC_AUTH_CREDS    ← write to secrets/basic_auth_credentials
OAUTH_SECRET        ← write to secrets/oauth_secrets
```

`prod-media` secrets:
```
SSH_HOST          = <LXC 102 IP>
SSH_KEY           = <deploy key for LXC 102>
TRAEFIK_AUTH_BYPASS_KEY
PLEX_CLAIM_TOKEN    ← write to secrets/plex_claim_token
VPN_USER
VPN_PASS
VPN_PROV
SONARR_API_KEY
RADARR_API_KEY
PROWLARR_API_KEY
SABNZBD_API_KEY
PLEX_ADVERTISE_IP
```

### 8.4 Set up SSH deploy keys

Run this once per LXC:

```bash
# On the LXC (or on your workstation)
ssh-keygen -t ed25519 -C "github-deploy-lxc101" -f ~/.ssh/deploy_lxc101 -N ""

# On the LXC — add public key to authorized_keys for the deploy user
cat ~/.ssh/deploy_lxc101.pub >> /root/.ssh/authorized_keys

# In GitHub — add private key as environment secret SSH_KEY in prod-infra environment
cat ~/.ssh/deploy_lxc101
```

### 8.5 Multi-LXC deployment workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to all LXCs

on:
  push:
    branches: [main]
    paths:
      - 'compose/**'
      - 'compose.*.yml'
      - 'scripts/**'
  workflow_dispatch:
    inputs:
      target:
        description: 'Target LXC (all / infra / media / home / productivity / network / monitoring / utilities)'
        default: 'all'
        required: true

jobs:
  deploy-infra:
    if: ${{ github.event.inputs.target == 'all' || github.event.inputs.target == 'infra' || github.event_name == 'push' }}
    runs-on: ubuntu-latest
    environment: prod-infra
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to infra LXC
        uses: appleboy/ssh-action@v1
        env:
          # Non-secret config
          DOCKER_DIR: /root/docker
          CONF_DIR: /root/docker/appdata
          TZ: Europe/Amsterdam
          PUID: "1000"
          PGID: "1000"
          DOMAINNAME_1: example.com
          HOSTNAME: docker
          AUTHENTIK_VERSION: "2025.8.1"
          # Secrets
          TRAEFIK_AUTH_BYPASS_KEY: ${{ secrets.TRAEFIK_AUTH_BYPASS_KEY }}
          PSQL_DBPASS: ${{ secrets.PSQL_DBPASS }}
          AUTHENTIK_SECRET: ${{ secrets.AUTHENTIK_SECRET }}
          AUTHENTIK_DBPASS: ${{ secrets.AUTHENTIK_DBPASS }}
          MONGO_ROOT_PASS: ${{ secrets.MONGO_ROOT_PASS }}
        with:
          host: ${{ secrets.SSH_HOST }}
          username: root
          key: ${{ secrets.SSH_KEY }}
          envs: DOCKER_DIR,CONF_DIR,TZ,PUID,PGID,DOMAINNAME_1,HOSTNAME,AUTHENTIK_VERSION,TRAEFIK_AUTH_BYPASS_KEY,PSQL_DBPASS,AUTHENTIK_SECRET,AUTHENTIK_DBPASS,MONGO_ROOT_PASS
          script: |
            set -e
            cd $DOCKER_DIR

            # Pull latest compose files
            git pull origin main

            # Write .env from injected environment variables
            cat > .env << EOF
            DOCKER_DIR=${DOCKER_DIR}
            CONF_DIR=${CONF_DIR}
            LOG_DIR=${DOCKER_DIR}/logs
            TZ=${TZ}
            PUID=${PUID}
            PGID=${PGID}
            DOMAINNAME_1=${DOMAINNAME_1}
            HOSTNAME=${HOSTNAME}
            AUTHENTIK_VERSION=${AUTHENTIK_VERSION}
            TRAEFIK_AUTH_BYPASS_KEY=${TRAEFIK_AUTH_BYPASS_KEY}
            PSQL_DBUSER=postgres
            PSQL_DBPASS=${PSQL_DBPASS}
            AUTHENTIK_DBNAME=authentik
            AUTHENTIK_DBUSER=authentik
            AUTHENTIK_DBPASS=${AUTHENTIK_DBPASS}
            AUTHENTIK_SECRET=${AUTHENTIK_SECRET}
            MONGO_ROOT_USER=admin
            MONGO_ROOT_PASS=${MONGO_ROOT_PASS}
            EOF

            # Write Docker file-based secrets
            mkdir -p secrets
            echo -n "${{ secrets.CF_DNS_API_TOKEN }}" > secrets/cf_dns_api_token
            echo -n "${{ secrets.BASIC_AUTH_CREDS }}" > secrets/basic_auth_credentials
            echo -n "${{ secrets.OAUTH_SECRET }}" > secrets/oauth_secrets
            chmod 600 secrets/*

            # Deploy
            docker compose pull --quiet
            docker compose up -d --remove-orphans
            docker image prune -f

  deploy-media:
    if: ${{ github.event.inputs.target == 'all' || github.event.inputs.target == 'media' || github.event_name == 'push' }}
    runs-on: ubuntu-latest
    environment: prod-media
    # Run in parallel with other LXCs — each is independent
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to media LXC
        uses: appleboy/ssh-action@v1
        env:
          TRAEFIK_AUTH_BYPASS_KEY: ${{ secrets.TRAEFIK_AUTH_BYPASS_KEY }}
          VPN_USER: ${{ secrets.VPN_USER }}
          VPN_PASS: ${{ secrets.VPN_PASS }}
          VPN_PROV: ${{ secrets.VPN_PROV }}
          SONARR_API_KEY: ${{ secrets.SONARR_API_KEY }}
          RADARR_API_KEY: ${{ secrets.RADARR_API_KEY }}
          PROWLARR_API_KEY: ${{ secrets.PROWLARR_API_KEY }}
          SABNZBD_API_KEY: ${{ secrets.SABNZBD_API_KEY }}
          PLEX_ADVERTISE_IP: ${{ secrets.PLEX_ADVERTISE_IP }}
        with:
          host: ${{ secrets.SSH_HOST }}
          username: root
          key: ${{ secrets.SSH_KEY }}
          envs: TRAEFIK_AUTH_BYPASS_KEY,VPN_USER,VPN_PASS,VPN_PROV,SONARR_API_KEY,RADARR_API_KEY,PROWLARR_API_KEY,SABNZBD_API_KEY,PLEX_ADVERTISE_IP
          script: |
            set -e
            cd /root/docker
            git pull origin main
            cat > .env << EOF
            DOCKER_DIR=/root/docker
            CONF_DIR=/root/docker/appdata
            MEDIA_DIR=/mnt/media
            DOWNLOAD_DIR=/mnt/downloads
            TZ=Europe/Amsterdam
            PUID=1000
            PGID=1000
            DOMAINNAME_1=example.com
            HOSTNAME=docker
            POSTGRES_HOST=10.10.0.10
            REDIS_HOST=10.10.0.10
            TRAEFIK_AUTH_BYPASS_KEY=${TRAEFIK_AUTH_BYPASS_KEY}
            VPN_USER=${VPN_USER}
            VPN_PASS=${VPN_PASS}
            VPN_PROV=${VPN_PROV}
            SONARR_API_KEY=${SONARR_API_KEY}
            RADARR_API_KEY=${RADARR_API_KEY}
            PROWLARR_API_KEY=${PROWLARR_API_KEY}
            SABNZBD_API_KEY=${SABNZBD_API_KEY}
            PLEX_ADVERTISE_IP=${PLEX_ADVERTISE_IP}
            EOF
            mkdir -p secrets
            echo -n "${{ secrets.PLEX_CLAIM_TOKEN }}" > secrets/plex_claim_token
            chmod 600 secrets/*
            docker compose pull --quiet
            docker compose up -d --remove-orphans
            docker image prune -f

  # Add deploy-home, deploy-productivity, deploy-network,
  # deploy-monitoring, deploy-utilities following the same pattern.
  # Each has its own environment and only the secrets it needs.
```

> **Note on order**: `deploy-infra` should complete before other LXCs start if you're doing a fresh setup (databases need to be up first). For rolling updates, jobs run in parallel safely.

---

## 9. Phase 7 — Traefik Cross-LXC Routing

### The problem

Traefik on LXC 101 uses Docker labels to discover services. But services on LXC 102-107 are on different Docker engines — Traefik can't see their labels.

### The solution: file-based routing for cross-LXC services

Traefik already supports a file provider (your `appdata/traefik3/rules/` directory). When a service moves to another LXC, its Traefik routing moves from labels in the compose file to a YAML file in that directory.

```
appdata/traefik3/rules/<HOSTNAME>/
├── middlewares.yml         ← chain-authentik, chain-no-auth (already exists)
├── sonarr.yml              ← routing rule for Sonarr (on LXC 102)
├── radarr.yml
├── plex.yml
├── home-assistant.yml      ← routing rule for HA (on LXC 103)
└── ...
```

Traefik watches this directory and picks up changes without restart.

### File-based routing rule template

For a service on LXC 102 (10.10.0.20), exposed on port 8989:

```yaml
# appdata/traefik3/rules/<HOSTNAME>/sonarr.yml
http:
  routers:
    sonarr-rtr:
      entryPoints:
        - websecure
      rule: "Host(`sonarr.$DOMAINNAME_1`)"
      middlewares:
        - chain-authentik@file
      service: sonarr-svc
      priority: 99

    sonarr-rtr-bypass:
      entryPoints:
        - websecure
      rule: "Host(`sonarr.$DOMAINNAME_1`) && Header(`traefik-auth-bypass-key`, `$TRAEFIK_AUTH_BYPASS_KEY`)"
      middlewares:
        - chain-no-auth@file
      service: sonarr-svc
      priority: 100

  services:
    sonarr-svc:
      loadBalancer:
        servers:
          - url: "http://10.10.0.20:8989"
```

> Traefik file provider supports Go template functions including `env`. Use `{{ env "DOMAINNAME_1" }}` if you want to reference env vars. Or hardcode the value — it's less portable but simpler.

### Port exposure pattern on LXC 102-107

When a service moves to a new LXC, change its compose file from `expose` to `ports` bound to the vmbr1 interface:

```yaml
# Before (single LXC, labels-based routing)
services:
  sonarr:
    expose:
      - 8989
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.sonarr-rtr.rule=Host(`sonarr.$DOMAINNAME_1`)"
      # ... more labels

# After (multi-LXC, file-based routing)
services:
  sonarr:
    ports:
      - "10.10.0.20:8989:8989"   # Bind ONLY to vmbr1 — not exposed on vmbr0
    # No traefik labels needed — routing is in the file provider
```

**Why bind to 10.10.0.20 only?** If you use `"8989:8989"`, the port publishes on all interfaces including vmbr0 (internet-accessible). Binding to the vmbr1 IP means only Traefik and other LXCs on that internal bridge can reach it. This is the correct security posture.

### Checklist when moving a service to a new LXC

- [ ] Service compose file: change `expose` to `ports: ["10.10.0.X:PORT:PORT"]`
- [ ] Service compose file: remove `traefik.*` labels (keep `traefik.enable=false` or remove entirely)
- [ ] Create `appdata/traefik3/rules/<HOSTNAME>/<service>.yml` on LXC 101 with the routing rule pointing to `http://10.10.0.X:PORT`
- [ ] Update service's database connection to point to `10.10.0.10` (not `postgres` container name)
- [ ] Stop old container on source LXC
- [ ] Copy appdata to destination LXC: `rsync -av /root/docker/appdata/<service>/ root@10.10.0.X:/root/docker/appdata/<service>/`
- [ ] Start container on destination LXC
- [ ] Verify routing: `curl -H "Host: sonarr.example.com" https://traefik-ip/`

### Services that stay on LXC 101 (labels still work)

Services that run on LXC 101 itself (Authentik, Adminer, any utilities on infra) continue to use Docker labels as before. Only cross-LXC services need file-based routing.

---

## 10. Phase 8 — Migration Order & Service Move Playbook

### Recommended migration order

1. **LXC 101 (infra)** — Already exists. Separate databases into their own stack but keep in LXC 101. Ensure Traefik and databases are healthy before touching anything else.

2. **LXC 103 (home)** — Migrate Home Assistant stack. HA is the most complex due to hardware (Zigbee USB, GPU for Frigate). Do this before media because HA has no database dependencies on Postgres by default.

3. **LXC 102 (media)** — Migrate *arr stack and Plex. These are stateless-ish (configs in appdata, media on RAID). Easy to migrate and easy to roll back.

4. **LXC 104 (productivity)** — Migrate Immich, Paperless, Nextcloud. These need database connections to LXC 101's Postgres. Do after confirming LXC 101 is stable.

5. **LXC 105 (network)** — Pi-hole and Unifi. Quick. Pi-hole DNS needs careful timing to avoid DNS downtime.

6. **LXC 106 (monitoring)** — Migrate Prometheus/Grafana. Prometheus scrapes services on other LXCs via vmbr1 IPs — update scrape targets after migration.

7. **LXC 107 (utilities)** — Last, least critical.

### Service move playbook (step-by-step)

Follow this for each service:

```bash
# Step 1: On SOURCE LXC — take a snapshot of appdata
SOURCE_SERVICE=sonarr
SOURCE_APPDATA=/root/docker/appdata/$SOURCE_SERVICE
DATE=$(date +%Y%m%d)
tar czf /tmp/${SOURCE_SERVICE}_backup_${DATE}.tar.gz -C $SOURCE_APPDATA .

# Step 2: Copy appdata to DESTINATION LXC
DEST_LXC_IP=10.10.0.20
scp /tmp/${SOURCE_SERVICE}_backup_${DATE}.tar.gz root@$DEST_LXC_IP:/tmp/

# On destination LXC:
mkdir -p /root/docker/appdata/$SOURCE_SERVICE
tar xzf /tmp/${SOURCE_SERVICE}_backup_${DATE}.tar.gz -C /root/docker/appdata/$SOURCE_SERVICE

# Step 3: Create routing rule on LXC 101
# Write the file-based Traefik rule (see template above)

# Step 4: Stop service on source LXC
docker compose stop $SOURCE_SERVICE

# Step 5: Start service on destination LXC
docker compose up -d $SOURCE_SERVICE

# Step 6: Verify
curl -IL https://$SOURCE_SERVICE.yourdomain.com
# Check logs
docker compose logs -f $SOURCE_SERVICE

# Step 7: If OK, remove compose file from source LXC's compose.yml include list
# If NOT OK, start it again on source LXC (rollback)
docker compose start $SOURCE_SERVICE  # on source
```

### Updating Prometheus scrape targets after migration

When services move to new LXC IPs, update Prometheus scrape configs:

```yaml
# appdata/prometheus/prometheus.yml — update scrape targets
scrape_configs:
  - job_name: 'sonarr'
    static_configs:
      - targets: ['10.10.0.20:9707']   # Was: sonarr-exporter:9707

  - job_name: 'radarr'
    static_configs:
      - targets: ['10.10.0.20:9708']

  # Services on home LXC
  - job_name: 'node-home'
    static_configs:
      - targets: ['10.10.0.30:9100']   # node-exporter on home LXC
```

---

## Appendix — Per-LXC compose.yml Templates

After migration, each LXC has its own `compose.yml`. These are stored in the same Git repo under a `lxc/` directory:

```
lxc/
├── infra/compose.yml         → LXC 101
├── media/compose.yml         → LXC 102
├── home/compose.yml          → LXC 103
├── productivity/compose.yml  → LXC 104
├── network/compose.yml       → LXC 105
├── monitoring/compose.yml    → LXC 106
└── utilities/compose.yml     → LXC 107
```

Each LXC clones the repo and symlinks or copies its compose.yml:

```bash
# On LXC 102 (media)
cd /root/docker
ln -sf lxc/media/compose.yml compose.yml
# OR just: docker compose -f lxc/media/compose.yml up -d
```

**`lxc/infra/compose.yml`:**
```yaml
networks:
  t3_proxy:
    name: t3_proxy
    driver: bridge
    ipam:
      config:
        - subnet: 10.2.0.0/16
  default:
    driver: bridge

secrets:
  basic_auth_credentials:
    file: $DOCKER_DIR/secrets/basic_auth_credentials
  cf_dns_api_token:
    file: $DOCKER_DIR/secrets/cf_dns_api_token
  oauth_secrets:
    file: $DOCKER_DIR/secrets/oauth_secrets

include:
  - ../../compose/reverse-proxy/compose.traefik.yml
  - ../../compose/reverse-proxy/compose.authentik.yml
  - ../../compose/database/compose.postgres.yml
  - ../../compose/database/compose.redis.yml
  - ../../compose/database/compose.mongo.yml
  - ../../compose/database/compose.adminer.yml
```

**`lxc/media/compose.yml`:**
```yaml
networks:
  t3_proxy:
    name: t3_proxy
    driver: bridge

secrets:
  plex_claim_token:
    file: $DOCKER_DIR/secrets/plex_claim_token

include:
  - ../../compose/media-server/compose.plex.yml
  - ../../compose/media-server/compose.sonarr.yml
  - ../../compose/media-server/compose.radarr.yml
  - ../../compose/media-server/compose.prowlarr.yml
  - ../../compose/media-server/compose.sabnzbd.yml
  - ../../compose/media-server/compose.qbittorrent.yml
  - ../../compose/media-server/compose.tautulli.yml
  - ../../compose/media-server/compose.bazarr.yml
  # ... etc
```

---

*This guide covers your specific hardware. CPU cooling should be your first action — 96°C is too close to the 100°C Tjunction limit for comfort during a long migration. After that, work through the phases in order.*
