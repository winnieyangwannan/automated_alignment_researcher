#!/bin/bash
#SBATCH --job-name=aar-train
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=8
#SBATCH --gpus=1
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%x-%j.out
#
# RESEARCH side of the hardened (two-user) loop. Run as aar-user (the AAR).
# Trains a method, stages the model to the shared submissions channel, then
# POLLS for the composite the eval worker (running as eval-user) writes
# after scoring against the LOCKED holdout. This job never reads the holdout.
# Args: <idea> [run_id]. Requires scripts/eval_worker.sh running as the eval user.

set -euo pipefail
IDEA="${1:?usage: slurm_train_submit.sh <idea> [run_id]}"
# UNIQUE run_id ENFORCEMENT: every run_id MUST be namespaced by this chain's IDEA_UID
# (= MODEL-SEED-launchtime, unique per chain), so two chains can NEVER mint the same id —
# which was the root cause of cross-chain score mis-binding. Prepend it unless the agent's
# tag already carries it (the prompt has the agent build it WITH the prefix, so this is a
# no-op for compliant ids and a hard safety net otherwise).
_TAG="${2:-${IDEA}-$(date +%s)}"
if [ -n "${IDEA_UID:-}" ]; then
  case "${_TAG}" in "${IDEA_UID}"*) RUN_ID="${_TAG}";; *) RUN_ID="${IDEA_UID}__${_TAG}";; esac
else
  RUN_ID="${_TAG}"
