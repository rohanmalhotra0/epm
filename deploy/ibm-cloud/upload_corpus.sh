#!/usr/bin/env bash
# Upload one or more training-corpus JSONL files to the COS training bucket.
# Creates the bucket if it does not exist, uploads every file given as an
# argument, then lists the bucket so you can eyeball what is there.
#
# Prereqs:
#   - ibmcloud CLI, logged in (`ibmcloud login --sso` works fine)
#   - the cloud-object-storage plugin (`ibmcloud plugin install cloud-object-storage`)
#   - the COS instance CRN configured once: `ibmcloud cos config crn`
#     (find it with `ibmcloud resource service-instance epmw-cos`), or set
#     COS_CRN below to configure it non-interactively.
#
# Usage:
#   ./upload_corpus.sh data/training/synthetic.jsonl data/training/real.jsonl
#   BUCKET=epmw-training-data REGION=us-south ./upload_corpus.sh corpus.jsonl
#
# Env:
#   BUCKET   target bucket           (default: epmw-training-data — the terraform default)
#   REGION   bucket region           (default: us-south)
#   COS_CRN  COS instance CRN        (optional; if set, configured non-interactively)
#
# No secrets are read or printed by this script.

set -euo pipefail

BUCKET="${BUCKET:-epmw-training-data}"
REGION="${REGION:-us-south}"

die() { echo "ERROR: $*" >&2; exit 1; }

[ "$#" -ge 1 ] || die "no files given. Usage: $0 <file.jsonl> [more.jsonl ...]"

command -v ibmcloud >/dev/null 2>&1 \
  || die "ibmcloud CLI not found. Install it: https://cloud.ibm.com/docs/cli"

ibmcloud plugin show cloud-object-storage >/dev/null 2>&1 \
  || die "COS plugin missing. Run: ibmcloud plugin install cloud-object-storage"

for f in "$@"; do
  [ -f "$f" ] || die "file not found: $f"
done

if [ -n "${COS_CRN:-}" ]; then
  ibmcloud cos config crn --crn "${COS_CRN}" >/dev/null
fi

echo "==> Ensuring bucket ${BUCKET} exists (${REGION})"
if ! ibmcloud cos bucket-head --bucket "${BUCKET}" --region "${REGION}" >/dev/null 2>&1; then
  ibmcloud cos bucket-create --bucket "${BUCKET}" --region "${REGION}" --class smart
  echo "    created."
else
  echo "    already exists."
fi

for f in "$@"; do
  key="$(basename "$f")"
  echo "==> Uploading ${f} -> cos://${BUCKET}/${key}"
  ibmcloud cos upload --bucket "${BUCKET}" --region "${REGION}" --key "${key}" --file "$f"
done

echo "==> Bucket contents"
ibmcloud cos objects --bucket "${BUCKET}" --region "${REGION}"
