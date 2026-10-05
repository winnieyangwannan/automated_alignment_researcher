#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/scripts/aar_runtime_env.sh"
[ "${1:-}" = --include-web ] || { echo "usage: $0 --include-web" >&2; exit 2; }
"${HARNESS_PY}" "${AAR_REPO}/replication/preflight_multidimensional.py" \
  --validate-artifacts-only --require-claude-budget
mkdir -p "${AAR_RUNTIME_ROOT}/logs"
setup_jid="$(sbatch --parsable --output="${AAR_RUNTIME_ROOT}/logs/env-setup-%j.out" \
  "${AAR_REPO}/replication/setup_env_multidimensional.sbatch")"
gpu_jid="$(sbatch --parsable --dependency="afterok:${setup_jid%%;*}" \
  --output="${AAR_RUNTIME_ROOT}/logs/gpu-preflight-%j.out" \
  "${AAR_REPO}/replication/gpu_preflight_multidimensional.sbatch")"
eval_gpu_jid="$(sbatch --parsable --dependency="afterok:${setup_jid%%;*}" \
  --output="${AAR_RUNTIME_ROOT}/logs/eval-gpu-preflight-%j.out" \
  "${AAR_REPO}/replication/eval_gpu_preflight_multidimensional.sbatch")"
web_jid="$(sbatch --parsable --dependency="afterok:${setup_jid%%;*}" \
  --output="${AAR_RUNTIME_ROOT}/logs/web-preflight-%j.out" \
  "${AAR_REPO}/replication/smoke_aar_internet_multidimensional.sbatch")"
printf 'env_setup=%s\ngpu_preflight=%s\neval_gpu_preflight=%s\nweb_preflight=%s\n' \
  "${setup_jid}" "${gpu_jid}" "${eval_gpu_jid}" "${web_jid}"
