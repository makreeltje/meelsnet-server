#!/usr/bin/env python3
"""
GitOps Webhook Receiver for Meelsnet Server

Lightweight HTTP server that receives GitHub webhook push events,
verifies the HMAC-SHA256 signature, and triggers the GitOps controller
to deploy affected LXC containers.

Runs on Proxmox as a systemd service. No external dependencies required.
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ---------------------------------------------------------------------------
# Configuration (override via /etc/gitops/config.env or environment)
# ---------------------------------------------------------------------------
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
BRANCH = os.environ.get("BRANCH", "main")
CONTROLLER_PATH = os.environ.get(
    "CONTROLLER_PATH", "/opt/gitops/gitops-controller.sh"
)
LOG_DIR = os.environ.get("LOG_DIR", "/var/log/gitops")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "webhook.log")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("gitops-webhook")

# ---------------------------------------------------------------------------
# Deploy lock (prevent concurrent deployments)
# ---------------------------------------------------------------------------
deploy_lock = threading.Lock()


def verify_signature(payload: bytes, signature_header: str) -> bool:
    """Verify GitHub HMAC-SHA256 webhook signature."""
    if not WEBHOOK_SECRET:
        log.warning("No WEBHOOK_SECRET configured — skipping signature verification")
        return True

    if not signature_header:
        return False

    # GitHub sends: sha256=<hex digest>
    if not signature_header.startswith("sha256="):
        return False

    expected = signature_header[7:]
    mac = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), expected)


def get_changed_files(payload: dict) -> list[str]:
    """Extract list of changed files from a GitHub push event payload."""
    changed = set()
    for commit in payload.get("commits", []):
        changed.update(commit.get("added", []))
        changed.update(commit.get("modified", []))
        changed.update(commit.get("removed", []))
    return sorted(changed)


def trigger_deploy():
    """Run the GitOps controller sync in the background."""
    if not deploy_lock.acquire(blocking=False):
        log.info("Deployment already in progress — skipping")
        return

    def run():
        try:
            log.info("Triggering gitops-controller sync...")
            result = subprocess.run(
                [CONTROLLER_PATH, "sync"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode == 0:
                log.info("Deployment completed successfully")
            else:
                log.error("Deployment failed (exit %d): %s", result.returncode, result.stderr)
            if result.stdout:
                log.info("Controller output:\n%s", result.stdout)
        except subprocess.TimeoutExpired:
            log.error("Deployment timed out after 600s")
        except Exception as e:
            log.error("Deployment error: %s", e)
        finally:
            deploy_lock.release()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/webhook":
            self.send_error(404)
            return

        # Read payload
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0 or content_length > 10 * 1024 * 1024:
            self.send_error(400, "Invalid content length")
            return

        payload = self.rfile.read(content_length)

        # Verify HMAC signature
        signature = self.headers.get("X-Hub-Signature-256", "")
        if not verify_signature(payload, signature):
            log.warning("Invalid webhook signature from %s", self.client_address[0])
            self.send_error(403, "Invalid signature")
            return

        # Parse payload
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Check event type
        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            log.info("Received ping event — webhook configured correctly")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "pong"}).encode())
            return

        if event != "push":
            log.info("Ignoring event type: %s", event)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ignored"}).encode())
            return

        # Check branch
        ref = data.get("ref", "")
        expected_ref = f"refs/heads/{BRANCH}"
        if ref != expected_ref:
            log.info("Ignoring push to %s (watching %s)", ref, expected_ref)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ignored", "reason": "wrong branch"}).encode())
            return

        # Log what changed
        changed_files = get_changed_files(data)
        commit_sha = data.get("after", "unknown")
        log.info(
            "Push to %s — commit %s — %d file(s) changed: %s",
            BRANCH, commit_sha[:8], len(changed_files), ", ".join(changed_files[:10]),
        )

        # Trigger deployment (async — return 202 immediately)
        trigger_deploy()

        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "accepted",
            "commit": commit_sha,
            "changed_files": len(changed_files),
        }).encode())

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return
        self.send_error(404)

    def log_message(self, format, *args):
        # Suppress default access logs (we have our own logging)
        pass


def main():
    if not WEBHOOK_SECRET:
        log.warning(
            "WEBHOOK_SECRET is not set! Webhook signature verification is DISABLED. "
            "Set WEBHOOK_SECRET in /etc/gitops/config.env for production use."
        )

    server = HTTPServer(("0.0.0.0", WEBHOOK_PORT), WebhookHandler)
    log.info("GitOps webhook listener started on port %d", WEBHOOK_PORT)
    log.info("Endpoints: POST /webhook, GET /health")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
