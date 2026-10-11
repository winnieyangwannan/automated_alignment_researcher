#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN14_DIR="$(cd -- "${CANARY_DIR}/../.." && pwd)"
export AAR_RUN14_MODE=canary
export AAR_RUN_CONFIG="${CANARY_DIR}/config/run.yaml"
exec "${RUN14_DIR}/launch/submit_full.sh"
