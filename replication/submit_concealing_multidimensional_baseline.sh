#!/bin/bash
# Submit only the missing concealing-uncertainty source baseline. Existing
# honesty and sycophancy results are consumed later by the merge recorder.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/scripts/aar_runtime_env.sh"
[ "$(git -C "${AAR_REPO}" branch --show-current)" = uv ] || { echo "branch must be uv" >&2; exit 2; }
if ! git -C "${AAR_REPO}" diff --quiet || \
  ! git -C "${AAR_REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
if [ -n "$(git -C "${AAR_REPO}" status --porcelain --untracked-files=all -- \
  aar benchmark_docs scripts replication pyproject.toml uv.lock)" ]; then
  echo "refusing untracked or modified baseline-critical files" >&2
  exit 2
fi

commit="$(git -C "${AAR_REPO}" rev-parse HEAD)"
short_commit="$(git -C "${AAR_REPO}" rev-parse --short=12 HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${short_commit}"
attempt_parent="/checkpoint/ram/aar/${USER:?}/concealing-uncertainty-gemma4-31b-baseline-attempts"
attempt_dir="${attempt_parent}/${attempt_id}"
mkdir -p "${attempt_parent}"
mkdir "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

export AAR_RUNTIME_ROOT="${attempt_dir}"
export AAR_BASELINE_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}"
job_id="$(sbatch --parsable --output="${attempt_dir}/logs/baseline-%j.out" --export=ALL \
  "${AAR_REPO}/replication/baseline_concealing_multidimensional.sbatch")"
printf 'job_id=%s\nattempt_dir=%s\ngit_commit=%s\n' \
  "${job_id}" "${attempt_dir}" "${commit}" | tee \
  "${attempt_dir}/metadata/submission.txt"
