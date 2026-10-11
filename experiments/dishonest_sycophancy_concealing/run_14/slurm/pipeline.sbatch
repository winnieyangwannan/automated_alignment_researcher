#!/bin/bash
#SBATCH --job-name=aar-run14-native-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through run_14/launch/submit_full.sh}"
ATTEMPT="${AAR_RUN_ATTEMPT_DIR:?missing attempt}"
RUN_CONFIG="${AAR_RUN_CONFIG:?missing run config}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing source commit}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing baseline}"
RECOVERED_SOURCES="${AAR_RECOVERED_BASELINE_SOURCES:?missing source bundle}"
export HF_HOME="${ATTEMPT}/cache/huggingface"

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
eval "$("${HARNESS_PY}" "${REPO}/scripts/load_aar_run_config.py" "${RUN_CONFIG}")"
[ "${AAR_AUTODATA:?missing data-generation backend}" = 0 ] || {
  echo "Run 14 requires native data generation" >&2
  exit 2
}
while IFS= read -r name; do unset "${name}"; done < <(compgen -A variable AAR_AUTODATA_)
export AAR_AUTODATA=0

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "wrong branch" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "commit drift" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "dirty worktree" >&2
  exit 2
fi
mkdir -p "${HF_HOME}" "${ATTEMPT}/metadata"

export AAR_EXPECTED_BRANCH=autodata AAR_RUNTIME_ROOT="${ATTEMPT}"
export AAR_BASELINE_OVERRIDES="${ATTEMPT}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT=/storage/home/winnieyangwn/aar-recovery/run7_continuation_shared/librarian
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"
export LITREVIEW_SKIP=1 AAR_LIT_AXIS_READ_ONLY=1

export EVAL_INFERENCE_BACKEND=vllm EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536 EVAL_VLLM_MAX_NUM_SEQS=256
export EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=32768 EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export EVAL_VLLM_ENABLE_PREFIX_CACHING=1 EVAL_VLLM_ENFORCE_EAGER=0
export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint EVAL_VLLM_REQUIRE_MERGED=1
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH="${ATTEMPT}/runtime/serve_api_v2/worker/worker_vllm.sh"
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT}" AAR_VLLM_EPHEMERAL_MERGED=1
export AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680

export AAR_WEB_MODE=native_web
export KIMI_CLI_PATH=/storage/home/${USER}/tools/kimi-code-2.1.1/node_modules/.bin/kimi
export PATH=/storage/home/${USER}/tools/node-v22.22.0-linux-arm64/bin:"${PATH}"
export AAR_KIMI_SERVE_DEPLOYMENT=aar_8-kimi26 AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT=/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2
export KIMI_MODEL_MAX_CONTEXT_SIZE=262144 KIMI_MODEL_MAX_OUTPUT_SIZE=65536
export KIMI_MODEL_MAX_COMPLETION_TOKENS=65536 KIMI_MODEL_CAPABILITIES=tool_use
export KIMI_MODEL_REASONING_KEY=reasoning_content AAR_KIMI_MCP_MAX_TEXT_CHARS=65536
export AAR_KIMI_SCORE_WAIT_SECONDS=21600
unset KIMI_AGENT_MODEL

export AAR_REQUIRE_METHOD_CONTRACT=1 AAR_REQUIRE_GEMMA4_TARGETS=1 AAR_REQUIRE_METHOD_SMOKE=1
export AAR_WRITE_TRAIN_FAILURE_MARKER=1 AAR_TRAIN_MEM=128G AAR_REQUIRE_TRAIN_RECEIPT=1
export AAR_PRETRAIN_SMOKE=1
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1 AAR_REQUIRE_PHASE_TIMINGS=1
export OVERLOADED_MAX_RETRIES=0 AAR_FUNCTIONAL_SMOKE=1 AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_START_EVAL_WORKER=1 AAR_EVAL_GPU_CAP="${AAR_EVAL_GPUS:?}"
export AAR_CHAIN_SANITIZE_ENV=1 AAR_RUNTIME_ENV_DISABLE_FILE=1
export AAR_RESEARCH_ENV_ISOLATION=0 AAR_HIDE_EVAL_CONFIG=1

[ "${AAR_AGENT_BACKEND:?}" = kimi ] || { echo "Run 14 requires Kimi" >&2; exit 2; }
[ "${AAR_TARGET_SUCCESSFUL_ITERATIONS:?}" -ge 1 ] || { echo "invalid target pair count" >&2; exit 2; }
[ "${AAR_MAX_ITERATIONS_PER_CHAIN:?}" -ge "${AAR_TARGET_SUCCESSFUL_ITERATIONS}" ] || {
  echo "session budget is below the score/result-pair target" >&2; exit 2;
}
for required in "${REUSED_BASELINE}" "${RECOVERED_SOURCES}" "${TARGET_MODEL_PATH}" \
  "${AAR_VLLM_WORKER_SH}" "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" \
  "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${KIMI_CLI_PATH}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done

"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" \
  --provenance-output "${ATTEMPT}/metadata/baseline_reuse_provenance.json" >/dev/null
cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
bash "${REPO}/scripts/publish_holdout.sh"

read -r -a seeds <<< "${AAR_RESEARCH_SEEDS:?missing research seeds}"
children="${ATTEMPT}/metadata/children.tsv"
: > "${children}"
for seed in "${seeds[@]}"; do
  export AAR_TEAM_ID="run14-gemma4-31b-kimi26-${seed}-${SLURM_JOB_ID}"
  launch_log="${ATTEMPT}/metadata/launch-${seed}.txt"
  bash "${REPO}/scripts/launch_team.sh" "${seed}" \
    "${AAR_MAX_ITERATIONS_PER_CHAIN}" "${AAR_CHAIN_HOURS}" | tee "${launch_log}"
  evaluator="$(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${launch_log}")"
  chain="$(awk -v seed="${seed}" '$0 ~ "^\\[team\\] chain " seed " -> job [0-9]+$"{print $NF}' "${launch_log}")"
  if [ -z "${evaluator}" ] || [ -z "${chain}" ]; then
    echo "missing child jobs for ${seed}" >&2
    exit 1
  fi
  printf '%s\t%s\t%s\n' "${seed}" "${evaluator}" "${chain}" | tee -a "${children}"
done

[ "$(wc -l < "${children}")" -eq "${#seeds[@]}" ] || { echo "incomplete child manifest" >&2; exit 1; }
[ "$(cut -f2 "${children}" | sort -u | wc -l)" -eq "${#seeds[@]}" ] || { echo "duplicate evaluator IDs" >&2; exit 1; }
[ "$(cut -f3 "${children}" | sort -u | wc -l)" -eq "${#seeds[@]}" ] || { echo "duplicate chain IDs" >&2; exit 1; }
printf 'research_backend=kimi\nresearch_model=Kimi-K2.6\ndata_generation_backend=native\nautodata=0\nchains=%s\ntarget_score_result_pairs=%s\nseeds=%s\n' \
  "${#seeds[@]}" "${AAR_TARGET_SUCCESSFUL_ITERATIONS}" "${AAR_RESEARCH_SEEDS}" \
  > "${ATTEMPT}/metadata/full-launch.env"
echo "[run14] launched ${#seeds[@]} isolated native-generation chains"
