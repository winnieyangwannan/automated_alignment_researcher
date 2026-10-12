#!/bin/bash
# Submit Run 13 Canary Trial 2 through the shared fail-closed engine.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
export AAR_RUN13_TRIAL_CONFIG="${SCRIPT_DIR}/autodata_run.yaml"
exec "${CANARY_DIR}/launch/launch.sh" "$@"
