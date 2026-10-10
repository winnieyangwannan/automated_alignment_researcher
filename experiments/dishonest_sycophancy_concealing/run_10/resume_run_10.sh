#!/bin/bash
# Configure Run 10, then delegate artifact-safe recovery to the shared engine.
set -euo pipefail
umask 077

ATTEMPT_DIR="$(realpath -e -- "${1:?usage: $0 <full-attempt-dir> [seeds]}")"
REQUESTED_SEEDS="${2:-alpha beta gamma delta epsilon}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
export MODE=full
SECRET_ENV="$(realpath -e -- "${AAR_RUN10_SECRET_ENV:-${REPO}/.env}")"
export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
if [ -f "${ATTEMPT_DIR}/metadata/run.yaml" ]; then
  export AAR_RUN_CONFIG="${ATTEMPT_DIR}/metadata/run.yaml"
fi

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/configure_run_10_environment.sh"
export AAR_PRETRAIN_SMOKE=1
export AAR_EVAL_WORKERS=5 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00 AAR_EVAL_IDLE_SECONDS=604200
export AAR_MAX_CONCURRENT_TRAIN_JOBS=5

export AAR_RESUME_EXPECTED_BRANCH="${AAR_EXPECTED_BRANCH}"
export AAR_RESUME_EXPECTED_MODE=full
export AAR_RESUME_DEFAULT_SEEDS="alpha beta gamma delta epsilon"
export AAR_RESUME_ALLOWED_SEEDS="alpha beta gamma delta epsilon"
export AAR_RESUME_EVALUATOR_COUNT=5
export AAR_RESUME_HOURS="${AAR_RUN10_RESUME_HOURS:-167}"
export AAR_RESUME_JOB_PREFIX="aar-${SUITE_NAME}-${MODEL:-gemma4_31b}"

exec "${REPO}/scripts/resume_aar_team.sh" "${ATTEMPT_DIR}" "${REQUESTED_SEEDS}"
