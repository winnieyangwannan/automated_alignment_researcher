#!/bin/bash
# Launch five 12-hour multi-dimensional AAR chains from one canonical baseline.
set -euo pipefail
umask 077

[ "$#" = 1 ] || {
  echo "usage: AAR_CLAUDE_SPEND_CAP_USD=<cap> AAR_GPT_JUDGE_SPEND_CAP_USD=<cap> $0 <retained-attempt>/attempt.env" >&2
  exit 2
}
: "${AAR_CLAUDE_SPEND_CAP_USD:?explicit full-run Claude USD cap required}"
: "${AAR_GPT_JUDGE_SPEND_CAP_USD:?explicit full-run GPT judge USD cap required}"
: "${AAR_MULTIDIM_SCORING_CONFIRMED:?set to 1 only after confirming coverage weighting and per-benchmark regression gates}"
[ "${AAR_MULTIDIM_SCORING_CONFIRMED}" = 1 ] || { echo "AAR_MULTIDIM_SCORING_CONFIRMED must equal 1" >&2; exit 2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
attempt_env="$(realpath -e -- "$1")"
expected_base="/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts"

[ "$(grep -cve '^[[:space:]]*$' "${attempt_env}")" = 1 ] || {
  echo "attempt.env must contain exactly one non-empty line" >&2; exit 2;
}
grep -Eq '^export AAR_RUNTIME_ROOT=/checkpoint/ram/aar/[A-Za-z0-9._-]+/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/[A-Za-z0-9._-]+$' "${attempt_env}" || {
  echo "attempt.env is not a retained multi-dimensional baseline selector" >&2; exit 2;
}
# shellcheck disable=SC1090
source "${attempt_env}"
attempt_root="$(realpath -e -- "${AAR_RUNTIME_ROOT}")"
[ "${attempt_env}" = "${attempt_root}/attempt.env" ] || {
  echo "attempt.env must live at the root it selects" >&2; exit 2;
}
case "${attempt_root}" in "${expected_base}"/*) ;; *) echo "attempt outside ${expected_base}" >&2; exit 2;; esac

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

[ "$(git -C "${REPO}" branch --show-current)" = uv ] || { echo "branch must be uv" >&2; exit 2; }
git -C "${REPO}" diff --quiet && git -C "${REPO}" diff --cached --quiet || {
  echo "full launch requires a clean tracked worktree" >&2; exit 2;
}

baseline="${AAR_BASELINE_OVERRIDES}"
suite="${HOLDOUT_DIR}/honesty_sycophancy_concealing_uncertainty/honesty_sycophancy_concealing_uncertainty.yaml"
manifest="${AAR_RUNTIME_ROOT}/metadata/manifest-baseline.json"
for required in "${baseline}" "${suite}" "${manifest}"; do
  [ -s "${required}" ] || { echo "required retained artifact missing: ${required}" >&2; exit 2; }
done
"${HARNESS_PY}" - "${baseline}" "${manifest}" "${REPO}" <<'PY'
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

for name in ("AAR_CLAUDE_SPEND_CAP_USD", "AAR_GPT_JUDGE_SPEND_CAP_USD"):
    value = Decimal(os.environ[name])
    assert value.is_finite() and value > 0, f"{name} must be positive and finite"
baseline = json.loads(Path(sys.argv[1]).read_text())
manifest = json.loads(Path(sys.argv[2]).read_text())
head = subprocess.check_output(["git", "-C", sys.argv[3], "rev-parse", "HEAD"], text=True).strip()
assert baseline.get("status") == "canonical_final_commit_composed_baseline"
assert baseline.get("git_commit") == head
assert manifest.get("git_commit") == head
assert manifest.get("suite_benchmarks") == [
    "mask_factual", "mask_continuation", "mask_disinformation", "sycophancy_eval",
    "llm_uncertainty_bench", "verbalized_ece", "abstentionbench",
    "deceptionbench_reward", "sycon_fp", "sciq_uncertainty",
    "mmlu", "gsm8k", "ifeval",
]
assert manifest.get("judge") == {"backend": "model_api", "model": "gpt-5-6-luna"}
assert manifest.get("monitor") == {"backend": "model_api", "model": "claude-4-8-opus"}
assert manifest.get("librarian_model") == "claude-sonnet-4-6"
assert manifest.get("petri") == {"mode": "post_hoc_only", "included_in_optimization": False}
PY

bash "${REPO}/scripts/preflight_aar.sh"
submission_log="${AAR_RUNTIME_ROOT}/metadata/launch_multidimensional_12h_submission.txt"
[ ! -e "${submission_log}" ] || { echo "refusing to overwrite ${submission_log}" >&2; exit 2; }
[ ! -e "${AAR_RUNTIME_ROOT}/aar_teams/${AAR_TEAM_ID}" ] || { echo "team already exists" >&2; exit 2; }
bash "${REPO}/scripts/launch_team.sh" "alpha beta gamma delta epsilon" 500 12 | tee "${submission_log}"
"${HARNESS_PY}" "${SCRIPT_DIR}/record_manifest_v0.py" \
  --phase launch-12h --submission-log "${submission_log}"
