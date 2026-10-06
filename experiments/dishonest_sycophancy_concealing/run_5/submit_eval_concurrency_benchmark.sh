#!/bin/bash
# Submit an isolated Run 5 evaluator-concurrency benchmark.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
SOURCE_ATTEMPT="${AAR_CONCURRENCY_SOURCE_ATTEMPT:-/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run_attempts/20261006T082121Z-c7741c592f27}"
SOURCE_SUITE_DIR="${SOURCE_ATTEMPT}/eval/holdout/gemma4_31b/honesty_sycophancy_concealing_uncertainty"
MODEL_PATH="${AAR_CONCURRENCY_MODEL_PATH:-/checkpoint/ram/shared/models/google/gemma-4-31B-it}"
SECRET_ENV="${AAR_RUN5_SECRET_ENV:-/storage/home/winnieyangwn/aar-worktrees/uv/.env}"
EVAL_CONCURRENCIES="${AAR_EVAL_CONCURRENCIES:-1,2,4}"

[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "concurrency benchmark requires branch multi_vllm" >&2
  exit 2
}
git -C "${REPO}" diff --quiet && git -C "${REPO}" diff --cached --quiet || {
  echo "concurrency benchmark requires a clean tracked worktree" >&2
  exit 2
}
for required in "${SOURCE_SUITE_DIR}" "${MODEL_PATH}" "${SECRET_ENV}"; do
  [ -e "${required}" ] || { echo "required path missing: ${required}" >&2; exit 2; }
done

commit="$(git -C "${REPO}" rev-parse HEAD)"
short_commit="$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${short_commit}"
attempt_root="/checkpoint/ram/aar/${USER}/run5_eval_concurrency/${attempt_id}"
mkdir -p "${attempt_root}/logs" "${attempt_root}/metadata"
chmod 700 "${attempt_root}" "${attempt_root}/logs" "${attempt_root}/metadata"

job_id="$(sbatch --parsable \
  --output="${attempt_root}/logs/concurrency-%j.out" \
  --export=AAR_REPO="${REPO}",AAR_CONCURRENCY_ATTEMPT="${attempt_root}",AAR_CONCURRENCY_SOURCE_SUITE_DIR="${SOURCE_SUITE_DIR}",AAR_CONCURRENCY_MODEL_PATH="${MODEL_PATH}",AAR_CONCURRENCY_GIT_COMMIT="${commit}",AAR_EVAL_CONCURRENCIES="${EVAL_CONCURRENCIES}",HARNESS_ENV="${SECRET_ENV}",USER="${USER}" \
  "${SCRIPT_DIR}/benchmark_eval_concurrency.sbatch")"
printf 'job_id=%s\nattempt_root=%s\ngit_commit=%s\nmodel_path=%s\neval_concurrencies=%s\n' \
  "${job_id}" "${attempt_root}" "${commit}" "${MODEL_PATH}" "${EVAL_CONCURRENCIES}" | tee \
  "${attempt_root}/metadata/submission.txt"
