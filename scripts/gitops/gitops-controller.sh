#!/usr/bin/env bash
# =============================================================================
# GitOps Controller for Meelsnet Server
# =============================================================================
# Deploys affected LXC containers via Proxmox pct when changes are detected.
# Triggered by webhook (gitops-webhook.py) or manually via CLI.
#
# This replaces the push-based GitHub Actions workflow, removing the need for
# GitHub to have any access to the server (Tailscale, SSH keys, secrets).
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration (override via /etc/gitops/config.env)
# -----------------------------------------------------------------------------
REPO_URL="${REPO_URL:-git@github.com:makreeltje/meelsnet-server.git}"
REPO_DIR="${REPO_DIR:-/opt/gitops/meelsnet-server}"
BRANCH="${BRANCH:-main}"
STATE_DIR="${STATE_DIR:-/opt/gitops/state}"
LOG_DIR="${LOG_DIR:-/var/log/gitops}"
DOCKER_BASE="${DOCKER_BASE:-/root/docker}"

# Host-managed paths: repo content deployed directly onto the Proxmox host
# itself (not into any LXC) — the controller/webhook install and the backup
# scripts. See sync_host_managed_paths() below.
GITOPS_INSTALL_DIR="${GITOPS_INSTALL_DIR:-/opt/gitops}"
BACKUP_SCRIPTS_DIR="${BACKUP_SCRIPTS_DIR:-/root/scripts/backup}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

# Traefik file-provider rules — synced into the infra LXC (not the host).
# Traefik watches this directory and hot-reloads on change, so no restart needed.
TRAEFIK_LXC_ID="${TRAEFIK_LXC_ID:-101}"
TRAEFIK_RULES_DEST="${TRAEFIK_RULES_DEST:-/root/docker/appdata/traefik3/rules/meelsnet}"

# Load config override if present
CONFIG_FILE="/etc/gitops/config.env"
# shellcheck source=/dev/null
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

# -----------------------------------------------------------------------------
# LXC Mapping
# -----------------------------------------------------------------------------
# Each entry: LXC_ID|NAME
# Compose directories are derived dynamically from lxc/<name>/compose.yml includes,
# so adding a service to a LXC only requires editing that compose.yml — no changes here.
LXC_ENTRIES=(
  "101|infra"
  "102|media"
  "103|home"
  "104|productivity"
  "105|network"
  "106|monitoring"
  "107|juice-shop"
)

# Paths that affect ALL LXCs when changed
SHARED_PATHS=("compose/fragments")

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/gitops.log"

log() {
  local level="$1"; shift
  echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $*" | tee -a "$LOG_FILE"
}

log_info()  { log "INFO"  "$@"; }
log_warn()  { log "WARN"  "$@"; }
log_error() { log "ERROR" "$@"; }

# -----------------------------------------------------------------------------
# Notifications
# -----------------------------------------------------------------------------
# Sends a Discord embed. Call with: notify "success"|"failure" "title" "body"
# Requires DISCORD_WEBHOOK_URL in /etc/gitops/config.env.
# To switch to failure-only: add [[ "$1" == "failure" ]] || return 0 at top.
notify() {
  local status="$1" title="$2" body="$3"
  [[ -z "${DISCORD_WEBHOOK_URL:-}" ]] && return 0

  local color
  case "$status" in
    success) color=3066993  ;;  # green
    failure) color=15158332 ;;  # red
    *)       color=9807270  ;;  # grey
  esac

  local payload
  payload=$(printf '{"embeds":[{"title":"%s","description":"%s","color":%d}]}' \
    "$title" "$body" "$color")

  if ! curl -sf -X POST "$DISCORD_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      -d "$payload" > /dev/null 2>&1; then
    log_warn "Discord notification failed (webhook unreachable?)"
  fi
}

# -----------------------------------------------------------------------------
# State management
# -----------------------------------------------------------------------------
mkdir -p "$STATE_DIR"

get_last_deployed_sha() {
  local state_file="$STATE_DIR/last-deployed-sha"
  [[ -f "$state_file" ]] && cat "$state_file" || echo ""
}

set_last_deployed_sha() {
  echo "$1" > "$STATE_DIR/last-deployed-sha"
}

