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
echo "==> Deploying backend"
deploy_app epmw-backend "${BACKEND_IMAGE}" 8000 \
  --visibility project \
  --env EPMW_DATA_DIR=/data --env EPMW_LOG_JSON=true \
  --env-from-secret epmw-secrets \
  --mount-data-store /data=epmw-data

# Frontend: private to the VPC — reachable only over the client-to-site VPN.
echo "==> Deploying frontend"
deploy_app epmw-frontend "${FRONTEND_IMAGE}" 3000 \
  --visibility private \
  --env BACKEND_URL="http://epmw-backend.$(ibmcloud ce project current --output json | grep -o '"name": *"[^"]*"' | head -1 | sed 's/.*: *"//;s/"//')"

echo "==> Done"
ibmcloud ce app list
