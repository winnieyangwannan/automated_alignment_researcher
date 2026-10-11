#!/bin/bash
# Launch Run 12 Canary 2 Trial 5 from the shared production path.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN12_DIR="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"

export AAR_RUN12_MODE=bootstrap-canary
export AAR_RUN12_SEEDS=alpha
export AAR_RUN12_AUTODATA_RUN_CONFIG="${SCRIPT_DIR}/autodata_run.yaml"
export AAR_RUN12_TARGET_PAIRS=1

exec "${RUN12_DIR}/launch/submit_full.sh"
