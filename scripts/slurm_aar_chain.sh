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

# --- agent authentication + web mode ---
# Match the working FAIR librarian route: prefer Meta's authenticated Claude CLI
# when it advertises secure-internet mode. The integrity monitor uses Claude
# Opus 4.8 through FAIR Model API by default; its key is moved to a
# monitor-specific name so the internet-enabled agent child cannot use it.
if [ -z "${CLAUDE_CLI_PATH:-}" ]; then
  CLAUDE_CLI_PATH="$(command -v claude || true)"
fi
_requested_web="${AAR_WEB_MODE:-auto}"
case "${_requested_web}" in auto|meta_secure|native_web) ;; *)
  echo "[aar] ERROR: AAR_WEB_MODE must be auto, meta_secure, or native_web" >&2; exit 2;;
esac
_detected_web=native_web
if [ -n "${CLAUDE_CLI_PATH:-}" ] && [ -x "${CLAUDE_CLI_PATH}" ]; then
  _cli_help="$("${CLAUDE_CLI_PATH}" --help 2>&1 || true)"
  case "${_cli_help}" in *--secure-internet-mode*) _detected_web=meta_secure;; esac
  unset _cli_help
fi
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
if [ "${AAR_WEB_MODE}" = meta_secure ]; then
  [ -x "${CLAUDE_CLI_PATH:-}" ] || { echo "[aar] ERROR: meta_secure requires an executable Claude CLI" >&2; exit 2; }
  [ -x "${REPO}/scripts/aar-paper-search" ] || { echo "[aar] ERROR: paper-search helper is not executable" >&2; exit 2; }
  export CLAUDE_CLI_PATH META_CLAUDE_SECURE_INTERNET_MODE=1
  unset ANTHROPIC_API_KEY
elif [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[aar] ERROR: native_web mode requires ANTHROPIC_API_KEY" >&2
  exit 2
fi
unset _requested_web _detected_web

PY="${HARNESS_PY}"
[ -x "${PY}" ] || { echo "[aar] ERROR: Python is not executable: ${PY}" >&2; exit 2; }
cd "${REPO}"

# Per-chain MEMORY file (NOT shared between chains), under THIS team's logs/ folder.
# Parallel chains must not read or append each other's AGENT_LOG. Seed an explicit
# iteration-1 stub so a fresh chain reads a REAL "no history" note instead of
# confabulating past results (observed: a fresh chain invented 3 fake prior
# iterations). A fresh team gets a fresh TEAM_DIR, so it always starts clean.
CHAIN_TAG="$(printf '%s' "${MODEL:-qwen}-${SEED}" | tr -cs 'A-Za-z0-9' '_' | sed 's/^_//; s/_$//')"
export AAR_AGENT_LOG_PATH="${SESSION_LOGS_DIR}/AGENT_LOG_${CHAIN_TAG}.md"
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
  "${PY}" scripts/publish_suite.py --emit-prompt-baselines "${BASELINES_PATH}" \
    --suite "${SUITE_NAME}" --target-model "${TARGET_MODEL}"
fi

echo "[aar] launching chain seed=${SEED} suite=${SUITE_NAME} target=${TARGET_MODEL} (max ${MAX_H}h)"
# Export IDEA_UID/IDEA_NAME so share_finding's payload tags each forum finding
# with its chain identity (the launcher previously only passed --idea-uid as a
# CLI arg, so findings came back with idea_uid=None — fixed here). RUN_ID is left
# UNSET on purpose so evaluate_model mints a unique per-call id (IDEA_UID+ts).
# MODEL in the identity so a same-axis/different-model team gets distinct session
# ids, method-dir prefixes, and forum finding tags (no cross-team collision).
IDEA_UID="${MODEL:-qwen}-${SEED}-$(date +%s)"
export IDEA_UID
export IDEA_NAME="${MODEL:-qwen}-${SEED}"
# Training/evaluation jobs reload their own credentials from HARNESS_ENV. Keep
# unrelated secrets out of the internet-enabled Claude child.
unset MODEL_API_KEY LLAMA_API_KEY HF_TOKEN HUGGING_FACE_HUB_TOKEN OAI_API OPENAI_API_KEY
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN RUNPOD_API_KEY WANDB_API_KEY
PYTHONUNBUFFERED=1 "${PY}" -u run.py agent --idea-uid "${IDEA_UID}" --idea-name "${IDEA_NAME}" \
  --max-iterations "${MAX_ITERS}" --max-runtime "${FULL_AUTO_MAX_RUNTIME_SECONDS}" --local
echo "=== DONE ==="
