#!/bin/bash
# Launch one scored Kimi AAR iteration and retain its real PEFT candidate for
# the Run 12 automatic-promotion and next-iteration attachment proof.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"

export AAR_EXPECTED_BRANCH=autodata
export AAR_KIMI_SERVE_DEPLOYMENT=aar_8-kimi26
export AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KEEP_CHECKPOINTS=1
export AAR_RUN10_ATTEMPT_PARENT="/checkpoint/ram/${USER:?}/aar-runs/run12-adapter-target/research_canary_attempts"
export AAR_RUN10_TEAM_ID_PREFIX=run12-gemma4-31b-kimi26-research
export AAR_RUN10_CANARY_ITERATIONS="${AAR_RUN12_RESEARCH_MAX_ITERATIONS:-1}"
if [ -n "${AAR_RUN12_RECOVERED_AGENT_LOG_DIR:-}" ]; then
  export AAR_RUN10_RECOVERED_AGENT_LOG_DIR="${AAR_RUN12_RECOVERED_AGENT_LOG_DIR}"
fi

exec "${REPO}/experiments/dishonest_sycophancy_concealing/run_10/submit_run_10.sh" canary
