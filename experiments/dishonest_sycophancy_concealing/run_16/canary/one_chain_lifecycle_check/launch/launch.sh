#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN16_DIR="$(cd -- "${CANARY_DIR}/../.." && pwd)"
export AAR_RUN16_MODE=canary
export AAR_RUN_CONFIG="${CANARY_DIR}/config/run.yaml"
exec "${RUN16_DIR}/launch/submit_full.sh"
