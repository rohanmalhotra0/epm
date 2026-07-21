#!/usr/bin/env bash
# One-command IBM Cloud bootstrap for EPM Wizard.
#
# Does the one-time prep that deploy-code-engine.sh assumes already exists —
# the Container Registry namespace, the Code Engine project, and the backend
# secret bundle (watsonx credentials) — then hands off to deploy-code-engine.sh,
# which builds + pushes both images and creates/updates the two apps.
# Idempotent: safe to re-run (re-running rolls out a fresh image).
#
# This is the "run one thing" path for a first hosted deploy. It uses ephemeral
# storage (SQLite resets when the app scales to zero) and leaves the frontend
# PUBLIC with no login — add the App ID gate and/or managed Postgres afterward
# (see docs/IBM_CLOUD.md §4–§5). It cannot run from a network-restricted CI
# sandbox — it must run on a machine that can reach IBM Cloud.
#
# Prereqs (do these once, yourself):
#   1. Install the IBM Cloud CLI and Docker; start Docker.
#   2. ibmcloud login -a https://cloud.ibm.com -r us-south -g Default   (or --sso)
#   3. ibmcloud plugin install code-engine container-registry -f
#
# Usage:
#   WATSONX_API_KEY=<your-ibm-iam-api-key> \
#   WATSONX_PROJECT_ID=<your-watsonx.ai-project-id> \
#   ./bootstrap-code-engine.sh
#
# Optional overrides (sane defaults shown):
#   REGION=us-south ICR_NAMESPACE=epmw CE_PROJECT=epmw-project REGISTRY=us.icr.io

set -euo pipefail

REGION="${REGION:-us-south}"
ICR_NAMESPACE="${ICR_NAMESPACE:-epmw}"
CE_PROJECT="${CE_PROJECT:-epmw-project}"
REGISTRY="${REGISTRY:-us.icr.io}"
SECRET_NAME="${SECRET_NAME:-epmw-secrets}"
WATSONX_URL="${WATSONX_URL:-https://${REGION}.ml.cloud.ibm.com}"
HERE="$(cd "$(dirname "$0")" && pwd)"

: "${WATSONX_API_KEY:?set WATSONX_API_KEY to your IBM Cloud IAM api key (44 chars, no + / = ; :)}"
: "${WATSONX_PROJECT_ID:?set WATSONX_PROJECT_ID to your watsonx.ai project id}"

# A plaintext IAM key is 44 chars of [A-Za-z0-9_-]. Catch the common mistakes
# (an encrypted blob, or a key *name*) before they waste a whole deploy.
if printf '%s' "${WATSONX_API_KEY}" | grep -q '[+/=;:]'; then
  echo "!! WATSONX_API_KEY contains + / = ; or : — that is an encrypted blob, not a" >&2
  echo "   plaintext IAM key. Create one at cloud.ibm.com/iam/apikeys and copy it" >&2
  echo "   from the 'API key successfully created' dialog." >&2
  exit 1
fi

echo "==> Region ${REGION} | registry ${REGISTRY}/${ICR_NAMESPACE} | project ${CE_PROJECT}"
ibmcloud target -r "${REGION}" >/dev/null

# 1. Container Registry namespace (namespace-add is a no-op error if it exists).
echo "==> Ensuring ICR namespace ${ICR_NAMESPACE}"
ibmcloud cr region-set "${REGION}" >/dev/null 2>&1 || true
ibmcloud cr namespace-add "${ICR_NAMESPACE}" 2>/dev/null || echo "    (namespace already exists)"

# 2. Code Engine project (create only when missing), then select it.
if ibmcloud ce project get --name "${CE_PROJECT}" >/dev/null 2>&1; then
  echo "==> Code Engine project ${CE_PROJECT} exists"
else
  echo "==> Creating Code Engine project ${CE_PROJECT}"
  ibmcloud ce project create --name "${CE_PROJECT}"
fi
ibmcloud ce project select --name "${CE_PROJECT}"

# 3. Backend secret bundle (watsonx credentials). Recreate so re-runs pick up a
#    rotated key. Never baked into an image — injected as a Code Engine secret.
echo "==> Writing secret ${SECRET_NAME} (watsonx credentials)"
ibmcloud ce secret delete --name "${SECRET_NAME}" --force >/dev/null 2>&1 || true
ibmcloud ce secret create --name "${SECRET_NAME}" \
  --from-literal "WATSONX_API_KEY=${WATSONX_API_KEY}" \
  --from-literal "WATSONX_URL=${WATSONX_URL}" \
  --from-literal "WATSONX_PROJECT_ID=${WATSONX_PROJECT_ID}"

# 4. Build + push the images and create/update the apps.
echo "==> Handing off to deploy-code-engine.sh (builds images, creates apps)"
REGION="${REGION}" ICR_NAMESPACE="${ICR_NAMESPACE}" CE_PROJECT="${CE_PROJECT}" \
  REGISTRY="${REGISTRY}" "${HERE}/deploy-code-engine.sh"

echo
echo "==> Bootstrap complete. The frontend URL is the public epmw-frontend app above."
echo "    watsonx is wired via the ${SECRET_NAME} secret, so no in-app key entry is"
echo "    needed on the hosted instance. Add App ID login before sharing it widely"
echo "    (docs/IBM_CLOUD.md §5)."
