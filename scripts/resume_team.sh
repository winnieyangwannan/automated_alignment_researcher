#!/bin/bash
# Continue an existing team without archiving or resetting any state.
set -euo pipefail

TEAM_ID="${1:?usage: resume_team.sh <team_id> [seeds] [max_iters] [additional_hours]}"
SEEDS="${2:-alpha beta gamma delta epsilon}"
MAX_ITERS="${3:-500}"
MAX_H="${4:-36}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

TEAM_DIR="${AAR_TEAMS_DIR:-${AAR_RUNTIME_ROOT}/aar_teams}/${TEAM_ID}"
[ -d "${TEAM_DIR}" ] || { echo "[resume] missing team: ${TEAM_DIR}" >&2; exit 2; }
export TEAM_ID TEAM_DIR
export LOCAL_FINDINGS_DIR="${TEAM_DIR}/forum"
export SUBMISSIONS_DIR="${TEAM_DIR}/submissions"
export SCORES_DIR="${TEAM_DIR}/scores"
export AAR_IDEAS_DIR="${TEAM_DIR}/methods"
export SESSION_LOGS_DIR="${TEAM_DIR}/logs"
export LIT_FORUM_DIR="${TEAM_DIR}/litreview"

if [ "${AAR_START_EVAL_WORKER:-1}" = "1" ]; then
  [ -n "${HOLDOUT_DIR:-}" ] || { echo "[resume] HOLDOUT_DIR is required" >&2; exit 2; }
  "${REPO}/scripts/launch_eval_worker.sh" "${SUITE_NAME}" "${AAR_EVAL_IDLE_SECONDS:-14400}"
fi

for seed in ${SEEDS}; do
  jid="$(sbatch --parsable \
    --account="${AAR_SLURM_ACCOUNT}" --partition="${AAR_SLURM_PARTITION}" --qos="${AAR_AGENT_QOS}" \
    --time="${MAX_H}:30:00" \
    --job-name="aar-${SUITE_NAME}-${MODEL:-qwen}-${seed}-resume" \
    --output="${TEAM_DIR}/logs/%x_%j.out" \
    "${REPO}/scripts/slurm_aar_chain.sh" "explore-${seed}" "${MAX_H}" "${MAX_ITERS}" "${TEAM_ID}")"
  echo "[resume] chain ${seed} -> job ${jid}"
done
echo "[resume] TEAM_ID=${TEAM_ID}; preserved forum, methods, scores, and AGENT_LOG files"
