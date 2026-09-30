#!/bin/bash
# Launch one isolated AAR chain for exactly one research iteration.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_v0.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/scripts/aar_runtime_env.sh"

export AAR_TEAM_ID=sycophancy-gemma4_31b-opus48-canary-v0
export AAR_EVAL_TIME=06:00:00
export AAR_EVAL_IDLE_SECONDS=21600
"${HARNESS_PY}" "${AAR_REPO}/replication/preflight_v0.py" --canary

submission_log="${AAR_RUNTIME_ROOT}/metadata/launch_canary_submission.txt"
mkdir -p "$(dirname "${submission_log}")"
[ ! -e "${submission_log}" ] || {
  echo "refusing to overwrite ${submission_log}" >&2
  exit 2
}
bash "${AAR_REPO}/scripts/launch_team.sh" "canary" 1 5 | tee "${submission_log}"
"${HARNESS_PY}" "${AAR_REPO}/replication/record_manifest_v0.py" \
  --phase canary --submission-log "${submission_log}"
