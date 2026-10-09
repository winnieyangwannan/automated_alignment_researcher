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
if [ "${AAR_AUTODATA:-0}" = 1 ]; then
  if [ "${AAR_AUTODATA_LIFECYCLE_SUPERVISED:-0}" = 1 ]; then
    "${HARNESS_PY}" "${REPO}/scripts/autodata_lifecycle_supervisor.py" snapshot \
      --state "${AAR_AUTODATA_STATE:?missing live AutoData state}" \
      --retained-state "${AAR_AUTODATA_RETAINED_STATE:?missing retained AutoData state}" \
      --reason training-preflight >/dev/null
  fi
  "${HARNESS_PY}" -m aar.infrastructure.autodata_lifecycle preflight --run-id "${RUN_ID}"
fi

_receipt_path=""
if [ "${AAR_REQUIRE_TRAIN_RECEIPT:-0}" = "1" ]; then
  command -v flock >/dev/null || {
    echo "submit_train_job: flock is required for submission receipts" >&2
    exit 2
  }
  [[ "${RUN_ID}" =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "submit_train_job: run id is unsafe for a receipt: ${RUN_ID}" >&2
    exit 2
  }
  _receipt_dir="${TEAM_DIR}/.train_submissions"
  mkdir -p "${_receipt_dir}"
  _receipt_path="${_receipt_dir}/${RUN_ID}.env"
  exec 8>"${_receipt_path}.lock"
  flock 8
  if [ -f "${_receipt_path}" ]; then
    _existing_run="$(awk -F= '$1 == "run_id" {print substr($0, index($0, "=") + 1)}' "${_receipt_path}")"
    _existing_job="$(awk -F= '$1 == "job_id" {print $2}' "${_receipt_path}")"
    if [ "${_existing_run}" = "${RUN_ID}" ] && [[ "${_existing_job}" =~ ^[0-9]+$ ]]; then
      printf '%s\n' "${_existing_job}"
      exit 0
    fi
    echo "submit_train_job: invalid existing receipt: ${_receipt_path}" >&2
    exit 2
  fi
fi

if [ "${AAR_REQUIRE_METHOD_CONTRACT:-0}" = "1" ]; then
  _ideas_dir="${AAR_IDEAS_DIR:-${TEAM_DIR}/methods}"
  _method_path="${_ideas_dir}/${IDEA}/run.py"
  _proof_path="${_ideas_dir}/${IDEA}/.aar-method-contract.json"
  [ -f "${_method_path}" ] || {
    echo "submit_train_job: method is missing: ${_method_path}" >&2
    exit 2
  }
  _contract_args=("${_method_path}" --proof "${_proof_path}" --run-dry-run)
  if [ "${AAR_REQUIRE_GEMMA4_TARGETS:-0}" = "1" ]; then
    _contract_args+=(--require-gemma4-targets)
  fi
  if [ "${AAR_REQUIRE_METHOD_SMOKE:-0}" = "1" ]; then
    _contract_args+=(--require-smoke-run)
  fi
  timeout 60s "${HARNESS_PY:-python}" "${REPO}/scripts/validate_method_contract.py" \
    "${_contract_args[@]}" >&2
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

_resource_args=()
if [ -n "${AAR_TRAIN_MEM:-}" ]; then
  [[ "${AAR_TRAIN_MEM}" =~ ^[1-9][0-9]*[KMGTP]$ ]] || {
    echo "submit_train_job: AAR_TRAIN_MEM must look like 128G" >&2
    exit 2
  }
  _resource_args+=(--mem="${AAR_TRAIN_MEM}")
fi
if [ -n "${AAR_TRAIN_TIME:-}" ]; then
  [[ "${AAR_TRAIN_TIME}" =~ ^([0-9]+-)?[0-9]{2}:[0-9]{2}:[0-9]{2}$ ]] || {
    echo "submit_train_job: AAR_TRAIN_TIME must use Slurm D-HH:MM:SS format" >&2
    exit 2
  }
  _resource_args+=(--time="${AAR_TRAIN_TIME}")
fi

_jid="$(sbatch --parsable \
  --account="${AAR_SLURM_ACCOUNT}" \
  --partition="${AAR_SLURM_PARTITION}" \
  --qos="${AAR_TRAIN_QOS}" \
  --gpus="${AAR_TRAIN_GPUS:-1}" \
  --job-name="aar-train-${TEAM_ID:-team}" \
  --output="${TEAM_DIR}/logs/train-%j.out" \
  "${_resource_args[@]}" \
  "${_dependency[@]}" \
  "${REPO}/scripts/slurm_train_submit.sh" "${IDEA}" "${RUN_ID}")"

_job_id="${_jid%%;*}"
[[ "${_job_id}" =~ ^[0-9]+$ ]] || {
  echo "submit_train_job: sbatch returned an invalid job id: ${_jid}" >&2
  exit 2
}

if [ -n "${_receipt_path}" ]; then
  _receipt_tmp="${_receipt_path}.tmp.$$"
  printf 'run_id=%s\njob_id=%s\n' "${RUN_ID}" "${_job_id}" > "${_receipt_tmp}"
  mv -f -- "${_receipt_tmp}" "${_receipt_path}"
  flock -u 8
fi

if [ "${_limit}" -gt 0 ]; then
  _lanes[_lane]="${_jid%%;*}"
  printf '%s\n' "${_lanes[@]}" > "${_lane_state}"
  printf '%s\n' "$((_cursor + 1))" > "${_lane_state}.cursor"
  flock -u 9
  echo "[submit] dependency lane ${_lane}/${_limit}; prior=${_prior:-none}; job=${_jid}" >&2
fi
printf '%s\n' "${_jid}"