fi
echo "[train] canonical run_id=${RUN_ID}  (poll \$SCORES_DIR/${RUN_ID}.json and share_finding run_id=${RUN_ID})"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
elif [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/aar" ]; then
  REPO="$(cd -- "${SLURM_SUBMIT_DIR}" && pwd)"
elif [ -d "${SCRIPT_DIR}/../aar" ]; then
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
else
  echo "[train] ERROR: repository not found; set AAR_REPO or submit from the repository root" >&2
  exit 2
fi
# Generated methods live in the team's IDEAS_DIR (TEAM_DIR/methods); put it on the
# path so `import <idea>` resolves there, with REPO for the `aar` package + seed
# library (aar.ideas.<seed>). The heredoc tries the team top-level import first,
# then the repo seed package.
export AAR_IDEAS_DIR="${AAR_IDEAS_DIR:-${TEAM_DIR:+${TEAM_DIR}/methods}}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
export PYTHONPATH="${REPO}${AAR_IDEAS_DIR:+:${AAR_IDEAS_DIR}}${PYTHONPATH:+:${PYTHONPATH}}"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
export HARNESS_TRANSPORT=fs
# Resolve TARGET_MODEL from the same AXIS/MODEL contract as the chain.
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
# Env-honoring queue dirs: default under TEAM_DIR when set (per-team isolation), else
# the legacy shared path. The chain's env normally propagates these in via sbatch.
export SUBMISSIONS_DIR="${SUBMISSIONS_DIR:-${TEAM_DIR:+${TEAM_DIR}/submissions}}"
export SUBMISSIONS_DIR="${SUBMISSIONS_DIR:-${REPO}/_runs/submissions}"
export SCORES_DIR="${SCORES_DIR:-${TEAM_DIR:+${TEAM_DIR}/scores}}"
export SCORES_DIR="${SCORES_DIR:-${REPO}/_runs/scores}"
# NOTE: deliberately do NOT set/read HOLDOUT_DIR — this side can't read it.
PY="${HARNESS_PY}"
[ -x "${PY}" ] || { echo "[train] ERROR: Python is not executable: ${PY}" >&2; exit 2; }
STAGING="${TEAM_DIR:+${TEAM_DIR}/_train/${RUN_ID}}"
STAGING="${STAGING:-${REPO}/_runs/_train/${RUN_ID}}"
cd "${REPO}"

# FROZEN PRE-RUN PAPER — per-run audit stamp for the DECOUPLED flow. The inline flow stamps this
# inside the evaluate_model tool, but a decoupled run goes train -> put_model and never calls
# evaluate_model, so without this the run-keyed snapshot (.proposals/runs/<RUN_ID>.json) is never
# written and share_finding falls back to the per-CHAIN marker — which a later submit_idea_proposal
# overwrites (one marker per IDEA_UID). We snapshot THIS chain's currently-approved proposal paper to
# the run NOW, before training, while the marker still holds this run's paper. share_finding reads
# this run-keyed snapshot first (its lookup is keyed by run_id), restoring both the freeze guarantee
# and the per-run audit trail. Fail-open (|| true): a stamp failure must never block training.
PYTHONUNBUFFERED=1 "${PY}" -c "from aar.research_loop.tools.server_api_tools import _stamp_run_proposal as s; print('[train] per-run frozen-paper stamp ->', s('${RUN_ID}'))" \
  || echo "[train] WARN: per-run frozen-paper stamp errored (continuing)"

echo "[train] ${IDEA} -> stage model + submit (run ${RUN_ID})"
PYTHONUNBUFFERED=1 "${PY}" -u - <<PY
try:
    from ${IDEA}.run import run_experiment, MethodConfig   # team method (AAR_IDEAS_DIR on path)
except ModuleNotFoundError:
    from aar.ideas.${IDEA}.run import run_experiment, MethodConfig   # repo seed library
from aar import transport
out = run_experiment(MethodConfig(output_dir="${STAGING}"))
transport.put_model(out["model_path"], "${RUN_ID}")
print("[train] submitted ${RUN_ID}; waiting for eval worker to score it")
PY

# AUTO-PRUNE (1/2): the model is now staged into the submissions channel; the local _train staging copy
# is redundant. Drop it so the per-user quota doesn't fill (each checkpoint is ~6GB and a 47h run
# produces hundreds). Safe: nothing reads STAGING after put_model.
if [ "${AAR_KEEP_CHECKPOINTS:-0}" != "1" ]; then
  case "${STAGING}" in
    "${TEAM_DIR:-${REPO}/_runs}"/_train/*) rm -rf -- "${STAGING:?}" 2>/dev/null || true ;;
    *) echo "[train] REFUSING unsafe staging cleanup target: ${STAGING}" >&2; exit 2 ;;
  esac
else
  echo "[train] retaining staging checkpoint: ${STAGING}"
fi

echo "[train] polling for scores (eval worker scores it against the locked holdout)"
for _ in $(seq 1 "${AAR_SCORE_POLL_ATTEMPTS:-180}"); do   # default: up to ~1h
  if [ -f "${SCORES_DIR}/${RUN_ID}.json" ]; then
    echo "[train] composite:"; cat "${SCORES_DIR}/${RUN_ID}.json"; echo
    # AUTO-PRUNE (2/2): the eval wrote the score => it has finished reading the submitted model. The
    # ~6GB checkpoint is no longer needed (the finding keeps the code snapshot + the scores), so drop
    # it. Quota-safe; the eval (incl. held-out) is fully done by the time any score file exists.
    if [ "${AAR_KEEP_CHECKPOINTS:-0}" != "1" ]; then
      _submission_cleanup="${SUBMISSIONS_DIR:?}/${RUN_ID:?}"
      case "${_submission_cleanup}" in
        "${SUBMISSIONS_DIR}"/*) rm -rf -- "${_submission_cleanup:?}" 2>/dev/null || true ;;
        *) echo "[train] REFUSING unsafe submission cleanup target" >&2; exit 2 ;;
      esac
      echo "[train] pruned model checkpoints (staging + submission)"
    else
      echo "[train] retaining submitted checkpoint: ${SUBMISSIONS_DIR}/${RUN_ID}"
    fi
    echo "=== DONE ==="; exit 0
  fi
  sleep 20
done
echo "[train] TIMEOUT waiting for scores — is the eval worker running?"; exit 1
