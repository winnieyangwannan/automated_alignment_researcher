#!/bin/bash
# Launch Run 12 Canary 2 v2 through the shared immutable submitter.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RUN12_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
REPO="$(cd -- "${RUN12_DIR}/../../.." && pwd -P)"
RUN_CONFIG="$(realpath -e -- "${SCRIPT_DIR}/autodata_run.yaml")"

[[ "$(git -C "${REPO}" branch --show-current)" == autodata ]] || {
  echo "Canary 2 v2 requires branch autodata" >&2
  exit 2
}
[[ "${AAR_EXPERIMENT_RUN_ID:-run12}" == run12 ]] || {
  echo "Canary 2 v2 requires experiment run ID run12" >&2
  exit 2
}
[[ "${AAR_RUN12_MODE:-bootstrap-canary}" == bootstrap-canary ]] || {
  echo "Canary 2 v2 requires bootstrap-canary mode" >&2
  exit 2
}
[[ "${AAR_RUN12_SEEDS:-alpha}" == alpha ]] || {
  echo "Canary 2 v2 requires exactly seed alpha" >&2
  exit 2
}
[[ "${AAR_RUN12_TARGET_PAIRS:-1}" == 1 ]] || {
  echo "Canary 2 v2 requires exactly one target pair" >&2
  exit 2
}
if [[ -n "${AAR_RUN12_AUTODATA_RUN_CONFIG:-}" ]] &&
   [[ "$(realpath -e -- "${AAR_RUN12_AUTODATA_RUN_CONFIG}")" != "${RUN_CONFIG}" ]]; then
  echo "Canary 2 v2 rejects a conflicting run config" >&2
  exit 2
fi
[[ "${AAR_RUN12_REUSE_BASE_DEPLOYMENT:-winnieyangwn-r12-alpha-i1-c0dab4f7}" == \
  winnieyangwn-r12-alpha-i1-c0dab4f7 ]] || {
  echo "Canary 2 v2 requires the confirmed fixed target deployment" >&2
  exit 2
}

export AAR_EXPERIMENT_RUN_ID=run12
export AAR_RUN12_MODE=bootstrap-canary
export AAR_RUN12_SEEDS=alpha
export AAR_RUN12_AUTODATA_RUN_CONFIG="${RUN_CONFIG}"
export AAR_RUN12_TARGET_PAIRS=1
export AAR_RUN12_REUSE_BASE_DEPLOYMENT=winnieyangwn-r12-alpha-i1-c0dab4f7

exec "${RUN12_DIR}/launch/submit_full.sh"
