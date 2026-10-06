#!/bin/bash
# Submit the vLLM baseline -> five-agent AAR pipeline from multi_vllm.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
PROVISIONAL="${1:-/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/metadata/gemma4_31b_multidimensional_baseline.json}"
PROVISIONAL="$(realpath -e -- "${PROVISIONAL}")"

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

commit="$(git -C "${REPO}" rev-parse HEAD)"
short_commit="$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${short_commit}"
attempt_parent="/checkpoint/ram/aar/${USER}/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/baseline_attempts"
attempt_dir="${attempt_parent}/${attempt_id}"
mkdir -p "${attempt_parent}"
mkdir "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

export AAR_REPO="${REPO}"
export AAR_RUNTIME_ROOT="${attempt_dir}"
export AAR_BASELINE_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}"
export AAR_PROVISIONAL_BASELINE_OVERRIDES="${PROVISIONAL}"
job_id="$(sbatch --parsable \
  --account=ram --partition=g3 --qos=g3_ram_high \
  --cpus-per-task=48 --gpus=4 --mem=512G --time=36:00:00 \
  --job-name=aar-gemma-vllm-run5-pipeline \
  --output="${attempt_dir}/logs/pipeline-%j.out" --export=ALL \
  "${REPO}/experiments/dishonest_sycophancy_concealing/run_5/run_5_pipeline.sbatch")"
printf 'pipeline_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nprovisional=%s\n' \
  "${job_id}" "${attempt_dir}" "${commit}" "${PROVISIONAL}" | tee \
  "${attempt_dir}/metadata/submission.txt"
