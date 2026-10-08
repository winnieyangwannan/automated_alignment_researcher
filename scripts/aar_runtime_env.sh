#!/bin/bash
# Shared runtime setup for AAR shell entrypoints. Source this file after setting
# REPO to the resolved repository root. Explicitly inherited values win over
# values in HARNESS_ENV; the environment file fills only missing configuration.

if [ -z "${REPO:-}" ] || [ ! -d "${REPO}/aar" ]; then
  echo "aar_runtime_env: REPO must name an AAR checkout before sourcing" >&2
  # shellcheck disable=SC2317  # this file is sourced; exit is the direct-run fallback
  return 2 2>/dev/null || exit 2
fi

_AAR_RESOLVED_REPO="$(cd -- "${REPO}" && pwd)"
# A research Slurm job can be launched with a complete, explicit allowlist and
# no credential file.  In that mode, never fall back to REPO/.env: doing so
# would undo the launch boundary merely because HARNESS_ENV was intentionally
# omitted.
case "${AAR_RUNTIME_ENV_DISABLE_FILE:-0}" in
  1|true|yes|on) _AAR_ENV_FILE="" ;;
  *) _AAR_ENV_FILE="${HARNESS_ENV:-${_AAR_RESOLVED_REPO}/.env}" ;;
esac
_AAR_PRESERVE=(
  AAR_REPO HARNESS_PY HARNESS_ENV AAR_RUNTIME_ROOT WORKSPACE_DIR
  AAR_RUNTIME_ENV_DISABLE_FILE AAR_CHAIN_SANITIZE_ENV AAR_RESEARCH_ENV_ISOLATION
  AXIS MODEL TARGET_MODEL TARGET_MODEL_PATH BASELINES_PATH TEAM_DIR
  AAR_SLURM_ACCOUNT AAR_SLURM_PARTITION AAR_AGENT_QOS AAR_TRAIN_QOS AAR_EVAL_QOS
  AAR_TRAIN_GPUS AAR_EVAL_GPUS AAR_EVAL_GPU_CAP AAR_EVAL_WORKERS AAR_EVAL_IDLE_SECONDS AAR_EVAL_TIME
  AAR_FUNCTIONAL_SMOKE AAR_START_EVAL_WORKER AAR_KEEP_CHECKPOINTS AAR_REQUIRE_ADAPTER
  AAR_NO_LOCAL_GPU
  AAR_MAX_CONCURRENT_TRAIN_JOBS AAR_SUITE_BENCHMARKS AAR_TARGET_ENABLE_THINKING
  AAR_TRAIN_EXIT_AFTER_SUBMIT
  AAR_PHASE_TIMINGS_PATH AAR_REQUIRE_PHASE_TIMINGS AAR_TRAIN_SUBMITTED_AT_NS
  EVAL_AUTO_CEILING EVAL_RUN_GEN_CEILING EVAL_RUN_BATCH EVAL_RUN_NGRAM
  EVAL_REQUIRE_EXACT_MAX_NEW_TOKENS
  MASK_GENERATION_TOKEN_BUDGET
  AAR_BASELINE_OVERRIDES AAR_EFFORT AAR_METHOD_TRAIN_MINUTES
  AAR_MULTIDIM_SCORING_CONFIRMED
  AAR_CLAUDE_SPEND_CAP_USD AAR_GPT_JUDGE_SPEND_CAP_USD AAR_OPENAI_JUDGE_SPEND_CAP_USD
  AAR_CLAUDE_SESSION_BUDGET_USD AAR_REQUIRE_SUCCESSFUL_ITERATIONS
  AAR_TARGET_SUCCESSFUL_ITERATIONS
  AAR_VERIFY_TWO_ITERATION_ARTIFACTS OVERLOADED_MAX_RETRIES
  AAR_EXPECTED_BRANCH AAR_HIDE_EVAL_CONFIG
  AAR_AUTODATA AAR_AUTODATA_PLUGIN_ROOT AAR_AUTODATA_SHA
  AAR_AUTODATA_CHECKOUT AAR_AUTODATA_RECIPE_ROOT
  AAR_AUTODATA_STATE AAR_AUTODATA_ARTIFACTS AAR_AUTODATA_WORKSPACES
  AAR_AUTODATA_BROKER_URL AAR_AUTODATA_CAPABILITY
  AAR_AUTODATA_BROKER_PYTHON AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE
  AAR_AUTODATA_MODEL_ENV_FILE AAR_AUTODATA_CAMPAIGN_POLICY
  AAR_AUTODATA_CONCURRENCY AAR_AUTODATA_META_MAX_ITERATIONS
  AAR_AUTODATA_META_MIN_ITERATIONS AAR_AUTODATA_META_EARLY_STOP_PATIENCE
  AAR_AUTODATA_TUNING_TASKS AAR_AUTODATA_VALIDATION_TASKS
  AAR_AUTODATA_TEST_TASKS AAR_AUTODATA_PRODUCTION_ROWS
  AAR_AUTODATA_PRODUCTION_INITIAL_TASKS AAR_AUTODATA_PRODUCTION_MAX_TASKS
  AAR_AUTODATA_APPROVAL_PRIVATE_KEY AAR_AUTODATA_APPROVAL_PUBLIC_KEY
  AAR_AUTODATA_APPROVAL_PUBLIC_KEY_SHA256 AAR_AUTODATA_APPROVAL_ACTOR
  AAR_AUTODATA_APPROVAL_POLICY_VERSION AAR_AUTODATA_PROPOSAL_BINDINGS
  AAR_AUTODATA_RESOURCES_READY
  AAR_SERVE_V2_DEPLOYMENT_DIR AAR_SERVE_V2_MODEL
  AAR_WEB_MODE AAR_AGENT_MODEL AAR_MONITOR_BACKEND MONITOR_MODEL CLAUDE_CLI_PATH
  META_CLAUDE_CODE_RELEASE
  AAR_MONITOR_MODEL_API_KEY
  ANTHROPIC_API_KEY ANT_high_prio_API ANT_API_KEY
  MODEL_API_KEY LLAMA_API_KEY HF_TOKEN HUGGING_FACE_HUB_TOKEN OAI_API OPENAI_API_KEY
  HF_HOME JUDGE_BACKEND JUDGE_MODEL MASK_JUDGE_MODEL JUDGE_MODEL_LOCAL
  JUDGE_CONCURRENCY ANTHROPIC_MIN_INTERVAL_S
  EVAL_RUN_GEN_CEILING_BENCHMARKS EVAL_BATCH_SIZE EVAL_NO_REPEAT_NGRAM
  EVAL_FAIL_ON_ALLOCATOR_WARNING EVAL_MAX_TRUNCATION_RATE
  EVAL_TRUNCATION_MIN_COMPLETIONS
  EVAL_INFERENCE_BACKEND EVAL_MODEL_PATH_OVERRIDE EVAL_FAIL_ON_SCORING_ERROR
  EVAL_VLLM_LORA_STRATEGY EVAL_VLLM_REQUIRE_MERGED
  EVAL_VLLM_MAX_MODEL_LEN EVAL_VLLM_MAX_NUM_SEQS EVAL_VLLM_MAX_NUM_BATCHED_TOKENS
  EVAL_VLLM_GPU_MEMORY_UTILIZATION EVAL_VLLM_ENABLE_PREFIX_CACHING
  EVAL_VLLM_ENFORCE_EAGER EVAL_VLLM_VERIFY_LORA
  AAR_VLLM_CONTAINER_IMAGE AAR_VLLM_WORKER_SH AAR_VLLM_MERGE_PY
  AAR_VLLM_MERGED_ROOT AAR_VLLM_CONTAINER_RW_MOUNT
  AAR_VLLM_EPHEMERAL_MERGED AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES
  AAR_BENCHMARK_DOCS BENCHMARK_DOCS_DIR HOLDOUT_DIR HELDOUT_SCORES_DIR
  LLM_UNCERTAINTY_SRC LLM_UNCERTAINTY_SOURCE_MANIFEST
  SUBMISSIONS_DIR SCORES_DIR LOCAL_FINDINGS_DIR AAR_IDEAS_DIR SESSION_LOGS_DIR
  LIT_AXIS_DIR LIT_FORUM_DIR LITREVIEW_CACHE_ROOT LITREVIEW_MODEL LITREVIEW_MIN LITREVIEW_SKIP LITREVIEW_REFRESH
  AAR_LIT_AXIS_READ_ONLY
  AAR_DIMENSIONS LITREVIEW_DIMENSIONS LITREVIEW_TARGET_MODEL LITREVIEW_PROMPT_VERSION
)
# Variables the research-chain wrapper may receive through Slurm. This list is
# intentionally derived from the ordinary portable runtime surface and then
# removes operator credential files and raw provider credentials. The AutoData
# plugin root and pinned SHA are non-secret inputs; production credentials stay
# outside the research child.
AAR_RESEARCH_CHAIN_ENV_ALLOWLIST=()
for _aar_candidate in "${_AAR_PRESERVE[@]}" \
  HOME USER LOGNAME SHELL PATH LANG LC_ALL TERM TZ TMPDIR PYTHONPATH; do
  case "${_aar_candidate}" in
    HARNESS_ENV|ANTHROPIC_API_KEY|ANT_high_prio_API|ANT_API_KEY|MODEL_API_KEY|LLAMA_API_KEY|HF_TOKEN|HUGGING_FACE_HUB_TOKEN|OAI_API|OPENAI_API_KEY)
      continue
      ;;
  esac
  AAR_RESEARCH_CHAIN_ENV_ALLOWLIST+=("${_aar_candidate}")
