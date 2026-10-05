#!/bin/bash
#SBATCH --job-name=aar-v0-baseline
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --gpus=2
#SBATCH --mem=192G
#SBATCH --time=12:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:-${SLURM_SUBMIT_DIR:?submit from the replication worktree}}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_v0.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/.venv/bin/activate"

ATTEMPT_DIR="${AAR_BASELINE_ATTEMPT_DIR:?submit with submit_baseline_v0.sh}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing submitted Git commit}"
case "${ATTEMPT_DIR}" in
  /checkpoint/*) ;;
  *) echo "baseline output must be under /checkpoint: ${ATTEMPT_DIR}" >&2; exit 2 ;;
esac
[ "${AAR_RUNTIME_ROOT}" = "${ATTEMPT_DIR}" ] || {
  echo "baseline runtime root does not match its retained attempt" >&2
  exit 2
}
[ "$(git -C "${REPO}" branch --show-current)" = uv ] || {
  echo "baseline requires branch uv" >&2
  exit 2
}
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || {
  echo "worktree commit changed after baseline submission" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "baseline requires a clean tracked HPC worktree" >&2
  exit 2
fi
[ "${EVAL_RUN_BATCH}" = 2 ] || {
  echo "baseline must inherit EVAL_RUN_BATCH=2 from env_v0.sh" >&2
  exit 2
}
[ "${EVAL_RUN_GEN_CEILING}" = 8192 ] || {
  echo "baseline must inherit EVAL_RUN_GEN_CEILING=8192 from env_v0.sh" >&2
  exit 2
}
[ "${EVAL_RUN_GEN_CEILING_BENCHMARKS}" = "sycophancy_eval sycon_fp gsm8k ifeval" ] || {
  echo "baseline must apply the 8192-token ceiling to every generative suite benchmark" >&2
  exit 2
}
[ -d "${ATTEMPT_DIR}" ] || {
  echo "baseline attempt directory is missing: ${ATTEMPT_DIR}" >&2
  exit 2
}
[ ! -e "${ATTEMPT_DIR}/metadata/baseline_started.json" ] || {
  echo "refusing to reuse baseline attempt: ${ATTEMPT_DIR}" >&2
  exit 2
}

BASE_INPUT="${AAR_RUNTIME_ROOT}/baseline_input"
OUT_DIR="${AAR_RUNTIME_ROOT}/baseline_results"
mkdir -p "${OUT_DIR}" "${AAR_RUNTIME_ROOT}/metadata"
export EVAL_GPUS=auto
unset EVAL_MAX_NEW_TOKENS

"${HARNESS_PY}" - "${ATTEMPT_DIR}/metadata/baseline_started.json" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "started_utc": datetime.now(timezone.utc).isoformat(),
    "git_commit": os.environ["AAR_BASELINE_GIT_COMMIT"],
    "model": "google/gemma-4-31B-it",
    "judge_backend": os.environ["JUDGE_BACKEND"],
    "judge_model": os.environ["JUDGE_MODEL"],
    "benchmarks": os.environ["AAR_SUITE_BENCHMARKS"].split(),
    "batch_size": int(os.environ["EVAL_RUN_BATCH"]),
    "freeform_generation_ceiling": int(os.environ["EVAL_RUN_GEN_CEILING"]),
    "generation_ceiling_benchmarks": os.environ[
        "EVAL_RUN_GEN_CEILING_BENCHMARKS"
    ].split(),
}, indent=2) + "\n")
PY

# This runs inside the actual baseline Slurm allocation, immediately before
# Gemma is loaded. It fails closed unless the pinned GPT judge completes one
# minimal request through FAIR Model API.
"${HARNESS_PY}" "${REPO}/replication/preflight_v0.py" --judge-smoke-only

# Materialize the full suite inside the allocation rather than doing dataset
# work on the login node. The attempt is fresh, so any existing suite is an
# error rather than something to replace.
[ ! -e "${BASE_INPUT}/sycophancy" ] || {
  echo "refusing to overwrite baseline input: ${BASE_INPUT}/sycophancy" >&2
  exit 2
}
(unset AAR_BASELINE_OVERRIDES; "${HARNESS_PY}" "${REPO}/scripts/publish_suite.py" \
  --suite sycophancy --target-model google/gemma-4-31B-it \
  --holdout-dir "${BASE_INPUT}" --only sycophancy_eval sycon_fp mmlu gsm8k ifeval)

"${HARNESS_PY}" -u -m aar.eval_pod.run_eval \
  --suite "${BASE_INPUT}/sycophancy/sycophancy.yaml" \
  --model "${TARGET_MODEL_PATH}" \
  --secret-dir "${BASE_INPUT}/sycophancy" \
  --out "${OUT_DIR}/baseline.research.json" \
  --heldout-dir "${OUT_DIR}/private"

"${HARNESS_PY}" "${REPO}/replication/record_baseline_v0.py" \
  "${OUT_DIR}/private/baseline.research.json" "${AAR_BASELINE_OVERRIDES}"

# Publish the immutable production suite only after all five exact-model
# baselines exist, so no placeholder can enter the hill-climb configuration.
bash "${REPO}/scripts/publish_holdout.sh"
"${HARNESS_PY}" "${REPO}/replication/record_manifest_v0.py" --phase baseline
echo "[baseline-v0] complete; production suite=${HOLDOUT_DIR}/sycophancy/sycophancy.yaml"
