#!/bin/bash
# Create or complete the exact Run 14 Opus 5/Gemma/Luna provider proof.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
GATE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
REPO="$(cd -- "${GATE_DIR}/../../../../.." && pwd -P)"
SHARED_CANARY="${REPO}/experiments/dishonest_sycophancy_concealing/run_12/canary/canary_1/submit_target_canary.sh"

export AAR_EXPERIMENT_RUN_ID=run14
export AAR_RUN12_AUTODATA_CANARY_CONFIG="${GATE_DIR}/config/run.yaml"
export AAR_RUN12_AUTODATA_PROFILE_CONFIG="${REPO}/configs/autodata/target_aware_model_api_claude_opus_5_c8_v1.yaml"
export AAR_AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/checkpoint/ram/${USER:?}/source-worktrees/autodata-f53bc21}"
export AAR_RUN12_TARGET_KIND=base
export AAR_RUN12_TARGET_DEPLOYMENT_ID="${AAR_RUN14_REUSE_BASE_DEPLOYMENT:-winnieyangwn-r12-alpha-i1-c0dab4f7}"
export AAR_RUN12_SECRET_ENV="${AAR_RUN14_SECRET_ENV:-/storage/home/${USER}/aar-worktrees/autodata/.env}"

required_autodata_sha=f53bc2136905461ffdbba0a203a12e351e184aaf
[ "$(git -C "${AAR_AUTODATA_CHECKOUT}" rev-parse HEAD)" = "${required_autodata_sha}" ] || {
  echo "Run 14 proof requires AutoData ${required_autodata_sha}" >&2
  exit 2
}
if ! git -C "${AAR_AUTODATA_CHECKOUT}" diff --quiet || \
    ! git -C "${AAR_AUTODATA_CHECKOUT}" diff --cached --quiet; then
    echo "Run 14 proof requires a clean AutoData checkout" >&2
    exit 2
fi

exec "${SHARED_CANARY}" "$@"
