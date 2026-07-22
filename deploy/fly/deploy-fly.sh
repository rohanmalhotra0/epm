#!/usr/bin/env bash
#
# deploy-fly.sh — bootstrap the EPM Wizard two-app Fly.io deployment.
#
# Creates (if missing) a private, always-warm backend app and a public frontend
# app, wires the frontend to the backend over private 6PN networking, sets the
# required secrets, deploys both, and prints the public frontend URL.
#
# Idempotent: safe to re-run to roll out a new image or reconcile config.
#
# Usage:
#   export TOGETHER_API_KEY=...              # Together AI inference key
#   export EPMW_DATABASE_URL=...             # Neon: postgresql+psycopg://.../db?sslmode=require
#   export EPMW_SECRET_MASTER_KEY=...        # stable key for the encrypted secret store
#   ./deploy-fly.sh                          # deploy (default)
#   ./deploy-fly.sh teardown                 # destroy both apps (and volumes)
#
# Optional overrides (env):
#   BACKEND_APP (default epmw-backend), FRONTEND_APP (default epmw-frontend),
#   FLY_REGION (default iad), FLY_ORG (default personal), VOLUME_SIZE_GB (1).
#   If you change BACKEND_APP, also update BACKEND_URL in frontend.fly.toml.
#
# Requires: flyctl on PATH and `fly auth login` already done. This script never
# runs flyctl for you if the prereqs are missing — it fails fast with guidance.

set -euo pipefail

BACKEND_APP="${BACKEND_APP:-epmw-backend}"
FRONTEND_APP="${FRONTEND_APP:-epmw-frontend}"
FLY_REGION="${FLY_REGION:-iad}"
FLY_ORG="${FLY_ORG:-personal}"
VOLUME_SIZE_GB="${VOLUME_SIZE_GB:-1}"
BACKEND_VOLUME="epmw_data"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ---- output helpers (single-quote any string containing a literal $) ---------
info()  { printf '\033[0;34m[fly]\033[0m %s\n' "$*"; }
ok()    { printf '\033[0;32m[fly]\033[0m %s\n' "$*"; }
warn()  { printf '\033[0;33m[fly]\033[0m %s\n' "$*" >&2; }
die()   { printf '\033[0;31m[fly] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# flyctl is distributed as both `fly` and `flyctl`; prefer whichever exists.
FLY="fly"

require_flyctl() {
  if command -v fly >/dev/null 2>&1; then
    FLY="fly"
  elif command -v flyctl >/dev/null 2>&1; then
    FLY="flyctl"
  else
    die 'flyctl not found. Install it: https://fly.io/docs/flyctl/install/ then run `fly auth login`.'
  fi
  if ! "$FLY" auth whoami >/dev/null 2>&1; then
    die 'Not logged in to Fly. Run `fly auth login` first.'
  fi
}

app_exists() { "$FLY" apps list 2>/dev/null | awk '{print $1}' | grep -qx "$1"; }

ensure_app() {
  local app="$1"
  if app_exists "$app"; then
    info "App '$app' already exists — reusing."
  else
    info "Creating app '$app' in org '$FLY_ORG'..."
    "$FLY" apps create "$app" --org "$FLY_ORG"
  fi
}

ensure_volume() {
  # Create the backend's persistent volume once. Even with external Postgres the
  # app needs it for artifacts, contexts, secrets, RAG indexes and backups.
  local app="$1"
  local count
  count="$("$FLY" volumes list -a "$app" 2>/dev/null | awk -v v="$BACKEND_VOLUME" '$2==v || $1==v {n++} END{print n+0}')"
  if [ "$count" -ge 1 ]; then
    info "Volume '$BACKEND_VOLUME' already exists on '$app' — reusing."
  else
    info "Creating ${VOLUME_SIZE_GB}GB volume '$BACKEND_VOLUME' on '$app'..."
    "$FLY" volumes create "$BACKEND_VOLUME" --app "$app" --region "$FLY_REGION" --size "$VOLUME_SIZE_GB" --yes
  fi
}

require_secret_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    die "Environment variable $name is not set. Export it before running (see header)."
  fi
}

