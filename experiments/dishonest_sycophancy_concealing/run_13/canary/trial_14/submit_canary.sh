#!/bin/bash
# Submit the Run 13 Canary Trial 14 mutable-challenge comparison.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
REPO="$(cd -- "${CANARY_DIR}/../../../.." && pwd -P)"

: "${AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT:?set this to the reviewed Trial 14 commit}"
: "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST:?set this to the external mode-600 Trial 14 recovery manifest}"
[[ "${AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "reviewed coordinator commit must be a full Git SHA" >&2
  exit 2
}
git -C "${REPO}" merge-base --is-ancestor \
  "${AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT}" HEAD || {
    echo "reviewed Trial 14 commit is not in this checkout" >&2
    exit 2
  }
if [ ! -f "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}" ] || \
    [ -L "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}" ]; then
  echo "Trial 14 recovery manifest must be an external regular file" >&2
  exit 2
fi
manifest_mode="$(stat -c '%a' -- "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}")"
manifest_owner="$(stat -c '%u' -- "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}")"
if [ "${manifest_mode}" != 600 ] || [ "${manifest_owner}" != "$(id -u)" ]; then
  echo "Trial 14 recovery manifest must be owned by this user with mode 0600" >&2
  exit 2
fi
grep -q 'trial4|trial5|trial6|trial7|trial8|trial9|trial10|trial11|trial12|trial13|trial14)' \
  "${CANARY_DIR}/launch/launch.sh" || {
    echo "Run 13 launcher lacks reviewed Trial 14 recovery support" >&2
    exit 2
  }

export AAR_RUN13_TRIAL_CONFIG="${SCRIPT_DIR}/autodata_run.yaml"
exec "${CANARY_DIR}/launch/launch.sh" "$@"
