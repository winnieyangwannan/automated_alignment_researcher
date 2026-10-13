#!/bin/bash
# Submit the Run 14 v3 recipe mutable-challenge AutoData comparison.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
GATE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
CANARY_DIR="$(cd -- "${GATE_DIR}/../.." && pwd -P)"
REPO="$(cd -- "${CANARY_DIR}/../../../.." && pwd -P)"

: "${AAR_RUN14_LIFECYCLE_COORDINATOR_COMMIT:?set this to the reviewed Run 14 launcher commit}"
: "${AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST:?set this to the external mode-600 Run 14 recovery manifest}"
[[ "${AAR_RUN14_LIFECYCLE_COORDINATOR_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "reviewed coordinator commit must be a full Git SHA" >&2
  exit 2
}
git -C "${REPO}" merge-base --is-ancestor \
  "${AAR_RUN14_LIFECYCLE_COORDINATOR_COMMIT}" HEAD || {
    echo "reviewed Run 14 launcher commit is not in this checkout" >&2
    exit 2
  }
if [ ! -f "${AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST}" ] || \
    [ -L "${AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST}" ]; then
  echo "Run 14 recovery manifest must be an external regular file" >&2
  exit 2
fi
manifest_mode="$(stat -c '%a' -- "${AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST}")"
manifest_owner="$(stat -c '%u' -- "${AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST}")"
if [ "${manifest_mode}" != 600 ] || [ "${manifest_owner}" != "$(id -u)" ]; then
  echo "Run 14 recovery manifest must be owned by this user with mode 0600" >&2
  exit 2
fi

export AAR_RUN14_CANARY_CONFIG="${GATE_DIR}/config/run.yaml"
exec "${CANARY_DIR}/launch/launch.sh" "$@"
