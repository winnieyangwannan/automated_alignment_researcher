#!/bin/bash
#SBATCH --job-name=aar-v0-web-smoke
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
set -euo pipefail
REPO="${AAR_REPO:-${SLURM_SUBMIT_DIR:?submit from the replication worktree}}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_v0.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
export CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH:-/usr/local/bin/claude}"
"${HARNESS_PY}" "${REPO}/replication/smoke_aar_internet_v0.py"
