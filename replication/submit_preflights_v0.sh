#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_v0.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/scripts/aar_runtime_env.sh"
mkdir -p "${AAR_RUNTIME_ROOT}/logs"
include_web=0
case "${1:-}" in
  --include-web)
    include_web=1
    "${HARNESS_PY}" "${AAR_REPO}/replication/preflight_v0.py" \
      --require-claude-budget
    ;;
  --include-web-canary)
    include_web=1
    ;;
  '') ;;
  *) echo "usage: $0 [--include-web|--include-web-canary]" >&2; exit 2 ;;
esac
setup_jid="$(sbatch --parsable --output="${AAR_RUNTIME_ROOT}/logs/env-setup-%j.out" \
  "${AAR_REPO}/replication/setup_env_v0.sbatch")"
gpu_jid="$(sbatch --parsable --dependency="afterok:${setup_jid%%;*}" \
  --output="${AAR_RUNTIME_ROOT}/logs/gpu-preflight-%j.out" \
  "${AAR_REPO}/replication/gpu_preflight_v0.sbatch")"
eval_gpu_jid="$(sbatch --parsable --dependency="afterok:${setup_jid%%;*}" \
  --output="${AAR_RUNTIME_ROOT}/logs/eval-gpu-preflight-%j.out" \
  "${AAR_REPO}/replication/eval_gpu_preflight_v0.sbatch")"
printf 'env_setup=%s\ngpu_preflight=%s\neval_gpu_preflight=%s\n' \
  "${setup_jid}" "${gpu_jid}" "${eval_gpu_jid}"
if [ "${include_web}" = 1 ]; then
  web_jid="$(sbatch --parsable --dependency="afterok:${setup_jid%%;*}" \
    --output="${AAR_RUNTIME_ROOT}/logs/web-preflight-%j.out" \
    "${AAR_REPO}/replication/smoke_aar_internet_v0.sbatch")"
  printf 'web_preflight=%s\n' "${web_jid}"
fi
