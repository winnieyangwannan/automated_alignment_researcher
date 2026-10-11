#!/bin/bash
# Launch the Run 16 one-chain gate through the shared production path.
set -euo pipefail
umask 077

[ "$#" -eq 0 ] || { echo "usage: $0" >&2; exit 2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
RUN16_DIR="$(cd -- "${CANARY_DIR}/../.." && pwd -P)"
export AAR_RUN16_MODE=canary
export AAR_RUN_CONFIG="${CANARY_DIR}/config/run.yaml"
exec "${RUN16_DIR}/launch/submit_full.sh"
