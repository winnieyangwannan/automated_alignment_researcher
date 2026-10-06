#!/bin/bash
# Submit an evaluation-only recovery for the retained Run 5 iteration 1/2 adapters.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
SOURCE_ATTEMPT="${1:-/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run_attempts/20261006T082121Z-c7741c592f27}"
REUSED_BASELINE="${2:-/checkpoint/ram/aar/${USER}/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/metadata/gemma4_31b_multidimensional_baseline.json}"
SECRET_ENV="${AAR_RUN5_SECRET_ENV:-/storage/home/winnieyangwn/aar-worktrees/uv/.env}"
SOURCE_ATTEMPT="$(realpath -e -- "${SOURCE_ATTEMPT}")"
REUSED_BASELINE="$(realpath -e -- "${REUSED_BASELINE}")"
SECRET_ENV="$(realpath -e -- "${SECRET_ENV}")"
SOURCE_TEAM_DIR="${SOURCE_ATTEMPT}/aar_teams/honesty-sycophancy-concealing-gemma4_31b-opus48-fiveiter-vllm-run5-v0"

[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "Run 5 recovery requires branch multi_vllm" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || \
   ! git -C "${REPO}" diff --cached --quiet; then
  echo "Run 5 recovery requires a clean tracked worktree" >&2
  exit 2
fi
for tracked in \
  experiments/dishonest_sycophancy_concealing/run_5/submit_eval_recovery.sh \
  experiments/dishonest_sycophancy_concealing/run_5/run_5_eval_recovery.sbatch; do
  git -C "${REPO}" ls-files --error-unmatch "${tracked}" >/dev/null || {
    echo "recovery launcher is not committed: ${tracked}" >&2
    exit 2
  }
done
[ -x "${REPO}/.venv/bin/python" ] || {
  echo "recovery requires the worktree-local ARM64 environment" >&2
  exit 2
}
"${REPO}/.venv/bin/python" -c \
  'import platform; assert platform.machine() == "aarch64"' || {
  echo "recovery orchestration environment is not ARM64" >&2
  exit 2
}

source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${source_root}" --verify-only >/dev/null
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
export AAR_REPO="${REPO}"
export HARNESS_ENV="${SECRET_ENV}"
# Load only the runtime allowlist. Never print or copy the secret file or values.
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || {
    echo "Run 5 recovery requires nonempty ${secret_name} in HARNESS_ENV" >&2
    exit 2
  }
done
"${REPO}/.venv/bin/python" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" >/dev/null
[ -d "${SOURCE_TEAM_DIR}" ] || {
  echo "source Run 5 team is missing: ${SOURCE_TEAM_DIR}" >&2
  exit 2
}

commit="$(git -C "${REPO}" rev-parse HEAD)"
short_commit="$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${short_commit}"
attempt_parent="/checkpoint/ram/aar/${USER}/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/eval_recovery_attempts"
attempt_dir="${attempt_parent}/${attempt_id}"
mkdir -p "${attempt_parent}"
mkdir "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

job_id="$(sbatch --parsable \
  --account=ram --partition=g3 --qos=g3_ram_high \
  --cpus-per-task=16 --mem=128G --time=02:00:00 \
  --job-name=aar-run5-eval-recovery-launch \
  --output="${attempt_dir}/logs/pipeline-%j.out" \
  --export=AAR_REPO="${REPO}",AAR_RUN_ATTEMPT_DIR="${attempt_dir}",AAR_EXPECTED_COMMIT="${commit}",AAR_REUSED_BASELINE="${REUSED_BASELINE}",AAR_SOURCE_TEAM_DIR="${SOURCE_TEAM_DIR}",HARNESS_ENV="${HARNESS_ENV}",LLM_UNCERTAINTY_SRC="${LLM_UNCERTAINTY_SRC}",LLM_UNCERTAINTY_SOURCE_MANIFEST="${LLM_UNCERTAINTY_SOURCE_MANIFEST}",USER="${USER}" \
  "${REPO}/experiments/dishonest_sycophancy_concealing/run_5/run_5_eval_recovery.sbatch")"
printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nsource_team_dir=%s\nreused_baseline=%s\n' \
  "${job_id}" "${attempt_dir}" "${commit}" "${SOURCE_TEAM_DIR}" \
  "${REUSED_BASELINE}" | tee "${attempt_dir}/metadata/submission.txt"
