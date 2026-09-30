#!/bin/bash
#SBATCH --job-name=aar-v0-eval-gpu-smoke
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=8
#SBATCH --gpus=2
#SBATCH --mem=32G
#SBATCH --time=00:10:00
set -euo pipefail
REPO="${AAR_REPO:-${SLURM_SUBMIT_DIR:?submit from the replication worktree}}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_v0.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
export EVAL_GPUS=auto
"${HARNESS_PY}" - <<'PY'
import json
import torch
from aar.eval_pod.run_eval import _resolve_ngpu

assert torch.cuda.is_available()
assert torch.cuda.device_count() == 2, torch.cuda.device_count()
assert _resolve_ngpu() == 2
for device in range(2):
    x = torch.ones((64, 64), device=f"cuda:{device}", dtype=torch.bfloat16)
    assert float((x @ x)[0, 0]) == 64.0
print(json.dumps({
    "ok": True,
    "devices": [torch.cuda.get_device_name(i) for i in range(2)],
    "eval_workers": _resolve_ngpu(),
}))
PY
mkdir -p "${AAR_RUNTIME_ROOT}/preflight"
date --iso-8601=seconds > "${AAR_RUNTIME_ROOT}/preflight/evaluator_gpu.ok"
