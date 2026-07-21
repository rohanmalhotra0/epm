#!/usr/bin/env bash
# Build EPM Wizard's images IN IBM Cloud (Code Engine build, Kaniko) straight
# from the public GitHub repo, then deploy the two apps — NO local Docker.
#
# Use this when Docker Desktop won't cooperate. It assumes the Container
# Registry namespace, the Code Engine project, and the epmw-secrets bundle
# already exist (bootstrap-code-engine.sh created them). It hands the app
# create/update off to deploy-code-engine.sh with SKIP_BUILD=1.
#
# Prereqs: ibmcloud CLI logged in (ibmcloud login --sso), code-engine +
# container-registry plugins, and the bootstrap already run once.
#
# Usage:
#   ICR_APIKEY=<ibm-iam-api-key-with-registry-write> \
#   ./deploy-code-engine-cloudbuild.sh
#
# The IAM key just needs Container Registry write in this account; the same
# account-owner key you used for watsonx works.

set -euo pipefail

REGION="${REGION:-us-south}"
ICR_NAMESPACE="${ICR_NAMESPACE:-epmw}"
CE_PROJECT="${CE_PROJECT:-epmw-project}"
REGISTRY="${REGISTRY:-us.icr.io}"
SOURCE_REPO="${SOURCE_REPO:-https://github.com/rohanmalhotra0/epm}"
SOURCE_REV="${SOURCE_REV:-main}"
REG_SECRET="${REG_SECRET:-epmw-icr}"
BUILD_SIZE="${BUILD_SIZE:-large}"
TAG="latest"   # cloud-built images are :latest so the deploy half matches
HERE="$(cd "$(dirname "$0")" && pwd)"

: "${ICR_APIKEY:?set ICR_APIKEY to an IBM Cloud IAM api key with Container Registry write}"

BACKEND_IMAGE="${REGISTRY}/${ICR_NAMESPACE}/epmw-backend:${TAG}"
FRONTEND_IMAGE="${REGISTRY}/${ICR_NAMESPACE}/epmw-frontend:${TAG}"

echo "==> Project ${CE_PROJECT} | source ${SOURCE_REPO}@${SOURCE_REV}"
ibmcloud ce project select --name "${CE_PROJECT}"

# Registry access secret so the in-cloud build can push to ICR.
if ibmcloud ce registry get --name "${REG_SECRET}" >/dev/null 2>&1; then
  echo "==> Registry secret ${REG_SECRET} exists"
else
  echo "==> Creating registry secret ${REG_SECRET}"
  ibmcloud ce registry create --name "${REG_SECRET}" --server "${REGISTRY}" \
    --username iamapikey --password "${ICR_APIKEY}"
fi

# Create (or update) a build definition and run it to completion.
cloud_build() {
  local name="$1" dockerfile="$2" image="$3"
  echo "==> Cloud-building ${image} (Dockerfile ${dockerfile})"
  if ibmcloud ce build get --name "${name}" >/dev/null 2>&1; then
    ibmcloud ce build update --name "${name}" \
      --source "${SOURCE_REPO}" --commit "${SOURCE_REV}" \
      --strategy dockerfile --dockerfile "${dockerfile}" --context-dir . \
      --image "${image}" --registry-secret "${REG_SECRET}" --size "${BUILD_SIZE}"
  else
    ibmcloud ce build create --name "${name}" \
      --source "${SOURCE_REPO}" --commit "${SOURCE_REV}" \
      --strategy dockerfile --dockerfile "${dockerfile}" --context-dir . \
      --image "${image}" --registry-secret "${REG_SECRET}" --size "${BUILD_SIZE}"
  fi
  ibmcloud ce buildrun submit --build "${name}" --wait
}

cloud_build epmw-backend-build backend/Dockerfile "${BACKEND_IMAGE}"
cloud_build epmw-frontend-build frontend/Dockerfile "${FRONTEND_IMAGE}"

# Deploy the apps using the sibling script's create/update logic, skipping its
# local Docker build. TAG=latest makes its derived image names match ours.
echo "==> Deploying apps from the cloud-built images"
SKIP_BUILD=1 TAG="${TAG}" REGION="${REGION}" ICR_NAMESPACE="${ICR_NAMESPACE}" \
  CE_PROJECT="${CE_PROJECT}" REGISTRY="${REGISTRY}" REGISTRY_SECRET="${REG_SECRET}" \
  "${HERE}/deploy-code-engine.sh"

echo
echo "==> Done. The public frontend URL is the epmw-frontend app listed above."
