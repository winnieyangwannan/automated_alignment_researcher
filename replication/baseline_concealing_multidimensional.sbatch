#!/bin/bash
#SBATCH --job-name=aar-md-concealing-bl
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=32
#SBATCH --gpus=4
#SBATCH --mem=384G
#SBATCH --time=36:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:-${SLURM_SUBMIT_DIR:?submit from the uv worktree}}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/.venv/bin/activate"

ATTEMPT_DIR="${AAR_BASELINE_ATTEMPT_DIR:?missing retained attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing submitted commit}"
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
MANIFEST="${AAR_RUNTIME_ROOT}/metadata/baseline_started.json"
mkdir -p "${OUT_DIR}" "${AAR_RUNTIME_ROOT}/metadata"
export EVAL_GPUS=auto
export JUDGE_CONCURRENCY=16
unset EVAL_MAX_NEW_TOKENS

"${HARNESS_PY}" - "${MANIFEST}" <<'PY'
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "started_utc": datetime.now(timezone.utc).isoformat(),
    "git_commit": subprocess.check_output(
        ["git", "-C", os.environ["AAR_REPO"], "rev-parse", "HEAD"], text=True
    ).strip(),
    "model_identity": "google/gemma-4-31B-it",
    "judge": {"backend": os.environ["JUDGE_BACKEND"], "model": os.environ["JUDGE_MODEL"]},
    "thinking_enabled": True,
    "evaluation_health": {
        "batch_size": int(os.environ["EVAL_RUN_BATCH"]),
        "freeform_generation_ceiling": int(os.environ["EVAL_RUN_GEN_CEILING"]),
        "evaluation_gpus": len([
            value for value in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",")
            if value.strip()
        ]),
        "judge_concurrency": int(os.environ["JUDGE_CONCURRENCY"]),
    },
    "suite_benchmarks": [
        "llm_uncertainty_bench", "verbalized_ece", "abstentionbench", "sciq_uncertainty"
    ],
}, indent=2) + "\n")
PY

"${HARNESS_PY}" "${REPO}/replication/preflight_v0.py" --judge-smoke-only
# This source run measures the baseline that will later populate the override;
# it cannot consume the not-yet-created run-local override itself.
(unset AAR_BASELINE_OVERRIDES; "${HARNESS_PY}" "${REPO}/scripts/publish_suite.py" \
  --suite concealing_uncertainty --target-model google/gemma-4-31B-it \
  --holdout-dir "${BASE_INPUT}" \
  --only llm_uncertainty_bench verbalized_ece abstentionbench sciq_uncertainty)

"${HARNESS_PY}" -u -m aar.eval_pod.run_eval \
  --suite "${BASE_INPUT}/concealing_uncertainty/concealing_uncertainty.yaml" \
  --model "${TARGET_MODEL_PATH}" \
  --secret-dir "${BASE_INPUT}/concealing_uncertainty" \
  --out "${OUT_DIR}/baseline.research.json" \
  --heldout-dir "${OUT_DIR}/private"

echo "[concealing-baseline] result=${OUT_DIR}/private/baseline.research.json"
echo "[concealing-baseline] manifest=${MANIFEST}"
