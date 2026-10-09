#!/bin/bash
#SBATCH --job-name=aar-run7-storage-continuation-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_storage_continuation.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing recovery attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing submitted commit}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing retained baseline}"
RECOVERED_SOURCES="${AAR_RECOVERED_BASELINE_SOURCES:?missing recovered sources}"
SNAPSHOT_ROOT="${AAR_RUN7_CLAUDE_SNAPSHOT:?missing Claude snapshot}"
export HF_HOME="${ATTEMPT_DIR}/cache/huggingface"

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

[ "${HF_HOME}" = "${ATTEMPT_DIR}/cache/huggingface" ] || {
  echo "continuation-local HF_HOME was overridden" >&2
  exit 2
}
mkdir -p "${HF_HOME}"
echo "[run7-continuation] isolated HF_HOME=${HF_HOME}"

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
export AAR_VLLM_WORKER_SH="${ATTEMPT_DIR}/runtime/serve_api_v2/worker/worker_vllm.sh"
export AAR_VLLM_WORKER_SHA256=913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}"
export AAR_VLLM_EPHEMERAL_MERGED=1
export AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680

export AAR_TEAM_ID="honesty-sycophancy-concealing-gemma4_31b-opus48-run7-storage-continuation-${SLURM_JOB_ID}"
export AAR_CLAUDE_SPEND_CAP_USD=500
export AAR_GPT_JUDGE_SPEND_CAP_USD=500
export AAR_CLAUDE_SESSION_BUDGET_USD=100
export OVERLOADED_MAX_RETRIES=0
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1
export AAR_REQUIRE_PHASE_TIMINGS=1
export AAR_VERIFY_TWO_ITERATION_ARTIFACTS=0
export AAR_FUNCTIONAL_SMOKE=1
export AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_MAX_CONCURRENT_TRAIN_JOBS=5
export AAR_EVAL_WORKERS=5
export AAR_EVAL_GPUS=4
export AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00
export AAR_EVAL_IDLE_SECONDS=604200
export AAR_START_EVAL_WORKER=1
export AAR_MAX_ITERATIONS_BY_SEED="alpha=43,beta=44,gamma=45,delta=44,epsilon=44"

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
for required in "${REUSED_BASELINE}" "${RECOVERED_SOURCES}" "${SNAPSHOT_ROOT}" \
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

seed_dir="${ATTEMPT_DIR}/recovered_seed"
"${HARNESS_PY}" \
  "${REPO}/experiments/dishonest_sycophancy_concealing/run_7/reconstruct_recovery_seed.py" \
  --snapshot-root "${SNAPSHOT_ROOT}" --output "${seed_dir}" --expected-entries 14 \
  > "${ATTEMPT_DIR}/metadata/reconstruction.json"
[ "$(find "${seed_dir}/forum" -maxdepth 1 -type f -name '*.json' | wc -l)" -eq 14 ] || {
  echo "recovery seed does not contain 14 findings" >&2
  exit 2
}
[ "$(find "${seed_dir}/agent_logs" -maxdepth 1 -type f -name 'AGENT_LOG_*.md' | wc -l)" -eq 5 ] || {
  echo "recovery seed does not contain five chain memories" >&2
  exit 2
}
seed_team_id=run7-recovered-history
mkdir -p "${ATTEMPT_DIR}/aar_teams/${seed_team_id}/forum"
cp -- "${seed_dir}/forum"/*.json "${ATTEMPT_DIR}/aar_teams/${seed_team_id}/forum/"
export SEED_FORUM_FROM="${seed_team_id}"
export AAR_RECOVERED_AGENT_LOG_DIR="${seed_dir}/agent_logs"

launch_log="${ATTEMPT_DIR}/metadata/launch_run7_storage_continuation.txt"
bash "${REPO}/scripts/launch_team.sh" "alpha beta gamma delta epsilon" 50 167 | tee "${launch_log}"

mapfile -t evaluator_ids < <(awk '/^\[launch\] evaluator [1-5]\/5 -> job [0-9]+$/{print $NF}' "${launch_log}")
mapfile -t chain_ids < <(awk '/^\[team\] chain (alpha|beta|gamma|delta|epsilon) -> job [0-9]+$/{print $NF}' "${launch_log}")
[ "${#evaluator_ids[@]}" -eq 5 ] || { echo "expected five evaluator job IDs" >&2; exit 1; }
[ "${#chain_ids[@]}" -eq 5 ] || { echo "expected five research-chain job IDs" >&2; exit 1; }
[ "$(printf '%s\n' "${evaluator_ids[@]}" | sort -u | wc -l)" -eq 5 ] || {
  echo "evaluator job IDs are not distinct" >&2
  exit 1
}
[ "$(printf '%s\n' "${chain_ids[@]}" | sort -u | wc -l)" -eq 5 ] || {
  echo "research-chain job IDs are not distinct" >&2
  exit 1
}
{
  printf 'evaluator_jobs=%s\n' "${evaluator_ids[*]}"
  printf 'research_chain_jobs=%s\n' "${chain_ids[*]}"
  printf 'research_seeds=alpha beta gamma delta epsilon\n'
  printf 'remaining_sessions=alpha:43,beta:44,gamma:45,delta:44,epsilon:44\n'
  printf 'evaluator_gpus_per_job=4\n'
  printf 'ephemeral_merged_checkpoints=1\n'
  printf 'recovered_public_findings=14\n'
} > "${ATTEMPT_DIR}/metadata/children.env"
echo "[run7-continuation] launch verified: five reconstructed continuation chains and five evaluators"
