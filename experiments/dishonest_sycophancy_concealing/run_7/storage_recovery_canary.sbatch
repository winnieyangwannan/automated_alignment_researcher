#!/bin/bash
#SBATCH --job-name=aar-run7-storage-recovery-canary-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_storage_recovery_canary.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing recovery attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing submitted commit}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing retained baseline}"
RECOVERED_SOURCES="${AAR_RECOVERED_BASELINE_SOURCES:?missing recovered sources}"
export HF_HOME="${ATTEMPT_DIR}/cache/huggingface"

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

[ "${HF_HOME}" = "${ATTEMPT_DIR}/cache/huggingface" ] || {
  echo "recovery-local HF_HOME was overridden" >&2
  exit 2
}
mkdir -p "${HF_HOME}"
echo "[run7-recovery-canary] isolated HF_HOME=${HF_HOME}"

export AAR_EXPECTED_BRANCH=multi_vllm
export AAR_RUNTIME_ROOT="${ATTEMPT_DIR}"
export AAR_BASELINE_OVERRIDES="${ATTEMPT_DIR}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT_DIR}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT_DIR}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT="/storage/home/winnieyangwn/aar-recovery/run7_continuation_shared/librarian"
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"

export EVAL_INFERENCE_BACKEND=vllm
export EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536
export EVAL_VLLM_MAX_NUM_SEQS=256
export EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=32768
export EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export EVAL_VLLM_ENABLE_PREFIX_CACHING=1
export EVAL_VLLM_ENFORCE_EAGER=0
export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint
export EVAL_VLLM_REQUIRE_MERGED=1
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH=/checkpoint/ram/shared/vllm_deployments_v2/baseline_gemma-4-31b-ib/src/serve_api_v2/worker/worker_vllm.sh
export AAR_VLLM_WORKER_SHA256=913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}"
export AAR_VLLM_EPHEMERAL_MERGED=1
export AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680

export AAR_TEAM_ID="honesty-sycophancy-concealing-gemma4_31b-opus48-run7-recovery-canary-${SLURM_JOB_ID}"
export AAR_CLAUDE_SPEND_CAP_USD=100
export AAR_GPT_JUDGE_SPEND_CAP_USD=100
export AAR_CLAUDE_SESSION_BUDGET_USD=100
export OVERLOADED_MAX_RETRIES=0
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1
export AAR_REQUIRE_PHASE_TIMINGS=1
export AAR_VERIFY_TWO_ITERATION_ARTIFACTS=0
export AAR_FUNCTIONAL_SMOKE=1
export AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_MAX_CONCURRENT_TRAIN_JOBS=1
export AAR_EVAL_WORKERS=1
export AAR_EVAL_GPUS=4
export AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=18:00:00
export AAR_EVAL_IDLE_SECONDS=61200
export AAR_START_EVAL_WORKER=1

[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "wrong branch" >&2
  exit 2
}
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || {
  echo "commit drift" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked HPC worktree is dirty" >&2
  exit 2
fi
for required in "${REUSED_BASELINE}" "${RECOVERED_SOURCES}" \
  "${TARGET_MODEL_PATH}" "${AAR_VLLM_WORKER_SH}" "${AAR_VLLM_MERGE_PY}" \
  "${HARNESS_PY}" "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${HARNESS_ENV}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done
[ "$(sha256sum "${AAR_VLLM_WORKER_SH}" | awk '{print $1}')" = \
  "${AAR_VLLM_WORKER_SHA256}" ] || {
  echo "vLLM worker snapshot hash mismatch" >&2
  exit 2
}
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || {
    echo "required runtime credential is empty: ${secret_name}" >&2
    exit 2
  }
done
"${HARNESS_PY}" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "$(dirname -- "${LLM_UNCERTAINTY_SOURCE_MANIFEST}")" \
  --verify-only >/dev/null

mkdir -p "${ATTEMPT_DIR}/metadata"
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" \
  --provenance-output "${ATTEMPT_DIR}/metadata/baseline_reuse_provenance.json" >/dev/null
cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${AAR_BASELINE_OVERRIDES}" --recovered-source-dir "${RECOVERED_SOURCES}" >/dev/null
bash "${REPO}/scripts/publish_holdout.sh"

launch_log="${ATTEMPT_DIR}/metadata/launch_run7_storage_recovery_canary.txt"
bash "${REPO}/scripts/launch_team.sh" "canary" 1 17 | tee "${launch_log}"

evaluator_id="$(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${launch_log}")"
chain_id="$(awk '/^\[team\] chain canary -> job [0-9]+$/{print $NF}' "${launch_log}")"
[ -n "${evaluator_id}" ] || { echo "expected one evaluator job ID" >&2; exit 1; }
[ -n "${chain_id}" ] || { echo "expected one research-chain job ID" >&2; exit 1; }
{
  printf 'evaluator_jobs=%s\n' "${evaluator_id}"
  printf 'research_chain_jobs=%s\n' "${chain_id}"
  printf 'research_seeds=canary\n'
  printf 'max_iterations_per_chain=1\n'
  printf 'evaluator_gpus_per_job=4\n'
  printf 'ephemeral_merged_checkpoints=1\n'
} > "${ATTEMPT_DIR}/metadata/children.env"
echo "[run7-recovery-canary] launch verified: one chain and one four-GPU evaluator"
