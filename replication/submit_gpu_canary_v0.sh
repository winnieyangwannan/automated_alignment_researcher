#!/bin/bash
# Create a fresh retained attempt and submit the 20-item Gemma evaluation canary.
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
  echo "canary launcher requires branch uv" >&2
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

canary_root="${AAR_RUNTIME_ROOT}/gpu_canaries"
attempt_dir="${canary_root}/${attempt_id}"
case "${attempt_dir}" in
  /checkpoint/*) ;;
  *) echo "canary output must resolve under /checkpoint: ${attempt_dir}" >&2; exit 2 ;;
esac
mkdir -p "${canary_root}"
if ! mkdir "${attempt_dir}"; then
  echo "refusing to overwrite retained canary attempt: ${attempt_dir}" >&2
  exit 2
fi

export AAR_CANARY_ATTEMPT_DIR="${attempt_dir}"
export AAR_CANARY_GIT_COMMIT="${commit}"
job_id="$(sbatch --parsable \
  --output="${attempt_dir}/slurm-%j.out" \
  --export=ALL \
  "${AAR_REPO}/replication/gpu_canary_v0.sbatch")"
printf 'job_id=%s\nattempt_dir=%s\ngit_commit=%s\n' \
  "${job_id}" "${attempt_dir}" "${commit}" | tee "${attempt_dir}/submission.txt"
