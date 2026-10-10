#!/bin/bash
# Resume selected chains in an existing AAR team without resetting artifacts.
# Experiment wrappers configure the normal runtime first, then set:
#   AAR_RESUME_DEFAULT_SEEDS, AAR_RESUME_EVALUATOR_COUNT, AAR_RESUME_HOURS
# Optional policy: AAR_RESUME_ALLOWED_SEEDS, AAR_RESUME_EXPECTED_BRANCH,
# AAR_RESUME_EXPECTED_MODE, and AAR_RESUME_JOB_PREFIX.

set -euo pipefail
umask 077

ATTEMPT_DIR="$(realpath -e -- "${1:?usage: $0 <attempt-dir> [\"seed ...\"]}")"
REQUESTED_SEEDS="${2:-${AAR_RESUME_DEFAULT_SEEDS:-}}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
else
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
fi
export AAR_REPO="${REPO}"

: "${SUITE_NAME:?source the experiment runtime configuration before resuming}"
: "${AAR_RESUME_EVALUATOR_COUNT:?set the desired evaluator job count}"
: "${AAR_RESUME_HOURS:?set replacement-chain wall-clock hours}"
case "${AAR_RESUME_EVALUATOR_COUNT}" in
  ''|*[!0-9]*) echo "invalid desired evaluator count" >&2; exit 2;;
esac
case "${AAR_RESUME_HOURS}" in
  ''|0|*[!0-9]*) echo "invalid recovery hours" >&2; exit 2;;
esac
read -r -a requested_seeds <<< "${REQUESTED_SEEDS}"
[ "${#requested_seeds[@]}" -gt 0 ] || { echo "no recovery seeds requested" >&2; exit 2; }
read -r -a allowed_seeds <<< "${AAR_RESUME_ALLOWED_SEEDS:-}"

current_branch="$(git -C "${REPO}" branch --show-current)"
if [ -n "${AAR_RESUME_EXPECTED_BRANCH:-}" ] && \
   [ "${current_branch}" != "${AAR_RESUME_EXPECTED_BRANCH}" ]; then
  echo "recovery requires branch ${AAR_RESUME_EXPECTED_BRANCH}; found ${current_branch}" >&2
  exit 2
fi
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi

submission="${ATTEMPT_DIR}/metadata/submission.txt"
children="${ATTEMPT_DIR}/metadata/children.env"
if [ ! -f "${submission}" ] || [ ! -f "${children}" ]; then
  echo "attempt is missing launch metadata" >&2
  exit 2
fi
recorded_mode="$(sed -n 's/^mode=//p' "${submission}")"
if [ -n "${AAR_RESUME_EXPECTED_MODE:-}" ] && \
   [ "${recorded_mode}" != "${AAR_RESUME_EXPECTED_MODE}" ]; then
  echo "target mode is ${recorded_mode:-missing}, expected ${AAR_RESUME_EXPECTED_MODE}" >&2
  exit 2
fi
original_commit="$(sed -n 's/^git_commit=//p' "${submission}")"
[ -n "${original_commit}" ] || { echo "submission metadata has no git commit" >&2; exit 2; }
git -C "${REPO}" merge-base --is-ancestor "${original_commit}" HEAD || {
  echo "recovery source does not descend from original commit ${original_commit}" >&2
  exit 2
}

mapfile -t teams < <(find "${ATTEMPT_DIR}/aar_teams" -mindepth 1 -maxdepth 1 -type d)
[ "${#teams[@]}" -eq 1 ] || { echo "expected exactly one AAR team" >&2; exit 2; }
TEAM_DIR="${teams[0]}"
TEAM_ID="$(basename -- "${TEAM_DIR}")"
AAR_TEAM_ID="${TEAM_ID}"
export TEAM_DIR TEAM_ID AAR_TEAM_ID
export LOCAL_FINDINGS_DIR="${TEAM_DIR}/forum" SUBMISSIONS_DIR="${TEAM_DIR}/submissions"
export SCORES_DIR="${TEAM_DIR}/scores" AAR_IDEAS_DIR="${TEAM_DIR}/methods"
export SESSION_LOGS_DIR="${TEAM_DIR}/logs" LIT_FORUM_DIR="${TEAM_DIR}/litreview"
mkdir -p "${TEAM_DIR}/logs" "${ATTEMPT_DIR}/metadata"

registry="${ATTEMPT_DIR}/metadata/recovery_jobs.tsv"
lock="${ATTEMPT_DIR}/metadata/recovery_jobs.lock"
exec 9>"${lock}"
flock -n 9 || { echo "another recovery is already running for this attempt" >&2; exit 2; }
touch "${registry}"

