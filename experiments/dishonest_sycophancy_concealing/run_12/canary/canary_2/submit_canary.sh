#!/bin/bash
# Launch the production-only Run 12 canary from the shared production path.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN12_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

export AAR_RUN12_MODE=bootstrap-canary
export AAR_RUN12_SEEDS=alpha
export AAR_RUN12_AUTODATA_RUN_CONFIG="${SCRIPT_DIR}/autodata_run.yaml"
export AAR_RUN12_AUTODATA_PROFILE_CONFIG="${SCRIPT_DIR}/../../../../../configs/autodata/target_aware_local_c32_v1.yaml"
# The shared controller schema retains this field, but production-only canary
# success is determined solely by its verified production marker, not a pair.
export AAR_RUN12_TARGET_PAIRS=1

exec "${RUN12_DIR}/launch/submit_full.sh"
