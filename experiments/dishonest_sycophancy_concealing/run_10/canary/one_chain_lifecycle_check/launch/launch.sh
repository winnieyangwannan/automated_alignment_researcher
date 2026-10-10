#!/bin/bash
# Launch the bounded one-chain lifecycle check through Run 10's shared engine.
set -euo pipefail

[ "$#" -eq 0 ] || { echo "usage: $0" >&2; exit 2; }
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CHECK_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN10_DIR="$(cd -- "${CHECK_DIR}/../.." && pwd)"
export AAR_RUN_CONFIG="${CHECK_DIR}/config/run.yaml"

exec "${RUN10_DIR}/launch/submit_run_10.sh" smoke
