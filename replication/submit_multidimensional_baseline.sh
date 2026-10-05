#!/bin/bash
# Submit the final-commit composed baseline using a validated provisional union.
set -euo pipefail
umask 077
[ "$#" = 1 ] || { echo "usage: $0 <provisional-13-entry-override.json>" >&2; exit 2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${AAR_REPO}/scripts/aar_runtime_env.sh"
provisional="$(realpath -e -- "$1")"
"${HARNESS_PY}" - "${provisional}" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload.get("status") == "provisional_until_final_commit_composed_baseline_passes"
scores = payload.get("scores", {}).get("google/gemma-4-31B-it", {})
assert len(scores) == 13 and all(row.get("n", 0) > 0 for row in scores.values())
PY
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
attempt_parent="${AAR_RUNTIME_BASE}/baseline_attempts"
attempt_dir="${attempt_parent}/${attempt_id}"
mkdir -p "${attempt_parent}"
mkdir "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

export AAR_RUNTIME_ROOT="${attempt_dir}"
export AAR_BASELINE_OVERRIDES="${attempt_dir}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${attempt_dir}/eval/holdout/gemma4_31b"
export AAR_BASELINE_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}"
export AAR_PROVISIONAL_BASELINE_OVERRIDES="${provisional}"
job_id="$(sbatch --parsable --output="${attempt_dir}/logs/baseline-%j.out" --export=ALL \
  "${AAR_REPO}/replication/baseline_multidimensional.sbatch")"
printf 'job_id=%s\nattempt_dir=%s\ngit_commit=%s\nprovisional=%s\n' \
  "${job_id}" "${attempt_dir}" "${commit}" "${provisional}" | tee \
  "${attempt_dir}/metadata/submission.txt"
