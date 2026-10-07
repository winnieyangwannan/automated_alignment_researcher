#!/bin/bash
# Submit five parallel 50-iteration research chains and five four-GPU evaluators.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
REUSED_BASELINE="${1:-/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/metadata/gemma4_31b_multidimensional_baseline.json}"
REUSED_BASELINE="$(realpath -e -- "${REUSED_BASELINE}")"
SECRET_ENV="${AAR_RUN7_SECRET_ENV:-/storage/home/winnieyangwn/aar-worktrees/uv/.env}"
SECRET_ENV="$(realpath -e -- "${SECRET_ENV}")"

[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "run 7 requires branch multi_vllm" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "run 7 requires a clean tracked worktree" >&2
  exit 2
fi
if [ -n "$(git -C "${REPO}" status --porcelain --untracked-files=all -- \
  aar benchmark_docs scripts replication pyproject.toml uv.lock \
  experiments/dishonest_sycophancy_concealing/run_7)" ]; then
  echo "run 7 refuses untracked or modified launch-critical files" >&2
  exit 2
fi
[ -x "${REPO}/.venv/bin/python" ] || {
  echo "run 7 requires its worktree-local ARM64 environment at ${REPO}/.venv" >&2
  exit 2
}
"${REPO}/.venv/bin/python" -c \
  'import platform; assert platform.machine() == "aarch64"' || {
  echo "run 7 host orchestration environment is not ARM64" >&2
  exit 2
}
source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${source_root}" --verify-only >/dev/null || {
  echo "run 7 requires the pinned LLM-Uncertainty-Bench source" >&2
  exit 2
}
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
export AAR_REPO="${REPO}"
export HARNESS_ENV="${SECRET_ENV}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || {
    echo "run 7 requires nonempty ${secret_name} in ${HARNESS_ENV}" >&2
    exit 2
  }
done
"${REPO}/.venv/bin/python" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" >/dev/null

commit="$(git -C "${REPO}" rev-parse HEAD)"
short_commit="$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${short_commit}"
attempt_parent="/checkpoint/ram/aar/${USER}/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run7_attempts"
attempt_dir="${attempt_parent}/${attempt_id}"
mkdir -p "${attempt_parent}"
mkdir "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

export AAR_RUNTIME_ROOT="${attempt_dir}"
export AAR_RUN_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}"
export AAR_REUSED_BASELINE="${REUSED_BASELINE}"
job_id="$(sbatch --parsable \
  --account=ram --partition=g3 --qos=g3_ram_high \
  --cpus-per-task=16 --mem=128G --time=02:00:00 \
  --job-name=aar-gemma-vllm-run7-launch \
  --output="${attempt_dir}/logs/pipeline-%j.out" \
  --export=AAR_REPO="${REPO}",AAR_RUNTIME_ROOT="${attempt_dir}",AAR_RUN_ATTEMPT_DIR="${attempt_dir}",AAR_BASELINE_GIT_COMMIT="${commit}",AAR_REUSED_BASELINE="${REUSED_BASELINE}",HARNESS_ENV="${HARNESS_ENV}",LLM_UNCERTAINTY_SRC="${LLM_UNCERTAINTY_SRC}",LLM_UNCERTAINTY_SOURCE_MANIFEST="${LLM_UNCERTAINTY_SOURCE_MANIFEST}",USER="${USER}" \
  "${REPO}/experiments/dishonest_sycophancy_concealing/run_7/run_7_pipeline.sbatch")"
printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nreused_baseline=%s\nresearch_chains=5\nmax_iterations_per_chain=50\nevaluator_jobs=5\nevaluator_gpus_per_job=4\n' \
  "${job_id}" "${attempt_dir}" "${commit}" "${REUSED_BASELINE}" | tee \
  "${attempt_dir}/metadata/submission.txt"
