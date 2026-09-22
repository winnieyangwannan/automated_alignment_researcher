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
LOG_DIR="${TEAM_DIR:-${AAR_RUNTIME_ROOT}}/logs"
mkdir -p "${LOG_DIR}"
echo "[launch] suite '${SUITE}' has ${N} benchmarks -> evaluator gpu:${GPUS}"
sbatch --account="${AAR_SLURM_ACCOUNT}" --partition="${AAR_SLURM_PARTITION}" \
  --qos="${AAR_EVAL_QOS}" --gpus="${GPUS}" \
  --output="${LOG_DIR}/aar-eval-${SUITE}-%j.out" --job-name="aar-eval-${SUITE}" \
  "${REPO}/scripts/eval_worker.sh" "${SUITE}" "${IDLE}" auto
