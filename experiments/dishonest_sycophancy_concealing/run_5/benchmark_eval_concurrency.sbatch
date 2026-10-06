#!/bin/bash
# Benchmark one, two, and four in-process vLLM evaluator engines on one GB300 node.
# Submit only through submit_eval_concurrency_benchmark.sh.
#SBATCH --job-name=aar-run5-eval-concurrency
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=32
#SBATCH --gpus=4
#SBATCH --mem=256G
#SBATCH --time=04:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_eval_concurrency_benchmark.sh}"
OUT="${AAR_CONCURRENCY_ATTEMPT:?missing benchmark attempt root}"
SOURCE_SUITE_DIR="${AAR_CONCURRENCY_SOURCE_SUITE_DIR:?missing source suite directory}"
MODEL_PATH="${AAR_CONCURRENCY_MODEL_PATH:?missing target model path}"
EXPECTED_COMMIT="${AAR_CONCURRENCY_GIT_COMMIT:?missing source commit}"
export HF_HOME="${OUT}/cache/huggingface"

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"

[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "concurrency benchmark requires branch multi_vllm" >&2
  exit 2
}
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || {
  echo "concurrency benchmark source commit drifted" >&2
  exit 2
}
for required in "${MODEL_PATH}" "${SOURCE_SUITE_DIR}" "${HARNESS_ENV}"; do
  [ -e "${required}" ] || { echo "required path missing: ${required}" >&2; exit 2; }
done
for secret_name in HF_TOKEN MODEL_API_KEY; do
  [ -n "${!secret_name:-}" ] || { echo "required runtime credential is empty: ${secret_name}" >&2; exit 2; }
done

mkdir -p "${OUT}/suite" "${OUT}/results" "${OUT}/cache/huggingface"
chmod 700 "${OUT}" "${OUT}/suite" "${OUT}/results" "${OUT}/cache"
cp -a -- "${SOURCE_SUITE_DIR}/." "${OUT}/suite/"
source_suite="${OUT}/suite/honesty_sycophancy_concealing_uncertainty.yaml"
test_suite="${OUT}/suite/run5_eval_throughput.yaml"
"${HARNESS_PY}" "${REPO}/scripts/select_eval_concurrency_suite.py" \
  "${source_suite}" "${test_suite}" \
  --subset-size-cap "${AAR_CONCURRENCY_SUBSET_SIZE:-64}" \
  --benchmark llm_uncertainty_bench \
  --benchmark verbalized_ece \
  --benchmark mmlu \
  --benchmark gsm8k \
  --benchmark ifeval

export PYTHONPATH="${REPO}"
export AAR_REPO="${REPO}"
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH=/checkpoint/ram/shared/vllm_deployments_v2/aar-gemma-4-31b-it/src/serve_api_v2/worker/worker_vllm.sh
export AAR_VLLM_CONTAINER_RW_MOUNT="${OUT}"
export MODEL_CFG_PATH="${MODEL_PATH}"
export TARGET_MODEL_PATH="${MODEL_PATH}"
export EVAL_INFERENCE_BACKEND=vllm
export EVAL_VLLM_LORA_STRATEGY=base
export EVAL_VLLM_REQUIRE_MERGED=0
export EVAL_VLLM_MAX_MODEL_LEN=65536
export EVAL_VLLM_MAX_NUM_SEQS=256
export EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.80
export EVAL_VLLM_ENABLE_PREFIX_CACHING=1
export EVAL_VLLM_ENFORCE_EAGER=0
export EVAL_FAIL_ON_ALLOCATOR_WARNING=1
export EVAL_MAX_TRUNCATION_RATE=
export EVAL_TRUNCATION_MIN_COMPLETIONS=20
export BENCHMARK_DOCS_DIR="${REPO}/benchmark_docs"
export AAR_BENCHMARK_DOCS="${REPO}/benchmark_docs"

echo "[concurrency] commit=${EXPECTED_COMMIT} host=$(hostname)"
echo "[concurrency] host CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader
"${REPO}/scripts/run_vllm_container.sh" python3 -c \
  'import os, torch; print("[concurrency] container CUDA_VISIBLE_DEVICES=%r cuda_devices=%d" % (os.getenv("CUDA_VISIBLE_DEVICES"), torch.cuda.device_count()), flush=True)'

IFS=',' read -r -a concurrencies <<< "${AAR_EVAL_CONCURRENCIES:-1,2,4}"
for concurrency in "${concurrencies[@]}"; do
  case "${concurrency}" in 1|2|3|4) ;; *) echo "unsupported concurrency: ${concurrency}" >&2; exit 2;; esac
  result_dir="${OUT}/results/gpu${concurrency}"
  mkdir -p "${result_dir}/heldout"
  chmod 700 "${result_dir}" "${result_dir}/heldout"
  export EVAL_GPUS="${concurrency}"
  start_epoch="$(date +%s)"
  start_iso="$(date --iso-8601=seconds)"
  echo "[concurrency] start gpu=${concurrency} at ${start_iso}"
  set +e
  /usr/bin/time -f "wall_seconds=%e user_seconds=%U system_seconds=%S max_rss_kb=%M" \
    -o "${result_dir}/time.txt" \
    "${REPO}/scripts/run_vllm_container.sh" \
      python3 -u -m aar.eval_pod.run_eval \
      --suite "${test_suite}" \
      --model "${MODEL_PATH}" \
      --secret-dir "${OUT}/suite" \
      --out "${result_dir}/scores.json" \
      --heldout-dir "${result_dir}/heldout" \
      > "${result_dir}/eval.log" 2>&1
  status=$?
  set -e
  end_epoch="$(date +%s)"
  printf 'gpu_concurrency=%s\nstatus=%s\nstart=%s\nend=%s\nelapsed_seconds=%s\n' \
    "${concurrency}" "${status}" "${start_iso}" "$(date --iso-8601=seconds)" \
    "$((end_epoch - start_epoch))" | tee "${result_dir}/summary.txt"
  cat "${result_dir}/time.txt"
done

echo "[concurrency] complete results=${OUT}/results"
