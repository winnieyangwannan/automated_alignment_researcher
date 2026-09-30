#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_v0.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/scripts/aar_runtime_env.sh"
mkdir -p "${AAR_RUNTIME_ROOT}/logs"
"${HARNESS_PY}" "${AAR_REPO}/replication/preflight_v0.py"
gpu_jid="$(sbatch --parsable --output="${AAR_RUNTIME_ROOT}/logs/gpu-preflight-%j.out" \
  "${AAR_REPO}/replication/gpu_preflight_v0.sbatch")"
web_jid="$(sbatch --parsable --output="${AAR_RUNTIME_ROOT}/logs/web-preflight-%j.out" \
  "${AAR_REPO}/replication/smoke_aar_internet_v0.sbatch")"
printf 'gpu_preflight=%s\nweb_preflight=%s\n' "${gpu_jid}" "${web_jid}"
