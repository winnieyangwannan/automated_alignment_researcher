#!/bin/bash
#SBATCH --job-name=aar-run12-full-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through run_12/launch/submit_full.sh}"
ATTEMPT="${AAR_RUN_ATTEMPT_DIR:?missing attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing source commit}"
SOURCE_SNAPSHOT="${AAR_SOURCE_SNAPSHOT:?missing immutable source snapshot}"
TRUSTED_HARNESS_PY="${AAR_TRUSTED_HARNESS_PY:?missing trusted harness Python}"
TRUSTED_HARNESS_ENV="${HARNESS_ENV:?missing trusted harness environment}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing baseline}"
RECOVERED_SOURCES="${AAR_RECOVERED_BASELINE_SOURCES:?missing source bundle}"
export HF_HOME="${ATTEMPT}/cache/huggingface"

[ "${REPO}" = "${SOURCE_SNAPSHOT}" ] || { echo "source snapshot path drift" >&2; exit 2; }
[ "${REPO}" = "${ATTEMPT}/runtime/aar-source" ] || { echo "source is not attempt-local" >&2; exit 2; }
[ ! -e "${REPO}/.venv" ] || { echo "source snapshot unexpectedly contains a virtual environment" >&2; exit 2; }
[ -x "${TRUSTED_HARNESS_PY}" ] || { echo "trusted harness Python is not executable" >&2; exit 2; }
trusted_harness_realpath="$(realpath -e -- "${TRUSTED_HARNESS_PY}")"
case "${trusted_harness_realpath}" in
  "${ATTEMPT}/runtime/"*) echo "trusted harness Python is snapshot-relative" >&2; exit 2 ;;
esac
[ -f "${TRUSTED_HARNESS_ENV}" ] || { echo "trusted harness environment is unavailable" >&2; exit 2; }
trusted_harness_env_realpath="$(realpath -e -- "${TRUSTED_HARNESS_ENV}")"
case "${trusted_harness_env_realpath}" in
  "${ATTEMPT}/runtime/"*) echo "trusted harness environment is snapshot-relative" >&2; exit 2 ;;
esac
[ -z "$(git -C "${REPO}" branch --show-current)" ] || { echo "source snapshot is not detached" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "commit drift" >&2; exit 2; }
[ -z "$(git -C "${REPO}" remote)" ] || { echo "source snapshot retains a remote" >&2; exit 2; }
[ ! -e "${REPO}/.git/objects/info/alternates" ] || { echo "source snapshot has shared-object alternates" >&2; exit 2; }
if [ -n "$(git -C "${REPO}" status --porcelain --untracked-files=all)" ]; then
  echo "dirty source snapshot" >&2
  exit 2
fi
AUTODATA_SNAPSHOT="${AAR_AUTODATA_CHECKOUT:?missing AutoData snapshot}"
[ "${AUTODATA_SNAPSHOT}" = "${ATTEMPT}/runtime/autodata-source" ] || { echo "AutoData source is not attempt-local" >&2; exit 2; }
[ ! -e "${AUTODATA_SNAPSHOT}/.venv" ] || { echo "AutoData snapshot unexpectedly contains a virtual environment" >&2; exit 2; }
[ -z "$(git -C "${AUTODATA_SNAPSHOT}" branch --show-current)" ] || { echo "AutoData source is not detached" >&2; exit 2; }
[ "$(git -C "${AUTODATA_SNAPSHOT}" rev-parse HEAD)" = "${AAR_AUTODATA_SHA:?missing AutoData commit}" ] || { echo "AutoData commit drift" >&2; exit 2; }
[ -z "$(git -C "${AUTODATA_SNAPSHOT}" remote)" ] || { echo "AutoData snapshot retains a remote" >&2; exit 2; }
[ ! -e "${AUTODATA_SNAPSHOT}/.git/objects/info/alternates" ] || { echo "AutoData snapshot has shared-object alternates" >&2; exit 2; }
if [ -n "$(git -C "${AUTODATA_SNAPSHOT}" status --porcelain --untracked-files=all)" ]; then
  echo "dirty AutoData source snapshot" >&2
  exit 2
