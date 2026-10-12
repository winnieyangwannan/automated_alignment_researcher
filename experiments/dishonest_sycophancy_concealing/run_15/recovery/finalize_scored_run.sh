#!/bin/bash
# Recover only a missing finding for an already-approved and already-scored run.
set -euo pipefail
umask 077

[ "$#" -ge 1 ] && [ "$#" -le 3 ] || {
  echo "usage: $0 <run15-attempt-directory> [seed run_id]" >&2
  exit 2
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN15_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO="$(cd -- "${RUN15_DIR}/../../.." && pwd)"
ATTEMPT="$(realpath -e -- "$1")"
SEED="${2:-}"
RUN_ID="${3:-}"
SECRET_ENV="$(realpath -e -- "${AAR_RUN15_SECRET_ENV:-${REPO}/.env}")"

[ -x "${REPO}/.venv/bin/python" ] || {
  echo "missing worktree-local runtime" >&2
  exit 2
}
[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || {
  echo "Run 15 recovery requires branch autodata" >&2
  exit 2
}
case "${ATTEMPT}" in
  /checkpoint/ram/aar/"${USER:?}"/run15_native_generation/canary_attempts/*)
    [ -z "${SEED}" ] && [ -z "${RUN_ID}" ] || {
      echo "canary finding recovery does not take a seed or run_id" >&2
      exit 2
    }
    RUN_CONFIG="$(realpath -e -- "${RUN15_DIR}/canary/one_chain_lifecycle_check/config/run.yaml")"
    ;;
  /checkpoint/ram/aar/"${USER:?}"/run15_native_generation/full_attempts/*)
    [[ "${SEED}" =~ ^(alpha|beta|gamma|delta|epsilon)$ ]] || {
      echo "full-attempt finding recovery requires one canonical seed" >&2
      exit 2
    }
    [[ "${RUN_ID}" =~ ^[A-Za-z0-9._-]+$ ]] || {
      echo "full-attempt finding recovery requires one safe run_id" >&2
      exit 2
    }
    RUN_CONFIG="$(realpath -e -- "${RUN15_DIR}/config/run.yaml")"
    ;;
  *) echo "not a Run 15 attempt: ${ATTEMPT}" >&2; exit 2 ;;
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

export PATH="/storage/home/${USER}/tools/node-v22.22.0-linux-arm64/bin:${PATH}"
export KIMI_CLI_PATH="/storage/home/${USER}/tools/kimi-code-2.1.1/node_modules/.bin/kimi"
export AAR_WEB_MODE=native_web
export AAR_KIMI_SERVE_DEPLOYMENT=autodata2_8-kimi26
export AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT="/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2"
export KIMI_MODEL_CAPABILITIES=tool_use KIMI_MODEL_MAX_CONTEXT_SIZE=262144
export KIMI_MODEL_MAX_OUTPUT_SIZE=65536 KIMI_MODEL_MAX_COMPLETION_TOKENS=65536
unset KIMI_AGENT_MODEL

_finalizer_args=("${ATTEMPT}")
[ -z "${SEED}" ] || _finalizer_args+=(--seed "${SEED}" --run-id "${RUN_ID}")
exec timeout 2100 "${REPO}/.venv/bin/python" \
  "${SCRIPT_DIR}/finalize_scored_run.py" "${_finalizer_args[@]}"
