#!/usr/bin/env bash
# =============================================================================
# GitOps Controller - Setup Script
# =============================================================================
# Run this on Proxmox to install the GitOps controller + webhook listener.
# Usage: bash setup.sh
# =============================================================================

set -euo pipefail

INSTALL_DIR="/opt/gitops"
CONFIG_DIR="/etc/gitops"
LOG_DIR="/var/log/gitops"

echo "=== GitOps Controller Setup ==="
echo ""

# Create directories
echo "[1/8] Creating directories..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR" "$INSTALL_DIR/state"

# Copy scripts
echo "[2/8] Installing scripts..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/gitops-controller.sh" "$INSTALL_DIR/gitops-controller.sh"
cp "$SCRIPT_DIR/gitops-webhook.py" "$INSTALL_DIR/gitops-webhook.py"
chmod +x "$INSTALL_DIR/gitops-controller.sh"

# Copy config if not exists
if [[ ! -f "$CONFIG_DIR/config.env" ]]; then
  echo "[3/8] Creating config from example..."
  cp "$SCRIPT_DIR/config.env.example" "$CONFIG_DIR/config.env"
  echo "  -> Edit /etc/gitops/config.env with your settings"
else
  echo "[3/8] Config already exists, skipping..."
fi

# Generate webhook secret if not set
if ! grep -q "^WEBHOOK_SECRET=.\+" "$CONFIG_DIR/config.env" 2>/dev/null; then
  echo "[4/8] Generating webhook secret..."
  SECRET=$(openssl rand -hex 32)
  sed -i "s/^WEBHOOK_SECRET=$/WEBHOOK_SECRET=$SECRET/" "$CONFIG_DIR/config.env"
  echo "  -> Webhook secret generated: $SECRET"
  echo "  -> Add this same secret to your GitHub webhook configuration"
else
  echo "[4/8] Webhook secret already set, skipping..."
fi

# Install systemd units
echo "[5/8] Installing systemd units..."
cp "$SCRIPT_DIR/gitops-webhook.service" /etc/systemd/system/
cp "$SCRIPT_DIR/gitops-sync.service"   /etc/systemd/system/
cp "$SCRIPT_DIR/gitops-sync.timer"     /etc/systemd/system/
systemctl daemon-reload

# Enable webhook service
echo "[6/8] Enabling webhook service..."
systemctl enable gitops-webhook.service

# Enable and start the periodic sync timer
echo "[7/8] Enabling periodic sync timer..."
systemctl enable --now gitops-sync.timer

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo ""
echo "  1. Create a read-only GitHub deploy key:"
echo "     ssh-keygen -t ed25519 -f /root/.ssh/github_deploy_key -N '' -C 'gitops-proxmox'"
echo ""
echo "  2. Add the public key to GitHub:"
echo "     cat /root/.ssh/github_deploy_key.pub"
echo "     -> GitHub repo > Settings > Deploy keys > Add (read-only)"
echo ""
echo "  3. Configure SSH to use the deploy key:"
echo "     cat >> /root/.ssh/config << EOF"
echo "     Host github.com"
echo "       IdentityFile /root/.ssh/github_deploy_key"
echo "       IdentitiesOnly yes"
echo "     EOF"
echo ""
echo "  4. Edit config if needed:"
echo "     nano /etc/gitops/config.env"
echo ""
echo "  5. Configure the GitHub webhook:"
echo "     -> GitHub repo > Settings > Webhooks > Add webhook"
echo "     -> Payload URL: https://<proxmox-ip-or-domain>:9000/webhook"
echo "     -> Content type: application/json"
echo "     -> Secret: (copy from /etc/gitops/config.env)"
echo "     -> Events: Just the push event"
echo ""
echo "  6. Start the services:"
echo "     systemctl start gitops-webhook.service"
echo "     systemctl start gitops-sync.timer   # periodic sync already enabled"
echo ""
echo "  7. Test with a manual sync:"
echo "     /opt/gitops/gitops-controller.sh sync"
echo ""
echo "  8. Check status:"
echo "     /opt/gitops/gitops-controller.sh status"
echo "     systemctl list-timers gitops-sync.timer"
echo "     journalctl -u gitops-sync.service -f"
echo "     journalctl -u gitops-webhook.service -f"
