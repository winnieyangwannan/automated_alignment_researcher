#!/bin/bash
#SBATCH --job-name=aar-eval-worker
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=8
#SBATCH --gpus=2
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=slurm-%x-%j.out
#
# Eval worker — SUBMIT THIS AS eval-user (the secret-holding user):
#   ssh eval-user@<login> 'cd <repo>; sbatch scripts/eval_worker.sh'
#
# Holds one GPU and drains the submission queue: for each run the research user
# stages a model for (marker `.submitted`, no scores yet), it scores the model
# against the LOCKED holdout (which only this user can read) and writes the
# composite to the shared SCORES_DIR. The research/AAR side never reads the
# holdout — it only stages a model and polls SCORES_DIR. Exits after being idle.

set -uo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
elif [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/aar" ]; then
  REPO="$(cd -- "${SLURM_SUBMIT_DIR}" && pwd)"
else
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
fi
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
# Generation budget: leave EVAL_MAX_NEW_TOKENS UNSET so scoring uses the per-model
# AUTO budget (models.py: model's remaining context, capped by EVAL_AUTO_CEILING).
# This is the SAME default the baseline run uses — baseline and method-scoring can
# no longer diverge (the 256-vs-512 truncation bug that broke the gsm8k floor).
export HARNESS_TRANSPORT=fs
# All four dirs are env-honoring (default = today's path). A per-model worker for a
# SECOND team on the same axis passes model-namespaced dirs (holdout_<model>,
# submissions_<model>, scores_<model>) so two models' eval queues + baselines never
# cross. Unset (the normal single-team case) => byte-identical to before.
# HOLDOUT_DIR default is DEFERRED: it's set per-MODEL (holdout/<model_tag>) in the per-team block
# below, derived from the team id so it ALWAYS matches what publish_holdout wrote — two same-axis/
# different-model teams can't collide. Explicit HOLDOUT_DIR (or the legacy fallback at the end) wins.
export HOLDOUT_DIR="${HOLDOUT_DIR-}"
# GOLDEN per-benchmark decoding source — EVAL-SIDE ONLY. benchmark_docs names the held-out
# benchmarks, so it must NEVER live on the research (aar-user) side or the AAR could read
# which benchmark is held out. The eval pod (this user) reads it to score each benchmark at
# the exact config its baseline used. Lives next to the holdout, mode-700.
export BENCHMARK_DOCS_DIR="${BENCHMARK_DOCS_DIR:-${REPO}/benchmark_docs}"
# HELD-OUT scores: per-team (set in the per-team block); legacy fallback finalized after HOLDOUT_DIR.
export SUBMISSIONS_DIR="${SUBMISSIONS_DIR:-${AAR_RUNTIME_ROOT}/submissions}"
export SCORES_DIR="${SCORES_DIR:-${AAR_RUNTIME_ROOT}/scores}"      # research-readable handoff (stripped)
PY="${HARNESS_PY}"
[ -x "${PY}" ] || { echo "[worker] ERROR: Python is not executable: ${PY}" >&2; exit 2; }
SUITE="${1:-sycophancy}"
IDLE_EXIT="${2:-1800}"   # exit after this many seconds with no work
if [ "${SUITE}" = honesty ]; then
  export JUDGE_BACKEND="${JUDGE_BACKEND:-model_api}"
  export JUDGE_MODEL="${JUDGE_MODEL:-claude-4-8-opus}"
  export MASK_JUDGE_MODEL="${MASK_JUDGE_MODEL:-claude-4-8-opus}"
  case "${JUDGE_BACKEND}" in
    model_api) [ -n "${MODEL_API_KEY:-}" ] || { echo "[worker] ERROR: honesty Model API judge requires MODEL_API_KEY" >&2; exit 2; };;
    anthropic) [ -n "${ANTHROPIC_API_KEY:-${ANT_high_prio_API:-${ANT_API_KEY:-}}}" ] || { echo "[worker] ERROR: honesty Anthropic judge requires a direct key" >&2; exit 2; };;
    *) echo "[worker] ERROR: honesty JUDGE_BACKEND must be model_api or anthropic" >&2; exit 2;;
  esac
