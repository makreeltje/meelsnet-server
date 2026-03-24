#!/usr/bin/env bash
# =============================================================================
# GitOps Controller - Setup Script
# =============================================================================
# Run this on Proxmox to install the GitOps controller.
# Usage: bash setup.sh
# =============================================================================

set -euo pipefail

INSTALL_DIR="/opt/gitops"
CONFIG_DIR="/etc/gitops"
LOG_DIR="/var/log/gitops"

echo "=== GitOps Controller Setup ==="
echo ""

# Create directories
echo "[1/5] Creating directories..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR" "$INSTALL_DIR/state"

# Copy controller script
echo "[2/5] Installing controller script..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/gitops-controller.sh" "$INSTALL_DIR/gitops-controller.sh"
chmod +x "$INSTALL_DIR/gitops-controller.sh"

# Copy config if not exists
if [[ ! -f "$CONFIG_DIR/config.env" ]]; then
  echo "[3/5] Creating config from example..."
  cp "$SCRIPT_DIR/config.env.example" "$CONFIG_DIR/config.env"
  echo "  -> Edit /etc/gitops/config.env with your settings"
else
  echo "[3/5] Config already exists, skipping..."
fi

# Install systemd units
echo "[4/5] Installing systemd units..."
cp "$SCRIPT_DIR/gitops-controller.service" /etc/systemd/system/
cp "$SCRIPT_DIR/gitops-controller.timer" /etc/systemd/system/
systemctl daemon-reload

# Enable timer
echo "[5/5] Enabling timer..."
systemctl enable gitops-controller.timer

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Create a read-only GitHub deploy key:"
echo "     ssh-keygen -t ed25519 -f /root/.ssh/github_deploy_key -N '' -C 'gitops-proxmox'"
echo ""
echo "  2. Add the public key to GitHub:"
echo "     cat /root/.ssh/github_deploy_key.pub"
echo "     -> GitHub repo → Settings → Deploy keys → Add (read-only)"
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
echo "  5. Test with a manual sync:"
echo "     /opt/gitops/gitops-controller.sh sync"
echo ""
echo "  6. Start the timer:"
echo "     systemctl start gitops-controller.timer"
echo ""
echo "  7. Check status:"
echo "     /opt/gitops/gitops-controller.sh status"
echo "     journalctl -u gitops-controller.service -f"
