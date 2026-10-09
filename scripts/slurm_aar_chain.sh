#!/bin/bash
#SBATCH --job-name=aar-chain
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=48:00:00
#SBATCH --output=slurm-%x-%j.out
#
# The chain is CPU-only. Training is always submitted as a separate GPU job by
# scripts/submit_train_job.sh; the evaluator is another independently allocated job.
# Launch one autonomous AAR chain against a safety-axis submit-model suite. The axis
# (suite, held-out, property, objective, seed, target model) comes from scripts/axis_env.sh
# (default sycophancy; override with AXIS=<name> -> scripts/axis/<name>.env).
# The agent (Claude) iteratively writes methods, trains a model, then calls the
# evaluate_model tool which STAGES the model and POLLS for scores — a separate
# eval worker (running as the secret-holding user) does the scoring against the
# mode-700 holdout. This chain runs as the research user and never reads the
# holdout. Run several with different --job-name for N parallel chains that see
# each other on the leaderboard.
#
# PREREQ: an eval worker must be draining the queue. As the eval user, run once:
#   sbatch scripts/eval_worker.sh sycophancy
#
# Usage: sbatch --job-name=aar-syco-v1 scripts/slurm_aar_chain.sh <seed_name> [max_hours]

set -euo pipefail
SEED="${1:-explore}"
MAX_H="${2:-47}"               # wall-clock safety (under the 48h Slurm limit)
MAX_ITERS="${3:-500}"         # hard cap on iterations (= sessions) per chain (default 500 as of 2026-06-20; the 47h walltime usually binds before this)
# TEAM_ID scopes the forum: every AAR in the SAME team launch shares one forum
# and accumulates into it; a NEW team (next launch) gets its OWN new forum. The
# team launcher (scripts/launch_team.sh) generates one TEAM_ID and passes it to
# every chain. Fallback below is only for a one-off single-chain run.
TEAM_ID="${4:-${TEAM_ID:-team-$(date +%Y%m%d-%H%M%S)}}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
elif [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/aar" ]; then
  REPO="$(cd -- "${SLURM_SUBMIT_DIR}" && pwd)"
elif [ -d "${SCRIPT_DIR}/../aar" ]; then
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
else
  echo "[aar] ERROR: repository not found; set AAR_REPO or submit from the repository root" >&2
  exit 2
fi
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

# --- harness wiring ---
# PER-AXIS CONFIG lives in ONE place: scripts/axis_env.sh (sourced here). It sets
# PROMPT_TEMPLATE, SUITE_NAME, HELD_OUT_BENCH, SAFETY_PROPERTY, SAFETY_OBJECTIVE,
# SEED_METHOD, TARGET_MODEL — the complete axis swap surface. The team launcher sources
# the SAME file, so they can't disagree. Switch axes by editing axis_env.sh or running
# with AXIS=<name> (scripts/axis/<name>.env). The prompt is generic — it renders the
# property/objective/benchmarks from these + benchmark_docs/<SUITE_NAME>/baseline.json.
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
export HARNESS_TRANSPORT=fs
# Hardened isolation: do NOT export HOLDOUT_DIR here — the research user (this
# job, and the agent it spawns) cannot read the holdout. The eval worker reads
# it. The agent's evaluate_model tool stages the model and polls for scores.
export EVAL_VIA_WORKER=true
export LOCAL_MODE=true            # no S3 / no RunPod / no central server
export AAR_MODE=true
export FULL_AUTO_MAX_RUNTIME_SECONDS=$(( MAX_H * 3600 ))
export MAX_ITERATIONS="${MAX_ITERS}"   # stop after this many iterations (whichever first)
export FORUM_BACKEND=fs           # default under LOCAL_MODE; explicit for clarity
# ===========================================================================
# ONE FOLDER PER TEAM. Everything this team produces lives under TEAM_DIR=
# aar_teams/<TEAM_ID>/ — findings (forum/), the train/eval queue (submissions/,
# scores/), generated method code (methods/), logs/, and the team's OWN in-run
# literature (litreview/). The launcher exports these; we honor them (`:-`) and
# fall back to deriving from TEAM_DIR so a one-off single-chain run also consolidates.
# (Exception: the axis-wide literature BASELINE is shared per-axis at aar_litreview/<axis>/.)
# ===========================================================================
export TEAM_DIR="${TEAM_DIR:-${AAR_RUNTIME_ROOT}/aar_teams/${TEAM_ID}}"
mkdir -p "${TEAM_DIR}"/{forum,submissions,scores,methods,logs,litreview,_train}
export LOCAL_FINDINGS_DIR="${LOCAL_FINDINGS_DIR:-${TEAM_DIR}/forum}"
export SUBMISSIONS_DIR="${SUBMISSIONS_DIR:-${TEAM_DIR}/submissions}"
export SCORES_DIR="${SCORES_DIR:-${TEAM_DIR}/scores}"
export AAR_IDEAS_DIR="${AAR_IDEAS_DIR:-${TEAM_DIR}/methods}"      # where the agent writes method packages
export SESSION_LOGS_DIR="${SESSION_LOGS_DIR:-${TEAM_DIR}/logs}"   # per-session transcripts (config.LOGS_DIR)
export LIT_FORUM_DIR="${LIT_FORUM_DIR:-${TEAM_DIR}/litreview}"    # team's OWN in-run lit (private)
export LIT_AXIS_DIR="${LIT_AXIS_DIR:-${REPO}/_runs/litreview/${AXIS:-sycophancy}}"  # axis baseline (read-only)
echo "[aar] team=${TEAM_ID}  TEAM_DIR=${TEAM_DIR}"
echo "[aar] forum=${LOCAL_FINDINGS_DIR}  methods=${AAR_IDEAS_DIR}  lit(team)=${LIT_FORUM_DIR}  lit(axis)=${LIT_AXIS_DIR}"

# AutoData broker readiness is probed before the later research-agent setup, so
# establish the trusted harness interpreter before either path can use it.
PY="${HARNESS_PY}"
[ -x "${PY}" ] || { echo "[aar] ERROR: Python is not executable: ${PY}" >&2; exit 2; }

_autodata_broker_pid=''
_autodata_broker_database=''
_autodata_broker_database_retained=''
_autodata_supervisor_pid=''
_autodata_native_state=''
_autodata_native_state_retained=''
snapshot_autodata_broker_database() {
  if [ -n "${_autodata_broker_database}" ] \
      && [ -f "${_autodata_broker_database}" ] \
      && [ -n "${_autodata_broker_database_retained}" ]; then
    "${AAR_AUTODATA_BROKER_PYTHON:-python3}" -c \
      'import sqlite3,sys; connection=sqlite3.connect(sys.argv[1]); connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall(); connection.close()' \
      "${_autodata_broker_database}"
    _autodata_broker_database_staging="${_autodata_broker_database_retained}.tmp.$$"
    cp -- "${_autodata_broker_database}" "${_autodata_broker_database_staging}"
    chmod 600 "${_autodata_broker_database_staging}"
    mv -- "${_autodata_broker_database_staging}" "${_autodata_broker_database_retained}"
  fi
}
cleanup_autodata_broker() {
  if [ -n "${_autodata_supervisor_pid}" ] && kill -0 "${_autodata_supervisor_pid}" 2>/dev/null; then
    kill "${_autodata_supervisor_pid}" 2>/dev/null || true
    wait "${_autodata_supervisor_pid}" 2>/dev/null || true
  fi
  if [ -n "${_autodata_native_state}" ] \
      && [ -n "${_autodata_native_state_retained}" ] \
      && [ -f "${_autodata_native_state}" ]; then
    "${PY}" "${REPO}/scripts/autodata_lifecycle_supervisor.py" snapshot \
      --state "${_autodata_native_state}" \
      --retained-state "${_autodata_native_state_retained}" \
      --reason chain-cleanup >/dev/null || true
  fi
  if [ -n "${_autodata_broker_pid}" ] && kill -0 "${_autodata_broker_pid}" 2>/dev/null; then
    kill "${_autodata_broker_pid}" 2>/dev/null || true
    wait "${_autodata_broker_pid}" 2>/dev/null || true
  fi
  snapshot_autodata_broker_database || true
}
trap cleanup_autodata_broker EXIT
if [ "${AAR_AUTODATA:-0}" = 1 ]; then
  : "${AAR_AUTODATA_CHECKOUT:?missing canonical AutoData checkout}"
  : "${AAR_AUTODATA_PLUGIN_ROOT:?missing pinned AutoData plugin root}"
  : "${AAR_AUTODATA_BROKER_PYTHON:?missing broker Python}"
  : "${AAR_AUTODATA_BROKER_RUNNER:?missing broker runner}"
  : "${AAR_AUTODATA_MODEL_ENV_FILE:?missing model workload env path}"
  : "${AAR_AUTODATA_CAMPAIGN_POLICY:?missing campaign policy}"
  : "${AAR_AUTODATA_CAPABILITY:?missing attempt-scoped broker capability}"
  : "${AAR_AUTODATA_APPROVAL_PRIVATE_KEY:?missing delegated approval key}"
  : "${AAR_AUTODATA_APPROVAL_PUBLIC_KEY:?missing delegated approval public key}"
  export AUTODATA_CACHE_DIR="${AUTODATA_CACHE_DIR:-${AAR_RUNTIME_ROOT}/autodata/plugin-cache}"
  mkdir -p "${AUTODATA_CACHE_DIR}"
  chmod 700 "${AUTODATA_CACHE_DIR}"
  export AAR_AUTODATA_WRAPPER_PYTHON
  AAR_AUTODATA_WRAPPER_PYTHON="$(
    AUTODATA_CACHE_DIR="${AUTODATA_CACHE_DIR}" \
      "${AAR_AUTODATA_BROKER_PYTHON}" \
      "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/bootstrap.py"
  )"
  [ -x "${AAR_AUTODATA_WRAPPER_PYTHON}" ] || {
    echo "[aar] ERROR: AutoData plugin bootstrap did not return an executable" >&2
    exit 2
  }
  "${AAR_AUTODATA_WRAPPER_PYTHON}" -c \
    'import autodata,autodata.engine; assert autodata.__version__ == "1.0.0"' || {
      echo "[aar] ERROR: bootstrapped AutoData plugin import failed" >&2
      exit 2
    }
  echo "[aar] AutoData plugin bootstrap verified (cache=attempt-local, interpreter=pinned)"
  _autodata_root="${TEAM_DIR}/autodata/broker"
  mkdir -p "${_autodata_root}"
  chmod 700 "${TEAM_DIR}/autodata" "${_autodata_root}"
  _autodata_broker_database_root="${SLURM_TMPDIR:-/tmp}/aar-autodata-broker-${SLURM_JOB_ID:-$$}"
  mkdir -p "${_autodata_broker_database_root}"
  chmod 700 "${_autodata_broker_database_root}"
  _autodata_broker_database="${_autodata_broker_database_root}/broker.db"
  _autodata_broker_database_retained="${_autodata_root}/broker.db"
  if [ -f "${_autodata_broker_database_retained}" ]; then
    cp -- "${_autodata_broker_database_retained}" "${_autodata_broker_database}"
    chmod 600 "${_autodata_broker_database}"
  fi
  _autodata_native_state_retained="${TEAM_DIR}/autodata/native/state.db"
  export AAR_AUTODATA_RETAINED_STATE="${_autodata_native_state_retained}"
  if [ "${AAR_AUTODATA_LIFECYCLE_SUPERVISED:-0}" = 1 ]; then
    _autodata_native_database_root="${SLURM_TMPDIR:-/tmp}/aar-autodata-native-${SLURM_JOB_ID:-$$}"
    mkdir -p "${_autodata_native_database_root}"
    chmod 700 "${_autodata_native_database_root}"
    _autodata_native_state="${_autodata_native_database_root}/state.db"
    "${PY}" "${REPO}/scripts/autodata_lifecycle_supervisor.py" restore \
      --state "${_autodata_native_state}" \
      --retained-state "${_autodata_native_state_retained}" \
      --require-manifest >/dev/null
    export AAR_AUTODATA_STATE="${_autodata_native_state}"
  else
    _autodata_native_state="${_autodata_native_state_retained}"
    export AAR_AUTODATA_STATE="${_autodata_native_state}"
  fi
  export AAR_AUTODATA_ARTIFACTS="${TEAM_DIR}/autodata/native/artifacts"
  export AAR_AUTODATA_WORKSPACES="${TEAM_DIR}/autodata/native/workspaces"
  export AAR_AUTODATA_SUPERVISOR_CONTROL="${TEAM_DIR}/autodata/native/lifecycle-control.json"
  export AAR_AUTODATA_APPROVAL_AUDIT_DIR="${TEAM_DIR}/autodata/approvals"
  mkdir -p "$(dirname -- "${AAR_AUTODATA_STATE}")" "${AAR_AUTODATA_ARTIFACTS}" \
    "${AAR_AUTODATA_WORKSPACES}" "${AAR_AUTODATA_APPROVAL_AUDIT_DIR}"
  chmod 700 "${TEAM_DIR}/autodata/native" "${AAR_AUTODATA_ARTIFACTS}" \
    "${AAR_AUTODATA_WORKSPACES}" "${AAR_AUTODATA_APPROVAL_AUDIT_DIR}"
  _autodata_capability_file="${_autodata_root}/capability"
  printf '%s\n' "${AAR_AUTODATA_CAPABILITY}" > "${_autodata_capability_file}"
  chmod 600 "${_autodata_capability_file}"
  _autodata_port=$(( 10000 + (${SLURM_JOB_ID:-8791} % 40000) ))
  export AAR_AUTODATA_BROKER_URL="http://127.0.0.1:${_autodata_port}"
  _autodata_broker_args=(
    --runner "${AAR_AUTODATA_BROKER_RUNNER}"
    --root "${_autodata_root}"
    --database "${_autodata_broker_database}"
    --host 127.0.0.1 --port "${_autodata_port}"
    --max-concurrent "${AAR_AUTODATA_CONCURRENCY:?}"
    --auth-token-file "${_autodata_capability_file}"
    --workload-env-file "${AAR_AUTODATA_MODEL_ENV_FILE}"
    --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY}"
    --anonymous-registry docker.io
  )
  if [ "${AAR_AUTODATA_BROKER_RUNNER}" = sandoq-firecracker ]; then
    : "${AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE:?missing SandoQ token path}"
    _autodata_broker_args+=(
      --gateway-url "${SANDOQ_GATEWAY_URL:-https://sandoq-gateway.eks-prod.cf.aws.metafb.cloud}"
      --execsidecar-token-file "${AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE}"
      --no-registry-preflight
    )
  elif [ "${AAR_AUTODATA_BROKER_RUNNER}" != local-bwrap ]; then
    echo "[aar] ERROR: unsupported AutoData broker runner: ${AAR_AUTODATA_BROKER_RUNNER}" >&2
    exit 2
  fi
  PYTHONPATH="${AAR_AUTODATA_CHECKOUT}/src" \
    "${AAR_AUTODATA_BROKER_PYTHON}" -m autodata.broker.cli \
      "${_autodata_broker_args[@]}" \
      > "${TEAM_DIR}/logs/autodata-broker.log" 2>&1 &
  _autodata_broker_pid=$!
  for _autodata_probe in $(seq 1 60); do
    if "${PY}" -c 'import os,urllib.request; r=urllib.request.Request(os.environ["AAR_AUTODATA_BROKER_URL"]+"/healthz",headers={"Authorization":"Bearer "+os.environ["AAR_AUTODATA_CAPABILITY"]}); urllib.request.urlopen(r,timeout=2).read()' 2>/dev/null; then
      break
    fi
    kill -0 "${_autodata_broker_pid}" 2>/dev/null || {
      echo "[aar] ERROR: AutoData broker exited during startup" >&2
      exit 2
    }
    sleep 1
  done
  kill -0 "${_autodata_broker_pid}" 2>/dev/null || { echo "[aar] ERROR: AutoData broker is not running" >&2; exit 2; }
  echo "[aar] campaign-scoped AutoData broker ready (pid=${_autodata_broker_pid}, runner=${AAR_AUTODATA_BROKER_RUNNER}, concurrency=${AAR_AUTODATA_CONCURRENCY}, database=node-local)"
  if [ "${AAR_AUTODATA_LIFECYCLE_SUPERVISED:-0}" = 1 ]; then
    "${PY}" "${REPO}/scripts/autodata_lifecycle_supervisor.py" run \
      --python "${AAR_AUTODATA_WRAPPER_PYTHON}" \
      --state "${AAR_AUTODATA_STATE}" \
      --retained-state "${AAR_AUTODATA_RETAINED_STATE}" \
      --control-file "${AAR_AUTODATA_SUPERVISOR_CONTROL}" \
      --artifacts "${AAR_AUTODATA_ARTIFACTS}" \
      --workspaces "${AAR_AUTODATA_WORKSPACES}" \
      --lock-file "${TEAM_DIR}/autodata/native/lifecycle-supervisor.lock" \
      --status-file "${TEAM_DIR}/autodata/native/lifecycle-supervisor-status.json" \
      --log-file "${TEAM_DIR}/logs/autodata-lifecycle-supervisor.log" &
    _autodata_supervisor_pid=$!
    sleep 1
    kill -0 "${_autodata_supervisor_pid}" 2>/dev/null || {
      echo "[aar] ERROR: AutoData lifecycle supervisor exited during startup" >&2
      exit 2
    }
    echo "[aar] AutoData lifecycle supervisor ready (pid=${_autodata_supervisor_pid}, meta_timeout=2h, production_timeout=8h, state=node-local)"
  fi
  unset _autodata_broker_args _autodata_broker_database_root \
    _autodata_capability_file _autodata_probe _autodata_port \
    _autodata_native_database_root
