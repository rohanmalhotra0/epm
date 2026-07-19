#!/usr/bin/env bash
# End-to-end QLoRA run on a fresh GPU VSI (Path B — see docs/TRAINING.md §6):
#   venv + deps -> pull corpus from COS -> train_qlora.py -> upload results.
#
# Run ON the GPU instance (ssh in via its floating/private IP). Prereqs there:
#   - NVIDIA driver + CUDA (install first on a minimal Ubuntu image:
#     `sudo apt-get install -y nvidia-driver-550 nvidia-utils-550` + reboot,
#     or start from a GPU-ready image)
#   - python3-venv, and the ibmcloud CLI with the cloud-object-storage plugin,
#     logged in (`ibmcloud login --apikey @/path/to/keyfile`) with the COS
#     instance CRN configured (`ibmcloud cos config crn`).
#
# Usage:
#   BUCKET=epmw-training-data \
#   TRAIN_KEY=corpus.jsonl VAL_KEY=corpus.val.jsonl \
#   ./run_training.sh [extra train_qlora.py args, e.g. --epochs 4]
#
# Env:
#   BUCKET      COS bucket with the corpus       (default: epmw-training-data)
#   REGION      bucket region                    (default: us-south)
#   TRAIN_KEY   chat-format train JSONL key      (default: corpus.jsonl)
#   VAL_KEY     chat-format val JSONL key        (optional; skip eval if unset)
#   RUN_NAME    output prefix in COS + on disk   (default: epmw-qlora-<date>)
#   MERGE       "true" to merge adapters for serving/import (default: true)
#
# The instance costs money by the hour — destroy it as soon as the artifacts
# are back in COS (terraform apply -var enable_gpu_training=false).

set -euo pipefail

BUCKET="${BUCKET:-epmw-training-data}"
REGION="${REGION:-us-south}"
TRAIN_KEY="${TRAIN_KEY:-corpus.jsonl}"
VAL_KEY="${VAL_KEY:-}"
RUN_NAME="${RUN_NAME:-epmw-qlora-$(date +%Y%m%d-%H%M)}"
MERGE="${MERGE:-true}"

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${HOME}/epmw-training/${RUN_NAME}"
mkdir -p "${WORK}/data" "${WORK}/out"

die() { echo "ERROR: $*" >&2; exit 1; }
command -v ibmcloud >/dev/null 2>&1 || die "ibmcloud CLI not found on this instance"
ibmcloud plugin show cloud-object-storage >/dev/null 2>&1 \
  || die "COS plugin missing: ibmcloud plugin install cloud-object-storage"
command -v nvidia-smi >/dev/null 2>&1 || die "nvidia-smi not found — install the NVIDIA driver first"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

echo "==> Python venv + training deps (first run takes a few minutes)"
if [ ! -d "${HOME}/epmw-training/venv" ]; then
  python3 -m venv "${HOME}/epmw-training/venv"
fi
# shellcheck disable=SC1091
source "${HOME}/epmw-training/venv/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r "${HERE}/requirements.txt"

echo "==> Pulling corpus from cos://${BUCKET}"
ibmcloud cos download --bucket "${BUCKET}" --region "${REGION}" \
  --key "${TRAIN_KEY}" "${WORK}/data/train.jsonl"
VAL_ARGS=()
if [ -n "${VAL_KEY}" ]; then
  ibmcloud cos download --bucket "${BUCKET}" --region "${REGION}" \
    --key "${VAL_KEY}" "${WORK}/data/val.jsonl"
  VAL_ARGS=(--val-file "${WORK}/data/val.jsonl")
fi

MERGE_ARGS=()
[ "${MERGE}" = "true" ] && MERGE_ARGS=(--merge)

echo "==> Training (${RUN_NAME})"
python "${HERE}/train_qlora.py" \
  --train-file "${WORK}/data/train.jsonl" \
  "${VAL_ARGS[@]}" \
  --output-dir "${WORK}/out" \
  "${MERGE_ARGS[@]}" \
  "$@"

echo "==> Uploading artifacts back to cos://${BUCKET}/${RUN_NAME}/"
tar -C "${WORK}/out" -czf "${WORK}/adapter.tar.gz" adapter
ibmcloud cos upload --bucket "${BUCKET}" --region "${REGION}" \
  --key "${RUN_NAME}/adapter.tar.gz" --file "${WORK}/adapter.tar.gz"
if [ -d "${WORK}/out/merged" ]; then
  tar -C "${WORK}/out" -czf "${WORK}/merged.tar.gz" merged
  ibmcloud cos upload --bucket "${BUCKET}" --region "${REGION}" \
    --key "${RUN_NAME}/merged.tar.gz" --file "${WORK}/merged.tar.gz"
fi
[ -f "${WORK}/out/metrics.json" ] && ibmcloud cos upload --bucket "${BUCKET}" \
  --region "${REGION}" --key "${RUN_NAME}/metrics.json" --file "${WORK}/out/metrics.json"

cat <<EOF

==> Done. Artifacts in cos://${BUCKET}/${RUN_NAME}/
Next steps:
  * Serve here (OpenAI-compatible):   ./serve_openai_compat.sh ${WORK}/out/merged
  * ...or import the merged model into watsonx.ai as a custom foundation model
    (docs/TRAINING.md section 6).
  * Run the bake-off against it before shipping (docs/TRAINING.md section 5).
  * DESTROY THIS INSTANCE when finished — it bills hourly:
      terraform apply -var enable_gpu_training=false
EOF
