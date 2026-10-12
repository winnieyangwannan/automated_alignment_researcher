#!/bin/bash
# Submit Run 13 Canary Trial 4 after the reviewed clarify-design coordinator lands.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
REPO="$(cd -- "${CANARY_DIR}/../../../.." && pwd -P)"

: "${AAR_RUN13_CLARIFY_COORDINATOR_COMMIT:?set this to the reviewed clarify_design coordinator commit}"
: "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST:?set this to the external mode-0600 Trial 4 recovery manifest}"
[[ "${AAR_RUN13_CLARIFY_COORDINATOR_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "clarify-design coordinator commit must be a full Git SHA" >&2
  exit 2
}
git -C "${REPO}" merge-base --is-ancestor \
  "${AAR_RUN13_CLARIFY_COORDINATOR_COMMIT}" HEAD || {
    echo "reviewed clarify-design coordinator commit is not in this checkout" >&2
    exit 2
  }
if [ ! -f "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}" ] || \
    [ -L "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}" ]; then
  echo "Trial 4 recovery manifest must be an external regular file" >&2
  exit 2
fi
manifest_mode="$(stat -c '%a' -- "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}")"
manifest_owner="$(stat -c '%u' -- "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}")"
if [ "${manifest_mode}" != 600 ] || [ "${manifest_owner}" != "$(id -u)" ]; then
  echo "Trial 4 recovery manifest must be owned by this user with mode 0600" >&2
  exit 2
fi
grep -q 'AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST' \
  "${CANARY_DIR}/launch/launch.sh" || {
    echo "Run 13 launcher lacks the reviewed pre-AutoData recovery import seam" >&2
    exit 2
  }

export AAR_RUN13_TRIAL_CONFIG="${SCRIPT_DIR}/autodata_run.yaml"
exec "${CANARY_DIR}/launch/launch.sh" "$@"
