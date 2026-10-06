#!/bin/bash
#SBATCH --job-name=aar-gemma-vllm-run5-pipeline
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=48
#SBATCH --gpus=4
#SBATCH --mem=512G
#SBATCH --time=36:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_5.sh}"
ATTEMPT_DIR="${AAR_BASELINE_ATTEMPT_DIR:?missing retained attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing submitted commit}"
PROVISIONAL="${AAR_PROVISIONAL_BASELINE_OVERRIDES:?missing provisional baseline}"

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

export AAR_EXPECTED_BRANCH=multi_vllm
export AAR_RUNTIME_ROOT="${ATTEMPT_DIR}"
export AAR_BASELINE_OVERRIDES="${ATTEMPT_DIR}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT_DIR}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT_DIR}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT="/checkpoint/ram/aar/${USER}/honesty-sycophancy-gemma4-31b-v0/librarian"
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"

export EVAL_INFERENCE_BACKEND=vllm
export EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536
export EVAL_VLLM_MAX_NUM_SEQS=256
export EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.80
export EVAL_VLLM_ENABLE_PREFIX_CACHING=1
export EVAL_VLLM_ENFORCE_EAGER=0
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH=/checkpoint/ram/shared/vllm_deployments_v2/aar-gemma-4-31b-it/src/serve_api_v2/worker/worker_vllm.sh
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}"
export AAR_VLLM_MERGED_ROOT="${ATTEMPT_DIR}/merged_candidates"

export AAR_TEAM_ID=honesty-sycophancy-concealing-gemma4_31b-opus48-fiveiter-vllm-run5-v0
export AAR_CLAUDE_SPEND_CAP_USD=500
export AAR_GPT_JUDGE_SPEND_CAP_USD=500
export AAR_CLAUDE_SESSION_BUDGET_USD=100
export OVERLOADED_MAX_RETRIES=0
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1
export AAR_VERIFY_TWO_ITERATION_ARTIFACTS=0
export AAR_FUNCTIONAL_SMOKE=1
export AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_MAX_CONCURRENT_TRAIN_JOBS=1
export AAR_EVAL_GPUS=4
export AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00
export AAR_EVAL_IDLE_SECONDS=604200
export AAR_START_EVAL_WORKER=1

[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || { echo "wrong branch" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "commit drift" >&2; exit 2; }
git -C "${REPO}" diff --quiet && git -C "${REPO}" diff --cached --quiet || {
  echo "tracked HPC worktree is dirty" >&2
  exit 2
}
for required in "${PROVISIONAL}" "${TARGET_MODEL_PATH}" "${LIT_AXIS_DIR}/manifest.json" \
  "${AAR_VLLM_WORKER_SH}" "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done
[ "${EVAL_INFERENCE_BACKEND}" = vllm ] || { echo "vLLM backend not enabled" >&2; exit 2; }
[ "${AAR_VLLM_CONTAINER_IMAGE}" = docker.io/vllm/vllm-openai:v0.25.1 ] || {
  echo "unvalidated image" >&2
  exit 2
}

BASE_INPUT="${ATTEMPT_DIR}/baseline_input"
OUT_DIR="${ATTEMPT_DIR}/baseline_results"
mkdir -p "${BASE_INPUT}" "${OUT_DIR}/private" "${ATTEMPT_DIR}/metadata"
export EVAL_GPUS=4
unset EVAL_MAX_NEW_TOKENS EVAL_VLLM_REQUIRE_MERGED EVAL_MODEL_PATH_OVERRIDE
export EVAL_VLLM_LORA_STRATEGY=base

"${HARNESS_PY}" - "${ATTEMPT_DIR}/metadata/baseline_started.json" <<'PY'
import importlib.metadata, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "started_utc": datetime.now(timezone.utc).isoformat(),
    "git_branch": subprocess.check_output(["git", "-C", os.environ["AAR_REPO"], "branch", "--show-current"], text=True).strip(),
    "git_commit": os.environ["AAR_BASELINE_GIT_COMMIT"],
    "model_identity": "google/gemma-4-31B-it",
    "model_path": os.environ["TARGET_MODEL_PATH"],
    "inference_backend": "vllm",
    "vllm_image": os.environ["AAR_VLLM_CONTAINER_IMAGE"],
    "vllm_strategy": "base",
    "language_model_only": True,
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

AAR_BASELINE_OVERRIDES="${PROVISIONAL}" "${HARNESS_PY}" "${REPO}/scripts/publish_suite.py" \
  --suite honesty_sycophancy_concealing_uncertainty \
  --target-model google/gemma-4-31B-it --holdout-dir "${BASE_INPUT}"

export MODEL_CFG_PATH="${TARGET_MODEL_PATH}"
"${REPO}/scripts/run_vllm_container.sh" python3 -u -m aar.eval_pod.run_eval \
  --suite "${BASE_INPUT}/honesty_sycophancy_concealing_uncertainty/honesty_sycophancy_concealing_uncertainty.yaml" \
  --model "${TARGET_MODEL_PATH}" \
  --secret-dir "${BASE_INPUT}/honesty_sycophancy_concealing_uncertainty" \
  --out "${OUT_DIR}/baseline.research.json" \
  --heldout-dir "${OUT_DIR}/private"

private_result="${OUT_DIR}/private/baseline.research.json"
"${HARNESS_PY}" - "${private_result}" <<'PY'
import json, sys
from pathlib import Path
result = json.loads(Path(sys.argv[1]).read_text())
if result.get("inference_backend") != "vllm":
    raise SystemExit(f"baseline did not use vLLM: {result.get('inference_backend')!r}")
if result.get("error"):
    raise SystemExit(f"baseline failed: {result['error']}")
if len(result.get("per_benchmark", {})) != 13:
    raise SystemExit("baseline did not produce all 13 benchmark scores")
PY

"${HARNESS_PY}" "${REPO}/replication/record_composed_baseline.py" \
  --result "${private_result}" \
  --manifest "${ATTEMPT_DIR}/metadata/baseline_started.json" \
  --repo "${REPO}" --output "${AAR_BASELINE_OVERRIDES}"
bash "${REPO}/scripts/publish_holdout.sh"
"${HARNESS_PY}" "${REPO}/replication/record_manifest_v0.py" --phase baseline

export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint
export EVAL_VLLM_REQUIRE_MERGED=1
launch_log="${ATTEMPT_DIR}/metadata/launch_run5_vllm_submission.txt"
bash "${REPO}/scripts/launch_team.sh" "pilot" 5 167 | tee "${launch_log}"
echo "[run5] vLLM baseline completed and sequential five-iteration AAR launched"
