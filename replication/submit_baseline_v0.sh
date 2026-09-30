#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_v0.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/scripts/aar_runtime_env.sh"
case "${1:-}" in
  --canary)
    "${HARNESS_PY}" "${AAR_REPO}/replication/preflight_v0.py" --baseline-canary
    ;;
  '')
    "${HARNESS_PY}" "${AAR_REPO}/replication/preflight_v0.py" \
      --require-openai-budget
    ;;
  *)
    echo "usage: $0 [--canary]" >&2
    exit 2
    ;;
esac
BASE_INPUT="${AAR_RUNTIME_ROOT}/baseline_input"
if [ -e "${BASE_INPUT}/sycophancy" ]; then
  echo "refusing to overwrite retained baseline input: ${BASE_INPUT}/sycophancy" >&2
  exit 2
fi
mkdir -p "${AAR_RUNTIME_ROOT}/logs"
(unset AAR_BASELINE_OVERRIDES; "${HARNESS_PY}" "${AAR_REPO}/scripts/publish_suite.py" \
  --suite sycophancy --target-model google/gemma-4-31B-it \
  --holdout-dir "${BASE_INPUT}" --only sycophancy_eval sycon_fp mmlu gsm8k ifeval)
sbatch --parsable --output="${AAR_RUNTIME_ROOT}/logs/baseline-%j.out" \
  "${AAR_REPO}/replication/baseline_v0.sbatch"
