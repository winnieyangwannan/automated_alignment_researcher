#!/bin/bash
#SBATCH --job-name=aar-v0-env
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --gpus=1
#SBATCH --mem=96G
#SBATCH --time=01:00:00
set -euo pipefail
REPO="${AAR_REPO:-${SLURM_SUBMIT_DIR:?submit from the replication worktree}}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_v0.sh"
[ "$(git -C "${REPO}" branch --show-current)" = uv ] || {
  echo "wrong branch" >&2
  exit 2
}
UV=/storage/home/winnieyangwn/envs/aar-uv-bootstrap/bin/uv
[ -x "${UV}" ] || { echo "ARM64 uv bootstrap is missing: ${UV}" >&2; exit 2; }
cd "${REPO}"
"${UV}" sync --frozen
source .venv/bin/activate
export PYTHONPATH="${PWD}"
export AAR_BENCHMARK_DOCS="${PWD}/benchmark_docs"
export BENCHMARK_DOCS_DIR="${PWD}/benchmark_docs"
python - <<'PY'
import platform
import torch
import transformers
import peft
import trl
import claude_agent_sdk

assert platform.machine() == "aarch64", platform.machine()
assert torch.version.cuda, "PyTorch is not CUDA-enabled"
assert torch.cuda.is_available(), "torch.cuda.is_available() is false"
x = torch.ones((64, 64), device="cuda", dtype=torch.bfloat16)
assert float((x @ x)[0, 0]) == 64.0
print("CUDA", torch.version.cuda, torch.cuda.get_device_name(0))
print("imports", transformers.__version__, peft.__version__, trl.__version__)
PY
mkdir -p "${AAR_RUNTIME_ROOT}/preflight"
date --iso-8601=seconds > "${AAR_RUNTIME_ROOT}/preflight/environment.ok"