done
# The operator-side integrity monitor is part of the chain parent, not the
# Claude research subprocess.  It gets a purpose-specific credential instead
# of the general MODEL_API_KEY inherited by older launchers.
AAR_RESEARCH_CHAIN_ENV_ALLOWLIST+=(AAR_MONITOR_ANTHROPIC_API_KEY)
declare -A _AAR_WAS_SET=()
for _aar_name in "${_AAR_PRESERVE[@]}"; do
  if [[ -v "${_aar_name}" ]]; then
    _AAR_WAS_SET["${_aar_name}"]=1
  fi
done

if [ -f "${_AAR_ENV_FILE}" ]; then
  while IFS= read -r _aar_line || [ -n "${_aar_line}" ]; do
    _aar_line="${_aar_line%$'\r'}"
    case "${_aar_line}" in ''|'#'*) continue;; esac
    _aar_name="${_aar_line%%=*}"
    _aar_value="${_aar_line#*=}"
    [[ "${_aar_name}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    _aar_allowed=0
    for _aar_candidate in "${_AAR_PRESERVE[@]}"; do
      if [ "${_aar_candidate}" = "${_aar_name}" ]; then _aar_allowed=1; break; fi
    done
    [ "${_aar_allowed}" = 1 ] || continue
    [[ -v "_AAR_WAS_SET[${_aar_name}]" ]] && continue
    _aar_value="${_aar_value#"${_aar_value%%[![:space:]]*}"}"
    _aar_value="${_aar_value%"${_aar_value##*[![:space:]]}"}"
    if [[ "${_aar_value}" =~ ^(.*[^[:space:]])[[:space:]]+#.*$ ]]; then
      _aar_value="${BASH_REMATCH[1]}"
    fi
    if [[ "${_aar_value}" == \"*\" && "${_aar_value}" == *\" ]]; then
      _aar_value="${_aar_value:1:${#_aar_value}-2}"
    elif [[ "${_aar_value}" == \'*\' && "${_aar_value}" == *\' ]]; then
      _aar_value="${_aar_value:1:${#_aar_value}-2}"
    fi
    printf -v "${_aar_name}" '%s' "${_aar_value}"
    # shellcheck disable=SC2163  # export the variable whose name is in _aar_name
    export "${_aar_name}"
  done < "${_AAR_ENV_FILE}"
fi

REPO="${_AAR_RESOLVED_REPO}"
export AAR_REPO="${REPO}"
if [ -n "${_AAR_ENV_FILE}" ]; then
  export HARNESS_ENV="${_AAR_ENV_FILE}"
else
  unset HARNESS_ENV
fi
export HARNESS_PY="${HARNESS_PY:-${REPO}/.venv/bin/python}"
case "${HARNESS_PY}" in ./*) export HARNESS_PY="${REPO}/${HARNESS_PY#./}";; esac

case "${WORKSPACE_DIR:-}" in
  ''|.) export WORKSPACE_DIR="${REPO}" ;;
esac
case "${AAR_BENCHMARK_DOCS:-}" in
  ''|./benchmark_docs) export AAR_BENCHMARK_DOCS="${REPO}/benchmark_docs" ;;
esac
case "${BENCHMARK_DOCS_DIR:-}" in
  ''|./benchmark_docs) export BENCHMARK_DOCS_DIR="${REPO}/benchmark_docs" ;;
esac

export AAR_RUNTIME_ROOT="${AAR_RUNTIME_ROOT:-${REPO}/_runs}"
case "${AAR_RUNTIME_ROOT}" in ./*) export AAR_RUNTIME_ROOT="${REPO}/${AAR_RUNTIME_ROOT#./}";; esac
export HF_HOME="${HF_HOME:-${AAR_RUNTIME_ROOT}/cache/huggingface}"
export PYTHONPATH="${REPO}${PYTHONPATH:+:${PYTHONPATH}}"

# FAIR defaults. Other sites can override every field before invoking a launcher.
export AAR_SLURM_ACCOUNT="${AAR_SLURM_ACCOUNT:-ram}"
export AAR_SLURM_PARTITION="${AAR_SLURM_PARTITION:-g3}"
export AAR_AGENT_QOS="${AAR_AGENT_QOS:-g3_ram_high}"
export AAR_TRAIN_QOS="${AAR_TRAIN_QOS:-g3_ram_high}"
export AAR_EVAL_QOS="${AAR_EVAL_QOS:-g3_ram_high}"

unset _AAR_RESOLVED_REPO _AAR_ENV_FILE _AAR_PRESERVE _AAR_WAS_SET
unset _aar_name _aar_value _aar_allowed _aar_candidate _aar_line
