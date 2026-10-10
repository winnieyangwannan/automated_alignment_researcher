#!/bin/bash
# Launch an eval worker with a bounded GPU count. The evaluator distributes all
# suite benchmarks across the allocated GPUs; AAR_EVAL_GPUS defaults to 2 and is
# capped by AAR_EVAL_GPU_CAP (default 4, one FAIR GB300 node).
#
# PREREQ — publish the holdout for the axis+model FIRST (writes the suite YAML this reads):
#   AXIS=sycophancy MODEL=mistral scripts/publish_holdout.sh
# Then launch the worker for the SAME axis (the model is baked into the published holdout, so
# the worker itself is model-independent — it just scores submitted models against that suite):
#   AXIS=sycophancy scripts/launch_eval_worker.sh
#
# The suite file is still counted to avoid requesting idle GPUs.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
else
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
fi
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# Default the suite from the SAME single source the research side uses (scripts/axis_env.sh),
# so the eval worker scores the axis the chains optimize. Pass an explicit arg (or AXIS=<name>)
# to override. The held-out is read from the published suite YAML, so it stays in sync.
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
SUITE="${1:-${SUITE_NAME}}"
IDLE="${2:-8000}"
WORKERS="${3:-${AAR_EVAL_WORKERS:-1}}"
case "${WORKERS}" in ''|*[!0-9]*) echo "ERROR: evaluator worker count must be an integer" >&2; exit 2;; esac
[ "${WORKERS}" -ge 1 ] || { echo "ERROR: evaluator worker count must be at least 1" >&2; exit 2; }
[ "${WORKERS}" -le 32 ] || { echo "ERROR: evaluator worker count must be at most 32" >&2; exit 2; }
HOLDOUT="${HOLDOUT_DIR:-}"
[ -n "${HOLDOUT}" ] || { echo "ERROR: HOLDOUT_DIR must be explicit" >&2; exit 2; }
YAML="${HOLDOUT}/${SUITE}/${SUITE}.yaml"
N=$(grep -c '^- name:' "${YAML}" 2>/dev/null || echo 0)
[ "${N}" -ge 1 ] || { echo "ERROR: no benchmarks in ${YAML} — publish the holdout first:" \
  "AXIS=${AXIS:-sycophancy} MODEL=${MODEL:-qwen} scripts/publish_holdout.sh" >&2; exit 1; }
GPUS="${AAR_EVAL_GPUS:-2}"
case "${GPUS}" in ''|*[!0-9]*) echo "ERROR: AAR_EVAL_GPUS must be an integer" >&2; exit 2;; esac
[ "${GPUS}" -ge 1 ] || { echo "ERROR: AAR_EVAL_GPUS must be at least 1" >&2; exit 2; }
[ "${GPUS}" -le "${N}" ] || GPUS="${N}"
[ "${GPUS}" -le "${AAR_EVAL_GPU_CAP:-4}" ] || GPUS="${AAR_EVAL_GPU_CAP:-4}"
MEMORY="${AAR_EVAL_MEM:-0}"
if [[ ! "${MEMORY}" =~ ^(0|[1-9][0-9]*[KMGTP]?)$ ]]; then
  echo "ERROR: AAR_EVAL_MEM must be 0 (all node memory) or a Slurm memory value" >&2
  exit 2
fi
LOG_DIR="${TEAM_DIR:-${AAR_RUNTIME_ROOT}}/logs"
mkdir -p "${LOG_DIR}"
echo "[launch] suite '${SUITE}' has ${N} benchmarks -> ${WORKERS} evaluator worker(s), gpu:${GPUS} each, mem:${MEMORY}"
_TIME_ARGS=()
[ -z "${AAR_EVAL_TIME:-}" ] || _TIME_ARGS=(--time="${AAR_EVAL_TIME}")
_JOB_IDS=()
for ((worker_index=1; worker_index<=WORKERS; worker_index++)); do
  _submission="$(sbatch --account="${AAR_SLURM_ACCOUNT}" --partition="${AAR_SLURM_PARTITION}" \
    --qos="${AAR_EVAL_QOS}" --nodes=1 --ntasks=1 --gpus="${GPUS}" --mem="${MEMORY}" \
    "${_TIME_ARGS[@]}" \
    --output="${LOG_DIR}/aar-eval-${SUITE}-%j.out" --job-name="aar-eval-${SUITE}-w${worker_index}" \
    "${REPO}/scripts/eval_worker.sh" "${SUITE}" "${IDLE}" "${GPUS}")"
  printf '%s\n' "${_submission}"
  _job_id="$(printf '%s\n' "${_submission}" | awk '/Submitted batch job [0-9]+/{id=$4} END {print id}')"
  if [ -z "${_job_id}" ]; then
    echo "ERROR: could not parse evaluator ${worker_index}/${WORKERS} job id from sbatch output" >&2
    exit 1
  fi
  _JOB_IDS+=("${_job_id}")
  echo "[launch] evaluator ${worker_index}/${WORKERS} -> job ${_job_id}"
done
echo "[launch] evaluator_jobs=${_JOB_IDS[*]}"