set_backend_secrets() {
  local app="$1"
  info "Staging backend secrets (TOGETHER_API_KEY, EPMW_DATABASE_URL, EPMW_SECRET_MASTER_KEY)..."
  # --stage stores them without triggering a deploy on a machine-less app; the
  # subsequent `fly deploy` applies them. Values are read from the environment.
  "$FLY" secrets set --stage --app "$app" \
    "TOGETHER_API_KEY=${TOGETHER_API_KEY}" \
    "EPMW_DATABASE_URL=${EPMW_DATABASE_URL}" \
    "EPMW_SECRET_MASTER_KEY=${EPMW_SECRET_MASTER_KEY}"
}

deploy_app() {
  # Build from the repo root so the Dockerfiles' COPY paths resolve.
  local app="$1" config="$2" dockerfile="$3"
  info "Deploying '$app'..."
  "$FLY" deploy "$REPO_ROOT" \
    --config "$config" \
    --dockerfile "$REPO_ROOT/$dockerfile" \
    --app "$app" \
    --ha=false \
    --yes
}

harden_backend_private() {
  # Keep the backend off the public internet: release any public IP Fly may have
  # allocated. The frontend still reaches it over 6PN at <app>.internal:8000.
  # Best-effort — flyctl table formats vary by version, so never fail the run.
  local app="$1"
  info "Ensuring backend '$app' is private (releasing any public IPs)..."
  "$FLY" ips list -a "$app" 2>/dev/null \
    | awk 'tolower($3) ~ /public/ {print $2}' \
    | while IFS= read -r addr; do
        [ -n "$addr" ] && "$FLY" ips release "$addr" -a "$app" >/dev/null 2>&1 || true
      done
  return 0
}

ensure_frontend_public() {
  # Make sure the public frontend actually has public IPs allocated (idempotent).
  local app="$1"
  local ips
  ips="$("$FLY" ips list -a "$app" 2>/dev/null | awk 'tolower($3) ~ /public/ {print $2}')"
  if [ -z "$ips" ]; then
    info "Allocating public IPs for frontend '$app'..."
    "$FLY" ips allocate-v4 --shared -a "$app" >/dev/null 2>&1 || true
    "$FLY" ips allocate-v6 -a "$app" >/dev/null 2>&1 || true
  fi
}

do_deploy() {
  require_flyctl
  require_secret_env TOGETHER_API_KEY
  require_secret_env EPMW_DATABASE_URL
  require_secret_env EPMW_SECRET_MASTER_KEY

  ensure_app "$BACKEND_APP"
  ensure_volume "$BACKEND_APP"
  set_backend_secrets "$BACKEND_APP"
  deploy_app "$BACKEND_APP" "$SCRIPT_DIR/backend.fly.toml" "backend/Dockerfile"
  harden_backend_private "$BACKEND_APP"

  ensure_app "$FRONTEND_APP"
  deploy_app "$FRONTEND_APP" "$SCRIPT_DIR/frontend.fly.toml" "frontend/Dockerfile"
  ensure_frontend_public "$FRONTEND_APP"

  ok "Deploy complete."
  printf '\n'
  ok "Frontend URL: https://${FRONTEND_APP}.fly.dev"
  printf '\n'
  # Single-quoted so `set -u` never tries to expand the literal $ in the cost note.
  info 'Backend is private (6PN only); frontend proxies /api to it at'
  info "      http://${BACKEND_APP}.internal:8000"
  info 'Estimated cost at light usage: ~$10-20/mo Fly + external Neon Postgres.'
  info 'NEXT: add the oauth2-proxy login gate before sharing the URL (README section 6).'
  info 'Roll back a bad release with:  fly releases --app '"$BACKEND_APP"'  then  fly deploy --image <prev-image>'
}

do_teardown() {
  require_flyctl
  warn "This destroys apps '$FRONTEND_APP', '$BACKEND_APP' and (if present) 'epmw-auth', including the backend volume and all data on it."
  printf 'Type the frontend app name (%s) to confirm: ' "$FRONTEND_APP"
  local confirm
  read -r confirm
  [ "$confirm" = "$FRONTEND_APP" ] || die "Confirmation did not match; aborting."
  for app in "$FRONTEND_APP" "$BACKEND_APP" "epmw-auth"; do
    if app_exists "$app"; then
      info "Destroying '$app'..."
      "$FLY" apps destroy "$app" --yes || true
    fi
  done
  ok "Teardown complete. IBM Cloud resources are untouched (tear those down separately)."
}

main() {
  local cmd="${1:-deploy}"
  case "$cmd" in
    deploy)   do_deploy ;;
    teardown) do_teardown ;;
    *)        die "Unknown command '$cmd'. Use: deploy | teardown" ;;
  esac
}

main "$@"
