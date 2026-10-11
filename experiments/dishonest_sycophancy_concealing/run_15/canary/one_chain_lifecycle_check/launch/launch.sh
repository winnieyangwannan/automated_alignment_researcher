#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN15_DIR="$(cd -- "${CANARY_DIR}/../.." && pwd)"
export AAR_RUN15_MODE=canary
export AAR_RUN_CONFIG="${CANARY_DIR}/config/run.yaml"
exec "${RUN15_DIR}/launch/submit_full.sh"
