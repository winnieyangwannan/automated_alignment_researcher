#!/bin/bash
#SBATCH --job-name=aar-run10-kimi-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_10.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing commit}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing baseline}"
RECOVERED_SOURCES="${AAR_RECOVERED_BASELINE_SOURCES:?missing sources}"
MODE="${AAR_RUN10_MODE:?missing canary/full mode}"
export HF_HOME="${ATTEMPT_DIR}/cache/huggingface"

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
[ "${HF_HOME}" = "${ATTEMPT_DIR}/cache/huggingface" ] || { echo "attempt-local HF_HOME overridden" >&2; exit 2; }
mkdir -p "${HF_HOME}"

export AAR_EXPECTED_BRANCH=multi_kimi AAR_RUNTIME_ROOT="${ATTEMPT_DIR}"
export AAR_BASELINE_OVERRIDES="${ATTEMPT_DIR}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT_DIR}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT_DIR}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT=/storage/home/winnieyangwn/aar-recovery/run7_continuation_shared/librarian
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"

export EVAL_INFERENCE_BACKEND=vllm EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536 EVAL_VLLM_MAX_NUM_SEQS=256 EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=32768
export EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.90 EVAL_VLLM_ENABLE_PREFIX_CACHING=1 EVAL_VLLM_ENFORCE_EAGER=0
export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint EVAL_VLLM_REQUIRE_MERGED=1
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH="${ATTEMPT_DIR}/runtime/serve_api_v2/worker/worker_vllm.sh"
export AAR_VLLM_WORKER_SHA256=913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}" AAR_VLLM_EPHEMERAL_MERGED=1
export AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680

export AAR_AGENT_BACKEND=kimi AAR_WEB_MODE=native_web
export KIMI_CLI_PATH="${AAR_RUN10_KIMI_ROOT:-/storage/home/${USER}/tools/kimi-code-2.1.1}/node_modules/.bin/kimi"
export PATH="${AAR_RUN10_NODE_ROOT:-/storage/home/${USER}/tools/node-v22.22.0-linux-arm64}/bin:${PATH}"
export AAR_KIMI_SERVE_DEPLOYMENT=steerability_8-kimi26 AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT="/storage/home/${USER}/ram_common/vllm_tools/serve_api_v2"
export KIMI_MODEL_MAX_CONTEXT_SIZE=262144 KIMI_MODEL_MAX_OUTPUT_SIZE=65536
export KIMI_MODEL_MAX_COMPLETION_TOKENS=65536
export KIMI_MODEL_CAPABILITIES=tool_use KIMI_MODEL_REASONING_KEY=reasoning_content
export AAR_KIMI_MCP_MAX_TEXT_CHARS=16000
export AAR_REQUIRE_METHOD_CONTRACT=1 AAR_REQUIRE_GEMMA4_TARGETS=1 AAR_REQUIRE_METHOD_SMOKE=1
export AAR_WRITE_TRAIN_FAILURE_MARKER=1
export AAR_TRAIN_MEM=128G AAR_REQUIRE_TRAIN_RECEIPT=1
unset KIMI_AGENT_MODEL

export AAR_TEAM_ID="honesty-sycophancy-concealing-gemma4_31b-kimi26-run10-${MODE}-${SLURM_JOB_ID}"
export AAR_GPT_JUDGE_SPEND_CAP_USD=500 OVERLOADED_MAX_RETRIES=0
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1 AAR_REQUIRE_PHASE_TIMINGS=1 AAR_VERIFY_TWO_ITERATION_ARTIFACTS=0
export AAR_FUNCTIONAL_SMOKE=1 AAR_MULTIDIM_SCORING_CONFIRMED=1 AAR_START_EVAL_WORKER=1
if [ "${MODE}" = smoke ]; then
  seeds=smoke; iterations=1; hours=2
  export AAR_START_EVAL_WORKER=0 AAR_EVAL_WORKERS=0
  export AAR_MAX_CONCURRENT_TRAIN_JOBS=1 AAR_METHOD_SMOKE=1
  export AAR_TRAIN_TIME=00:15:00
  export AAR_KEEP_CHECKPOINTS=1
elif [ "${MODE}" = canary ]; then
  seeds=canary; iterations=1; hours=17
  export AAR_MAX_CONCURRENT_TRAIN_JOBS=1 AAR_EVAL_WORKERS=1 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
  export AAR_EVAL_TIME=18:00:00 AAR_EVAL_IDLE_SECONDS=61200
else
  seeds="alpha beta gamma delta epsilon"; iterations=50; hours=167
  export AAR_MAX_CONCURRENT_TRAIN_JOBS=5 AAR_EVAL_WORKERS=5 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
  export AAR_EVAL_TIME=7-00:00:00 AAR_EVAL_IDLE_SECONDS=604200
fi