elif [ "${SUITE}" = honesty_sycophancy ] || [ "${SUITE}" = honesty_sycophancy_concealing_uncertainty ]; then
  export JUDGE_BACKEND="${JUDGE_BACKEND:-model_api}"
  export JUDGE_MODEL="${JUDGE_MODEL:-gpt-5-6-luna}"
  export MASK_JUDGE_MODEL="${MASK_JUDGE_MODEL:-gpt-5-6-luna}"
  [ -n "${MODEL_API_KEY:-}" ] || { echo "[worker] ERROR: composed-suite Model API judge requires MODEL_API_KEY" >&2; exit 2; }
fi
if [ -z "${HF_TOKEN:-}" ]; then
  echo "[worker] ERROR: HF_TOKEN is required for the target model/datasets" >&2
  exit 2
fi
# Benchmarks score in parallel across the allocated GPUs. The launcher passes
# its validated numeric GPU count so containerized evaluation does not depend on
# Slurm's CUDA_VISIBLE_DEVICES surviving the container environment boundary.
# Direct invocations may still pass "auto" as the third argument.
export EVAL_GPUS="${3:-auto}"
# BATCH-SIZE PARITY: greedy decode is NOT batch-invariant (FP-path drift ~0.5 pt), so the
# trained-eval batch MUST equal the suite's baseline batch or the composite delta is corrupted.
# hallucination was baselined at batch 32 (3.2x faster gen on H200, ~36/140 GB). Other suites
# default to models.py's 16 here — NOTE their baselines used 8 (pre-existing mismatch; see
# train_baseline_sync.md). The multi-dimensional Gemma run pins one 8192-token
# private-thinking + visible-answer budget on baseline and candidate evaluation.
case "${SUITE}" in
  sycophancy)          export EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-8}";  export EVAL_AUTO_CEILING="${EVAL_AUTO_CEILING:-8192}"; export EVAL_RUN_GEN_CEILING="${EVAL_RUN_GEN_CEILING:-8192}"; export EVAL_RUN_NGRAM="${EVAL_RUN_NGRAM:-4}" ;;
  honesty)             export EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-32}"; export EVAL_AUTO_CEILING="${EVAL_AUTO_CEILING:-8192}"; export EVAL_RUN_GEN_CEILING="${EVAL_RUN_GEN_CEILING:-8192}"; export EVAL_RUN_NGRAM="${EVAL_RUN_NGRAM:-4}"; export EVAL_NO_REPEAT_NGRAM="${EVAL_NO_REPEAT_NGRAM:-4}" ;;
  honesty_sycophancy)  export EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-4}";  export EVAL_AUTO_CEILING="${EVAL_AUTO_CEILING:-8192}"; export EVAL_RUN_GEN_CEILING="${EVAL_RUN_GEN_CEILING:-8192}"; export EVAL_RUN_NGRAM="${EVAL_RUN_NGRAM:-4}"; export EVAL_NO_REPEAT_NGRAM="${EVAL_NO_REPEAT_NGRAM:-4}" ;;
  honesty_sycophancy_concealing_uncertainty) export EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-4}"; export EVAL_AUTO_CEILING="${EVAL_AUTO_CEILING:-8192}"; export EVAL_RUN_GEN_CEILING="${EVAL_RUN_GEN_CEILING:-8192}"; export EVAL_RUN_NGRAM="${EVAL_RUN_NGRAM:-4}"; export EVAL_NO_REPEAT_NGRAM="${EVAL_NO_REPEAT_NGRAM:-4}" ;;
  refusal)             export EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-8}";  export EVAL_AUTO_CEILING="${EVAL_AUTO_CEILING:-4096}" ;;
  hallucination|faithfulness) export EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-32}"
                      # ragtruth FAITHFULNESS needs the finetuned Llama-2-13b detector (~0.80 F1), not the
                      # prompt-judge fallback — pin both (mirror eval_job.sh / baseline_hallucination.sh).
                      export RAGTRUTH_DETECTOR="${RAGTRUTH_DETECTOR:-/opt/aar/work/aar_repo_runs/_ragtruth_detector}"
                      export RAGTRUTH_DETECTOR_BASE="${RAGTRUTH_DETECTOR_BASE:-meta-llama/Llama-2-13b-hf}" ;;
  power_seeking)      export EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-32}" ;;