fi

# --- agent authentication + web mode ---
# Claude remains the default. Kimi is selected only through
# AAR_AGENT_BACKEND=kimi and uses the Kimi CLI's own configured authentication.
_agent_backend="${AAR_AGENT_BACKEND:-claude}"
_requested_web="${AAR_WEB_MODE:-auto}"
case "${_requested_web}" in auto|meta_secure|native_web) ;; *)
  echo "[aar] ERROR: AAR_WEB_MODE must be auto, meta_secure, or native_web" >&2; exit 2;;
esac
_detected_web=native_web
case "${_agent_backend}" in
  claude)
    if [ -z "${CLAUDE_CLI_PATH:-}" ]; then
      CLAUDE_CLI_PATH="$(command -v claude || true)"
    fi
    if [ -n "${CLAUDE_CLI_PATH:-}" ] && [ -x "${CLAUDE_CLI_PATH}" ]; then
      _cli_help="$("${CLAUDE_CLI_PATH}" --help 2>&1 || true)"
      case "${_cli_help}" in *--secure-internet-mode*) _detected_web=meta_secure;; esac
      unset _cli_help
    fi
    ;;
  kimi)
    if [ -z "${KIMI_CLI_PATH:-}" ]; then
      KIMI_CLI_PATH="$(command -v kimi || true)"
    fi
    [ -x "${KIMI_CLI_PATH:-}" ] || { echo "[aar] ERROR: Kimi backend requires KIMI_CLI_PATH or kimi on PATH" >&2; exit 2; }
    [ "${_requested_web}" != meta_secure ] || { echo "[aar] ERROR: meta_secure web mode is Claude-only" >&2; exit 2; }
    export KIMI_CLI_PATH
    ;;
  *) echo "[aar] ERROR: AAR_AGENT_BACKEND must be claude or kimi" >&2; exit 2;;
