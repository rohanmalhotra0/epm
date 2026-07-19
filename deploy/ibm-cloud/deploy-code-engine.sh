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
  --env-from-secret epmw-secrets \
  ${DB_ARGS[@]+"${DB_ARGS[@]}"} \
  --mount-data-store /data=epmw-data

# Frontend: public HTTPS endpoint by default, with App ID (OIDC) as the
# security boundary — matches the terraform default enable_vpn=false and needs
# nothing installed on the user's machine. Set FRONTEND_VISIBILITY=private for
# the VPN topology (enable_vpn=true), where it is reachable only over the
# client-to-site VPN.
echo "==> Deploying frontend"
deploy_app epmw-frontend "${FRONTEND_IMAGE}" 3000 \
  --visibility "${FRONTEND_VISIBILITY:-public}" \
  --env BACKEND_URL="http://epmw-backend.$(ibmcloud ce project current --output json | grep -o '"name": *"[^"]*"' | head -1 | sed 's/.*: *"//;s/"//')"

echo "==> Done"
ibmcloud ce app list
