#!/bin/bash
# Launch Run 17 Canary 2 through the shared, source-pinned Run 12 AutoData engine.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RUN17_DIR="$(cd -- "${SCRIPT_DIR}/../../.." && pwd -P)"
REPO="$(cd -- "${RUN17_DIR}/../../.." && pwd -P)"
RUN12_DIR="${REPO}/experiments/dishonest_sycophancy_concealing/run_12"

: "${AAR_RUN17_CANARY_ROOT:?set AAR_RUN17_CANARY_ROOT to the retained Claude/target broker proof root}"

export AAR_EXPERIMENT_RUN_ID=run17
export AAR_RUN12_MODE=bootstrap-canary
export AAR_RUN12_SEEDS=alpha
export AAR_RUN12_TARGET_PAIRS=1
export AAR_RUN12_AUTODATA_RUN_CONFIG="${RUN17_DIR}/config/run.yaml"
export AAR_RUN12_CANARY_ROOT="${AAR_RUN17_CANARY_ROOT}"
export AAR_RUN12_REUSE_BASE_DEPLOYMENT="${AAR_RUN17_REUSE_BASE_DEPLOYMENT:-winnieyangwn-r12-alpha-i1-c0dab4f7}"

exec "${RUN12_DIR}/launch/submit_full.sh"
