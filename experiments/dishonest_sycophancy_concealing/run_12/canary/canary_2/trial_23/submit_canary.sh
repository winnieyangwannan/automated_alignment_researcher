#!/bin/bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RUN12_DIR="$(cd -- "${SCRIPT_DIR}/../../.." && pwd -P)"
REPO="$(cd -- "${RUN12_DIR}/../../.." && pwd -P)"
RUN_CONFIG="$(realpath -e -- "${SCRIPT_DIR}/autodata_run.yaml")"
CANARY_PROOF_ROOT="/checkpoint/ram/${USER:?}/aar-runs/run12-adapter-target/20261011T221515Z-b6db78771f9c"

[[ "$(git -C "${REPO}" branch --show-current)" == autodata ]] || exit 2
[[ "${AAR_EXPERIMENT_RUN_ID:-run12}" == run12 ]] || exit 2
[[ "${AAR_RUN12_MODE:-bootstrap-canary}" == bootstrap-canary ]] || exit 2
[[ "${AAR_RUN12_SEEDS:-alpha}" == alpha ]] || exit 2
[[ "${AAR_RUN12_TARGET_PAIRS:-1}" == 1 ]] || exit 2
if [[ -n "${AAR_RUN12_AUTODATA_RUN_CONFIG:-}" ]] &&
   [[ "$(realpath -e -- "${AAR_RUN12_AUTODATA_RUN_CONFIG}")" != "${RUN_CONFIG}" ]]; then
  echo "Trial 23 rejects a conflicting run config" >&2
  exit 2
fi
if [[ -n "${AAR_RUN12_CANARY_ROOT:-}" ]] &&
   [[ "$(realpath -e -- "${AAR_RUN12_CANARY_ROOT}")" != "${CANARY_PROOF_ROOT}" ]]; then
  echo "Trial 23 rejects a conflicting canary proof root" >&2
  exit 2
fi
[[ "${AAR_RUN12_REUSE_BASE_DEPLOYMENT:-winnieyangwn-r12-alpha-i1-c0dab4f7}" == \
  winnieyangwn-r12-alpha-i1-c0dab4f7 ]] || exit 2

export AAR_EXPERIMENT_RUN_ID=run12
export AAR_RUN12_MODE=bootstrap-canary
export AAR_RUN12_SEEDS=alpha
export AAR_RUN12_AUTODATA_RUN_CONFIG="${RUN_CONFIG}"
export AAR_RUN12_TARGET_PAIRS=1
export AAR_RUN12_REUSE_BASE_DEPLOYMENT=winnieyangwn-r12-alpha-i1-c0dab4f7
export AAR_RUN12_CANARY_ROOT="${CANARY_PROOF_ROOT}"
export AAR_AUTODATA_CLARIFY_COORDINATOR=1
export AAR_AUTODATA_APPROVAL_COORDINATOR=1
export AAR_AUTODATA_SEMANTIC_WORKER=kimi
unset AAR_AUTODATA_GROUNDING_COORDINATOR
unset AAR_AUTODATA_PIPELINE_COORDINATOR
unset AAR_AUTODATA_ANALYSIS_COORDINATOR
unset AAR_AUTODATA_MUTATION_COORDINATOR
unset AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR
unset AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE

exec "${RUN12_DIR}/launch/submit_full.sh"