esac
# NB: the above are a FALLBACK only — run_eval now pins decoding PER-BENCHMARK from the
# eval-side benchmark_docs/<group>/baseline.json (the capability basket at its own config on
# every axis), so each benchmark is scored exactly as its baseline was.
# JUDGE backend MUST also match the axis's baseline, or judge-scored benchmarks diverge from
# their baseline. The baseline scripts pin it per axis: hallucination = LOCAL Qwen2.5-7B
# (baseline_hallucination.sh); honesty/sycophancy/refusal = OpenAI per-paper (baseline_honesty/
# newsyc/safety_v2). eval_worker had set NONE -> run_eval defaulted to openai -> hallucination
# would have been judged by OpenAI but baselined on local Qwen. Pin it to match:
case "${SUITE}" in
  # hallucination: judge-free (logprob) legs except ragtruth's finetuned detector — local Qwen, pin both sides.
  hallucination) export JUDGE_BACKEND="${JUDGE_BACKEND:-local}"; export JUDGE_MODEL_LOCAL="${JUDGE_MODEL_LOCAL:-Qwen/Qwen2.5-7B-Instruct}" ;;
  # faithfulness (2026-06-27 redesign): the 2 MULTI-TURN free-form legs (faith_mt_grounded/claimcheck) AND
  # ragtruth are now Haiku-judged free-form generation → ANTHROPIC claude-haiku-4-5 @ conc 100 (mirrors the
  # `bias)` case; the logprob legs llm_aggrefact_A/B + summedits have no judge → unaffected). NB: this moves
  # ragtruth's judge from local-Qwen → Haiku, so ragtruth must be re-baselined on Haiku (baseline_faithfulness.sh).
  faithfulness) export JUDGE_BACKEND="${JUDGE_BACKEND:-anthropic}"; export JUDGE_MODEL="${JUDGE_MODEL:-claude-haiku-4-5}"; export JUDGE_CONCURRENCY="${JUDGE_CONCURRENCY:-100}" ;;
  # privacy: privacylens is the only judged leg (confaide + privaci_bench are rule-scored). Switched to
  # ANTHROPIC claude-haiku-4-5 (2026-06-22) — a stronger CoT judge than local Qwen for the leakage + 0-3
  # helpfulness judgments. The Anthropic key is sourced above (same plumbing as honesty).
  privacy) export JUDGE_BACKEND="${JUDGE_BACKEND:-anthropic}"; export JUDGE_MODEL="${JUDGE_MODEL:-claude-haiku-4-5}"; export JUDGE_CONCURRENCY="${JUDGE_CONCURRENCY:-4}"; export ANTHROPIC_MIN_INTERVAL_S="${ANTHROPIC_MIN_INTERVAL_S:-0.2}" ;;   # throttle Haiku to stay under the 429 limit (anthropic_chat also honors Retry-After)
  # power_seeking: machiavelli legs are rule-scored (logprob); only instrumental_eval is judged, on the
  # LOCAL Qwen2.5-7B 3-way judge (CONV/NOCONV/REFUSAL) — pin it both sides.
  power_seeking) export JUDGE_BACKEND="${JUDGE_BACKEND:-local}"; export JUDGE_MODEL_LOCAL="${JUDGE_MODEL_LOCAL:-Qwen/Qwen2.5-7B-Instruct}" ;;
  # concealing_uncertainty: llm_uncertainty_bench + verbalized_ece are rule/logprob-scored (no judge); only
  # abstentionbench is judged, on the LOCAL Qwen2.5-7B BLIND abstain-detector — pin it to match the baseline.
  concealing_uncertainty) export JUDGE_BACKEND="${JUDGE_BACKEND:-local}"; export JUDGE_MODEL_LOCAL="${JUDGE_MODEL_LOCAL:-Qwen/Qwen2.5-7B-Instruct}" ;;
  # reward_hacking: the MCQ legs (loophole_*/revealing_score) are RULE-scored (logprob, no judge); only the
  # FREE-FORM leg (reward_hacking_freeform[_heldout]) is judged. Its plugin calls the ANTHROPIC claude-haiku-4-5
  # 3-way judge (HACK/HONOR/EXCLUDE) directly; pin backend + concurrency/throttle (mirror privacy + eval_job.sh)
  # so the Haiku calls are fast and rate-limit-safe. The Anthropic key is loaded by the shared runtime helper.
  reward_hacking) export JUDGE_BACKEND="${JUDGE_BACKEND:-anthropic}"; export JUDGE_MODEL="${JUDGE_MODEL:-claude-haiku-4-5}"; export JUDGE_CONCURRENCY="${JUDGE_CONCURRENCY:-100}"; export ANTHROPIC_MIN_INTERVAL_S="${ANTHROPIC_MIN_INTERVAL_S:-0}" ;;   # conc 100 / no throttle (2026-06-27; mirror eval_job.sh): the 3 free-form legs judge in 1-2 waves; high-prio key + Retry-After backoff on any 429.
  # Paper-aligned choice for this run: Claude Opus 4.8 through FAIR Model API.
  # Baseline and trained evaluation must use these same values.
  honesty) export JUDGE_BACKEND="${JUDGE_BACKEND:-model_api}"; export JUDGE_MODEL="${JUDGE_MODEL:-claude-4-8-opus}"; export MASK_JUDGE_MODEL="${MASK_JUDGE_MODEL:-claude-4-8-opus}" ;;
  honesty_sycophancy|honesty_sycophancy_concealing_uncertainty) export JUDGE_BACKEND="${JUDGE_BACKEND:-model_api}"; export JUDGE_MODEL="${JUDGE_MODEL:-gpt-5-6-luna}"; export MASK_JUDGE_MODEL="${MASK_JUDGE_MODEL:-gpt-5-6-luna}" ;;
  # bias: the two MULTI-TURN FREE-FORM legs (bias_mt_decision/bias_mt_occupation) are judged for engagement ×
  # A-vs-B invariance; bbq + bbq_heldout are RULE-scored (logprob, no judge). ANTHROPIC claude-haiku-4-5 — a
  # strong CoT judge for the free-form decision/recommendation comparisons. Concurrency 100 (Haiku handles it;
  # anthropic_chat honors Retry-After on any 429 bursts). The shared runtime helper loads the key.
  bias) export JUDGE_BACKEND="${JUDGE_BACKEND:-anthropic}"; export JUDGE_MODEL="${JUDGE_MODEL:-claude-haiku-4-5}"; export JUDGE_CONCURRENCY="${JUDGE_CONCURRENCY:-100}" ;;
  sycophancy|refusal) export JUDGE_BACKEND="${JUDGE_BACKEND:-openai}" ;;
