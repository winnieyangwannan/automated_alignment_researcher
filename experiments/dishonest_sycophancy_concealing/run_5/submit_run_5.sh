#!/bin/bash
# Submit the retained-baseline -> five-iteration AAR launch from multi_vllm.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
REUSED_BASELINE="${1:-/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/metadata/gemma4_31b_multidimensional_baseline.json}"
REUSED_BASELINE="$(realpath -e -- "${REUSED_BASELINE}")"

[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "run 5 requires branch multi_vllm" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "run 5 requires a clean tracked worktree" >&2
  exit 2
fi
if [ -n "$(git -C "${REPO}" status --porcelain --untracked-files=all -- \
  aar benchmark_docs scripts replication pyproject.toml uv.lock \
  experiments/dishonest_sycophancy_concealing/run_5)" ]; then
  echo "run 5 refuses untracked or modified launch-critical files" >&2
  exit 2
fi
[ -x "${REPO}/.venv/bin/python" ] || {
  echo "run 5 requires its worktree-local ARM64 environment at ${REPO}/.venv" >&2
  echo "run replication/setup_env_multidimensional.sbatch on a g3 allocation first" >&2
  exit 2
}
"${REPO}/.venv/bin/python" -c \
  'import platform; assert platform.machine() == "aarch64"' || {
  echo "run 5 host orchestration environment is not ARM64" >&2
  exit 2
}
source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${source_root}" --verify-only >/dev/null || {
  echo "run 5 requires the pinned LLM-Uncertainty-Bench source" >&2
  echo "run scripts/prepare_llm_uncertainty_source.py before submitting" >&2
  exit 2
}
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
"${REPO}/.venv/bin/python" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" >/dev/null

commit="$(git -C "${REPO}" rev-parse HEAD)"
short_commit="$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${short_commit}"
attempt_parent="/checkpoint/ram/aar/${USER}/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run_attempts"
attempt_dir="${attempt_parent}/${attempt_id}"
mkdir -p "${attempt_parent}"
mkdir "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

export AAR_REPO="${REPO}"
export AAR_RUNTIME_ROOT="${attempt_dir}"
export AAR_RUN_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}"
export AAR_REUSED_BASELINE="${REUSED_BASELINE}"
job_id="$(sbatch --parsable \
  --account=ram --partition=g3 --qos=g3_ram_high \
  --cpus-per-task=16 --mem=128G --time=02:00:00 \
  --job-name=aar-gemma-vllm-run5-launch \
  --output="${attempt_dir}/logs/pipeline-%j.out" --export=ALL \
  "${REPO}/experiments/dishonest_sycophancy_concealing/run_5/run_5_pipeline.sbatch")"
printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nreused_baseline=%s\n' \
  "${job_id}" "${attempt_dir}" "${commit}" "${REUSED_BASELINE}" | tee \
  "${attempt_dir}/metadata/submission.txt"
