#!/bin/bash
# Submit a replacement evaluator pool for an existing retained Run 7 attempt.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
ATTEMPT_DIR="$(realpath -e -- "${1:?usage: $0 <run7-attempt-dir>}")"
SECRET_ENV="${AAR_RUN7_SECRET_ENV:-/storage/home/winnieyangwn/aar-worktrees/uv/.env}"
SECRET_ENV="$(realpath -e -- "${SECRET_ENV}")"

[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "Run 7 evaluator recovery requires branch multi_vllm" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "Run 7 evaluator recovery requires a clean tracked worktree" >&2
  exit 2
fi
[ -f "${ATTEMPT_DIR}/metadata/children.env" ] || {
  echo "not a launched Run 7 attempt: ${ATTEMPT_DIR}" >&2
  exit 2
}
source_root="${REPO}/data/LLM-Uncertainty-Bench"
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
export AAR_REPO="${REPO}"
export HARNESS_ENV="${SECRET_ENV}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"

commit="$(git -C "${REPO}" rev-parse HEAD)"
export AAR_RUN_ATTEMPT_DIR="${ATTEMPT_DIR}"
export AAR_EXPECTED_COMMIT="${commit}"
job_id="$(sbatch --parsable \
  --account=ram --partition=g3 --qos=g3_ram_high \
  --cpus-per-task=16 --mem=128G --time=02:00:00 \
  --job-name=aar-run7-eval-recovery-launch \
  --output="${ATTEMPT_DIR}/logs/eval-recovery-%j.out" \
  --export=AAR_REPO="${REPO}",AAR_RUN_ATTEMPT_DIR="${ATTEMPT_DIR}",AAR_EXPECTED_COMMIT="${commit}",HARNESS_ENV="${HARNESS_ENV}",LLM_UNCERTAINTY_SRC="${LLM_UNCERTAINTY_SRC}",LLM_UNCERTAINTY_SOURCE_MANIFEST="${LLM_UNCERTAINTY_SOURCE_MANIFEST}",USER="${USER}" \
  "${REPO}/experiments/dishonest_sycophancy_concealing/run_7/run_7_eval_recovery.sbatch")"
printf 'recovery_launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\n' \
  "${job_id}" "${ATTEMPT_DIR}" "${commit}"