esac
# Run SEVERAL of these concurrently to parallelize scoring (one worker is a
# bottleneck for many chains — ~10-14 min/submission). As the eval user:
#   for i in $(seq 3); do sbatch scripts/eval_worker.sh sycophancy 8000; done
# The atomic mkdir-claim below lets N workers drain the same queue without
# double-scoring: exactly one worker claims each submission.
WORKER_ID="${SLURM_JOB_ID:-$$}"
# The holdout path is explicit. Never reconstruct it from TEAM_ID: current team
# ids include an agent-model tag, and inference previously selected the wrong
# per-model suite. Same-user functional smoke keeps eval-private outputs in a
# clearly marked team subdirectory; a future separate evaluator can override
# AAR_EVAL_RUNTIME_ROOT with its private filesystem.
[ -n "${HOLDOUT_DIR}" ] || { echo "[worker] ERROR: HOLDOUT_DIR must be explicit" >&2; exit 2; }
[ -r "${HOLDOUT_DIR}/${SUITE}/${SUITE}.yaml" ] || {
  echo "[worker] ERROR: suite is not readable: ${HOLDOUT_DIR}/${SUITE}/${SUITE}.yaml" >&2
  exit 2
}
EVAL_TEAM_DIR="${AAR_EVAL_RUNTIME_ROOT:-${TEAM_DIR:-${AAR_RUNTIME_ROOT}}/_eval_private}"
mkdir -p "${EVAL_TEAM_DIR}/heldout_scores" "${EVAL_TEAM_DIR}/_evalwork"
mkdir -p "${EVAL_TEAM_DIR}/timings"
chmod 700 "${EVAL_TEAM_DIR}" "${EVAL_TEAM_DIR}/heldout_scores" \
  "${EVAL_TEAM_DIR}/_evalwork" "${EVAL_TEAM_DIR}/timings" 2>/dev/null || true
export HELDOUT_SCORES_DIR="${HELDOUT_SCORES_DIR:-${EVAL_TEAM_DIR}/heldout_scores}"
export HARNESS_RUNS_DIR="${EVAL_TEAM_DIR}"

