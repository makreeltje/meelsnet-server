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
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

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
# Per-connection socket timeout (seconds): a client that connects and then
# stalls mid-request is dropped instead of occupying a handler thread forever.
REQUEST_TIMEOUT = int(os.environ.get("WEBHOOK_REQUEST_TIMEOUT", "15"))

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
# Deploy coordination (coalescing concurrent webhook events)
# ---------------------------------------------------------------------------
deploy_lock = threading.Lock()
resync_pending = threading.Event()


def verify_signature(payload: bytes, signature_header: str) -> bool:
    """Verify GitHub HMAC-SHA256 webhook signature."""
    if not WEBHOOK_SECRET:
        # Fail closed: no secret configured means no request can be trusted.
        # main() refuses to start the server without a secret, so this path
        # should be unreachable in practice — but never treat a missing
        # secret as "verification not required".
        log.error("No WEBHOOK_SECRET configured — rejecting request")
        return False

    if not signature_header:
        return False

    # GitHub sends: sha256=<hex digest>
    if not signature_header.startswith("sha256="):
        return False

    expected = signature_header[7:]
    mac = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), expected)


def respond_ok(handler):
    """Answer a handled delivery with 204 No Content.

    Traefik only access-logs 204-299 and 3xx-5xx (see compose.traefik.yml),
    so 200/202 answers never showed up in its log. 204 makes every handled
    webhook delivery visible on router gitops-rtr without widening the
    global status filter. GitHub accepts any 2xx.
    """
    handler.send_response(204)
    handler.end_headers()


def get_changed_files(payload: dict) -> list[str]:
    """Extract list of changed files from a GitHub push event payload."""
    changed = set()
    for commit in payload.get("commits", []):
        changed.update(commit.get("added", []))
        changed.update(commit.get("modified", []))
        changed.update(commit.get("removed", []))
    return sorted(changed)


def trigger_deploy():
    """Run the GitOps controller sync in the background.

    If a sync is already running, the event is coalesced: a flag is set so
    that the running sync loop re-syncs once more after finishing, picking up
    whatever new commits arrived in the meantime.
    """
    if not deploy_lock.acquire(blocking=False):
        resync_pending.set()
        log.info("Deployment already in progress — queued re-sync after current run")
        return

    def run():
        try:
            while True:
                resync_pending.clear()
                log.info("Triggering gitops-controller sync...")
                result = subprocess.run(
                    [CONTROLLER_PATH, "sync"],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if result.returncode == 0:
                    log.info("Deployment completed successfully")
                    if result.stderr:
                        log.warning("Deployment warnings:\n%s", result.stderr.strip())
                else:
                    log.error("Deployment failed (exit %d): %s", result.returncode, result.stderr)
                if result.stdout:
                    log.info("Controller output:\n%s", result.stdout)

                if resync_pending.is_set():
                    log.info("Re-sync pending — running another cycle")
                else:
                    break
        except subprocess.TimeoutExpired:
            log.error("Deployment timed out after 600s")
        except Exception as e:
            log.error("Deployment error: %s", e)
        finally:
            resync_pending.clear()
            deploy_lock.release()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


class WebhookHandler(BaseHTTPRequestHandler):
    # StreamRequestHandler applies this to the connection socket, so slow
    # reads (headers or body) raise instead of blocking indefinitely.
    timeout = REQUEST_TIMEOUT

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

        # Delivery identifiers for correlating with GitHub's "Recent deliveries"
        # (not secrets; the signature header is deliberately never logged).
        delivery = self.headers.get("X-GitHub-Delivery", "-")
        user_agent = self.headers.get("User-Agent", "-")

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
        log.info(
            "Delivery %s event=%s ua=%s from %s",
            delivery, event or "-", user_agent, self.client_address[0],
        )
        if event == "ping":
            log.info("Received ping event — webhook configured correctly")
            respond_ok(self)
            return

        if event != "push":
            log.info("Ignoring event type: %s", event)
            respond_ok(self)
            return

        # Check branch
        ref = data.get("ref", "")
        expected_ref = f"refs/heads/{BRANCH}"
        if ref != expected_ref:
            log.info("Ignoring push to %s (watching %s)", ref, expected_ref)
            respond_ok(self)
            return

        # Log what changed
        changed_files = get_changed_files(data)
        commit_sha = data.get("after", "unknown")
        log.info(
            "Push to %s — commit %s — %d file(s) changed: %s",
            BRANCH, commit_sha[:8], len(changed_files), ", ".join(changed_files[:10]),
        )

        # Trigger deployment (async — answer immediately)
        trigger_deploy()

        respond_ok(self)

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
        log.error(
            "WEBHOOK_SECRET is not set. Refusing to start with signature "
            "verification disabled — set WEBHOOK_SECRET in /etc/gitops/config.env "
            "(or the environment) before running this service."
        )
        sys.exit(1)

    # One thread per connection, so a slow or hung client cannot block other
    # deliveries. Deploys stay serialised (deploy_lock here, flock in the
    # controller).
    server = ThreadingHTTPServer(("0.0.0.0", WEBHOOK_PORT), WebhookHandler)
    server.daemon_threads = True
    log.info("GitOps webhook listener started on port %d", WEBHOOK_PORT)
    log.info("Endpoints: POST /webhook, GET /health")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
