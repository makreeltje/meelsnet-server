#!/bin/bash
# update-docker-hosts.sh

HOSTS_FILE="/etc/hosts"
BACKUP_FILE="/etc/hosts.backup"
MARKER_START="# DOCKER CONTAINERS START"
MARKER_END="# DOCKER CONTAINERS END"

# Backup original hosts file
cp $HOSTS_FILE $BACKUP_FILE

# Remove old Docker entries
sed -i "/$MARKER_START/,/$MARKER_END/d" $HOSTS_FILE

# Add new marker and entries
echo "$MARKER_START" >> $HOSTS_FILE

# Get container IPs and add to hosts
docker ps --format "table {{.Names}}" | tail -n +2 | while read container; do
    if [ "$container" != "homeassistant" ]; then
        IP=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $container 2>/dev/null)
        if [ ! -z "$IP" ]; then
            echo "$IP $container" >> $HOSTS_FILE
        fi
    fi
done

echo "$MARKER_END" >> $HOSTS_FILE

# Restart Home Assistant to pick up changes
docker restart homeassistant
