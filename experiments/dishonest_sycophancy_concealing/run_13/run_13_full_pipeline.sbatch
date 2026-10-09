#!/bin/bash
#SBATCH --job-name=aar-run13-full-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_13_full.sh}"
ATTEMPT="${AAR_RUN_ATTEMPT_DIR:?missing attempt}"
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
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT}" AAR_VLLM_EPHEMERAL_MERGED=0
export AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680

export AAR_AGENT_BACKEND=claude AAR_AGENT_MODEL=claude-opus-4-8
export AAR_WEB_MODE=meta_secure
export CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH:-/usr/local/bin/claude}"
export KIMI_CLI_PATH=/storage/home/${USER}/tools/kimi-code-2.1.1/node_modules/.bin/kimi
export PATH=/storage/home/${USER}/tools/node-v22.22.0-linux-arm64/bin:"${PATH}"
export AAR_KIMI_SERVE_DEPLOYMENT=aar_8-kimi26 AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT=/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2
export KIMI_MODEL_MAX_CONTEXT_SIZE=262144 KIMI_MODEL_MAX_OUTPUT_SIZE=65536
export KIMI_MODEL_MAX_COMPLETION_TOKENS=65536 KIMI_MODEL_CAPABILITIES=tool_use
export KIMI_MODEL_REASONING_KEY=reasoning_content AAR_KIMI_MCP_MAX_TEXT_CHARS=16000
export AAR_KIMI_SCORE_WAIT_SECONDS=21600
export AAR_CLAUDE_SPEND_CAP_USD=100 AAR_CLAUDE_SESSION_BUDGET_USD=100
export AAR_GPT_JUDGE_SPEND_CAP_USD=500
unset KIMI_AGENT_MODEL

export AAR_REQUIRE_METHOD_CONTRACT=1 AAR_REQUIRE_GEMMA4_TARGETS=1 AAR_REQUIRE_METHOD_SMOKE=1
export AAR_WRITE_TRAIN_FAILURE_MARKER=1 AAR_TRAIN_MEM=128G AAR_REQUIRE_TRAIN_RECEIPT=1
export AAR_KEEP_CHECKPOINTS=1 AAR_PRETRAIN_SMOKE=1 AAR_MAX_CONCURRENT_TRAIN_JOBS=1
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1 AAR_REQUIRE_PHASE_TIMINGS=1
export AAR_TARGET_SUCCESSFUL_ITERATIONS=1 OVERLOADED_MAX_RETRIES=0
export AAR_FUNCTIONAL_SMOKE=1 AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_START_EVAL_WORKER=1 AAR_EVAL_WORKERS=1 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00 AAR_EVAL_IDLE_SECONDS=604200
export AAR_CHAIN_MAX_HOURS=72 AAR_CHAIN_SANITIZE_ENV=1 AAR_RUNTIME_ENV_DISABLE_FILE=1
export AAR_RESEARCH_ENV_ISOLATION=1 AAR_HIDE_EVAL_CONFIG=1

export AAR_AUTODATA=1 AAR_AUTODATA_LIFECYCLE_SUPERVISED=1
export AAR_AUTODATA_BROKER_RUNNER=local-bwrap AAR_AUTODATA_ENVIRONMENT=oci-runner-firecracker-large
export AAR_AUTODATA_CONCURRENCY="${AAR_RUN13_AUTODATA_CONCURRENCY:-8}"
export AAR_AUTODATA_META_MAX_ITERATIONS=3 AAR_AUTODATA_META_MIN_ITERATIONS=3
export AAR_AUTODATA_META_EARLY_STOP_PATIENCE=3
export AAR_AUTODATA_TUNING_TASKS=64 AAR_AUTODATA_VALIDATION_TASKS=32 AAR_AUTODATA_TEST_TASKS=32
export AAR_AUTODATA_PRODUCTION_ROWS=1000 AAR_AUTODATA_PRODUCTION_INITIAL_TASKS=1250
export AAR_AUTODATA_PRODUCTION_MAX_TASKS=2000
export AAR_AUTODATA_RECIPE_ROOT="${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing"

"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" \
  --provenance-output "${ATTEMPT}/metadata/baseline_reuse_provenance.json" >/dev/null
cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
bash "${REPO}/scripts/publish_holdout.sh"

children="${ATTEMPT}/metadata/children.tsv"
: > "${children}"
for seed in alpha beta gamma delta epsilon; do
  chain_root="${ATTEMPT}/chains/${seed}"
  team_id="run13-gemma4-31b-opus48-${seed}-${SLURM_JOB_ID}"
  export AAR_TEAM_ID="${team_id}"
  export AAR_IDEA_UID_OVERRIDE="run13-${seed}-iteration-1"
  export AAR_RESUME_APPROVED_PROPOSAL=0
  export AAR_AUTODATA_CAMPAIGN_POLICY="${chain_root}/metadata/campaign-policy.json"
  export AAR_AUTODATA_PROPOSAL_BINDINGS="${chain_root}/secrets/proposal-bindings.json"
  export AAR_VLLM_MERGED_ROOT="${AAR_RUN13_CHECKPOINT_ROOT:?}/chains/${seed}/merged_candidates"
  AAR_AUTODATA_CAPABILITY="$(<"${chain_root}/secrets/capability")"
  export AAR_AUTODATA_CAPABILITY
  launch_log="${chain_root}/logs/initial-launch.txt"
  bash "${REPO}/scripts/launch_team.sh" "${seed}" 1 72 | tee "${launch_log}"
  evaluator="$(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${launch_log}")"
  chain="$(awk -v seed="${seed}" '$0 ~ "^\\[team\\] chain " seed " -> job [0-9]+$"{print $NF}' "${launch_log}")"
  if [ -z "${evaluator}" ] || [ -z "${chain}" ]; then
    echo "missing child jobs for ${seed}" >&2
    exit 1
  fi
  controller="$(sbatch --parsable --dependency="afterany:${chain}" \
    --output="${chain_root}/logs/controller-%j.out" --export=ALL \
    "${REPO}/experiments/dishonest_sycophancy_concealing/run_13/run_13_chain_controller.sbatch" \
    "${seed}" "${team_id}" "${chain}")"
  printf '%s\t%s\t%s\t%s\n' "${seed}" "${evaluator}" "${chain}" "${controller}" \
    | tee -a "${children}"
done

[ "$(wc -l < "${children}")" -eq 5 ] || { echo "did not launch five chains" >&2; exit 1; }
printf 'research_backend=claude\nresearch_model=claude-opus-4-8\nchains=5\ntarget_pairs_per_chain=5\n' \
  > "${ATTEMPT}/metadata/full-launch.env"
echo "[run13] five isolated Claude Opus 4.8 chains launched; controllers will rotate each chain target after every durable iteration"
