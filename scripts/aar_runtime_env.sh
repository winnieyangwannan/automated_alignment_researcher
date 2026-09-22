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
_AAR_ENV_FILE="${HARNESS_ENV:-${_AAR_RESOLVED_REPO}/.env}"
_AAR_PRESERVE=(
  AAR_REPO HARNESS_PY HARNESS_ENV AAR_RUNTIME_ROOT WORKSPACE_DIR
  AXIS MODEL TARGET_MODEL BASELINES_PATH TEAM_DIR
  AAR_SLURM_ACCOUNT AAR_SLURM_PARTITION AAR_AGENT_QOS AAR_TRAIN_QOS AAR_EVAL_QOS
  AAR_TRAIN_GPUS AAR_EVAL_GPUS AAR_EVAL_GPU_CAP AAR_EVAL_IDLE_SECONDS
  AAR_FUNCTIONAL_SMOKE AAR_START_EVAL_WORKER AAR_KEEP_CHECKPOINTS
  AAR_WEB_MODE AAR_AGENT_MODEL AAR_MONITOR_BACKEND MONITOR_MODEL CLAUDE_CLI_PATH
  AAR_MONITOR_MODEL_API_KEY
  ANTHROPIC_API_KEY ANT_high_prio_API ANT_API_KEY
  MODEL_API_KEY LLAMA_API_KEY HF_TOKEN HUGGING_FACE_HUB_TOKEN OAI_API OPENAI_API_KEY
  HF_HOME JUDGE_BACKEND JUDGE_MODEL MASK_JUDGE_MODEL JUDGE_MODEL_LOCAL
  JUDGE_CONCURRENCY ANTHROPIC_MIN_INTERVAL_S
  AAR_BENCHMARK_DOCS BENCHMARK_DOCS_DIR HOLDOUT_DIR HELDOUT_SCORES_DIR
  SUBMISSIONS_DIR SCORES_DIR LOCAL_FINDINGS_DIR AAR_IDEAS_DIR SESSION_LOGS_DIR
  LIT_AXIS_DIR LIT_FORUM_DIR LITREVIEW_MIN LITREVIEW_SKIP LITREVIEW_REFRESH
)
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
export HARNESS_ENV="${_AAR_ENV_FILE}"
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
