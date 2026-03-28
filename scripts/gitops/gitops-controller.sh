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

# Load config override if present
CONFIG_FILE="/etc/gitops/config.env"
# shellcheck source=/dev/null
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

# -----------------------------------------------------------------------------
# LXC Mapping
# -----------------------------------------------------------------------------
# Each entry: LXC_ID|NAME|COMPOSE_DIRS (comma-separated paths that trigger deploy)
# compose/fragments is a shared dependency that triggers ALL LXCs
LXC_ENTRIES=(
  "101|infra|lxc/infra,compose/reverse-proxy,compose/database"
  "102|media|lxc/media,compose/media-server"
  "103|home|lxc/home,compose/home-automation"
  "104|productivity|lxc/productivity,compose/productivity"
  "105|network|lxc/network,compose/network"
  "106|monitoring|lxc/monitoring,compose/monitoring"
  "107|utilities|lxc/utilities,compose/utilities"
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
# LXC deployment
# -----------------------------------------------------------------------------
parse_lxc_entry() {
  local entry="$1"
  LXC_ID=$(echo "$entry" | cut -d'|' -f1)
  LXC_NAME=$(echo "$entry" | cut -d'|' -f2)
  LXC_DIRS=$(echo "$entry" | cut -d'|' -f3)
}

lxc_is_affected() {
  local lxc_dirs="$1"
  shift
  local changed_files=("$@")

  IFS=',' read -ra dirs <<< "$lxc_dirs"
  for file in "${changed_files[@]}"; do
    # Check shared paths first
    for shared in "${SHARED_PATHS[@]}"; do
      if [[ "$file" == "$shared"/* ]]; then
        return 0
      fi
    done
    # Check LXC-specific paths
    for dir in "${dirs[@]}"; do
      if [[ "$file" == "$dir"/* ]]; then
        return 0
      fi
    done
  done
  return 1
}

deploy_to_lxc() {
  local lxc_id="$1" lxc_name="$2" lxc_dirs="$3" sha="$4"

  log_info "Deploying to LXC $lxc_id ($lxc_name)..."

  # Build the tar with all compose dirs this LXC needs (including fragments)
  IFS=',' read -ra dirs <<< "$lxc_dirs"
  local tar_args=()
  for dir in "${dirs[@]}"; do
    tar_args+=("$dir")
  done
  # Always include fragments (shared dependency)
  tar_args+=("compose/fragments")

  cd "$REPO_DIR"

  local tar_file="/tmp/lxc${lxc_id}-compose.tar.gz"
  if ! tar -czf "$tar_file" "${tar_args[@]}" 2>/dev/null; then
    log_error "Failed to create tar for LXC $lxc_id"
    record_lxc_deploy "$lxc_id" "FAILED" "$sha"
    return 1
  fi

  # Push tar into LXC and deploy
  if ! pct push "$lxc_id" "$tar_file" /tmp/compose.tar.gz; then
    log_error "Failed to push compose files to LXC $lxc_id"
    rm -f "$tar_file"
    record_lxc_deploy "$lxc_id" "FAILED" "$sha"
    return 1
  fi

  rm -f "$tar_file"

  # Extract and deploy inside the LXC
  # The LXC compose file uses relative include paths (e.g. compose/network/...)
  # which Docker Compose resolves relative to the compose file's directory.
  # We copy it to $DOCKER_BASE/compose.yml so includes resolve correctly.
  if ! pct exec "$lxc_id" -- bash -c "
    set -e
    export HOME=/root
    tar -xzf /tmp/compose.tar.gz -C $DOCKER_BASE
    rm -f /tmp/compose.tar.gz
    cp $DOCKER_BASE/lxc/$lxc_name/compose.yml $DOCKER_BASE/compose.yml
    cd $DOCKER_BASE
    docker compose --profile $lxc_name pull --quiet
    docker compose --profile $lxc_name up -d --remove-orphans
    docker image prune -f --filter 'until=24h'
  "; then
    log_error "Failed to deploy services in LXC $lxc_id ($lxc_name)"
    record_lxc_deploy "$lxc_id" "FAILED" "$sha"
    return 1
  fi

  log_info "Successfully deployed LXC $lxc_id ($lxc_name)"
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

  for entry in "${LXC_ENTRIES[@]}"; do
    parse_lxc_entry "$entry"

    if lxc_is_affected "$LXC_DIRS" "${changed_files[@]}"; then
      log_info "LXC $LXC_ID ($LXC_NAME) affected by changes"

      if deploy_to_lxc "$LXC_ID" "$LXC_NAME" "$LXC_DIRS" "$remote_sha"; then
        ((deployed_count++))
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
  else
    log_error "Some deployments failed — state NOT updated (will retry next cycle)"
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
}

cmd_deploy() {
  local target="${1:-all}"

  ensure_repo
  fetch_latest
  pull_latest

  local remote_sha
  remote_sha=$(get_remote_sha)

  for entry in "${LXC_ENTRIES[@]}"; do
    parse_lxc_entry "$entry"

    if [[ "$target" == "all" || "$target" == "$LXC_NAME" || "$target" == "$LXC_ID" ]]; then
      deploy_to_lxc "$LXC_ID" "$LXC_NAME" "$LXC_DIRS" "$remote_sha"
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

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Commands:
  sync           Check for changes and deploy affected LXCs (used by timer)
  status         Show current deployment status
  deploy [target] Force deploy to target (lxc name, id, or 'all')
  help           Show this help

Targets: all, infra, media, home, productivity, network, monitoring, utilities
         Or LXC ID: 101, 102, 103, 104, 105, 106, 107

Examples:
  $(basename "$0") sync              # Normal poll cycle
  $(basename "$0") status            # Show status
  $(basename "$0") deploy media      # Force redeploy media LXC
  $(basename "$0") deploy all        # Force redeploy everything
  $(basename "$0") deploy 102        # Force redeploy LXC 102
EOF
}

main() {
  local cmd="${1:-sync}"
  shift || true

  case "$cmd" in
    sync)         sync ;;
    status)       cmd_status ;;
    deploy)       cmd_force_deploy "${1:-all}" ;;
    help|--help)  usage ;;
    *)            log_error "Unknown command: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
