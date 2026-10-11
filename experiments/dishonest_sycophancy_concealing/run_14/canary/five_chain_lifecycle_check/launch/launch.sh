#!/bin/bash
# Launch the five-chain topology check after an exact one-chain proof passes.
set -euo pipefail

[ "$#" -eq 1 ] || {
  echo "usage: $0 <one-chain-attempt>/metadata/canary_passed.json" >&2
  exit 2
}
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN14_DIR="$(cd -- "${CANARY_DIR}/../.." && pwd)"
export AAR_RUN14_MODE=canary
export AAR_RUN_CONFIG="${CANARY_DIR}/config/run.yaml"
AAR_RUN14_PREREQUISITE_PROOF="$(realpath -e -- "$1")"
export AAR_RUN14_PREREQUISITE_PROOF
exec "${RUN14_DIR}/launch/submit_full.sh"
