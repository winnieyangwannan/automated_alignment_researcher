#!/bin/bash
#SBATCH --job-name=aar-run13-claude-canary-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_13_research_canary.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing retained attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing submitted commit}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing retained baseline}"
RECOVERED_SOURCES="${AAR_RECOVERED_BASELINE_SOURCES:?missing sources}"
MAX_ITERATIONS="${AAR_RUN13_RESEARCH_MAX_ITERATIONS:-1}"
export HF_HOME="${ATTEMPT_DIR}/cache/huggingface"

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

[ "${HF_HOME}" = "${ATTEMPT_DIR}/cache/huggingface" ] || {
  echo "attempt-local HF_HOME was overridden" >&2
  exit 2
}
mkdir -p "${HF_HOME}" "${ATTEMPT_DIR}/metadata" "${ATTEMPT_DIR}/research-tools"
ruff_source="$(dirname -- "${HARNESS_PY}")/ruff"
[ -x "${ruff_source}" ] || { echo "trusted harness lacks ruff" >&2; exit 2; }
cp -- "${ruff_source}" "${ATTEMPT_DIR}/research-tools/ruff"
chmod 500 "${ATTEMPT_DIR}/research-tools/ruff"
export AAR_RESEARCH_TOOL_DIR="${ATTEMPT_DIR}/research-tools"

export AAR_EXPECTED_BRANCH=autodata
export AAR_RUNTIME_ROOT="${ATTEMPT_DIR}"
export AAR_BASELINE_OVERRIDES="${ATTEMPT_DIR}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT_DIR}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT_DIR}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT=/storage/home/winnieyangwn/aar-recovery/run7_continuation_shared/librarian
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"

export EVAL_INFERENCE_BACKEND=vllm EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536 EVAL_VLLM_MAX_NUM_SEQS=256
export EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=32768
export EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export EVAL_VLLM_ENABLE_PREFIX_CACHING=1 EVAL_VLLM_ENFORCE_EAGER=0
export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint EVAL_VLLM_REQUIRE_MERGED=1
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH="${ATTEMPT_DIR}/runtime/serve_api_v2/worker/worker_vllm.sh"
export AAR_VLLM_WORKER_SHA256=913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}"
export AAR_VLLM_MERGED_ROOT="${ATTEMPT_DIR}/merged_candidates"

export AAR_AGENT_BACKEND=claude AAR_AGENT_MODEL=claude-opus-4-8
export AAR_WEB_MODE=meta_secure
export CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH:?missing Claude CLI}"
export AAR_RESEARCH_ENV_ISOLATION=1 AAR_CHAIN_SANITIZE_ENV=1
export AAR_RUNTIME_ENV_DISABLE_FILE=1 AAR_HIDE_EVAL_CONFIG=1
export AAR_LIT_AXIS_READ_ONLY=1
export AAR_MONITOR_MODEL_API_KEY="${MODEL_API_KEY:?missing monitor key}"

export AAR_TEAM_ID="run13-gemma4-31b-opus48-research-canary-${SLURM_JOB_ID}"
export AAR_CLAUDE_SPEND_CAP_USD=100 AAR_CLAUDE_SESSION_BUDGET_USD=100
export AAR_GPT_JUDGE_SPEND_CAP_USD=500 OVERLOADED_MAX_RETRIES=0
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1 AAR_REQUIRE_PHASE_TIMINGS=1
export AAR_VERIFY_TWO_ITERATION_ARTIFACTS=0 AAR_FUNCTIONAL_SMOKE=1
export AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_REQUIRE_METHOD_CONTRACT=1 AAR_REQUIRE_GEMMA4_TARGETS=1
export AAR_REQUIRE_METHOD_SMOKE=1 AAR_WRITE_TRAIN_FAILURE_MARKER=1
export AAR_REQUIRE_TRAIN_RECEIPT=1 AAR_PRETRAIN_SMOKE=1
export AAR_KEEP_CHECKPOINTS=1
export AAR_MAX_CONCURRENT_TRAIN_JOBS=1
export AAR_EVAL_WORKERS=1 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=18:00:00 AAR_EVAL_IDLE_SECONDS=61200
export AAR_START_EVAL_WORKER=1

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "wrong branch" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "commit drift" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
for required in "${REUSED_BASELINE}" "${RECOVERED_SOURCES}" "${TARGET_MODEL_PATH}" \
  "${AAR_VLLM_WORKER_SH}" "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" \
  "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${HARNESS_ENV}" "${CLAUDE_CLI_PATH}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done
[ "$(sha256sum "${AAR_VLLM_WORKER_SH}" | awk '{print $1}')" = "${AAR_VLLM_WORKER_SHA256}" ] || {
  echo "evaluator snapshot changed" >&2
  exit 2
}
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || { echo "missing ${secret_name}" >&2; exit 2; }
done
"${CLAUDE_CLI_PATH}" --help 2>&1 | grep -q -- --secure-internet-mode || {
  echo "Claude CLI lacks secure-internet mode" >&2
  exit 2
}
"${HARNESS_PY}" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "$(dirname -- "${LLM_UNCERTAINTY_SOURCE_MANIFEST}")" --verify-only >/dev/null
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" \
  --provenance-output "${ATTEMPT_DIR}/metadata/baseline_reuse_provenance.json" >/dev/null
cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${AAR_BASELINE_OVERRIDES}" --recovered-source-dir "${RECOVERED_SOURCES}" >/dev/null
bash "${REPO}/scripts/publish_holdout.sh"

launch_log="${ATTEMPT_DIR}/metadata/launch_run13_research_canary.txt"
bash "${REPO}/scripts/launch_team.sh" canary "${MAX_ITERATIONS}" 17 | tee "${launch_log}"
mapfile -t evaluator_ids < <(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${launch_log}")
mapfile -t chain_ids < <(awk '/^\[team\] chain canary -> job [0-9]+$/{print $NF}' "${launch_log}")
[ "${#evaluator_ids[@]}" -eq 1 ] || { echo "evaluator job ID missing" >&2; exit 1; }
[ "${#chain_ids[@]}" -eq 1 ] || { echo "research-chain job ID missing" >&2; exit 1; }
{
  printf 'evaluator_jobs=%s\n' "${evaluator_ids[0]}"
  printf 'research_chain_jobs=%s\n' "${chain_ids[0]}"
  printf 'research_seeds=canary\nmax_iterations_per_chain=%s\n' "${MAX_ITERATIONS}"
  printf 'evaluator_gpus_per_job=4\nresearch_backend=claude\n'
  printf 'research_model=claude-opus-4-8\nkeep_checkpoints=1\n'
} > "${ATTEMPT_DIR}/metadata/children.env"
echo "[run13] Claude research canary launched: evaluator=${evaluator_ids[0]} chain=${chain_ids[0]}"