fi

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
[ "${AAR_TRUSTED_HARNESS_PY}" = "${TRUSTED_HARNESS_PY}" ] || { echo "trusted harness Python was overwritten" >&2; exit 2; }
export HARNESS_PY="${TRUSTED_HARNESS_PY}"
[ -x "${HARNESS_PY}" ] || { echo "harness Python is not executable after environment bootstrap" >&2; exit 2; }
[ "${HARNESS_ENV}" = "${TRUSTED_HARNESS_ENV}" ] || { echo "trusted harness environment was overwritten" >&2; exit 2; }
[ "${WORKSPACE_DIR}" = "${REPO}" ] || { echo "workspace directory escaped source snapshot" >&2; exit 2; }
[ "${AAR_BENCHMARK_DOCS}" = "${REPO}/benchmark_docs" ] || { echo "benchmark docs escaped source snapshot" >&2; exit 2; }
[ "${BENCHMARK_DOCS_DIR}" = "${REPO}/benchmark_docs" ] || { echo "benchmark docs directory escaped source snapshot" >&2; exit 2; }
[ "${PYTHONPATH%%:*}" = "${REPO}" ] || { echo "Python path is not rooted at source snapshot" >&2; exit 2; }
mkdir -p "${HF_HOME}" "${ATTEMPT}/metadata"

# Exercise the pinned native engine itself, including meta finalization,
# zero-iteration production, budget validation, export, and recovery behavior.
PYTHONPATH="${AUTODATA_SNAPSHOT}:${AUTODATA_SNAPSHOT}/src" timeout 180 \
  "${HARNESS_PY}" -m unittest tests.test_engine \
  > "${ATTEMPT}/metadata/autodata-native-engine-contract.txt" 2>&1
chmod 400 "${ATTEMPT}/metadata/autodata-native-engine-contract.txt"

# Exercise the actual pinned native serializers against the trusted AAR meta
# and production constructors before any research or evaluator child exists.
PYTHONPATH="${REPO}:${AUTODATA_SNAPSHOT}/src" "${HARNESS_PY}" \
  "${REPO}/scripts/validate_autodata_adapter_contract.py" \
  --scratch-root "${ATTEMPT}/metadata" \
  > "${ATTEMPT}/metadata/autodata-adapter-contract.json"
chmod 400 "${ATTEMPT}/metadata/autodata-adapter-contract.json"
SEEDS_RAW="${AAR_RUN12_SEEDS:-alpha beta gamma delta epsilon}"
CHAIN_COUNT="${AAR_RUN12_CHAIN_COUNT:-5}"
TARGET_PAIRS="${AAR_RUN12_TARGET_PAIRS:-5}"
read -r -a seeds <<< "${SEEDS_RAW}"
[ "${#seeds[@]}" -eq "${CHAIN_COUNT}" ] || { echo "Run 12 chain count drift" >&2; exit 2; }

unset AAR_EXPECTED_BRANCH
export AAR_EXPECTED_COMMIT="${EXPECTED_COMMIT}" AAR_RUNTIME_ROOT="${ATTEMPT}"
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
export AAR_PRETRAIN_SMOKE=1 AAR_MAX_CONCURRENT_TRAIN_JOBS=1
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1 AAR_REQUIRE_PHASE_TIMINGS=1
export AAR_TARGET_SUCCESSFUL_ITERATIONS=1 OVERLOADED_MAX_RETRIES=0
export AAR_FUNCTIONAL_SMOKE=1 AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_START_EVAL_WORKER=1 AAR_EVAL_WORKERS=1 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00 AAR_EVAL_IDLE_SECONDS=604200
export AAR_CHAIN_MAX_HOURS=72 AAR_CHAIN_SANITIZE_ENV=1 AAR_RUNTIME_ENV_DISABLE_FILE=1
export AAR_RESEARCH_ENV_ISOLATION=0 AAR_HIDE_EVAL_CONFIG=1

export AAR_AUTODATA=1
: "${AAR_AUTODATA_RUNTIME_ENV:?missing compiled AutoData runtime environment}"
# shellcheck disable=SC1090
source "${AAR_AUTODATA_RUNTIME_ENV}"
[ "${AAR_RUN_STORAGE_ROOT:?missing configured storage root}" = "/checkpoint/ram/${USER}" ] || {
  echo "compiled Run 12 storage root drifted" >&2; exit 2;
}
[ "${AAR_KEEP_CHECKPOINTS:?missing checkpoint policy}" = 0 ] || {
  echo "Run 12 must prune redundant training checkpoints" >&2; exit 2;
}
[ "${AAR_TRAIN_EXIT_AFTER_SUBMIT:?missing decoupled training policy}" = 1 ] || {
  echo "Run 12 must retain submitted adapters for target promotion" >&2; exit 2;
}
[ "${AAR_EVAL_MEM:?missing evaluator memory}" = 0 ] || {
  echo "Run 12 evaluators must request all allocated node memory" >&2; exit 2;
}
[ "${EVAL_MAX_TRUNCATION_RATE:?missing truncation ceiling}" = 0.2 ] || {
  echo "Run 12 truncation ceiling drifted" >&2; exit 2;
}
[ "${AAR_AGENT_BACKEND:?missing research backend}" = kimi ] || {
  echo "Run 12 requires the Kimi research backend" >&2; exit 2;
}
[ "${AAR_KIMI_TURN_TIMEOUT_SECONDS:?missing Kimi turn timeout}" = 1800 ] || {
  echo "Run 12 Kimi turn timeout drifted" >&2; exit 2;
}
[ "${AAR_AUTODATA_TARGET_REQUIRED:-0}" = 1 ] || {
  echo "Run 12 compiled configuration is not target-aware" >&2
  exit 2
}
if [ "${AAR_RUN12_MODE:-full}" = bootstrap-canary ]; then
  case "${AAR_AUTODATA_STOP_AFTER:-}" in
    production)
      export AAR_METHOD_SMOKE=0
      ;;
    training_smoke)
      # Consume the complete verified dataset but bound optimization to the
      # method contract's real-CUDA one-step path.
      export AAR_METHOD_SMOKE=1
      ;;
    *)
      echo "bootstrap canary has an unsupported stop boundary" >&2
      exit 2
      ;;
  esac
  # Canary modes deliberately perform no held-out evaluation.
  export AAR_START_EVAL_WORKER=0
