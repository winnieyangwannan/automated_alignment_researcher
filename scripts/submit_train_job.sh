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

exec sbatch --parsable \
  --account="${AAR_SLURM_ACCOUNT}" \
  --partition="${AAR_SLURM_PARTITION}" \
  --qos="${AAR_TRAIN_QOS}" \
  --gpus="${AAR_TRAIN_GPUS:-1}" \
  --output="${TEAM_DIR}/logs/train-%j.out" \
  "${REPO}/scripts/slurm_train_submit.sh" "${IDEA}" "${RUN_ID}"
