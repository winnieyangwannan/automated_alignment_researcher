#!/bin/bash
#SBATCH --job-name=aareval
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=8
#SBATCH --gpus=1
#SBATCH --mem=48G
#SBATCH --time=00:30:00
#SBATCH --output=slurm-%x-%j.out
#
# Eval job for the multi-benchmark AAR harness (fs transport).
# Reads the SECRET suite from HOLDOUT_DIR + the submitted model from
# SUBMISSIONS_DIR, scores it, writes scores.json back. Args: <run_id> <suite>.
#
# ISOLATION (production): HOLDOUT_DIR must be owned by a SEPARATE eval user,
# mode 700, and this job must run as / be able to read that user (see
# ISOLATION.md). In dev (single user) it's the honor system — the AAR is told
# not to read it, but nothing enforces that yet.

set -euo pipefail
RUN_ID="${1:?usage: slurm_eval.sh <run_id> <suite>}"
SUITE="${2:?usage: slurm_eval.sh <run_id> <suite>}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="${AAR_REPO:-${HARNESS_REPO:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export HARNESS_TRANSPORT=fs
# OAI_API for judge benchmarks — extract just that key (don't source the whole
# .env; the SSH-key line has spaces and breaks `source`). Kept off the research side.
ENV_FILE="${HARNESS_ENV:-${REPO}/.env}"
if [ -z "${OAI_API:-}" ] && [ -f "${ENV_FILE}" ]; then
  OAI_API_VALUE="$(awk -F= '$1 == "OAI_API" { sub(/^[^=]*=/, ""); print; exit }' "${ENV_FILE}")"
  [ -z "${OAI_API_VALUE}" ] || export OAI_API="${OAI_API_VALUE}"
fi

cd "${REPO}"
# The normal installation creates .venv in the repository.  Evaluation users
# can point at a shared environment by setting HARNESS_PY to its Python binary.
PY="${HARNESS_PY}"
if [ ! -x "${PY}" ]; then
  echo "slurm_eval.sh: Python is not executable: ${PY} (set HARNESS_PY)" >&2
  exit 2
fi
PYTHONUNBUFFERED=1 "${PY}" -u -m aar.eval_pod.entrypoint --run-id "${RUN_ID}" --suite "${SUITE}"
echo "=== DONE ==="
