#!/bin/bash
# Resume selected Run 10 chains in place without duplicating completed sessions.
set -euo pipefail
umask 077

ATTEMPT_DIR="$(realpath -e -- "${1:?usage: $0 <full-attempt-dir> [seeds]}")"
REQUESTED_SEEDS="${2:-alpha beta gamma delta epsilon}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
export MODE=full
SECRET_ENV="$(realpath -e -- "${AAR_RUN10_SECRET_ENV:-${REPO}/.env}")"
export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"

[ "$(git -C "${REPO}" branch --show-current)" = multi_kimi ] || {
  echo "Run 10 recovery requires branch multi_kimi" >&2; exit 2;
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2; exit 2
fi
submission="${ATTEMPT_DIR}/metadata/submission.txt"
children="${ATTEMPT_DIR}/metadata/children.env"
if [ ! -f "${submission}" ] || [ ! -f "${children}" ]; then
  echo "attempt is missing Run 10 launch metadata" >&2
  exit 2
fi
[ "$(sed -n 's/^mode=//p' "${submission}")" = full ] || {
  echo "target is not a full Run 10 attempt" >&2; exit 2;
}
original_commit="$(sed -n 's/^git_commit=//p' "${submission}")"
git -C "${REPO}" merge-base --is-ancestor "${original_commit}" HEAD || {
  echo "recovery source does not descend from original commit ${original_commit}" >&2
  exit 2
}

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/configure_run_10_environment.sh"
export AAR_PRETRAIN_SMOKE=1
export AAR_EVAL_WORKERS=5 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00 AAR_EVAL_IDLE_SECONDS=604200
export AAR_MAX_CONCURRENT_TRAIN_JOBS=5

mapfile -t teams < <(find "${ATTEMPT_DIR}/aar_teams" -mindepth 1 -maxdepth 1 -type d)
[ "${#teams[@]}" -eq 1 ] || { echo "expected exactly one Run 10 team" >&2; exit 2; }
TEAM_DIR="${teams[0]}"
TEAM_ID="$(basename -- "${teams[0]}")"
AAR_TEAM_ID="${TEAM_ID}"
export TEAM_DIR TEAM_ID AAR_TEAM_ID
export LOCAL_FINDINGS_DIR="${TEAM_DIR}/forum" SUBMISSIONS_DIR="${TEAM_DIR}/submissions"
export SCORES_DIR="${TEAM_DIR}/scores" AAR_IDEAS_DIR="${TEAM_DIR}/methods"
export SESSION_LOGS_DIR="${TEAM_DIR}/logs" LIT_FORUM_DIR="${TEAM_DIR}/litreview"

registry="${ATTEMPT_DIR}/metadata/recovery_jobs.tsv"
lock="${ATTEMPT_DIR}/metadata/recovery_jobs.lock"
exec 9>"${lock}"
flock -n 9 || { echo "another Run 10 recovery is already running" >&2; exit 2; }
touch "${registry}"

valid_seed() {
  case "$1" in alpha|beta|gamma|delta|epsilon) return 0;; *) return 1;; esac
}
job_active() {
  local state
  state="$(squeue -h -j "$1" -o '%T' 2>/dev/null | head -1)"
  [ -n "${state}" ]
}
seed_has_active_job() {
  local seed="$1" job
  read -r -a original_jobs <<< "$(sed -n 's/^research_chain_jobs=//p' "${children}")"
  read -r -a original_seeds <<< "$(sed -n 's/^research_seeds=//p' "${children}")"
  for index in "${!original_seeds[@]}"; do
    if [ "${original_seeds[$index]}" = "${seed}" ] && job_active "${original_jobs[$index]}"; then
      return 0
    fi
  done
  while IFS=$'\t' read -r _ kind recorded_seed job _; do
    if [ "${kind}" = chain ] && [ "${recorded_seed}" = "${seed}" ] && job_active "${job}"; then
      return 0
    fi
  done < "${registry}"
  return 1
}

