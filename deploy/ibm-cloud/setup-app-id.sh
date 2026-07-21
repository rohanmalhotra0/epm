#!/usr/bin/env bash
# Put an IBM App ID email-invite login gate in front of the hosted EPM Wizard —
# NO Terraform. Provisions the App ID instance, creates an OIDC application,
# wires the oauth2-proxy secret, redeploys the login gate (via
# deploy-code-engine.sh), and registers the OAuth callback URL. The ONLY manual
# step left is inviting users in the App ID console.
#
# Prereqs: ibmcloud CLI logged in (us-south, Default RG); the app already
# deployed (bootstrap + cloud-build done); python3 and curl.
#
# Usage:
#   ./setup-app-id.sh
#
# Rollback (make the app public again): delete the epmw-appid secret and
# redeploy —  ibmcloud ce secret delete --name epmw-appid --force
#   then: SKIP_BUILD=1 TAG=latest REGISTRY_SECRET=epmw-icr FRONTEND_VISIBILITY=public ./deploy-code-engine.sh

set -euo pipefail

REGION="${REGION:-us-south}"
CE_PROJECT="${CE_PROJECT:-epmw-project}"
APPID_NAME="${APPID_NAME:-epmw-appid}"
APPID_PLAN="${APPID_PLAN:-graduated-tier}"   # free under ~1000 monthly active users
OIDC_APP_NAME="${OIDC_APP_NAME:-EPM Wizard}"
REGISTRY_SECRET="${REGISTRY_SECRET:-epmw-icr}"
HERE="$(cd "$(dirname "$0")" && pwd)"

jget() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

echo "==> [1/6] Ensuring App ID instance '${APPID_NAME}' (${APPID_PLAN})"
if ! ibmcloud resource service-instance "${APPID_NAME}" >/dev/null 2>&1; then
  ibmcloud resource service-instance-create "${APPID_NAME}" appid "${APPID_PLAN}" "${REGION}"
fi
TENANT="$(ibmcloud resource service-instance "${APPID_NAME}" --output json \
  | jget "(d[0] if isinstance(d,list) else d)['guid']")"
echo "    tenantId: ${TENANT}"
MGMT="https://${REGION}.appid.cloud.ibm.com/management/v4/${TENANT}"

echo "==> [2/6] Creating the OIDC application (App ID management API)"
TOKEN="$(ibmcloud iam oauth-tokens --output json | jget "d['iam_token']")"
# Reuse an app of this name if one already exists, else create it.
APP_JSON="$(curl -fsS -H "Authorization: ${TOKEN}" "${MGMT}/applications" \
  | python3 -c "import sys,json;a=[x for x in json.load(sys.stdin).get('applications',[]) if x.get('name')=='${OIDC_APP_NAME}'];print(json.dumps(a[0]) if a else '')")"
if [ -z "${APP_JSON}" ]; then
  APP_JSON="$(curl -fsS -X POST "${MGMT}/applications" -H "Authorization: ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${OIDC_APP_NAME}\",\"type\":\"regularwebapp\"}")"
fi
CLIENT_ID="$(printf '%s' "${APP_JSON}"  | jget "d['clientId']")"
CLIENT_SECRET="$(printf '%s' "${APP_JSON}" | jget "d['secret']")"
ISSUER="https://${REGION}.appid.cloud.ibm.com/oauth/v4/${TENANT}"
echo "    clientId: ${CLIENT_ID}"

echo "==> [3/6] Creating Code Engine secret '${APPID_NAME}'"
ibmcloud ce project select --name "${CE_PROJECT}" >/dev/null
COOKIE_SECRET="$(python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")"
ibmcloud ce secret delete --name "${APPID_NAME}" --force >/dev/null 2>&1 || true
ibmcloud ce secret create --name "${APPID_NAME}" \
  --from-literal "OAUTH2_PROXY_OIDC_ISSUER_URL=${ISSUER}" \
  --from-literal "OAUTH2_PROXY_CLIENT_ID=${CLIENT_ID}" \
  --from-literal "OAUTH2_PROXY_CLIENT_SECRET=${CLIENT_SECRET}" \
  --from-literal "OAUTH2_PROXY_COOKIE_SECRET=${COOKIE_SECRET}"

echo "==> [4/6] Redeploying with the login gate (frontend goes private, oauth2-proxy public)"
SKIP_BUILD=1 TAG=latest REGISTRY_SECRET="${REGISTRY_SECRET}" AUTH_SECRET="${APPID_NAME}" \
  "${HERE}/deploy-code-engine.sh"

echo "==> [5/6] Registering the OAuth callback URL in App ID"
AUTH_URL="$(ibmcloud ce app get --name epmw-auth --output url 2>/dev/null || true)"
if [ -z "${AUTH_URL}" ]; then
  echo "    !! could not read epmw-auth URL; re-run once the app is Ready." >&2
  exit 1
fi
TOKEN="$(ibmcloud iam oauth-tokens --output json | jget "d['iam_token']")"
curl -fsS -X PUT "${MGMT}/config/redirect_uris" -H "Authorization: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"redirectUris\":[\"${AUTH_URL}/oauth2/callback\"]}"
echo

echo "==> [6/6] Login gate is up:  ${AUTH_URL}"
echo
echo "    LAST STEP — invite yourself (console, ~1 min):"
echo "      IBM Cloud -> Resource list -> Services -> ${APPID_NAME}"
echo "      -> Manage Authentication -> Identity Providers -> Cloud Directory (enable)"
echo "      -> Manage Authentication -> Cloud Directory -> Users -> Create user (your email)"
echo "    Then open ${AUTH_URL} and sign in with that user."
