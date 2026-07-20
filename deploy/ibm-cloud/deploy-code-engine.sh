#!/usr/bin/env bash
# Build both EPM Wizard images, push them to IBM Container Registry, and
# create/update the two Code Engine apps. Idempotent: re-run to roll out a
# new version. Infrastructure (VPC, VPN, Code Engine project, ICR namespace)
# comes from ./terraform — see docs/IBM_CLOUD.md.
#
# Prereqs: ibmcloud CLI with container-registry + code-engine plugins, docker,
# and `ibmcloud login` already done.
#
# Usage:
#   REGION=us-south ICR_NAMESPACE=epmw CE_PROJECT=epmw-project ./deploy-code-engine.sh

set -euo pipefail

REGION="${REGION:-us-south}"
ICR_NAMESPACE="${ICR_NAMESPACE:-epmw}"
CE_PROJECT="${CE_PROJECT:-epmw-project}"
TAG="${TAG:-$(git rev-parse --short HEAD)}"
REGISTRY="${REGISTRY:-us.icr.io}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_IMAGE="${REGISTRY}/${ICR_NAMESPACE}/epmw-backend:${TAG}"
FRONTEND_IMAGE="${REGISTRY}/${ICR_NAMESPACE}/epmw-frontend:${TAG}"

echo "==> Building images (tag ${TAG})"
docker build -f "${REPO_ROOT}/backend/Dockerfile" -t "${BACKEND_IMAGE}" "${REPO_ROOT}"
docker build -f "${REPO_ROOT}/frontend/Dockerfile" -t "${FRONTEND_IMAGE}" "${REPO_ROOT}"

echo "==> Pushing to IBM Container Registry"
ibmcloud cr region-set "${REGION}" >/dev/null
ibmcloud cr login
docker push "${BACKEND_IMAGE}"
docker push "${FRONTEND_IMAGE}"

echo "==> Selecting Code Engine project ${CE_PROJECT}"
ibmcloud ce project select --name "${CE_PROJECT}"

deploy_app() {
  local name="$1" image="$2" port="$3"; shift 3
  if ibmcloud ce app get --name "${name}" >/dev/null 2>&1; then
    ibmcloud ce app update --name "${name}" --image "${image}" "$@"
  else
    ibmcloud ce app create --name "${name}" --image "${image}" --port "${port}" \
      --min-scale 0 --max-scale 2 "$@"
  fi
}

# Backend: private endpoint only; secrets (WATSONX_API_KEY, Oracle creds) are
# injected from a Code Engine secret backed by Secrets Manager — create it once:
#   ibmcloud ce secret create --name epmw-secrets --from-env-file .env.production
#
# Database: SQLite on the /data volume by default. To use IBM Cloud Databases
# for PostgreSQL instead (terraform: enable_postgres=true), create the optional
# secret (default name epmw-database, override via DB_SECRET) holding
# EPMW_DATABASE_URL — ICD requires TLS, so mount its CA cert from a secret and
# reference the mount path in sslrootcert:
#   ibmcloud ce secret create --name epmw-database --from-literal \
#     EPMW_DATABASE_URL='postgresql+psycopg://user:pass@host:port/db?sslmode=verify-full&sslrootcert=/etc/epmw/pg-ca.pem'
# When the secret exists it is injected below and wins over SQLite.
DB_SECRET="${DB_SECRET:-epmw-database}"
DB_ARGS=()
if ibmcloud ce secret get --name "${DB_SECRET}" >/dev/null 2>&1; then
  echo "==> Database secret ${DB_SECRET} found — backend will use EPMW_DATABASE_URL"
  DB_ARGS+=(--env-from-secret "${DB_SECRET}")
else
  echo "==> No ${DB_SECRET} secret — backend stays on SQLite (/data volume)"
fi