max_sessions="$(sed -n 's/^max_iterations_per_chain=//p' "${children}")"
case "${max_sessions}" in ''|*[!0-9]*) echo "invalid original session budget" >&2; exit 2;; esac
declare -A started_by_seed=()
declare -A remaining_by_seed=()
resume_seed_count=0
for seed in ${REQUESTED_SEEDS}; do
  valid_seed "${seed}" || { echo "invalid Run 10 seed: ${seed}" >&2; exit 2; }
  if seed_has_active_job "${seed}"; then
    echo "refusing duplicate active chain for seed ${seed}" >&2
    exit 2
  fi
  started="$(find "${TEAM_DIR}/logs" -maxdepth 1 -type f -name "session_*_${seed}_*.log" | wc -l)"
  started_by_seed["${seed}"]="${started}"
  if [ "${started}" -ge "${max_sessions}" ]; then
    echo "[resume] ${seed}: ${started}/${max_sessions} sessions already started; nothing to resume"
    continue
  fi
  remaining_by_seed["${seed}"]=$((max_sessions - started))
  resume_seed_count=$((resume_seed_count + 1))
done
if [ "${resume_seed_count}" -eq 0 ]; then
  echo "[resume] no selected chain has remaining sessions"
  exit 0
fi

active_evaluators=0
read -r -a original_evaluators <<< "$(sed -n 's/^evaluator_jobs=//p' "${children}")"
for job in "${original_evaluators[@]}"; do
  job_active "${job}" && active_evaluators=$((active_evaluators + 1))
done
while IFS=$'\t' read -r _ kind _ job _; do
  if [ "${kind}" = evaluator ] && job_active "${job}"; then
    active_evaluators=$((active_evaluators + 1))
  fi
done < "${registry}"
if [ "${active_evaluators}" -lt 5 ]; then
  missing_evaluators=$((5 - active_evaluators))
  eval_log="${ATTEMPT_DIR}/metadata/recovery_eval_$(date -u +%Y%m%dT%H%M%SZ).txt"
  "${REPO}/scripts/launch_eval_worker.sh" "${SUITE_NAME}" "${AAR_EVAL_IDLE_SECONDS}" "${missing_evaluators}" | tee "${eval_log}"
  while read -r job; do
    [ -n "${job}" ] || continue
    printf '%s\tevaluator\t-\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${job}" "$(git -C "${REPO}" rev-parse HEAD)" >> "${registry}"
  done < <(awk '/^\[launch\] evaluator [0-9]+\/[0-9]+ -> job [0-9]+$/{print $NF}' "${eval_log}")
fi

resume_hours="${AAR_RUN10_RESUME_HOURS:-167}"
case "${resume_hours}" in ''|*[!0-9]*) echo "invalid recovery hours" >&2; exit 2;; esac

for seed in ${REQUESTED_SEEDS}; do
  [ -n "${remaining_by_seed[${seed}]:-}" ] || continue
  started="${started_by_seed[${seed}]}"
  remaining="${remaining_by_seed[${seed}]}"
  job="$(sbatch --parsable \
    --account="${AAR_SLURM_ACCOUNT}" --partition="${AAR_SLURM_PARTITION}" --qos="${AAR_AGENT_QOS}" \
    --time="${resume_hours}:30:00" \
    --job-name="aar-${SUITE_NAME}-${MODEL:-gemma4_31b}-${seed}-resume" \
    --output="${TEAM_DIR}/logs/%x_%j.out" \
    "${REPO}/scripts/slurm_aar_chain.sh" "explore-${seed}" "${resume_hours}" "${remaining}" "${TEAM_ID}")"
  job="${job%%;*}"
  [[ "${job}" =~ ^[0-9]+$ ]] || { echo "invalid chain job id for ${seed}: ${job}" >&2; exit 2; }
  printf '%s\tchain\t%s\t%s\t%s\tremaining=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${seed}" "${job}" \
    "$(git -C "${REPO}" rev-parse HEAD)" "${remaining}" >> "${registry}"
  echo "[resume] ${seed}: ${started}/${max_sessions} started, job ${job} receives ${remaining} remaining sessions"
done

echo "[resume] preserved attempt=${ATTEMPT_DIR} team=${TEAM_ID}"
