Proxmox Migration Guide - Zero Data Loss
Current System Overview
System Configuration:

Hostname: meelsnet
Main Drive: 1.8TB NVMe SSD with Ubuntu LVM (1.3TB used, 506GB free)
Storage Array: 72.8TB RAID5 array (/mnt/storage) with 44TB used, 26TB free
RAID Configuration: md5 using drives sda, sdb, sdc, sdd, sde (5 drives, RAID5)
Application Data: ~1.1TB in /opt/appdata
Largest Applications:

Frigate: 810GB (NVR/Camera system)
Plex: 184GB (Media server)
Minecraft: 30GB (Game server)
Immich: 29GB (Photo management)
Prometheus: 9.5GB (Monitoring)
Migration Strategy: Non-Destructive Approach
Phase 1: Pre-Migration Backup (CRITICAL)
Run the automated backup script:

# Execute the backup script
sudo /mnt/storage/backup_script.sh

# Monitor progress (backup will take several hours for 1.1TB data)
tail -f /mnt/storage/backup/migration/appdata_backup.log
Manual verification steps:

# Verify RAID array is healthy
cat /proc/mdstat
mdadm --detail /dev/md5

# Check available space for backup
df -h /mnt/storage

# Verify Docker services are running
docker ps
cd /opt && docker-compose ps
Phase 2: Proxmox Installation
Pre-Installation:

Download Proxmox VE 8.2 ISO from https://www.proxmox.com/en/downloads
Create bootable USB using Rufus/Balena Etcher
Ensure system is powered via UPS (protect against power loss during install)
Installation Process:

Boot from Proxmox USB installer
Target Installation Drive: Select only the NVMe drive (/dev/nvme0n1)
DO NOT SELECT RAID DRIVES (sda, sdb, sdc, sdd, sde)
Filesystem: Choose ZFS (recommended) or ext4
Network Configuration:
IP: Set static IP (currently using 192.168.2.x network)
Gateway: Your router IP
DNS: 1.1.1.1, 8.8.8.8
Complete installation and reboot
Phase 3: Post-Installation Recovery
1. Access Proxmox Web Interface

https://YOUR-PROXMOX-IP:8006
Login with root credentials set during installation
2. Restore RAID Array

# SSH into Proxmox host
ssh root@YOUR-PROXMOX-IP

# Check if RAID drives are detected
lsblk
fdisk -l

# Assemble RAID array
mdadm --assemble --scan

# Create mount point and mount
mkdir -p /mnt/storage
mount /dev/md5 /mnt/storage

# Add to fstab for persistent mount
echo "/dev/md5 /mnt/storage ext4 defaults 0 2" >> /etc/fstab

# Verify data integrity
ls -la /mnt/storage/
ls -la /mnt/storage/backup/migration/
3. Install required packages

# Update Proxmox
apt update && apt upgrade -y

# Install necessary tools
apt install -y rsync curl wget git htop iotop
Container Strategy Options
Option A: Single LXC Container (Simplest Migration)
Create Ubuntu LXC Container:

Download Ubuntu 22.04 template via Proxmox web interface
Create container with these specs:
RAM: 16GB (adjust based on your total RAM)
CPU: 8 cores
Storage: 200GB (for OS + application configs)
Privileged: Yes (required for Docker)
Container Configuration:

# In Proxmox shell, edit container config
nano /etc/pve/lxc/[CONTAINER_ID].conf

# Add bind mount for storage
mp0: /mnt/storage,mp=/mnt/storage,backup=0

# Add Docker-related settings
lxc.apparmor.profile: unconfined
lxc.cap.add: sys_admin
lxc.cgroup2.devices.allow: a
lxc.mount.auto: "proc:rw sys:rw"
Inside LXC Container:

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Create directory structure
mkdir -p /opt/{appdata,compose,secrets}

# Restore configurations
rsync -av /mnt/storage/backup/migration/configs/compose/ /opt/compose/
rsync -av /mnt/storage/backup/migration/configs/secrets/ /opt/secrets/
cp /mnt/storage/backup/migration/configs/.env /opt/

# Restore application data
rsync -av --progress /mnt/storage/backup/migration/appdata/ /opt/appdata/

# Start services
cd /opt
docker-compose pull
docker-compose up -d
Option B: Multiple LXC Containers (Advanced)
Container 1: Media Stack

Services: Plex, Sonarr, Radarr, Prowlarr, SABnzbd, Transmission
RAM: 8GB, CPU: 4 cores, Storage: 100GB
Bind mount: /mnt/storage/media, /mnt/storage/downloads
Container 2: Monitoring Stack

