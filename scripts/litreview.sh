#!/bin/bash
#SBATCH --job-name=aar-litreview
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%x-%j.out
#
# Literature-review pre-phase: populate the team's SHARED lit forum with >=MIN
# method/paper entries before the AARs start. CPU-only — uses the Claude API +
# WebSearch/WebFetch, no GPU. Usage: sbatch scripts/litreview.sh <suite> <team_id> [min]
set -euo pipefail
SUITE="${1:?usage: litreview.sh <suite> <team_id> [min]}"
TEAM_ID="${2:?team_id}"
MIN="${3:-30}"
case "${MIN}" in
  ''|*[!0-9]*) echo "[litreview] ERROR: min must be a non-negative integer" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="${AAR_REPO:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}"
if [ ! -d "${REPO}/aar" ]; then
  echo "[litreview] ERROR: repository not found at ${REPO}; set AAR_REPO" >&2
  exit 2
fi
export PYTHONPATH="${REPO}"

# Load the worktree-local environment without scraping or printing secrets. An
# already-exported key wins, which makes explicit sbatch --export overrides safe.
ENV_FILE="${AAR_ENV_FILE:-${REPO}/.env}"
_INHERITED_ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY-}"
if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090  # caller-selected, trusted environment file
  . "${ENV_FILE}"
  set +a
fi
if [ -n "${_INHERITED_ANTHROPIC_API_KEY}" ]; then
  export ANTHROPIC_API_KEY="${_INHERITED_ANTHROPIC_API_KEY}"
fi
unset _INHERITED_ANTHROPIC_API_KEY
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[litreview] ERROR: ANTHROPIC_API_KEY is required (set it in the environment or ${ENV_FILE})" >&2
  exit 2
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
PY="${AAR_PYTHON:-${REPO}/.venv/bin/python}"
if [ ! -x "${PY}" ]; then
  echo "[litreview] ERROR: Python is not executable at ${PY}; set AAR_PYTHON" >&2
  exit 2
fi
cd "${REPO}"
echo "[litreview] axis=${SUITE} team=${TEAM_ID} model=${LITREVIEW_MODEL} -> ${LIT_FORUM_DIR} (min ${MIN})"
PYTHONUNBUFFERED=1 "${PY}" -u -m aar.litreview.run_litreview --suite "${SUITE}" --min-entries "${MIN}"
shopt -s nullglob
_entries=("${LIT_FORUM_DIR}"/*.json)
echo "[litreview] entries written: ${#_entries[@]}"
echo "=== DONE ==="
