#!/bin/bash
#SBATCH --job-name=aar-v0-baseline
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --gpus=2
#SBATCH --mem=192G
#SBATCH --time=08:00:00
set -euo pipefail

REPO="${AAR_REPO:-${SLURM_SUBMIT_DIR:?submit from the replication worktree}}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_v0.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
BASE_INPUT="${AAR_RUNTIME_ROOT}/baseline_input"
OUT_DIR="${AAR_RUNTIME_ROOT}/baseline_results"
mkdir -p "${OUT_DIR}" "${AAR_RUNTIME_ROOT}/metadata"
export EVAL_GPUS=auto
export JUDGE_BACKEND=openai
unset JUDGE_MODEL EVAL_MAX_NEW_TOKENS

"${HARNESS_PY}" -u -m aar.eval_pod.run_eval \
  --suite "${BASE_INPUT}/sycophancy/sycophancy.yaml" \
  --model "${TARGET_MODEL_PATH}" \
  --secret-dir "${BASE_INPUT}/sycophancy" \
  --out "${OUT_DIR}/baseline.research.json" \
  --heldout-dir "${OUT_DIR}/private"

"${HARNESS_PY}" "${REPO}/replication/record_baseline_v0.py" \
  "${OUT_DIR}/private/baseline.research.json" "${AAR_BASELINE_OVERRIDES}"

# Publish the immutable production suite only after all five exact-model
# baselines exist, so no placeholder can enter the hill-climb configuration.
bash "${REPO}/scripts/publish_holdout.sh"
echo "[baseline-v0] complete; production suite=${HOLDOUT_DIR}/sycophancy/sycophancy.yaml"