# Per-LXC deploy status (for dashboarding/debugging)
record_lxc_deploy() {
  local lxc_id="$1" status="$2" sha="$3"
  local timestamp
  timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo "$timestamp|$sha|$status" > "$STATE_DIR/lxc-${lxc_id}-last-deploy"
}

# Host-managed path sync status (for dashboarding/debugging), mirrors
# record_lxc_deploy but keyed by name instead of LXC ID.
record_host_sync() {
  local name="$1" status="$2" sha="$3"
  local timestamp
  timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo "$timestamp|$sha|$status" > "$STATE_DIR/host-${name}-last-sync"
}

# -----------------------------------------------------------------------------
# Git operations
# -----------------------------------------------------------------------------
ensure_repo() {
  if [[ ! -d "$REPO_DIR/.git" ]]; then
    log_info "Cloning repository..."
    git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$REPO_DIR"
  fi
}

fetch_latest() {
  cd "$REPO_DIR"
  git fetch origin "$BRANCH" --quiet
}

get_remote_sha() {
  cd "$REPO_DIR"
  git rev-parse "origin/$BRANCH"
}

get_local_sha() {
  cd "$REPO_DIR"
  git rev-parse HEAD
}

get_changed_files() {
  local from_sha="$1" to_sha="$2"
  cd "$REPO_DIR"
  git diff --name-only "$from_sha".."$to_sha"
}

pull_latest() {
  cd "$REPO_DIR"
  git reset --hard "origin/$BRANCH" --quiet 2>/dev/null || git reset --hard "origin/$BRANCH"
}

# -----------------------------------------------------------------------------
# Host-managed path deployment
# -----------------------------------------------------------------------------
# scripts/backup/** and scripts/gitops/** don't belong to any LXC — they run
# directly on the Proxmox host. $REPO_DIR is already a fresh git checkout by
# the time these run, so this is a local copy, not a pct push.

file_in_list() {
  local needle="$1"; shift
  local f
  for f in "$@"; do
    [[ "$f" == "$needle" ]] && return 0
  done
  return 1
}

# Copies $1 (repo-relative source) to $2 (absolute destination) via
# write-temp-then-rename in the destination directory, so a script that is
# currently executing (e.g. this controller updating itself) never reads a
# half-written file mid-run — mv within the same filesystem is an atomic
# rename, and a running process keeps its open handle to the old inode.
install_file() {
  local src="$REPO_DIR/$1" dest="$2" mode="${3:-644}"
  local tmp
  tmp=$(mktemp "$(dirname "$dest")/.$(basename "$dest").XXXXXX")
  cp "$src" "$tmp"
  chmod "$mode" "$tmp"
  mv "$tmp" "$dest"
}

