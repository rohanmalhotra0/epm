#!/usr/bin/env bash
# Provision IBM Cloud Databases for PostgreSQL and point the hosted EPM Wizard
# backend at it, so per-user data survives redeploys/restarts.
#
# ⚠️  PAID service (~$30-50/month). Provisioning takes ~20-30 minutes.
#
# Also rebuilds/redeploys with per-user isolation on (EPMW_MULTI_USER=true) and
# the App ID login gate kept in place — one command for the full durable,
# private, multi-user setup.
#
# Prereqs: ibmcloud CLI logged in (us-south, Default RG); app already deployed;
# python3; the App ID gate already set up (epmw-appid secret exists).
#
# Usage:
#   ICR_APIKEY=<ibm-iam-api-key> ./setup-postgres.sh
#
# Rollback to ephemeral SQLite: delete the epmw-database secret + redeploy.
#   ibmcloud ce secret delete --name epmw-database --force

set -euo pipefail

REGION="${REGION:-us-south}"
CE_PROJECT="${CE_PROJECT:-epmw-project}"
PG_NAME="${PG_NAME:-epmw-pg}"
PG_PLAN="${PG_PLAN:-standard}"
PG_KEY="${PG_KEY:-epmw-pg-key}"
DB_SECRET="${DB_SECRET:-epmw-database}"
HERE="$(cd "$(dirname "$0")" && pwd)"

: "${ICR_APIKEY:?set ICR_APIKEY to an IBM Cloud IAM api key (used for the image rebuild)}"

echo "==> [1/5] Provisioning PostgreSQL '${PG_NAME}' (PAID, ~\$30-50/mo)"
if ibmcloud resource service-instance "${PG_NAME}" >/dev/null 2>&1; then
  echo "    instance already exists"
else
  # ICD requires an explicit endpoint type. 'public' is TLS-encrypted and
  # reachable from Code Engine's egress without extra VPC/VPE wiring; harden to
  # 'private' later by reprovisioning with PG_ENDPOINTS=private once the project
  # has private service endpoints.
  ibmcloud resource service-instance-create "${PG_NAME}" databases-for-postgresql \
    "${PG_PLAN}" "${REGION}" --service-endpoints "${PG_ENDPOINTS:-public}"
fi

echo "==> [2/5] Waiting for it to become active (~20-30 min — this is the slow part)"
STATE=""
for i in $(seq 1 80); do
  STATE="$(ibmcloud resource service-instance "${PG_NAME}" --output json \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print((d[0] if isinstance(d,list) else d).get('state',''))" 2>/dev/null || echo)"
  echo "    [$i/80] state: ${STATE:-unknown}"
  [ "${STATE}" = "active" ] && break
  sleep 30
done
if [ "${STATE}" != "active" ]; then
  echo "    !! still not active. It may just need more time — re-run this script later;" >&2
  echo "       it skips creation and picks up where it left off." >&2
  exit 1
fi

echo "==> [3/5] Creating service key and reading the connection string"
if ibmcloud resource service-key "${PG_KEY}" >/dev/null 2>&1; then
  echo "    service key already exists"
else
  # Don't mask errors — service-key-create can fail if the deployment isn't yet
  # ready to mint credentials; retry a few times before giving up.
  for attempt in 1 2 3 4 5; do
    if ibmcloud resource service-key-create "${PG_KEY}" Administrator --instance-name "${PG_NAME}"; then
      break
    fi
    echo "    key create failed (attempt ${attempt}/5) — the DB may still be finalizing; waiting 30s"
    sleep 30
  done
fi
KEY_JSON="$(ibmcloud resource service-key "${PG_KEY}" --output json 2>/dev/null)"
if [ -z "${KEY_JSON}" ] || [ "${KEY_JSON}" = "[]" ]; then
  echo "    !! could not read service key '${PG_KEY}'. Create it manually and re-run:" >&2
  echo "       ibmcloud resource service-key-create ${PG_KEY} Administrator --instance-name ${PG_NAME}" >&2
  exit 1
fi
DB_URL="$(printf '%s' "${KEY_JSON}" | python3 -c "
import sys, json, urllib.parse
d = json.load(sys.stdin); d = d[0] if isinstance(d, list) else d
pg = d['credentials']['connection']['postgres']
host = pg['hosts'][0]; auth = pg['authentication']
u = urllib.parse.quote(auth['username'], safe=''); p = urllib.parse.quote(auth['password'], safe='')
# sslmode=require: TLS-encrypted (ICD mandates TLS) without needing the CA cert
# mounted. Upgrade to verify-full + a mounted CA later for cert verification.
print(f\"postgresql+psycopg://{u}:{p}@{host['hostname']}:{host['port']}/{pg['database']}?sslmode=require\")
")"
[ -n "${DB_URL}" ] || { echo "    !! could not build the connection string" >&2; exit 1; }
echo "    got connection string (host $(printf '%s' "${DB_URL}" | sed -E 's#.*@([^:/]+).*#\1#'))"

echo "==> [4/5] Storing it in Code Engine secret '${DB_SECRET}'"
ibmcloud ce project select --name "${CE_PROJECT}" >/dev/null
ibmcloud ce secret delete --name "${DB_SECRET}" --force >/dev/null 2>&1 || true
ibmcloud ce secret create --name "${DB_SECRET}" --from-literal "EPMW_DATABASE_URL=${DB_URL}"

echo "==> [5/5] Rebuilding + redeploying (Postgres + per-user isolation + login gate)"
EPMW_MULTI_USER="${EPMW_MULTI_USER:-true}" AUTH_SECRET="${AUTH_SECRET:-epmw-appid}" \
  REGISTRY_SECRET="${REGISTRY_SECRET:-epmw-icr}" ICR_APIKEY="${ICR_APIKEY}" \
  "${HERE}/deploy-code-engine-cloudbuild.sh"

echo
echo "==> Done. The backend now runs on managed PostgreSQL — per-user data"
echo "    persists across redeploys and restarts. First boot runs the schema"
echo "    migrations automatically."