# Recovery runs may keep durable state on /storage/home while placing each
# 62.5-GB merged serving checkpoint on the evaluator node. The root is derived
# here after Slurm assigns the job id, never supplied as an arbitrary deletion
# target. A marker and free-space gate make later cleanup fail closed.
if [ "${EVAL_INFERENCE_BACKEND:-transformers}" = vllm ] && \
   [ "${AAR_VLLM_EPHEMERAL_MERGED:-0}" = 1 ]; then
  _aar_local_parent="${SLURM_TMPDIR:-/tmp}"
  [ -d "${_aar_local_parent}" ] || {
    echo "[worker] ERROR: node-local merge parent is missing: ${_aar_local_parent}" >&2
    exit 2
  }
  _aar_local_parent="$(realpath -e -- "${_aar_local_parent}")"
  export AAR_VLLM_MERGED_ROOT="${_aar_local_parent}/aar-vllm-merged-${WORKER_ID}"
  mkdir -m 700 -- "${AAR_VLLM_MERGED_ROOT}"
  printf '%s\n' "${WORKER_ID}" > "${AAR_VLLM_MERGED_ROOT}/.aar-ephemeral-merged-root"
  chmod 600 "${AAR_VLLM_MERGED_ROOT}/.aar-ephemeral-merged-root"
  _aar_free_bytes="$(df -B1 --output=avail -- "${AAR_VLLM_MERGED_ROOT}" | awk 'NR == 2 {gsub(/[[:space:]]/, ""); print}')"
  _aar_min_free_bytes="${AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES:-75161927680}"
  case "${_aar_free_bytes}:${_aar_min_free_bytes}" in
    *[!0-9:]*|:*|*:) echo "[worker] ERROR: invalid node-local free-space values" >&2; exit 2;;
  esac
  [ "${_aar_free_bytes}" -ge "${_aar_min_free_bytes}" ] || {
    echo "[worker] ERROR: node-local merge root has ${_aar_free_bytes} bytes free; need ${_aar_min_free_bytes}" >&2
    exit 2
  }
  mkdir -p -- "${EVAL_TEAM_DIR}/merge_manifests"
  chmod 700 "${EVAL_TEAM_DIR}/merge_manifests"
  echo "[worker ${WORKER_ID}] ephemeral_merged_root=${AAR_VLLM_MERGED_ROOT} free_bytes=${_aar_free_bytes}"
  unset _aar_local_parent _aar_free_bytes _aar_min_free_bytes
fi
exec >> "${EVAL_TEAM_DIR}/eval_worker_${WORKER_ID}.out" 2>&1
echo "[worker ${WORKER_ID}] eval runtime: ${EVAL_TEAM_DIR}"
echo "[worker ${WORKER_ID}] explicit HOLDOUT_DIR=${HOLDOUT_DIR}"
CLAIMS="${SCORES_DIR}/.claims"
mkdir -p "${CLAIMS}" 2>/dev/null || true

cd "${REPO}" || exit 2
if [ "${EVAL_INFERENCE_BACKEND:-transformers}" = vllm ]; then
  [ "${AAR_VLLM_CONTAINER_IMAGE:-}" = docker.io/vllm/vllm-openai:v0.25.1 ] || {
    echo "[worker] ERROR: Gemma vLLM evaluation requires the validated v0.25.1 image" >&2
    exit 2
  }
  [ -x "${REPO}/scripts/run_vllm_container.sh" ] || {
    echo "[worker] ERROR: vLLM container runner is not executable" >&2
    exit 2
  }
  [ -x "${AAR_VLLM_MERGE_PY:-}" ] || {
    echo "[worker] ERROR: AAR_VLLM_MERGE_PY is not executable" >&2
    exit 2
  }
  echo "[worker ${WORKER_ID}] backend=vllm image=${AAR_VLLM_CONTAINER_IMAGE} lora_strategy=merged_checkpoint"
