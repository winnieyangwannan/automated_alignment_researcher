#!/bin/bash
#SBATCH --job-name=aar-v0-gpu-smoke
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --gpus=1
#SBATCH --mem=192G
#SBATCH --time=02:00:00
set -euo pipefail
REPO="${AAR_REPO:-${SLURM_SUBMIT_DIR:?submit from the replication worktree}}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_v0.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
OUT="${AAR_RUNTIME_ROOT}/preflight/gpu-${SLURM_JOB_ID}"
mkdir -p "${OUT}"
nvidia-smi
"${HARNESS_PY}" "${REPO}/scripts/model_hpc_gpu_test.py" \
  --model "${TARGET_MODEL_PATH}" \
  --cache-dir "${HF_HOME}" \
  --model-class image-text \
  --enable-thinking \
  --new-tokens 128 \
  --warmup-tokens 4 \
  --require-import peft \
  --require-import trl \
  --output-json "${OUT}/generation.json"
"${HARNESS_PY}" "${REPO}/replication/smoke_lora_v0.py" \
  --model "${TARGET_MODEL_PATH}" --output "${OUT}/adapter"
date --iso-8601=seconds > "${AAR_RUNTIME_ROOT}/preflight/gpu.ok"