esac
if [ "${_requested_web}" = auto ]; then
  export AAR_WEB_MODE="${_detected_web}"
else
  export AAR_WEB_MODE="${_requested_web}"
fi
export AAR_MONITOR_BACKEND="${AAR_MONITOR_BACKEND:-model_api}"
case "${AAR_MONITOR_BACKEND}" in
  model_api)
    export MONITOR_MODEL="${MONITOR_MODEL:-claude-4-8-opus}"
    export AAR_MONITOR_MODEL_API_KEY="${AAR_MONITOR_MODEL_API_KEY:-${MODEL_API_KEY:-}}"
    [ -n "${AAR_MONITOR_MODEL_API_KEY}" ] || {
      echo "[aar] ERROR: Model API monitor needs MODEL_API_KEY in ${HARNESS_ENV}" >&2
      exit 2
    }
    ;;
  anthropic)
    export MONITOR_MODEL="${MONITOR_MODEL:-claude-opus-4-8}"
    export AAR_MONITOR_ANTHROPIC_API_KEY="${AAR_MONITOR_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY:-${ANT_high_prio_API:-${ANT_API_KEY:-}}}}"
    [ -n "${AAR_MONITOR_ANTHROPIC_API_KEY}" ] || {
      echo "[aar] ERROR: Anthropic monitor needs a direct key in ${HARNESS_ENV}" >&2
      exit 2
    }
    ;;
  *) echo "[aar] ERROR: AAR_MONITOR_BACKEND must be model_api or anthropic" >&2; exit 2;;
