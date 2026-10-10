#!/bin/bash
# Launch the five-chain topology check after an exact one-chain proof passes.
set -euo pipefail

[ "$#" -eq 1 ] || {
  echo "usage: $0 <one-chain-attempt>/metadata/canary_passed.json" >&2
  exit 2
}
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CHECK_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN10_DIR="$(cd -- "${CHECK_DIR}/../.." && pwd)"
export AAR_RUN_CONFIG="${CHECK_DIR}/config/run.yaml"

exec "${RUN10_DIR}/launch/submit_run_10.sh" smoke "$1"
