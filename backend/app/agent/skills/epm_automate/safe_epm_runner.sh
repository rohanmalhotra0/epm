#!/usr/bin/env bash
# Secure EPM Automate runner template (Linux / macOS).
# - Credentials come from an encrypted .epw file, never plaintext.
# - Stops on failure, logs stdout/stderr, always attempts logout.
# - Never echoes secrets (set +x before authentication).
set -Eeuo pipefail
set +x

EPM_BIN="${EPM_BIN:-$HOME/epmautomate/bin/epmautomate.sh}"
EPM_USER="${EPM_USER:?Set EPM_USER}"
EPM_PASSWORD_FILE="${EPM_PASSWORD_FILE:?Set EPM_PASSWORD_FILE (path to encrypted .epw)}"
EPM_URL="${EPM_URL:?Set EPM_URL}"
LOG_DIR="${LOG_DIR:-$PWD/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/epm_$(date +%Y%m%d_%H%M%S).log"
LOGGED_IN=0

cleanup() {
  local status=$?
  if [[ "$LOGGED_IN" -eq 1 ]]; then
    "$EPM_BIN" logout >>"$LOG_FILE" 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT

echo "Target environment: $EPM_URL" | tee -a "$LOG_FILE"
"$EPM_BIN" login "$EPM_USER" "$EPM_PASSWORD_FILE" "$EPM_URL" >>"$LOG_FILE" 2>&1
LOGGED_IN=1

# ---------------------------------------------------------------------------
# Add validated commands below. Example (upload + Data Integration):
#
#   "$EPM_BIN" listFiles >>"$LOG_FILE" 2>&1
#   "$EPM_BIN" uploadFile "<LOCAL_FILE>" inbox >>"$LOG_FILE" 2>&1
#   "$EPM_BIN" runIntegration "<INTEGRATION_NAME>" importMode=Replace exportMode=Merge \
#       periodName="{Jan#FY26}" inputFileName="<FILE_NAME>" >>"$LOG_FILE" 2>&1
# ---------------------------------------------------------------------------