Services: Prometheus, Grafana, Loki, Exporters
RAM: 4GB, CPU: 2 cores, Storage: 50GB
Container 3: Home Automation

Services: Home Assistant, Zigbee2MQTT, Mosquitto
RAM: 2GB, CPU: 2 cores, Storage: 30GB
USB device passthrough for Zigbee stick
Container 4: Frigate NVR

Service: Frigate (camera system)
RAM: 8GB, CPU: 4 cores, Storage: 50GB
GPU passthrough if available
Bind mount: /mnt/storage/nvr
Container 5: Databases

Services: PostgreSQL, MongoDB
RAM: 4GB, CPU: 2 cores, Storage: 100GB
Network Configuration
Proxmox Host Network:

# Configure bridge for containers
auto vmbr0
iface vmbr0 inet static
    address 192.168.2.X/24
    gateway 192.168.2.1
    bridge-ports enp1s0
    bridge-stp off
    bridge-fd 0
Traefik Reverse Proxy:

Run in main container or dedicated container
Configure for meelsnet.nl domain
Import existing Traefik configuration from backup
Data Verification Checklist
After migration, verify these critical services:

Media Services:

[ ] Plex library intact and accessible
[ ] Sonarr/Radarr can see existing TV/Movies
[ ] Download clients can access download directories
Monitoring:

[ ] Prometheus data retained
[ ] Grafana dashboards working
[ ] Historical monitoring data accessible
Home Automation:

[ ] Home Assistant configuration intact
[ ] Zigbee devices reconnected
[ ] Automations functioning
Security & Access:

[ ] Traefik routing working
[ ] Authentik SSO functional
[ ] SSL certificates renewed
Databases:

[ ] PostgreSQL databases intact
[ ] MongoDB collections accessible
[ ] Application connections working
Rollback Plan
If migration fails, you can rollback:

Option 1: Restore Ubuntu

Boot from Ubuntu Live USB
Restore Ubuntu to NVMe drive
RAID array data remains untouched
Restore /opt/appdata from backup
Option 2: VM Migration

Create Ubuntu VM in Proxmox
Restore all services in VM
Continue with VM until LXC issues resolved
Performance Optimization
Post-Migration Tuning:

Enable hardware transcoding for Plex (if available)
Configure storage snapshots for important containers
Set up automated backups using Proxmox Backup Server
Monitor resource usage and adjust container allocations
Enable clustering if you plan to add more nodes
Security Considerations
Proxmox Security:

Change default SSH port (port 22)
Set up firewall rules for container access
Configure fail2ban for SSH protection
Regular security updates for host and containers
Backup encryption for sensitive data
Maintenance Schedule
Weekly:

Check container resource usage
Review logs for errors
Update container images
Monthly:

Proxmox host updates
RAID array health check
Backup verification
Quarterly:

Security audit
Performance optimization review
Capacity planning
Backup Strategy (Post-Migration)
Automated Backups:

# Create backup script for LXC containers
vzdump --mode snapshot --compress gzip --storage local --all

# Schedule in crontab
0 2 * * * /usr/bin/vzdump --mode snapshot --compress gzip --storage /mnt/storage/backups --all
Critical Data Backup:

Container snapshots to RAID array
Configuration files to cloud storage
Database dumps with retention policy
Support and Documentation
Useful Commands:

# Container management
pct list                          # List containers
pct start/stop/restart [VMID]    # Control containers
pct enter [VMID]                 # Enter container shell

# Storage management
pvesm status                     # Storage status
zfs list                         # ZFS pools (if using ZFS)

# Monitoring
pveversion                       # Proxmox version
pvecm status                     # Cluster status
Log Locations:

Proxmox logs: /var/log/pve/
Container logs: /var/log/lxc/
RAID logs: /var/log/mdadm/
Contact Information
Created: $(date)
System: meelsnet.nl
Migration Type: Ubuntu Docker → Proxmox LXC
Risk Level: LOW (RAID array preservation strategy)

⚠️ IMPORTANT REMINDERS:

NEVER SKIP THE BACKUP PHASE
Test RAID array accessibility before proceeding
Keep Ubuntu installation media as emergency recovery
Document any configuration changes during migration
Verify all services before decommissioning backups
🚨 EMERGENCY CONTACTS:

RAID Recovery: Professional data recovery service contact
Network Access: Router admin credentials location
Power: UPS runtime and generator procedures