else
  [ -z "${AAR_AUTODATA_STOP_AFTER:-}" ] || {
    echo "full mode must not inherit a canary stop boundary" >&2
    exit 2
  }
  export AAR_METHOD_SMOKE=0
fi

"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" \
  --provenance-output "${ATTEMPT}/metadata/baseline_reuse_provenance.json" >/dev/null
cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
if [ "${AAR_START_EVAL_WORKER}" = 1 ]; then
  bash "${REPO}/scripts/publish_holdout.sh"
else
  echo "[run12] bounded canary: skipping evaluator holdout publication"
fi

children="${ATTEMPT}/metadata/children.tsv"
: > "${children}"
for seed in "${seeds[@]}"; do
  chain_root="${ATTEMPT}/chains/${seed}"
  team_id="run12-gemma4-31b-kimi26-${seed}-${SLURM_JOB_ID}"
  export AAR_TEAM_ID="${team_id}"
  export AAR_IDEA_UID_OVERRIDE="run12-${seed}-iteration-1"
  export AAR_RESUME_APPROVED_PROPOSAL=0
  export AAR_AUTODATA_RUNTIME_ENV="${chain_root}/metadata/autodata-runtime.env"
  # shellcheck disable=SC1090
  source "${AAR_AUTODATA_RUNTIME_ENV}"
  [ "${AAR_AUTODATA_TARGET_REQUIRED:-0}" = 1 ] || {
    echo "chain ${seed} is not target-aware" >&2
    exit 2
  }
  export AAR_AUTODATA_PROPOSAL_BINDINGS="${chain_root}/secrets/proposal-bindings.json"
  export AAR_VLLM_MERGED_ROOT="${AAR_RUN12_CHECKPOINT_ROOT:?}/chains/${seed}/merged_candidates"
  AAR_AUTODATA_CAPABILITY="$(<"${chain_root}/secrets/capability")"
  export AAR_AUTODATA_CAPABILITY
  launch_log="${chain_root}/logs/initial-launch.txt"
  bash "${REPO}/scripts/launch_team.sh" "${seed}" 1 72 | tee "${launch_log}"
  evaluator="$(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${launch_log}")"
  chain="$(awk -v seed="${seed}" '$0 ~ "^\\[team\\] chain " seed " -> job [0-9]+$"{print $NF}' "${launch_log}")"
  if [ "${AAR_START_EVAL_WORKER}" = 0 ]; then
    evaluator="-"
  fi
  if [ -z "${evaluator}" ] || [ -z "${chain}" ]; then
    echo "missing child jobs for ${seed}" >&2
    exit 1
  fi
  controller="$(sbatch --parsable --dependency="afterany:${chain}" \
    --output="${chain_root}/logs/controller-%j.out" --export=ALL \
    "${REPO}/experiments/dishonest_sycophancy_concealing/run_12/slurm/chain_controller.sbatch" \
    "${seed}" "${team_id}" "${chain}")"
  printf '%s\t%s\t%s\t%s\n' "${seed}" "${evaluator}" "${chain}" "${controller}" \
    | tee -a "${children}"
done

[ "$(wc -l < "${children}")" -eq "${CHAIN_COUNT}" ] || { echo "did not launch all configured chains" >&2; exit 1; }
printf 'research_backend=kimi\nresearch_model=Kimi-K2.6\nchains=%s\ntarget_pairs_per_chain=%s\nseeds=%s\n' \
  "${CHAIN_COUNT}" "${TARGET_PAIRS}" "${SEEDS_RAW}" \
  > "${ATTEMPT}/metadata/full-launch.env"
echo "[run12] ${CHAIN_COUNT} isolated Kimi chain(s) launched; controllers will rotate each chain target after every durable iteration"
