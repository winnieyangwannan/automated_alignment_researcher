#!/bin/bash
#SBATCH --job-name=aar-v0-gpu-canary
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=8
#SBATCH --gpus=1
#SBATCH --mem=96G
#SBATCH --time=01:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:-${SLURM_SUBMIT_DIR:?submit from the replication worktree}}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_v0.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/.venv/bin/activate"

ATTEMPT_DIR="${AAR_CANARY_ATTEMPT_DIR:?submit with submit_gpu_canary_v0.sh}"
EXPECTED_COMMIT="${AAR_CANARY_GIT_COMMIT:?missing submitted Git commit}"
case "${ATTEMPT_DIR}" in
  /checkpoint/*) ;;
  *) echo "canary output must be under /checkpoint: ${ATTEMPT_DIR}" >&2; exit 2 ;;
esac
[ "$(git -C "${REPO}" branch --show-current)" = uv ] || {
  echo "canary requires branch uv" >&2
  exit 2
}
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || {
  echo "worktree commit changed after canary submission" >&2
  exit 2
}
git -C "${REPO}" diff --quiet && git -C "${REPO}" diff --cached --quiet || {
  echo "canary requires a clean tracked HPC worktree" >&2
  exit 2
}
[ "${EVAL_RUN_BATCH}" = 2 ] || {
  echo "canary must inherit EVAL_RUN_BATCH=2 from env_v0.sh" >&2
  exit 2
}
[ "${EVAL_RUN_GEN_CEILING}" = 8192 ] || {
  echo "canary must inherit EVAL_RUN_GEN_CEILING=8192 from env_v0.sh" >&2
  exit 2
}
[ "${EVAL_RUN_GEN_CEILING_BENCHMARKS}" = "sycophancy_eval sycon_fp gsm8k ifeval" ] || {
  echo "canary must inherit the complete generation-ceiling scope" >&2
  exit 2
}
[ -d "${ATTEMPT_DIR}" ] || {
  echo "canary attempt directory is missing: ${ATTEMPT_DIR}" >&2
  exit 2
}
[ ! -e "${ATTEMPT_DIR}/started.json" ] || {
  echo "refusing to reuse canary attempt: ${ATTEMPT_DIR}" >&2
  exit 2
}

INPUT_DIR="${ATTEMPT_DIR}/input"
RESULT_DIR="${ATTEMPT_DIR}/results"
mkdir "${INPUT_DIR}" "${RESULT_DIR}"

# Twenty completions exercise five full batches and the unchanged production
# truncation gate (more than 5% no-stop truncations fails at this sample size).
export EVAL_GPUS=1
unset EVAL_MAX_NEW_TOKENS

"${HARNESS_PY}" - "${ATTEMPT_DIR}/started.json" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "started_utc": datetime.now(timezone.utc).isoformat(),
    "git_commit": os.environ["AAR_CANARY_GIT_COMMIT"],
    "model": "google/gemma-4-31B-it",
    "judge_backend": os.environ["JUDGE_BACKEND"],
    "judge_model": os.environ["JUDGE_MODEL"],
    "benchmark": "sycophancy_eval",
    "subset_size": 20,
    "batch_size": int(os.environ["EVAL_RUN_BATCH"]),
    "freeform_generation_ceiling": int(os.environ["EVAL_RUN_GEN_CEILING"]),
    "generation_ceiling_benchmarks": os.environ[
        "EVAL_RUN_GEN_CEILING_BENCHMARKS"
    ].split(),
    "max_truncation_rate": float(os.environ["EVAL_MAX_TRUNCATION_RATE"]),
}, indent=2) + "\n")
PY

# Verify the exact production judge path from this GPU allocation before model
# loading. Any endpoint, credential, model, status, or output mismatch aborts.
"${HARNESS_PY}" "${REPO}/replication/preflight_v0.py" --judge-smoke-only

(unset AAR_BASELINE_OVERRIDES; "${HARNESS_PY}" "${REPO}/scripts/publish_suite.py" \
  --suite sycophancy \
  --target-model google/gemma-4-31B-it \
  --holdout-dir "${INPUT_DIR}" \
  --only sycophancy_eval \
  --force-n 20)

"${HARNESS_PY}" - "${INPUT_DIR}/sycophancy/sycophancy.yaml" <<'PY'
import sys
from pathlib import Path

import yaml

suite = yaml.safe_load(Path(sys.argv[1]).read_text())
benchmarks = suite.get("benchmarks", [])
assert len(benchmarks) == 1, benchmarks
assert benchmarks[0]["name"] == "sycophancy_eval", benchmarks
assert benchmarks[0]["subset_size"] == 20, benchmarks
PY

"${HARNESS_PY}" -u -m aar.eval_pod.run_eval \
  --suite "${INPUT_DIR}/sycophancy/sycophancy.yaml" \
  --model "${TARGET_MODEL_PATH}" \
  --secret-dir "${INPUT_DIR}/sycophancy" \
  --out "${RESULT_DIR}/canary.research.json"

"${HARNESS_PY}" - "${RESULT_DIR}/canary.research.json" "${ATTEMPT_DIR}/complete.json" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

score = json.loads(Path(sys.argv[1]).read_text())
benchmark = score["per_benchmark"]["sycophancy_eval"]
assert benchmark["n"] == 20, benchmark
Path(sys.argv[2]).write_text(json.dumps({
    "completed_utc": datetime.now(timezone.utc).isoformat(),
    "status": "passed",
    "scored_examples": benchmark["n"],
}, indent=2) + "\n")
PY

echo "[gpu-canary-v0] passed; retained artifacts=${ATTEMPT_DIR}"
