#!/bin/bash
# Create or complete the exact Run 17 Claude/Gemma/Luna broker proof.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RUN17_DIR="$(cd -- "${SCRIPT_DIR}/../../.." && pwd -P)"
REPO="$(cd -- "${RUN17_DIR}/../../.." && pwd -P)"
SHARED_CANARY="${REPO}/experiments/dishonest_sycophancy_concealing/run_12/canary/canary_1/submit_target_canary.sh"

export AAR_EXPERIMENT_RUN_ID=run17
export AAR_RUN12_AUTODATA_CANARY_CONFIG="${RUN17_DIR}/config/run.yaml"
export AAR_RUN12_AUTODATA_PROFILE_CONFIG="${REPO}/configs/autodata/target_aware_model_api_claude_opus_4_8_c32_v1.yaml"
export AAR_AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/storage/home/${USER:?}/autodata-worktrees/judge-repair-28a9c22}"
export AAR_RUN12_TARGET_KIND=base
export AAR_RUN12_TARGET_DEPLOYMENT_ID="${AAR_RUN17_REUSE_BASE_DEPLOYMENT:-winnieyangwn-r12-alpha-i1-c0dab4f7}"

required_autodata_sha=28a9c22125dc0cf101ebabc1b22408b4e974678a
[ "$(git -C "${AAR_AUTODATA_CHECKOUT}" rev-parse HEAD)" = "${required_autodata_sha}" ] || {
  echo "Run 17 proof requires AutoData ${required_autodata_sha}" >&2
  exit 2
}
git -C "${AAR_AUTODATA_CHECKOUT}" diff --quiet && \
  git -C "${AAR_AUTODATA_CHECKOUT}" diff --cached --quiet || {
    echo "Run 17 proof requires a clean AutoData checkout" >&2
    exit 2
  }

exec "${SHARED_CANARY}" "$@"