esac
if [ "${_agent_backend}" = claude ] && [ "${AAR_WEB_MODE}" = meta_secure ]; then
  [ -x "${CLAUDE_CLI_PATH:-}" ] || { echo "[aar] ERROR: meta_secure requires an executable Claude CLI" >&2; exit 2; }
  [ -x "${REPO}/scripts/aar-paper-search" ] || { echo "[aar] ERROR: paper-search helper is not executable" >&2; exit 2; }
  export CLAUDE_CLI_PATH META_CLAUDE_SECURE_INTERNET_MODE=1
  unset ANTHROPIC_API_KEY
elif [ "${_agent_backend}" = claude ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[aar] ERROR: native_web mode requires ANTHROPIC_API_KEY" >&2
  exit 2
fi
unset _agent_backend _requested_web _detected_web

# The research model has Bash/Read access, so same-UID environment
# scrubbing is insufficient by itself.  Put Claude Code in a mount/PID
# namespace that cannot see the operator's home or the run secret directory.
# The trusted Python parent remains outside for monitor credentials.
if [ "${AAR_RESEARCH_ENV_ISOLATION:-0}" = 1 ]; then
  command -v bwrap >/dev/null || {
    echo "[aar] ERROR: research environment isolation requires bwrap" >&2
    exit 2
  }
  [ -x "${REPO}/scripts/claude_research_bwrap.sh" ] || {
    echo "[aar] ERROR: Claude research sandbox wrapper is not executable" >&2
    exit 2
  }
  export AAR_CLAUDE_REAL_CLI_PATH="${CLAUDE_CLI_PATH:?missing real Claude CLI}"
  export CLAUDE_CLI_PATH="${REPO}/scripts/claude_research_bwrap.sh"
  # Fail before spending an agent call if the production mount boundary cannot
  # be constructed.  /bin/bash stands in for Claude only for this canary.
  # shellcheck disable=SC2016  # variables intentionally expand inside sandbox
  AAR_CLAUDE_REAL_CLI_PATH=/bin/bash "${CLAUDE_CLI_PATH}" -c '
    set -eu
    [ ! -s "$AAR_REPO/.env" ]
    [ ! -s "$AAR_REPO/.sandoq-firecracker-token" ]
    [ ! -e "$HOME/.ssh" ]
    if [ -d "$AAR_RUNTIME_ROOT/secrets" ]; then
      [ -z "$(find "$AAR_RUNTIME_ROOT/secrets" -mindepth 1 -print -quit)" ]
    fi
    touch "$AAR_RUNTIME_ROOT/.research-sandbox-write-canary"
    rm -f "$AAR_RUNTIME_ROOT/.research-sandbox-write-canary"
    if [ -d /var/slurm-tmp ]; then
      touch /var/slurm-tmp/.aar-research-sandbox-write-canary
      rm -f /var/slurm-tmp/.aar-research-sandbox-write-canary
    fi
  '
  echo "[aar] Claude research mount/PID namespace verified"
  # Exercise the real Meta launcher before a research session is counted. This
  # catches native-binary selection, sandbox ownership, and launcher startup
  # failures that a /bin/bash mount probe alone cannot detect.
  "${CLAUDE_CLI_PATH}" --version >/dev/null
  echo "[aar] Claude research launcher verified"
fi

cd "${REPO}"

# Per-chain MEMORY file (NOT shared between chains), under THIS team's logs/ folder.
# Parallel chains must not read or append each other's AGENT_LOG. Seed an explicit
# iteration-1 stub so a fresh chain reads a REAL "no history" note instead of
# confabulating past results (observed: a fresh chain invented 3 fake prior
# iterations). A fresh team gets a fresh TEAM_DIR, so it always starts clean.
CHAIN_TAG="$(printf '%s' "${MODEL:-qwen}-${SEED}" | tr -cs 'A-Za-z0-9' '_' | sed 's/^_//; s/_$//')"
export AAR_AGENT_LOG_PATH="${SESSION_LOGS_DIR}/AGENT_LOG_${CHAIN_TAG}.md"
mkdir -p "${TEAM_DIR}/timings"
export AAR_PHASE_TIMINGS_PATH="${TEAM_DIR}/timings/chain_${CHAIN_TAG}.jsonl"
if [ ! -f "${AAR_AGENT_LOG_PATH}" ] && [ -n "${AAR_RECOVERED_AGENT_LOG_DIR:-}" ]; then
  _recovered_log_dir="$(realpath -e -- "${AAR_RECOVERED_AGENT_LOG_DIR}")"
  _recovered_log="${_recovered_log_dir}/AGENT_LOG_${CHAIN_TAG}.md"
  [ -f "${_recovered_log}" ] || {
    echo "[aar] ERROR: recovered agent log is missing for ${CHAIN_TAG}" >&2
    exit 2
  }
  cp -- "${_recovered_log}" "${AAR_AGENT_LOG_PATH}"
  chmod 600 "${AAR_AGENT_LOG_PATH}"
  echo "[aar] seeded recovered chain memory from ${_recovered_log}"
  unset _recovered_log_dir _recovered_log
fi
if [ ! -f "${AAR_AGENT_LOG_PATH}" ]; then
  printf '# AGENT_LOG — chain %s\n\n## ITERATION 1 — NO PRIOR HISTORY\nThis chain has run NO prior iterations. You have NO past results, scores, or methods yet.\nDo NOT invent or recall any prior iteration — begin from the literature + leaderboard.\nRecord each iteration below as you complete it.\n' "${SEED}" > "${AAR_AGENT_LOG_PATH}"
fi

# Prompt/dashboard baseline table for THIS axis+model. BASELINES_PATH is set by axis_env.sh
# (tagged by axis+model). If the eval user already published the authoritative per-model
# baselines (publish_holdout.sh, from benchmark_docs), USE IT — don't clobber. Otherwise
# self-provision from the PUBLISHERS fallback (exact for qwen; WARNs for un-measured models).
# Held-out-excluded either way. _format_baselines + the monitor + the dashboard read this path.
if [ -f "${BASELINES_PATH}" ]; then
  echo "[aar] using pre-published baselines: ${BASELINES_PATH}"
else
  _ONLY_ARGS=()
  if [ -n "${AAR_SUITE_BENCHMARKS:-}" ]; then
    _only_text="${AAR_SUITE_BENCHMARKS//,/ }"
    read -r -a _only_names <<< "${_only_text}"
    _ONLY_ARGS=(--only "${_only_names[@]}")
  fi
  "${PY}" scripts/publish_suite.py --emit-prompt-baselines "${BASELINES_PATH}" \
    --suite "${SUITE_NAME}" --target-model "${TARGET_MODEL}" "${_ONLY_ARGS[@]}"
fi

echo "[aar] launching chain seed=${SEED} suite=${SUITE_NAME} target=${TARGET_MODEL} (max ${MAX_H}h)"
# Export IDEA_UID/IDEA_NAME so share_finding's payload tags each forum finding
# with its chain identity (the launcher previously only passed --idea-uid as a
# CLI arg, so findings came back with idea_uid=None — fixed here). RUN_ID is left
# UNSET on purpose so evaluate_model mints a unique per-call id (IDEA_UID+ts).
# MODEL in the identity so a same-axis/different-model team gets distinct session
# ids, method-dir prefixes, and forum finding tags (no cross-team collision).
IDEA_UID="${AAR_IDEA_UID_OVERRIDE:-${MODEL:-qwen}-${SEED}-$(date +%s)}"
export IDEA_UID
export IDEA_NAME="${MODEL:-qwen}-${SEED}"
# The evaluator was launched by the operator before this research job and
# retains its credential environment.  Training needs no provider credential.
# Keep raw credentials and every operator credential-file path out of the
# internet-enabled Claude child; agent.py independently enforces the same rule
# at the SDK subprocess boundary for purpose-specific monitor secrets.
unset MODEL_API_KEY LLAMA_API_KEY HF_TOKEN HUGGING_FACE_HUB_TOKEN OAI_API OPENAI_API_KEY
unset ANTHROPIC_API_KEY ANT_high_prio_API ANT_API_KEY HARNESS_ENV
unset AAR_RUN8_EXECSIDECAR_TOKEN_FILE AAR_RUN8_BROKER_TOKEN_FILE
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN RUNPOD_API_KEY WANDB_API_KEY
if [ "${AAR_AGENT_BACKEND:-claude}" = kimi ]; then
  unset ANTHROPIC_API_KEY ANT_high_prio_API ANT_API_KEY CLAUDE_CLI_PATH
fi
if [ "${AAR_HIDE_EVAL_CONFIG:-0}" = "1" ]; then
  # The evaluator has already inherited what it needs. Do not advertise the
  # run-specific full suite selection or baseline override to the researcher.
  unset HOLDOUT_DIR HELDOUT_SCORES_DIR AAR_SUITE_BENCHMARKS AAR_BASELINE_OVERRIDES
fi
PYTHONUNBUFFERED=1 "${PY}" -u run.py agent --idea-uid "${IDEA_UID}" --idea-name "${IDEA_NAME}" \
  --max-iterations "${MAX_ITERS}" --max-runtime "${FULL_AUTO_MAX_RUNTIME_SECONDS}" --local
if [ "${AAR_VERIFY_TWO_ITERATION_ARTIFACTS:-0}" = 1 ]; then
  "${PY}" "${REPO}/replication/verify_two_iteration_multidimensional.py" \
    --team-dir "${TEAM_DIR}" --expected-iterations 2
fi
echo "=== DONE ==="