valid_seed() {
  local candidate="$1" allowed
  [[ "${candidate}" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
  [ "${#allowed_seeds[@]}" -eq 0 ] && return 0
  for allowed in "${allowed_seeds[@]}"; do
    [ "${candidate}" = "${allowed}" ] && return 0
  done
  return 1
}

job_active() {
  local job="$1" state
  [[ "${job}" =~ ^[0-9]+$ ]] || return 1
  state="$(squeue -h -j "${job}" -o '%T' 2>/dev/null | head -1)"
  [ -n "${state}" ]
}

read -r -a original_jobs <<< "$(sed -n 's/^research_chain_jobs=//p' "${children}")"
read -r -a original_seeds <<< "$(sed -n 's/^research_seeds=//p' "${children}")"
[ "${#original_jobs[@]}" -eq "${#original_seeds[@]}" ] || {
  echo "launch metadata has mismatched research seeds and job IDs" >&2
  exit 2
}

seed_has_active_job() {
  local seed="$1" index _timestamp kind recorded_seed job _rest
  for index in "${!original_seeds[@]}"; do
    if [ "${original_seeds[$index]}" = "${seed}" ] && \
       job_active "${original_jobs[$index]}"; then
      return 0
    fi
  done
  while IFS=$'\t' read -r _timestamp kind recorded_seed job _rest; do
    if [ "${kind}" = chain ] && [ "${recorded_seed}" = "${seed}" ] && job_active "${job}"; then
      return 0
    fi
  done < "${registry}"
  return 1
}

max_sessions="$(sed -n 's/^max_iterations_per_chain=//p' "${children}")"
case "${max_sessions}" in
  ''|*[!0-9]*) echo "invalid original session budget" >&2; exit 2;;
esac
declare -A started_by_seed=()
declare -A remaining_by_seed=()
resume_seed_count=0
for seed in "${requested_seeds[@]}"; do
  valid_seed "${seed}" || { echo "invalid or disallowed recovery seed: ${seed}" >&2; exit 2; }
  if seed_has_active_job "${seed}"; then
    echo "refusing duplicate active chain for seed ${seed}" >&2
    exit 2
  fi
  started="$(find "${TEAM_DIR}/logs" -maxdepth 1 -type f -name "session_*_${seed}_*.log" -print | wc -l | tr -d ' ')"
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

declare -A active_evaluator_jobs=()
read -r -a original_evaluators <<< "$(sed -n 's/^evaluator_jobs=//p' "${children}")"
for job in "${original_evaluators[@]}"; do
  if job_active "${job}"; then active_evaluator_jobs["${job}"]=1; fi
done
while IFS=$'\t' read -r _timestamp kind _recorded_seed job _rest; do
  if [ "${kind}" = evaluator ] && job_active "${job}"; then
    active_evaluator_jobs["${job}"]=1
  fi
done < "${registry}"
active_evaluators="${#active_evaluator_jobs[@]}"
if [ "${active_evaluators}" -lt "${AAR_RESUME_EVALUATOR_COUNT}" ]; then
  missing_evaluators=$((AAR_RESUME_EVALUATOR_COUNT - active_evaluators))
  eval_log="${ATTEMPT_DIR}/metadata/recovery_eval_$(date -u +%Y%m%dT%H%M%SZ)_$$.txt"
  "${REPO}/scripts/launch_eval_worker.sh" \
    "${SUITE_NAME}" "${AAR_EVAL_IDLE_SECONDS:?missing evaluator idle timeout}" \
    "${missing_evaluators}" | tee "${eval_log}"
  mapfile -t launched_evaluators < <(
    awk '/^\[launch\] evaluator [0-9]+\/[0-9]+ -> job [0-9]+$/{print $NF}' "${eval_log}"
  )
  recovery_commit="$(git -C "${REPO}" rev-parse HEAD)"
  for job in "${launched_evaluators[@]}"; do
    [[ "${job}" =~ ^[0-9]+$ ]] || continue
    printf '%s\tevaluator\t-\t%s\t%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${job}" "${recovery_commit}" >> "${registry}"
  done
  [ "${#launched_evaluators[@]}" -eq "${missing_evaluators}" ] || {
    echo "expected ${missing_evaluators} replacement evaluator IDs, got ${#launched_evaluators[@]}" >&2
    exit 2
  }
fi

if [ -n "${AAR_RESUME_JOB_PREFIX:-}" ]; then
  job_prefix="${AAR_RESUME_JOB_PREFIX}"
else
  job_prefix="$(printf 'aar-%s-%s' "${SUITE_NAME}" "${MODEL:-model}" | tr -c 'A-Za-z0-9._-' '_')"
fi
[[ "${job_prefix}" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "unsafe recovery job prefix" >&2; exit 2; }
recovery_commit="$(git -C "${REPO}" rev-parse HEAD)"

for seed in "${requested_seeds[@]}"; do
  [ -n "${remaining_by_seed[${seed}]:-}" ] || continue
  started="${started_by_seed[${seed}]}"
  remaining="${remaining_by_seed[${seed}]}"
  job="$(sbatch --parsable \
    --account="${AAR_SLURM_ACCOUNT:?missing Slurm account}" \
    --partition="${AAR_SLURM_PARTITION:?missing Slurm partition}" \
    --qos="${AAR_AGENT_QOS:?missing agent QoS}" \
    --time="${AAR_RESUME_HOURS}:30:00" \
    --job-name="${job_prefix}-${seed}-resume" \
    --output="${TEAM_DIR}/logs/%x_%j.out" \
    "${REPO}/scripts/slurm_aar_chain.sh" "explore-${seed}" \
    "${AAR_RESUME_HOURS}" "${remaining}" "${TEAM_ID}")"
  job="${job%%;*}"
  [[ "${job}" =~ ^[0-9]+$ ]] || { echo "invalid chain job id for ${seed}: ${job}" >&2; exit 2; }
  printf '%s\tchain\t%s\t%s\t%s\tremaining=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${seed}" "${job}" \
    "${recovery_commit}" "${remaining}" >> "${registry}"
  echo "[resume] ${seed}: ${started}/${max_sessions} started, job ${job} receives ${remaining} remaining sessions"
done

echo "[resume] preserved attempt=${ATTEMPT_DIR} team=${TEAM_ID}"
