#!/bin/bash
# Recover only a missing finding for an already-approved and already-scored run.
set -euo pipefail
umask 077

[ "$#" -eq 1 ] || {
  echo "usage: $0 <run16-attempt-directory>" >&2
  exit 2
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN16_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO="$(cd -- "${RUN16_DIR}/../../.." && pwd)"
ATTEMPT="$(realpath -e -- "$1")"
RUN_CONFIG="$(realpath -e -- "${RUN16_DIR}/canary/one_chain_lifecycle_check/config/run.yaml")"
SECRET_ENV="$(realpath -e -- "${AAR_RUN16_SECRET_ENV:-${REPO}/.env}")"

[ -x "${REPO}/.venv/bin/python" ] || {
  echo "missing worktree-local runtime" >&2
  exit 2
}
[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || {
  echo "Run 16 recovery requires branch autodata" >&2
  exit 2
}
case "${ATTEMPT}" in
  /checkpoint/ram/aar/"${USER:?}"/run16_native_generation/canary_attempts/*) ;;
  *) echo "not a Run 16 canary attempt: ${ATTEMPT}" >&2; exit 2 ;;
esac

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
export AAR_RUN_CONFIG="${RUN_CONFIG}" AAR_RUN_ATTEMPT_DIR="${ATTEMPT}"
export AAR_RUNTIME_ROOT="${ATTEMPT}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
eval "$("${REPO}/.venv/bin/python" "${REPO}/scripts/load_aar_run_config.py" "${RUN_CONFIG}")"
[ "${AAR_AUTODATA:?missing data-generation backend}" = 0 ] || {
  echo "finding recovery requires data_generation.backend=native" >&2
  exit 2
}
while IFS= read -r name; do unset "${name}"; done < <(compgen -A variable AAR_AUTODATA_)
export AAR_AUTODATA=0

[ "${AAR_AGENT_BACKEND:?missing agent backend}" = claude ] || {
  echo "finding recovery requires Claude" >&2
  exit 2
}
export AAR_AGENT_MODEL=claude-opus-4-8 AAR_EFFORT=max AAR_WEB_MODE=meta_secure
export META_CLAUDE_SECURE_INTERNET_MODE=1
CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH:-$(command -v claude || true)}"
export CLAUDE_CLI_PATH
[ -x "${CLAUDE_CLI_PATH}" ] || { echo "Claude CLI is missing" >&2; exit 2; }

exec timeout 2100 "${REPO}/.venv/bin/python" \
  "${SCRIPT_DIR}/finalize_scored_run.py" "${ATTEMPT}"