echo "==> Deploying backend"
deploy_app epmw-backend "${BACKEND_IMAGE}" 8000 \
  --visibility project \
  --env EPMW_DATA_DIR=/data --env EPMW_LOG_JSON=true \
  --env WATSONX_CHAT_MODEL_ID="${WATSONX_CHAT_MODEL_ID:-meta-llama/llama-3-3-70b-instruct}" \
  --env WATSONX_EMBEDDINGS_MODEL_ID="${WATSONX_EMBEDDINGS_MODEL_ID:-ibm/slate-125m-english-rtrvr}" \
  --env-from-secret epmw-secrets \
  ${DB_ARGS[@]+"${DB_ARGS[@]}"} \
  --mount-data-store /data=epmw-data

# App ID front door (docs/IBM_CLOUD.md §5): when the epmw-appid secret exists,
# an oauth2-proxy app becomes the ONLY public endpoint and the frontend is
# flipped to project visibility behind it. Create the secret once from the
# terraform outputs (app_id_issuer_url / client id / client secret):
#   ibmcloud ce secret create --name epmw-appid \
#     --from-literal OAUTH2_PROXY_OIDC_ISSUER_URL="$(terraform output -raw app_id_issuer_url)" \
#     --from-literal OAUTH2_PROXY_CLIENT_ID="$(terraform output -raw app_id_client_id)" \
#     --from-literal OAUTH2_PROXY_CLIENT_SECRET="$(terraform output -raw app_id_client_secret)" \
#     --from-literal OAUTH2_PROXY_COOKIE_SECRET="$(python3 -c 'import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
# Then run ../configure-app-id.sh once to register the callback URL in App ID.
AUTH_SECRET="${AUTH_SECRET:-epmw-appid}"
AUTH_IMAGE="${AUTH_IMAGE:-quay.io/oauth2-proxy/oauth2-proxy:v7.6.0}"
PROJECT_NAME="$(ibmcloud ce project current --output json | grep -o '"name": *"[^"]*"' | head -1 | sed 's/.*: *"//;s/"//')"

FRONTEND_VISIBILITY_DEFAULT=public
if ibmcloud ce secret get --name "${AUTH_SECRET}" >/dev/null 2>&1; then
  FRONTEND_VISIBILITY_DEFAULT=project
fi

echo "==> Deploying frontend"
deploy_app epmw-frontend "${FRONTEND_IMAGE}" 3000 \
  --visibility "${FRONTEND_VISIBILITY:-${FRONTEND_VISIBILITY_DEFAULT}}" \
  --env BACKEND_URL="http://epmw-backend.${PROJECT_NAME}"

if ibmcloud ce secret get --name "${AUTH_SECRET}" >/dev/null 2>&1; then
  echo "==> ${AUTH_SECRET} secret found — deploying App ID login gate (oauth2-proxy)"
  deploy_app epmw-auth "${AUTH_IMAGE}" 4180 \
    --visibility public \
    --env OAUTH2_PROXY_PROVIDER=oidc \
    --env OAUTH2_PROXY_HTTP_ADDRESS=0.0.0.0:4180 \
    --env OAUTH2_PROXY_UPSTREAMS="http://epmw-frontend.${PROJECT_NAME}" \
    --env OAUTH2_PROXY_EMAIL_DOMAINS='*' \
    --env OAUTH2_PROXY_COOKIE_SECURE=true \
    --env OAUTH2_PROXY_FLUSH_INTERVAL=1s \
    --env-from-secret "${AUTH_SECRET}"
  # The redirect URL is this app's own generated URL — set it now that it exists.
  AUTH_URL="$(ibmcloud ce app get --name epmw-auth --output json | grep -o '"url": *"https[^"]*"' | head -1 | sed 's/.*: *"//;s/"//')"
  if [ -n "${AUTH_URL}" ]; then
    ibmcloud ce app update --name epmw-auth --env OAUTH2_PROXY_REDIRECT_URL="${AUTH_URL}/oauth2/callback" >/dev/null
    echo "==> Login gate: ${AUTH_URL}"
    echo "    Register the callback in App ID (once): ../configure-app-id.sh, or add"
    echo "    ${AUTH_URL}/oauth2/callback to the App ID redirect URLs manually."
  fi
else
  echo "==> No ${AUTH_SECRET} secret — frontend stays PUBLIC with no login."
  echo "    For the App ID front door, create the secret (see comment above) and re-run."
fi

echo "==> Done"
ibmcloud ce app list
