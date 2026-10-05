#!/bin/bash
#SBATCH --job-name=aar-multidim-baseline
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --gpus=2
#SBATCH --mem=192G
#SBATCH --time=36:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:-${SLURM_SUBMIT_DIR:?submit from the uv worktree}}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
# shellcheck disable=SC1091
source "${REPO}/.venv/bin/activate"

ATTEMPT_DIR="${AAR_BASELINE_ATTEMPT_DIR:?missing retained attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing submitted commit}"
PROVISIONAL="${AAR_PROVISIONAL_BASELINE_OVERRIDES:?missing provisional 13-entry override}"
[ -s "${PROVISIONAL}" ] || { echo "provisional override missing" >&2; exit 2; }
[ "$(git -C "${REPO}" branch --show-current)" = uv ] || { echo "branch must be uv" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "commit changed after submission" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || \
  ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
if [ -n "$(git -C "${REPO}" status --porcelain --untracked-files=all -- \
  aar benchmark_docs scripts replication pyproject.toml uv.lock)" ]; then
  echo "refusing untracked or modified baseline-critical files" >&2
  exit 2
fi
[ "${AAR_RUNTIME_ROOT}" = "${ATTEMPT_DIR}" ] || { echo "attempt root drift" >&2; exit 2; }
if [ "${EVAL_RUN_BATCH}" != 2 ] || [ "${EVAL_RUN_GEN_CEILING}" != 8192 ]; then
  echo "evaluation profile drift" >&2
  exit 2
fi

BASE_INPUT="${AAR_RUNTIME_ROOT}/baseline_input"
OUT_DIR="${AAR_RUNTIME_ROOT}/baseline_results"
mkdir -p "${OUT_DIR}" "${AAR_RUNTIME_ROOT}/metadata"
export EVAL_GPUS=auto
unset EVAL_MAX_NEW_TOKENS

"${HARNESS_PY}" - "${AAR_RUNTIME_ROOT}/metadata/baseline_started.json" <<'PY'
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "started_utc": datetime.now(timezone.utc).isoformat(),
    "git_commit": os.environ["AAR_BASELINE_GIT_COMMIT"],
    "model_identity": "google/gemma-4-31B-it",
    "judge": {"backend": os.environ["JUDGE_BACKEND"], "model": os.environ["JUDGE_MODEL"]},
    "thinking_enabled": True,
    "evaluation_health": {
        "batch_size": int(os.environ["EVAL_RUN_BATCH"]),
        "freeform_generation_ceiling": int(os.environ["EVAL_RUN_GEN_CEILING"]),
        "fail_on_allocator_warning": os.environ["EVAL_FAIL_ON_ALLOCATOR_WARNING"] == "1",
        "max_truncation_rate": float(os.environ["EVAL_MAX_TRUNCATION_RATE"]),
    },
    "suite_benchmarks": os.environ["AAR_SUITE_BENCHMARKS"].split(),
}, indent=2) + "\n")
PY

"${HARNESS_PY}" "${REPO}/replication/preflight_v0.py" --judge-smoke-only
[ ! -e "${BASE_INPUT}/honesty_sycophancy_concealing_uncertainty" ] || { echo "baseline input already exists" >&2; exit 2; }
AAR_BASELINE_OVERRIDES="${PROVISIONAL}" "${HARNESS_PY}" "${REPO}/scripts/publish_suite.py" \
  --suite honesty_sycophancy_concealing_uncertainty --target-model google/gemma-4-31B-it \
  --holdout-dir "${BASE_INPUT}"

"${HARNESS_PY}" -u -m aar.eval_pod.run_eval \
  --suite "${BASE_INPUT}/honesty_sycophancy_concealing_uncertainty/honesty_sycophancy_concealing_uncertainty.yaml" \
  --model "${TARGET_MODEL_PATH}" \
  --secret-dir "${BASE_INPUT}/honesty_sycophancy_concealing_uncertainty" \
  --out "${OUT_DIR}/baseline.research.json" \
  --heldout-dir "${OUT_DIR}/private"

"${HARNESS_PY}" "${REPO}/replication/record_composed_baseline.py" \
  --result "${OUT_DIR}/private/baseline.research.json" \
  --manifest "${AAR_RUNTIME_ROOT}/metadata/baseline_started.json" \
  --repo "${REPO}" --output "${AAR_BASELINE_OVERRIDES}"

bash "${REPO}/scripts/publish_holdout.sh"
"${HARNESS_PY}" "${REPO}/replication/record_manifest_v0.py" --phase baseline
echo "[multidim-baseline] canonical baseline and production suite complete"
