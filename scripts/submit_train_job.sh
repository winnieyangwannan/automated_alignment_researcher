#!/bin/bash
# Submit exactly one decoupled AAR training job with site-configurable Slurm
# resources. The autonomous agent calls this wrapper instead of embedding a
# cluster-specific sbatch command in its prompt.

set -euo pipefail
IDEA="${1:?usage: submit_train_job.sh <idea> <approved_run_id>}"
RUN_ID="${2:?usage: submit_train_job.sh <idea> <approved_run_id>}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
elif [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/aar" ]; then
  REPO="$(cd -- "${SLURM_SUBMIT_DIR}" && pwd)"
else
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
fi
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"

[ -n "${TEAM_DIR:-}" ] || { echo "submit_train_job: TEAM_DIR is required" >&2; exit 2; }
mkdir -p "${TEAM_DIR}/logs"

if [ "${AAR_REQUIRE_METHOD_CONTRACT:-0}" = "1" ]; then
  _ideas_dir="${AAR_IDEAS_DIR:-${TEAM_DIR}/methods}"
  _method_path="${_ideas_dir}/${IDEA}/run.py"
  _proof_path="${_ideas_dir}/${IDEA}/.aar-method-contract.json"
  [ -f "${_method_path}" ] || {
    echo "submit_train_job: method is missing: ${_method_path}" >&2
    exit 2
  }
  timeout 60s "${HARNESS_PY:-python}" "${REPO}/scripts/validate_method_contract.py" \
    "${_method_path}" --proof "${_proof_path}" --run-dry-run >&2
fi

AAR_TRAIN_SUBMITTED_AT_NS="$(date +%s%N)"
export AAR_TRAIN_SUBMITTED_AT_NS

_limit="${AAR_MAX_CONCURRENT_TRAIN_JOBS:-0}"
case "${_limit}" in ''|*[!0-9]*) echo "submit_train_job: AAR_MAX_CONCURRENT_TRAIN_JOBS must be an integer" >&2; exit 2;; esac

# Assign submissions to dependency lanes under a per-team lock. With N lanes,
# job k depends on the prior tail of lane k mod N, so at most N team training
# jobs can run simultaneously without making the agent block while a slot frees.
_dependency=()
if [ "${_limit}" -gt 0 ]; then
  command -v flock >/dev/null || { echo "submit_train_job: flock is required for concurrency limiting" >&2; exit 2; }
  _lane_state="${TEAM_DIR}/.train_dependency_lanes"
  _lane_lock="${TEAM_DIR}/.train_dependency_lanes.lock"
  exec 9>"${_lane_lock}"
  flock 9
  _lanes=()
  mapfile -t _lanes < "${_lane_state}" 2>/dev/null || true
  while [ "${#_lanes[@]}" -lt "${_limit}" ]; do _lanes+=(""); done
  _cursor=0
  if [ -r "${_lane_state}.cursor" ]; then read -r _cursor < "${_lane_state}.cursor" || _cursor=0; fi
  case "${_cursor}" in ''|*[!0-9]*) _cursor=0;; esac
  _lane=$((_cursor % _limit))
  _prior="${_lanes[${_lane}]:-}"
  [ -z "${_prior}" ] || _dependency=(--dependency="afterany:${_prior}")
fi

_jid="$(sbatch --parsable \
  --account="${AAR_SLURM_ACCOUNT}" \
  --partition="${AAR_SLURM_PARTITION}" \
  --qos="${AAR_TRAIN_QOS}" \
  --gpus="${AAR_TRAIN_GPUS:-1}" \
  --job-name="aar-train-${TEAM_ID:-team}" \
  --output="${TEAM_DIR}/logs/train-%j.out" \
  "${_dependency[@]}" \
  "${REPO}/scripts/slurm_train_submit.sh" "${IDEA}" "${RUN_ID}")"

if [ "${_limit}" -gt 0 ]; then
  _lanes[_lane]="${_jid%%;*}"
  printf '%s\n' "${_lanes[@]}" > "${_lane_state}"
  printf '%s\n' "$((_cursor + 1))" > "${_lane_state}.cursor"
  flock -u 9
  echo "[submit] dependency lane ${_lane}/${_limit}; prior=${_prior:-none}; job=${_jid}" >&2
fi
printf '%s\n' "${_jid}"
