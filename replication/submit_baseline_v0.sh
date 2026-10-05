#!/bin/bash
# Create a fresh retained attempt and submit the complete five-benchmark baseline.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_v0.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/.venv/bin/activate"

[ "$(git -C "${AAR_REPO}" branch --show-current)" = uv ] || {
  echo "baseline launcher requires branch uv" >&2
  exit 2
}
commit="$(git -C "${AAR_REPO}" rev-parse HEAD)"
short_commit="$(git -C "${AAR_REPO}" rev-parse --short=12 HEAD)"
attempt_id="${1:-$(date -u +%Y%m%dT%H%M%SZ)-${short_commit}}"
case "${attempt_id}" in
  ''|*[!A-Za-z0-9._-]*)
    echo "attempt id must contain only letters, numbers, dot, underscore, or hyphen" >&2
    exit 2
    ;;
esac

attempt_parent="${AAR_RUNTIME_BASE}/baseline_attempts"
attempt_dir="${attempt_parent}/${attempt_id}"
case "${attempt_dir}" in
  /checkpoint/*) ;;
  *) echo "baseline output must resolve under /checkpoint: ${attempt_dir}" >&2; exit 2 ;;
esac

"${HARNESS_PY}" "${AAR_REPO}/replication/preflight_v0.py" \
  --require-gpt-judge-budget

mkdir -p "${attempt_parent}"
if ! mkdir "${attempt_dir}"; then
  echo "refusing to overwrite retained baseline attempt: ${attempt_dir}" >&2
  exit 2
fi
mkdir "${attempt_dir}/metadata" "${attempt_dir}/logs"

export AAR_RUNTIME_ROOT="${attempt_dir}"
export AAR_BASELINE_OVERRIDES="${AAR_RUNTIME_ROOT}/metadata/gemma4_31b_baseline.json"
export HOLDOUT_DIR="${AAR_RUNTIME_ROOT}/eval/holdout/gemma4_31b"
export AAR_BASELINE_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}"

# Source this file before a later canary/full launch to select the exact
# retained baseline and holdout rooted in this attempt.
printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

job_id="$(sbatch --parsable \
  --output="${AAR_RUNTIME_ROOT}/logs/baseline-%j.out" \
  --export=ALL \
  "${AAR_REPO}/replication/baseline_v0.sbatch")"
printf 'job_id=%s\nattempt_dir=%s\ngit_commit=%s\n' \
  "${job_id}" "${attempt_dir}" "${commit}" | tee \
  "${attempt_dir}/metadata/submission.txt"
