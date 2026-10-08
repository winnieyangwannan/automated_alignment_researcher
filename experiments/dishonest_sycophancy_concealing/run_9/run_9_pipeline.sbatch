#!/bin/bash
#SBATCH --job-name=aar-gemma-autodata-run9-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_9.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing retained attempt}"

export AAR_EXPECTED_BRANCH=autodata
export AAR_TEAM_ID="run9-gemma4-31b-opus48-autodata-five-success-v1"
export AAR_CHAIN_SEEDS=pilot
export AAR_CHAIN_MAX_SESSIONS=8
export AAR_CHAIN_MAX_HOURS=72
export AAR_TARGET_SUCCESSFUL_ITERATIONS=5
export AAR_AGENT_MODEL=claude-opus-4-8
export AAR_FUNCTIONAL_SMOKE=0
export AAR_RESEARCH_ENV_ISOLATION=1
export AAR_CHAIN_SANITIZE_ENV=1
export AAR_RUNTIME_ENV_DISABLE_FILE=1
export AAR_MONITOR_MODEL_API_KEY="${MODEL_API_KEY:?missing monitor key}"
export AAR_HIDE_EVAL_CONFIG=1
export AAR_LIT_AXIS_READ_ONLY=1
export AAR_LAUNCH_LOG_NAME=launch_run9_submission.txt

export AAR_AUTODATA=1
export AAR_AUTODATA_CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:?}"
export AAR_AUTODATA_META_MAX_ITERATIONS=10
export AAR_AUTODATA_META_MIN_ITERATIONS=3
export AAR_AUTODATA_META_EARLY_STOP_PATIENCE=3
export AAR_AUTODATA_TUNING_TASKS=64
export AAR_AUTODATA_VALIDATION_TASKS=32
export AAR_AUTODATA_TEST_TASKS=32
export AAR_AUTODATA_PRODUCTION_ROWS=1000
export AAR_AUTODATA_PRODUCTION_INITIAL_TASKS=1250
export AAR_AUTODATA_PRODUCTION_MAX_TASKS=1500
export AAR_AUTODATA_RECIPE_ROOT="${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing"

export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}"
export AAR_VLLM_MERGED_ROOT="${ATTEMPT_DIR}/merged_candidates"
export AAR_VLLM_EPHEMERAL_MERGED=1
export AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680

exec bash "${REPO}/experiments/dishonest_sycophancy_concealing/run_5/run_5_pipeline.sbatch"