fi
echo "[worker ${WORKER_ID}] draining submissions for suite=${SUITE} (idle-exit ${IDLE_EXIT}s)"
publish_terminal_failure() {
  local failure_run_id="$1"
  local failure_reason="$2"
  local failure_code="${3:-evaluator_rejected}"
  "${PY}" -m aar.eval_pod.failure \
    --scores-dir "${SCORES_DIR}" \
    --run-id "${failure_run_id}" \
    --reason "${failure_reason}" \
    --stage evaluation \
    --error-code "${failure_code}" \
    --eval-job-id "${WORKER_ID}"
  rmdir "${CLAIMS}/${failure_run_id}" 2>/dev/null || true
}
cleanup_ephemeral_merge() {
  local cleanup_run_id="$1"
  local cleanup_root="${AAR_VLLM_MERGED_ROOT:-}"
  local cleanup_parent cleanup_expected cleanup_target cleanup_staging
  [ "${AAR_VLLM_EPHEMERAL_MERGED:-0}" = 1 ] || return 0
  case "${cleanup_run_id}" in ''|*/*|.|..) echo "[worker] REFUSING unsafe cleanup run id" >&2; return 1;; esac
  cleanup_parent="$(realpath -e -- "${SLURM_TMPDIR:-/tmp}")" || return 1
  cleanup_expected="${cleanup_parent}/aar-vllm-merged-${WORKER_ID}"
  [ "${cleanup_root}" = "${cleanup_expected}" ] || {
    echo "[worker] REFUSING cleanup outside derived node-local root: ${cleanup_root}" >&2
    return 1
  }
  if [ -L "${cleanup_root}" ] || \
     [ "$(cat -- "${cleanup_root}/.aar-ephemeral-merged-root" 2>/dev/null)" != "${WORKER_ID}" ]; then
    echo "[worker] REFUSING cleanup without the evaluator root marker" >&2
    return 1
  fi
  cleanup_target="${cleanup_root}/${cleanup_run_id}"
  cleanup_staging="${cleanup_target}.incomplete"
  case "${cleanup_target}" in "${cleanup_root}"/*) ;; *) return 1;; esac
  rm -rf --one-file-system -- "${cleanup_target}" "${cleanup_staging}"
  echo "[worker ${WORKER_ID}] removed ephemeral merged checkpoint for ${cleanup_run_id}"
}
last_work=$(date +%s)
while true; do
  did=0
  for d in "${SUBMISSIONS_DIR}"/*/; do
    [ -d "${d}" ] || continue
    rid=$(basename "$d")
    [ -f "${d}.submitted" ] || continue
    [ -f "${SCORES_DIR}/${rid}.json" ] && continue          # already scored
    if [ -f "${SCORES_DIR}/${rid}.failed.json" ] && \
       [ "${AAR_EVAL_RETRY_FAILED:-0}" != 1 ]; then
      continue                                                # terminal unless explicitly retried
    fi
    # Atomic claim: exactly one worker's mkdir succeeds for a given rid, so
    # parallel workers never double-score. (Claims live in the eval-writable
    # SCORES_DIR so every worker — same OS user — can create them.)
    mkdir "${CLAIMS}/${rid}" 2>/dev/null || continue        # claimed by another worker
    export AAR_CURRENT_RUN_ID="${rid}"
    export AAR_PHASE_TIMINGS_PATH="${EVAL_TEAM_DIR}/timings/${rid}.eval.jsonl"
    _submitted_at="$(stat -c %Y "${d}.submitted")"
    _claimed_at="$(date +%s)"
    "${PY}" -m aar.phase_timing record \
      --path "${AAR_PHASE_TIMINGS_PATH}" \
      --phase eval.queue_wait \
      --duration-seconds "$((_claimed_at - _submitted_at))"
    echo "[worker ${WORKER_ID}] scoring ${rid}"
    eval_cmd=("${PY}" -u -m aar.eval_pod.entrypoint --run-id "${rid}" --suite "${SUITE}")
    if [ "${EVAL_INFERENCE_BACKEND:-transformers}" = vllm ]; then
      : "${AAR_VLLM_MERGE_PY:?vLLM Gemma evaluation requires AAR_VLLM_MERGE_PY}"
      : "${AAR_VLLM_MERGED_ROOT:?vLLM Gemma evaluation requires AAR_VLLM_MERGED_ROOT}"
      : "${TARGET_MODEL_PATH:?vLLM Gemma evaluation requires TARGET_MODEL_PATH}"
      submitted_model="${d%/}/model"
      merged_model="${AAR_VLLM_MERGED_ROOT}/${rid}"
      mkdir -p "${AAR_VLLM_MERGED_ROOT}"
      echo "[worker ${WORKER_ID}] merging adapter ${submitted_model} -> ${merged_model}"
      if ! "${PY}" -m aar.phase_timing run \
          --path "${AAR_PHASE_TIMINGS_PATH}" \
          --phase eval.adapter_merge -- \
          "${AAR_VLLM_MERGE_PY}" "${REPO}/scripts/merge_peft_adapter.py" \
          --base-checkpoint "${TARGET_MODEL_PATH}" \
          --adapter "${submitted_model}" \
          --output "${merged_model}" \
          --source-commit "$(git -C "${REPO}" rev-parse HEAD)"; then
        echo "[worker ${WORKER_ID}] FAILED merge ${rid}"
        publish_terminal_failure "${rid}" \
          "adapter merge failed; candidate checkpoint is invalid; inspect the evaluator log" \
          "adapter_merge_failed"
        cleanup_ephemeral_merge "${rid}" || exit 2
        did=1; last_work=$(date +%s)
        continue
      fi
      [ -s "${merged_model}/.merge-complete.json" ] || {
        echo "[worker ${WORKER_ID}] FAILED missing merge manifest ${rid}"
        publish_terminal_failure "${rid}" \
          "adapter merge did not produce a complete checkpoint; inspect the evaluator log" \
          "merge_manifest_missing"
        cleanup_ephemeral_merge "${rid}" || exit 2
        did=1; last_work=$(date +%s)
        continue
      }
      if [ "${AAR_VLLM_EPHEMERAL_MERGED:-0}" = 1 ]; then
        manifest_copy="${EVAL_TEAM_DIR}/merge_manifests/${rid}.json"
        if [ -e "${manifest_copy}" ]; then
          manifest_copy="${EVAL_TEAM_DIR}/merge_manifests/${rid}.retry-${WORKER_ID}.json"
        fi
        manifest_tmp="${manifest_copy}.tmp.${WORKER_ID}"
        cp -- "${merged_model}/.merge-complete.json" "${manifest_tmp}"
        chmod 600 "${manifest_tmp}"
        mv -- "${manifest_tmp}" "${manifest_copy}"
        echo "[worker ${WORKER_ID}] retained merge manifest ${manifest_copy}"
      fi
      export EVAL_MODEL_PATH_OVERRIDE="${merged_model}"
      export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint
      export EVAL_VLLM_REQUIRE_MERGED=1
      export EVAL_FAIL_ON_SCORING_ERROR=1
      export MODEL_CFG_PATH="${merged_model}"
      export AAR_VLLM_CONTAINER_RW_MOUNT="${AAR_VLLM_CONTAINER_RW_MOUNT:-${AAR_RUNTIME_ROOT}}"
      eval_cmd=("${REPO}/scripts/run_vllm_container.sh" python3 -u -m aar.eval_pod.entrypoint --run-id "${rid}" --suite "${SUITE}")
    fi
    if PYTHONUNBUFFERED=1 "${eval_cmd[@]}"; then
      echo "[worker ${WORKER_ID}] done ${rid}"
    else
      echo "[worker ${WORKER_ID}] FAILED ${rid}"
      # A scoring failure is terminal for this candidate.  Retrying the same
      # immutable checkpoint and suite forever only burns GPUs and leaves the
      # research chain polling indefinitely.  Publish a held-out-safe failure
      # handoff (no item data or partial scores) so the chain can record the
      # rejected iteration and pivot to a new method.
      publish_terminal_failure "${rid}" \
        "evaluator rejected the candidate; inspect the evaluator job log" \
        "evaluator_runtime_failed"
    fi
    if [ "${AAR_VLLM_EPHEMERAL_MERGED:-0}" = 1 ]; then
      if [ ! -f "${SCORES_DIR}/${rid}.json" ] && \
         [ ! -f "${SCORES_DIR}/${rid}.failed.json" ]; then
        echo "[worker] ERROR: refusing cleanup before terminal handoff for ${rid}" >&2
        exit 2
      fi
      cleanup_ephemeral_merge "${rid}" || exit 2
    fi
    if [ "${AAR_VLLM_EPHEMERAL_MERGED:-0}" = 1 ]; then
      if [ ! -f "${SCORES_DIR}/${rid}.json" ] && \
         [ ! -f "${SCORES_DIR}/${rid}.failed.json" ]; then
        echo "[worker] ERROR: refusing cleanup before terminal handoff for ${rid}" >&2
        exit 2
      fi
      cleanup_ephemeral_merge "${rid}" || exit 2
    fi
    did=1; last_work=$(date +%s)
  done
  if [ "$did" = 0 ]; then
    now=$(date +%s)
    [ $(( now - last_work )) -ge "${IDLE_EXIT}" ] && { echo "[worker ${WORKER_ID}] idle ${IDLE_EXIT}s, exiting"; break; }
    sleep 20
  fi
done
echo "=== DONE ==="