[ "$(git -C "${REPO}" branch --show-current)" = multi_kimi ] || { echo "wrong branch" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "commit drift" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
for required in "${REUSED_BASELINE}" "${RECOVERED_SOURCES}" "${TARGET_MODEL_PATH}" "${AAR_VLLM_WORKER_SH}" \
  "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${HARNESS_ENV}" "${KIMI_CLI_PATH}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done
[ "$(sha256sum "${AAR_VLLM_WORKER_SH}" | awk '{print $1}')" = "${AAR_VLLM_WORKER_SHA256}" ] || { echo "evaluator snapshot changed" >&2; exit 2; }
for secret_name in HF_TOKEN MODEL_API_KEY; do [ -n "${!secret_name:-}" ] || { echo "missing ${secret_name}" >&2; exit 2; }; done
"${HARNESS_PY}" "${REPO}/scripts/prepare_llm_uncertainty_source.py" --output-root "$(dirname -- "${LLM_UNCERTAINTY_SOURCE_MANIFEST}")" --verify-only >/dev/null

mkdir -p "${ATTEMPT_DIR}/metadata"
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" "${REUSED_BASELINE}" \
  --recovered-source-dir "${RECOVERED_SOURCES}" --provenance-output "${ATTEMPT_DIR}/metadata/baseline_reuse_provenance.json" >/dev/null
cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" "${AAR_BASELINE_OVERRIDES}" --recovered-source-dir "${RECOVERED_SOURCES}" >/dev/null
if [ "${MODE}" != smoke ]; then
  bash "${REPO}/scripts/publish_holdout.sh"
fi

launch_log="${ATTEMPT_DIR}/metadata/launch_run10_${MODE}.txt"
bash "${REPO}/scripts/launch_team.sh" "${seeds}" "${iterations}" "${hours}" | tee "${launch_log}"
mapfile -t evaluator_ids < <(awk '/^\[launch\] evaluator [0-9]+\/[0-9]+ -> job [0-9]+$/{print $NF}' "${launch_log}")
mapfile -t chain_ids < <(awk '/^\[team\] chain [a-z]+ -> job [0-9]+$/{print $NF}' "${launch_log}")
expected=1; [ "${MODE}" = full ] && expected=5
expected_evaluators="${expected}"; [ "${MODE}" = smoke ] && expected_evaluators=0
[ "${#evaluator_ids[@]}" -eq "${expected_evaluators}" ] && [ "${#chain_ids[@]}" -eq "${expected}" ] || { echo "missing child job IDs" >&2; exit 1; }
if [ "${expected_evaluators}" -gt 0 ]; then
  [ "$(printf '%s\n' "${evaluator_ids[@]}" | sort -u | wc -l)" -eq "${expected_evaluators}" ] || { echo "duplicate evaluator IDs" >&2; exit 1; }
fi
[ "$(printf '%s\n' "${chain_ids[@]}" | sort -u | wc -l)" -eq "${expected}" ] || { echo "duplicate chain IDs" >&2; exit 1; }
{
  printf 'evaluator_jobs=%s\n' "${evaluator_ids[*]}"
  printf 'research_chain_jobs=%s\n' "${chain_ids[*]}"
  printf 'research_seeds=%s\n' "${seeds}"
  printf 'max_iterations_per_chain=%s\n' "${iterations}"
  printf 'evaluator_gpus_per_job=%s\nresearch_backend=kimi\nresearch_model=Kimi-K2.6\nephemeral_merged_checkpoints=1\n' "$([ "${MODE}" = smoke ] && echo 0 || echo 4)"
} > "${ATTEMPT_DIR}/metadata/children.env"
echo "[run10] ${MODE} launch verified with ${expected} chain(s) and ${expected_evaluators} evaluator(s)"

if [ "${MODE}" = smoke ]; then
  echo "[run10] waiting for the generated method's real-GPU one-step smoke"
  "${HARNESS_PY}" "${REPO}/experiments/dishonest_sycophancy_concealing/run_10/monitor_method_smoke.py" \
    "${ATTEMPT_DIR}" --timeout-seconds 6900 --poll-seconds 10
  smoke_proof="${ATTEMPT_DIR}/metadata/method_smoke_passed.json"
  run_id="$(jq -r '.run_id' "${smoke_proof}")"
  adapter_path="$(jq -r '.adapter_path' "${smoke_proof}")"
  export TEAM_DIR="${ATTEMPT_DIR}/aar_teams/${AAR_TEAM_ID}"
  export SUBMISSIONS_DIR="${TEAM_DIR}/submissions" SCORES_DIR="${TEAM_DIR}/scores"

  echo "[run10] method smoke passed; publishing holdout and staging the same adapter"
  bash "${REPO}/scripts/publish_holdout.sh"
  "${HARNESS_PY}" -c \
    'import sys; from aar.transport import put_model; print(put_model(sys.argv[1], sys.argv[2]))' \
    "${adapter_path}" "${run_id}"

  export AAR_EVAL_WORKERS=1 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
  export AAR_EVAL_TIME=18:00:00 AAR_EVAL_IDLE_SECONDS=61200
  eval_launch_log="${ATTEMPT_DIR}/metadata/launch_on_demand_evaluator.txt"
  "${REPO}/scripts/launch_eval_worker.sh" "${SUITE_NAME}" "${AAR_EVAL_IDLE_SECONDS}" 1 | tee "${eval_launch_log}"
  mapfile -t evaluator_ids < <(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${eval_launch_log}")
  [ "${#evaluator_ids[@]}" -eq 1 ] || { echo "on-demand evaluator ID missing" >&2; exit 1; }
  {
    printf 'evaluator_jobs=%s\n' "${evaluator_ids[0]}"
    printf 'research_chain_jobs=%s\n' "${chain_ids[*]}"
    printf 'research_seeds=%s\n' "${seeds}"
    printf 'max_iterations_per_chain=%s\n' "${iterations}"
    printf 'evaluator_gpus_per_job=4\nresearch_backend=kimi\nresearch_model=Kimi-K2.6\nephemeral_merged_checkpoints=1\n'
    printf 'method_smoke_passed=1\non_demand_evaluator=1\n'
  } > "${ATTEMPT_DIR}/metadata/children.env"
  echo "[run10] on-demand evaluator ${evaluator_ids[0]} launched for smoked run ${run_id}"
fi
