#!/bin/bash
# Launch the five-chain topology check after an exact one-chain proof passes.
set -euo pipefail

[ "$#" -eq 1 ] || {
  echo "usage: $0 <one-chain-attempt>/metadata/canary_passed.json" >&2
  exit 2
}
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN16_DIR="$(cd -- "${CANARY_DIR}/../.." && pwd)"
export AAR_RUN16_MODE=canary
export AAR_RUN_CONFIG="${CANARY_DIR}/config/run.yaml"
AAR_RUN16_PREREQUISITE_PROOF="$(realpath -e -- "$1")"
export AAR_RUN16_PREREQUISITE_PROOF
exec "${RUN16_DIR}/launch/submit_full.sh"
