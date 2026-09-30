#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_v0.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/scripts/aar_runtime_env.sh"
export AAR_EVAL_TIME=38:00:00
export AAR_EVAL_IDLE_SECONDS=136800
"${HARNESS_PY}" "${AAR_REPO}/replication/preflight_v0.py" --launch
bash "${AAR_REPO}/scripts/resume_team.sh" \
  "${AAR_TEAM_ID}" "alpha beta gamma delta epsilon" 500 36
