#!/bin/bash
#SBATCH --job-name=aar-litreview
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%x-%j.out
#
# Literature-review pre-phase: populate the team's SHARED lit forum with >=MIN
# method/paper entries before the AARs start. CPU-only — uses Claude through the
# Agent SDK and either native web tools or FAIR secure internet, no GPU.
# Usage: sbatch scripts/litreview.sh <suite> <team_id> [min]
set -euo pipefail
SUITE="${1:?usage: litreview.sh <suite> <team_id> [min]}"
TEAM_ID="${2:?team_id}"
MIN="${3:-30}"
case "${MIN}" in
  ''|*[!0-9]*) echo "[litreview] ERROR: min must be a non-negative integer" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
elif [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/aar" ]; then
  # Under sbatch, BASH_SOURCE may be a copy in Slurm's spool rather than this checkout.
  REPO="$(cd -- "${SLURM_SUBMIT_DIR}" && pwd)"
elif [ -d "${SCRIPT_DIR}/../aar" ]; then
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
else
  echo "[litreview] ERROR: repository not found; set AAR_REPO or submit from the repository root" >&2
  exit 2
fi
export PYTHONPATH="${REPO}${PYTHONPATH:+:${PYTHONPATH}}"

# Load the worktree-local environment without scraping or printing secrets. An
# already-exported key wins, which makes explicit sbatch --export overrides safe.
ENV_FILE="${HARNESS_ENV:-${REPO}/.env}"
_INHERITED_ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY-}"
_INHERITED_CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH-}"
if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090  # caller-selected, trusted environment file
  . "${ENV_FILE}"
  set +a
fi
if [ -n "${_INHERITED_ANTHROPIC_API_KEY}" ]; then
  export ANTHROPIC_API_KEY="${_INHERITED_ANTHROPIC_API_KEY}"
fi
if [ -n "${_INHERITED_CLAUDE_CLI_PATH}" ]; then
  export CLAUDE_CLI_PATH="${_INHERITED_CLAUDE_CLI_PATH}"
fi
unset _INHERITED_ANTHROPIC_API_KEY _INHERITED_CLAUDE_CLI_PATH

# Auto-detect Meta's authenticated launcher by its documented secure-internet
# flag. Operators can force either backend with LITREVIEW_WEB_MODE=meta_secure
# or LITREVIEW_WEB_MODE=native_web.
if [ -z "${CLAUDE_CLI_PATH:-}" ]; then
  CLAUDE_CLI_PATH="$(command -v claude || true)"
fi
_REQUESTED_WEB_MODE="${LITREVIEW_WEB_MODE:-auto}"
case "${_REQUESTED_WEB_MODE}" in
  auto|meta_secure|native_web) ;;
  *)
    echo "[litreview] ERROR: LITREVIEW_WEB_MODE must be auto, meta_secure, or native_web" >&2
    exit 2
    ;;
esac
_DETECTED_WEB_MODE=native_web
if [ -n "${CLAUDE_CLI_PATH:-}" ] && [ -x "${CLAUDE_CLI_PATH}" ]; then
  _CLI_HELP="$("${CLAUDE_CLI_PATH}" --help 2>&1 || true)"
  case "${_CLI_HELP}" in
    *--secure-internet-mode*) _DETECTED_WEB_MODE=meta_secure ;;
  esac
  unset _CLI_HELP
fi
if [ "${_REQUESTED_WEB_MODE}" = "auto" ]; then
  LITREVIEW_WEB_MODE="${_DETECTED_WEB_MODE}"
else
  LITREVIEW_WEB_MODE="${_REQUESTED_WEB_MODE}"
fi
export LITREVIEW_WEB_MODE
unset META_CLAUDE_SECURE_INTERNET_MODE
if [ "${LITREVIEW_WEB_MODE}" = "meta_secure" ]; then
  if [ -z "${CLAUDE_CLI_PATH:-}" ] || [ ! -x "${CLAUDE_CLI_PATH}" ]; then
    echo "[litreview] ERROR: meta_secure mode requires an executable Claude CLI" >&2
    exit 2
  fi
  export CLAUDE_CLI_PATH
  unset ANTHROPIC_API_KEY
  export META_CLAUDE_SECURE_INTERNET_MODE=1
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  unset CLAUDE_CLI_PATH
elif [ -n "${CLAUDE_CLI_PATH:-}" ] && [ -x "${CLAUDE_CLI_PATH}" ]; then
  export CLAUDE_CLI_PATH
else
  echo "[litreview] ERROR: neither ANTHROPIC_API_KEY nor an executable Claude CLI is available" >&2
  echo "[litreview] Set ANTHROPIC_API_KEY or CLAUDE_CLI_PATH (or put claude on PATH)." >&2
  exit 2
fi
unset _REQUESTED_WEB_MODE _DETECTED_WEB_MODE

# These credentials are not needed by either librarian route. Keeping them out
# of the child limits the impact of a malicious or prompt-injected paper.
unset MODEL_API_KEY LLAMA_API_KEY HF_TOKEN HUGGING_FACE_HUB_TOKEN OAI_API
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN RUNPOD_API_KEY
unset OPENAI_API_KEY WANDB_API_KEY

if [ "${LITREVIEW_WEB_MODE}" = "meta_secure" ]; then
  for _required in "${REPO}/scripts/aar-paper-search" /usr/bin/curl; do
    if [ ! -x "${_required}" ]; then
      echo "[litreview] ERROR: Meta secure mode requires executable ${_required}" >&2
      exit 2
    fi
  done
  unset _required
fi

# The survey populates the AXIS-WISE literature baseline (one per safety axis), shared
# read-only by every team on that axis. Teams add their OWN in-run entries to their
# per-team LIT_FORUM_DIR (under TEAM_DIR/litreview); the survey writes the axis baseline.
# write_lit_entry targets LIT_FORUM_DIR, so point it at the axis dir for this survey job.
export LIT_AXIS_DIR="${LIT_AXIS_DIR:-${REPO}/_runs/litreview/${SUITE}}"
export LIT_FORUM_DIR="${LITREVIEW_OUTPUT_DIR:-${LIT_AXIS_DIR}}"
mkdir -p "${LIT_FORUM_DIR}"
export LITREVIEW_WORKSPACE="${LITREVIEW_WORKSPACE:-${REPO}/_runs/litreview/workspaces/${TEAM_ID}}"
mkdir -p "${LITREVIEW_WORKSPACE}"
export LITREVIEW_MODEL="${LITREVIEW_MODEL:-claude-sonnet-4-6}"
PY="${HARNESS_PY:-${REPO}/.venv/bin/python}"
if [ ! -x "${PY}" ]; then
  echo "[litreview] ERROR: Python is not executable at ${PY}; set HARNESS_PY" >&2
  exit 2
fi
cd "${REPO}"
echo "[litreview] axis=${SUITE} team=${TEAM_ID} model=${LITREVIEW_MODEL} web=${LITREVIEW_WEB_MODE} -> ${LIT_FORUM_DIR} (min ${MIN})"
PYTHONUNBUFFERED=1 "${PY}" -u -m aar.litreview.run_litreview --suite "${SUITE}" --min-entries "${MIN}"
_ENTRY_COUNT="$("${PY}" -c 'from aar.research_loop.tools.lit_forum import count; print(count())')"
echo "[litreview] valid unique entries: ${_ENTRY_COUNT}"
echo "=== DONE ==="
