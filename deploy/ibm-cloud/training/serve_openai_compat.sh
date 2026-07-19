#!/usr/bin/env bash
# Serve the merged fine-tuned model on this GPU VSI with vLLM's
# OpenAI-compatible server, bound to 0.0.0.0:8080.
#
# Usage (on the GPU instance, after run_training.sh with MERGE=true):
#   ./serve_openai_compat.sh ~/epmw-training/<run>/out/merged [served-model-name]
#
# -----------------------------------------------------------------------------
# Wiring it into EPM Wizard
# -----------------------------------------------------------------------------
# In EPM Wizard: Settings -> AI Providers -> Add provider:
#   * Type:       generic (OpenAI-compatible)
#   * Base URL:   http://<VSI-private-IP>:8080/v1
#                 (the private IP is the terraform output `gpu_training_ip`;
#                 the backend reaches it inside the VPC — do NOT give the VSI
#                 a public/floating IP for serving)
#   * API key:    anything non-empty (vLLM does not check it by default)
#   * Model:      the served-model-name below (default: epmw-granite-tuned)
#
# Note the Code Engine backend must be able to reach the VPC subnet for this
# to work; if the backend runs outside the VPC, import the merged model into
# watsonx.ai as a custom foundation model instead (docs/TRAINING.md section 6).
#
# Serving keeps the hourly GPU meter running. For anything longer than a
# bake-off / demo, prefer the watsonx.ai import and destroy this instance.
# -----------------------------------------------------------------------------

set -euo pipefail

MODEL_DIR="${1:?usage: $0 <merged-model-dir> [served-model-name]}"
SERVED_NAME="${2:-epmw-granite-tuned}"
PORT="${PORT:-8080}"

[ -d "${MODEL_DIR}" ] || { echo "ERROR: model dir not found: ${MODEL_DIR}" >&2; exit 1; }

# vLLM has its own (heavy) dependency tree — keep it in a separate venv from
# the training one.
if [ ! -d "${HOME}/epmw-training/vllm-venv" ]; then
  python3 -m venv "${HOME}/epmw-training/vllm-venv"
fi
# shellcheck disable=SC1091
source "${HOME}/epmw-training/vllm-venv/bin/activate"
pip install --upgrade pip >/dev/null
pip install "vllm>=0.5,<1"

echo "==> Serving ${MODEL_DIR} as '${SERVED_NAME}' on 0.0.0.0:${PORT} (OpenAI-compatible)"
echo "    Endpoint for EPM Wizard: http://$(hostname -I | awk '{print $1}'):${PORT}/v1"
exec python -m vllm.entrypoints.openai.api_server \
  --model "${MODEL_DIR}" \
  --served-model-name "${SERVED_NAME}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --max-model-len "${MAX_MODEL_LEN:-4096}"