sync_backup_scripts() {
  local sha="$1"
  log_info "Host sync: scripts/backup/** changed — syncing to $BACKUP_SCRIPTS_DIR"
  mkdir -p "$BACKUP_SCRIPTS_DIR"

  local f base
  for f in "$REPO_DIR"/scripts/backup/*; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    install_file "scripts/backup/$base" "$BACKUP_SCRIPTS_DIR/$base" 755
    log_info "Host sync:   $base -> $BACKUP_SCRIPTS_DIR/$base"
  done

  # Prune scripts removed from the repo (e.g. mongo.sh after MongoDB was
  # decommissioned) so a stale script can't keep running via cron.
  for f in "$BACKUP_SCRIPTS_DIR"/*; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    if [[ ! -f "$REPO_DIR/scripts/backup/$base" ]]; then
      rm -f "$f"
      log_info "Host sync:   removed $BACKUP_SCRIPTS_DIR/$base (no longer in repo)"
    fi
  done

  log_info "Host sync: backup scripts up to date at $BACKUP_SCRIPTS_DIR"
  record_host_sync "backup-scripts" "OK" "$sha"
}

# Updates the controller/webhook install itself. Restarts gitops-webhook.service
# when webhook.py or the unit file changed — it's a long-running systemd
# service, so a file copy alone doesn't change its running behavior. The
# controller script itself needs no restart: it's invoked fresh every run.
sync_gitops_install() {
  local sha="$1"; shift
  local -a changed_files=("$@")
  local restart_webhook=0

  mkdir -p "$GITOPS_INSTALL_DIR"

  install_file "scripts/gitops/gitops-controller.sh" "$GITOPS_INSTALL_DIR/gitops-controller.sh" 755
  log_info "Host sync: updated $GITOPS_INSTALL_DIR/gitops-controller.sh (self-update — this run keeps executing the version already loaded in memory; the next invocation picks up the change)"

  if file_in_list "scripts/gitops/gitops-webhook.py" "${changed_files[@]}"; then
    install_file "scripts/gitops/gitops-webhook.py" "$GITOPS_INSTALL_DIR/gitops-webhook.py" 644
    log_info "Host sync: updated $GITOPS_INSTALL_DIR/gitops-webhook.py"
    restart_webhook=1
  fi

  if file_in_list "scripts/gitops/gitops-webhook.service" "${changed_files[@]}"; then
    install_file "scripts/gitops/gitops-webhook.service" "$SYSTEMD_DIR/gitops-webhook.service" 644
    log_info "Host sync: updated $SYSTEMD_DIR/gitops-webhook.service"
    restart_webhook=1
  fi

  local reload_systemd=0
  if file_in_list "scripts/gitops/gitops-sync.service" "${changed_files[@]}"; then
    install_file "scripts/gitops/gitops-sync.service" "$SYSTEMD_DIR/gitops-sync.service" 644
    log_info "Host sync: updated $SYSTEMD_DIR/gitops-sync.service"
    reload_systemd=1
  fi

  if file_in_list "scripts/gitops/gitops-sync.timer" "${changed_files[@]}"; then
    install_file "scripts/gitops/gitops-sync.timer" "$SYSTEMD_DIR/gitops-sync.timer" 644
    log_info "Host sync: updated $SYSTEMD_DIR/gitops-sync.timer"
    reload_systemd=1
  fi

  if [[ $reload_systemd -eq 1 || $restart_webhook -eq 1 ]]; then
    systemctl daemon-reload
    log_info "Host sync: ran systemctl daemon-reload"
  fi

  if [[ $reload_systemd -eq 1 ]]; then
    systemctl restart gitops-sync.timer 2>/dev/null || systemctl start gitops-sync.timer
    log_info "Host sync: restarted gitops-sync.timer to apply changes"
  fi

  if [[ $restart_webhook -eq 1 ]]; then
    if systemctl restart gitops-webhook.service; then
      log_info "Host sync: restarted gitops-webhook.service to apply changes"
    else
      log_error "Host sync: failed to restart gitops-webhook.service — check 'systemctl status gitops-webhook.service' manually"
      record_host_sync "gitops-install" "FAILED" "$sha"
      return 1
    fi
  fi

  log_info "Host sync: gitops controller install up to date at $GITOPS_INSTALL_DIR"
  record_host_sync "gitops-install" "OK" "$sha"
}

# Syncs traefik/ from the repo into the infra LXC at $TRAEFIK_RULES_DEST.
# Uses an atomic temp-dir swap so Traefik never reads a partial state mid-reload.
# Handles deletions cleanly (old directory is replaced wholesale).
sync_traefik_rules() {
  local sha="$1"
  log_info "Traefik rules changed — syncing to LXC $TRAEFIK_LXC_ID ($TRAEFIK_RULES_DEST)..."

  cd "$REPO_DIR"

  # Guard: these files are required for Traefik to function. Abort rather than
  # sync an incomplete directory and cause an outage via the atomic swap.
  local required_files=("traefik/tls-opts.yml")
  local missing=0
  for f in "${required_files[@]}"; do
    if [[ ! -f "$f" ]]; then
      log_error "Traefik rules: required file missing from repo: $f — aborting sync to avoid outage"
      missing=1
    fi
  done
  if [[ $missing -eq 1 ]]; then
    record_host_sync "traefik-rules" "FAILED" "$sha"
    return 1
  fi

  local tar_file="/tmp/traefik-rules.tar.gz"

  if ! tar -czf "$tar_file" -C traefik .; then
    log_error "Traefik rules: failed to create archive"
    record_host_sync "traefik-rules" "FAILED" "$sha"
    rm -f "$tar_file"
    return 1
  fi

  if ! pct push "$TRAEFIK_LXC_ID" "$tar_file" /tmp/traefik-rules.tar.gz; then
    log_error "Traefik rules: failed to transfer archive to LXC $TRAEFIK_LXC_ID"
    rm -f "$tar_file"
    record_host_sync "traefik-rules" "FAILED" "$sha"
    return 1
  fi

  rm -f "$tar_file"

  # Extract directly into the existing directory to preserve its inode.
  # Traefik's file watcher uses inotify and tracks the directory inode — an
  # atomic directory swap (mv) changes the inode and silently breaks hot-reload,
  # leaving Traefik watching the old (now-deleted) directory forever.
  # Trade-off: files deleted from the repo are not removed here; they persist
  # in the LXC until a manual 'deploy traefik' + Traefik restart.
  if ! pct exec "$TRAEFIK_LXC_ID" -- bash -c "
    set -e
    tar -xzf /tmp/traefik-rules.tar.gz -C '$TRAEFIK_RULES_DEST'
    rm -f /tmp/traefik-rules.tar.gz
  "; then
    log_error "Traefik rules: failed to apply in LXC $TRAEFIK_LXC_ID"
    record_host_sync "traefik-rules" "FAILED" "$sha"
    return 1
  fi

  log_info "Traefik rules synced to LXC $TRAEFIK_LXC_ID — Traefik will hot-reload automatically"
  record_host_sync "traefik-rules" "OK" "$sha"
}

# Dispatches to the two host-managed syncs above based on what actually
# changed in this commit range. Called from sync() (automatic) and
# cmd_deploy() (manual force-deploy, which passes its own file list).
sync_host_managed_paths() {
  local sha="$1"; shift
  local -a changed_files=("$@")
  local any_failed=0
  local f

  for f in "${changed_files[@]}"; do
    if [[ "$f" == scripts/backup/* ]]; then
      sync_backup_scripts "$sha"
      break
    fi
  done

  for f in "${changed_files[@]}"; do
    if [[ "$f" == scripts/gitops/* ]]; then
      if ! sync_gitops_install "$sha" "${changed_files[@]}"; then
        any_failed=1
      fi
      break
    fi
  done

  return $any_failed
}

# -----------------------------------------------------------------------------
# LXC deployment
# -----------------------------------------------------------------------------
parse_lxc_entry() {
  local entry="$1"
  LXC_ID=$(echo "$entry" | cut -d'|' -f1)
  LXC_NAME=$(echo "$entry" | cut -d'|' -f2)
}

# Derive compose directories from lxc/<name>/compose.yml include lines.
# Returns unique top-level directories (e.g. "compose/media-server") plus
# the LXC's own directory (e.g. "lxc/media").
get_lxc_compose_dirs() {
  local lxc_name="$1"
  local compose_file="$REPO_DIR/lxc/$lxc_name/compose.yml"

  if [[ ! -f "$compose_file" ]]; then
    log_error "compose.yml not found for LXC $lxc_name: $compose_file"
    return 1
  fi

  {
    echo "lxc/$lxc_name"
    grep -oP '(?<=- )compose/[^/]+' "$compose_file" | sort -u
  }
}

lxc_is_affected() {
  local lxc_name="$1"
  shift
  local changed_files=("$@")

  local -a dirs
  mapfile -t dirs < <(get_lxc_compose_dirs "$lxc_name")

  for file in "${changed_files[@]}"; do
    # Check shared paths first
    for shared in "${SHARED_PATHS[@]}"; do
      if [[ "$file" == "$shared"/* ]]; then
        return 0
      fi
    done
    # Check LXC-specific paths (derived from compose.yml)
    for dir in "${dirs[@]}"; do
      if [[ "$file" == "$dir"/* ]]; then
        return 0
      fi
    done
  done
  return 1
}

deploy_to_lxc() {
  local lxc_id="$1" lxc_name="$2" sha="$3"
  local deploy_started=$SECONDS

  log_info "Deploying to LXC $lxc_id ($lxc_name)..."

  # Build the tar with all compose dirs derived from lxc/<name>/compose.yml
  local -a dirs
  mapfile -t dirs < <(get_lxc_compose_dirs "$lxc_name")

  local tar_args=()
  for dir in "${dirs[@]}"; do
    tar_args+=("$dir")
  done
  # Always include fragments (shared dependency)
  tar_args+=("compose/fragments")

  cd "$REPO_DIR"

  local tar_file="/tmp/lxc${lxc_id}-compose.tar.gz"
  log_info "LXC $lxc_id ($lxc_name): creating deployment archive..."
  if ! tar -czf "$tar_file" "${tar_args[@]}" 2>/dev/null; then
    log_error "LXC $lxc_id ($lxc_name): failed to create deployment archive"
    record_lxc_deploy "$lxc_id" "FAILED" "$sha"
    return 1
  fi

  log_info "LXC $lxc_id ($lxc_name): transferring deployment archive..."
  if ! pct push "$lxc_id" "$tar_file" /tmp/compose.tar.gz; then
    log_error "LXC $lxc_id ($lxc_name): failed to transfer deployment archive"
    rm -f "$tar_file"
    record_lxc_deploy "$lxc_id" "FAILED" "$sha"
    return 1
  fi

  rm -f "$tar_file"

  # The LXC compose file uses relative include paths (e.g. compose/network/...)
  # which Docker Compose resolves relative to the compose file's directory.
  # We copy it to $DOCKER_BASE/compose.yml so includes resolve correctly.
  log_info "LXC $lxc_id ($lxc_name): applying compose configuration..."
  if ! pct exec "$lxc_id" -- bash -c "
    set -e
    export HOME=/root
    tar -xzf /tmp/compose.tar.gz -C $DOCKER_BASE
    rm -f /tmp/compose.tar.gz
    cp $DOCKER_BASE/lxc/$lxc_name/compose.yml $DOCKER_BASE/compose.yml
  "; then
    log_error "LXC $lxc_id ($lxc_name): failed to apply compose configuration"
    record_lxc_deploy "$lxc_id" "FAILED" "$sha"
    return 1
  fi

  log_info "LXC $lxc_id ($lxc_name): pulling container images..."
  if ! pct exec "$lxc_id" -- bash -c "
    set -e
    export HOME=/root
    cd $DOCKER_BASE
    set -a; source .env 2>/dev/null || true; set +a
    docker compose --profile all pull --quiet 2>&1
  "; then
    log_error "LXC $lxc_id ($lxc_name): failed to pull container images"
    record_lxc_deploy "$lxc_id" "FAILED" "$sha"
    return 1
  fi

  log_info "LXC $lxc_id ($lxc_name): updating services..."
  if ! pct exec "$lxc_id" -- bash -c "
    set -e
    export HOME=/root
    cd $DOCKER_BASE
    set -a; source .env 2>/dev/null || true; set +a
    docker compose --profile all up -d --remove-orphans 2>&1
  "; then
    log_error "LXC $lxc_id ($lxc_name): failed to update services"
    record_lxc_deploy "$lxc_id" "FAILED" "$sha"
    return 1
  fi

  local prune_output reclaimed_space
  log_info "LXC $lxc_id ($lxc_name): cleaning unused images older than 24 hours..."
  if ! prune_output=$(pct exec "$lxc_id" -- docker image prune -a -f --filter 'until=24h' 2>&1); then
    printf '%s\n' "$prune_output" >> "$LOG_FILE"
    log_error "LXC $lxc_id ($lxc_name): failed to clean unused images"
    record_lxc_deploy "$lxc_id" "FAILED" "$sha"
    return 1
  fi

  reclaimed_space=$(awk -F ': ' '/Total reclaimed space:/ { value=$2 } END { print value }' <<< "$prune_output")
  log_info "LXC $lxc_id ($lxc_name): image cleanup complete; reclaimed ${reclaimed_space:-unknown}"

  log_info "Successfully deployed LXC $lxc_id ($lxc_name) in $((SECONDS - deploy_started))s"
  record_lxc_deploy "$lxc_id" "OK" "$sha"
  return 0
}

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
validate_compose() {
  local lxc_name="$1"
  cd "$REPO_DIR"

  # Use a dummy .env for syntax validation
  # Copy the LXC compose file to the repo root so relative include paths
  # (e.g. compose/network/...) resolve correctly from the repo root.
  if [[ -f ".env.example" ]]; then
    local tmp_env tmp_compose
    tmp_env=$(mktemp)
    tmp_compose=$(mktemp "$REPO_DIR/compose.validate.XXXXXX.yml")
    sed 's/=$/=dummy/g' .env.example > "$tmp_env"
    cp "lxc/$lxc_name/compose.yml" "$tmp_compose"
    docker compose --env-file "$tmp_env" -f "$tmp_compose" config --quiet 2>/dev/null
    local result=$?
    rm -f "$tmp_env" "$tmp_compose"
    return $result
  fi
  return 0
}

# -----------------------------------------------------------------------------
# Main sync logic
# -----------------------------------------------------------------------------
sync() {
  ensure_repo
  fetch_latest

  local remote_sha
  remote_sha=$(get_remote_sha)

  local last_sha
  last_sha=$(get_last_deployed_sha)

  # First run: set state without deploying (existing LXCs are already running)
  if [[ -z "$last_sha" ]]; then
    local local_sha
    local_sha=$(get_local_sha)
    log_info "First run — recording current commit $local_sha as baseline"
    pull_latest
    set_last_deployed_sha "$remote_sha"
    return 0
  fi

  # No changes
  if [[ "$remote_sha" == "$last_sha" ]]; then
    return 0
  fi

  log_info "Changes detected: $last_sha → $remote_sha"

  # Get list of changed files
  local -a changed_files
  mapfile -t changed_files < <(get_changed_files "$last_sha" "$remote_sha")

  if [[ ${#changed_files[@]} -eq 0 ]]; then
    log_warn "No file changes found between commits — updating state"
    set_last_deployed_sha "$remote_sha"
    return 0
  fi

  log_info "Changed files: ${changed_files[*]}"

  # Pull the latest code
  pull_latest

  # Determine affected LXCs and deploy
  local any_failed=0
  local deployed_count=0

  if ! sync_host_managed_paths "$remote_sha" "${changed_files[@]}"; then
    any_failed=1
  fi

  for f in "${changed_files[@]}"; do
    if [[ "$f" == traefik/* ]]; then
      if ! sync_traefik_rules "$remote_sha"; then
        any_failed=1
      fi
      break
    fi
  done

  for entry in "${LXC_ENTRIES[@]}"; do
    parse_lxc_entry "$entry"

    if lxc_is_affected "$LXC_NAME" "${changed_files[@]}"; then
      log_info "LXC $LXC_ID ($LXC_NAME) affected by changes"

      if deploy_to_lxc "$LXC_ID" "$LXC_NAME" "$remote_sha"; then
        ((deployed_count++)) || true
      else
        any_failed=1
      fi
    fi
  done

  if [[ $deployed_count -eq 0 ]]; then
    log_info "No LXC containers affected by changes"
  else
    log_info "Deployed to $deployed_count LXC container(s)"
  fi

  # Only update state if all deployments succeeded
  if [[ $any_failed -eq 0 ]]; then
    set_last_deployed_sha "$remote_sha"
    local short_sha="${remote_sha:0:7}"
    notify success "GitOps: deploy succeeded" \
      "Commit \`$short_sha\` deployed to $deployed_count LXC(s) — ${changed_files[*]}"
  else
    log_error "Some deployments failed — state NOT updated (will retry next cycle)"
    notify failure "GitOps: deploy FAILED" \
      "One or more deployments failed for commit \`${remote_sha:0:7}\`. Check \`journalctl -u gitops-sync.service\` on Proxmox."
    return 1
  fi
}

# -----------------------------------------------------------------------------
# Manual commands
# -----------------------------------------------------------------------------
cmd_status() {
  echo "GitOps Controller Status"
  echo "========================"
  echo "Repository:  $REPO_URL"
  echo "Branch:      $BRANCH"
  echo "Local clone: $REPO_DIR"
  echo ""

  local last_sha
  last_sha=$(get_last_deployed_sha)
  if [[ -n "$last_sha" ]]; then
    echo "Last deployed: $last_sha"
  else
    echo "Last deployed: (never)"
  fi

  echo ""
  echo "LXC Status:"
  for entry in "${LXC_ENTRIES[@]}"; do
    parse_lxc_entry "$entry"
    local state_file="$STATE_DIR/lxc-${LXC_ID}-last-deploy"
    if [[ -f "$state_file" ]]; then
      local last_deploy
      last_deploy=$(cat "$state_file")
      echo "  LXC $LXC_ID ($LXC_NAME): $last_deploy"
    else
      echo "  LXC $LXC_ID ($LXC_NAME): no deployments recorded"
    fi
  done

  echo ""
  echo "Host-managed paths:"
  local host_name
  for host_name in backup-scripts gitops-install traefik-rules; do
    local host_state_file="$STATE_DIR/host-${host_name}-last-sync"
    if [[ -f "$host_state_file" ]]; then
      echo "  $host_name: $(cat "$host_state_file")"
    else
      echo "  $host_name: no syncs recorded"
    fi
  done
}

cmd_deploy() {
  local target="${1:-all}"

  ensure_repo
  fetch_latest
  pull_latest

  local remote_sha
  remote_sha=$(get_remote_sha)

  if [[ "$target" == "all" || "$target" == "scripts" ]]; then
    sync_backup_scripts "$remote_sha"
  fi

  if [[ "$target" == "all" || "$target" == "gitops" ]]; then
    sync_gitops_install "$remote_sha" "scripts/gitops/gitops-webhook.py" "scripts/gitops/gitops-webhook.service"
  fi

  if [[ "$target" == "all" || "$target" == "traefik" ]]; then
    sync_traefik_rules "$remote_sha"
  fi

  for entry in "${LXC_ENTRIES[@]}"; do
    parse_lxc_entry "$entry"

    if [[ "$target" == "all" || "$target" == "$LXC_NAME" || "$target" == "$LXC_ID" ]]; then
      deploy_to_lxc "$LXC_ID" "$LXC_NAME" "$remote_sha"
    fi
  done

  # Only update global state when deploying all LXCs, otherwise a targeted
  # deploy would mark the commit as fully deployed while other LXCs may
  # still need updating.
  if [[ "$target" == "all" ]]; then
    set_last_deployed_sha "$remote_sha"
  fi
}

cmd_force_deploy() {
  local target="${1:-all}"
  log_info "Force deploying: $target"
  cmd_deploy "$target"
}

cmd_notify_test() {
  if [[ -z "${DISCORD_WEBHOOK_URL:-}" ]]; then
    echo "DISCORD_WEBHOOK_URL is not set in /etc/gitops/config.env"
    exit 1
  fi
  notify success "GitOps: test notification" "Webhook is configured correctly."
  echo "Test notification sent."
}

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Commands:
  sync           Check for changes and deploy affected LXCs + host-managed
                 paths (used by timer)
  status         Show current deployment status
  deploy [target] Force deploy to target (lxc name, id, 'scripts', 'gitops',
                 or 'all')
  notify-test    Send a test Discord notification to verify the webhook
  help           Show this help

Targets: all, infra, media, home, productivity, network, monitoring, juice-shop
         Or LXC ID: 101, 102, 103, 104, 105, 106, 107
         scripts  — force-sync scripts/backup/** to $BACKUP_SCRIPTS_DIR
         gitops   — force-sync scripts/gitops/** to $GITOPS_INSTALL_DIR
                    (restarts gitops-webhook.service)
         traefik  — force-sync traefik/** into LXC $TRAEFIK_LXC_ID at
                    $TRAEFIK_RULES_DEST (Traefik hot-reloads automatically)

Examples:
  $(basename "$0") sync              # Normal poll cycle
  $(basename "$0") status            # Show status
  $(basename "$0") deploy media      # Force redeploy media LXC
  $(basename "$0") deploy scripts    # Force resync backup scripts
  $(basename "$0") deploy gitops     # Force resync + restart controller/webhook
  $(basename "$0") deploy traefik    # Force resync Traefik rules
  $(basename "$0") deploy all        # Force redeploy everything
  $(basename "$0") deploy 102        # Force redeploy LXC 102
EOF
}

main() {
  local cmd="${1:-sync}"
  shift || true

  case "$cmd" in
    sync)          sync ;;
    status)        cmd_status ;;
    deploy)        cmd_force_deploy "${1:-all}" ;;
    notify-test)   cmd_notify_test ;;
    help|--help)   usage ;;
    *)             log_error "Unknown command: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
