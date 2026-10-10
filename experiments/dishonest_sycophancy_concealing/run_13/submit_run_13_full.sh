#!/bin/bash
# Launch five independent Claude Opus 4.8 AAR chains with trusted targets.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/storage/home/${USER:?}/autodata-pipelines-run13-main}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
SECRET_ENV="$(realpath -e -- "${AAR_RUN13_SECRET_ENV:-${REPO}/.env}")"
RECOVERY_BUNDLE="$(realpath -e -- "${AAR_RUN13_RECOVERY_BUNDLE:-/storage/home/${USER}/aar-recovery/run7_20261007T004406Z-1b3303d02821/baseline_salvage}")"
REUSED_BASELINE="${RECOVERY_BUNDLE}/gemma4_31b_multidimensional_baseline.json"
RECOVERED_SOURCES="${RECOVERY_BUNDLE}/source_artifacts"
CANARY_ROOT="$(realpath -e -- "${AAR_RUN13_CANARY_ROOT:-/storage/home/${USER}/aar-runs/run13-adapter-target/20261009T104306Z-6cf11ae65d2b}")"
SV="/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2"
BASE_CHECKPOINT=/checkpoint/ram/shared/models/google/gemma-4-31B-it
REQUIRED_AUTODATA_SHA=823c5948854df14664f3168bc5e6c49a2cecb975
GENERATOR_DEPLOYMENT=aar_8-kimi26
export AAR_AUTODATA=1
export AAR_AUTODATA_PROFILE=target-aware-local-v1
export AAR_AUTODATA_GENERATOR_DEPLOYMENT="${GENERATOR_DEPLOYMENT}"
export AAR_KIMI_PROXY_INFO="${AAR_KIMI_PROXY_INFO:-/checkpoint/ram/shared/vllm_deployments_v2/${GENERATOR_DEPLOYMENT}/proxy_info.json}"

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "Run 13 requires branch autodata" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
if ! git -C "${AUTODATA_CHECKOUT}" diff --quiet || \
    ! git -C "${AUTODATA_CHECKOUT}" diff --cached --quiet; then
  echo "tracked AutoData worktree is dirty" >&2
  exit 2
fi
if [ ! -x "${REPO}/.venv/bin/python" ] || [ ! -x "${BROKER_PYTHON}" ]; then
  echo "missing runtime" >&2
  exit 2
fi
[ "$(git -C "${AUTODATA_CHECKOUT}" rev-parse HEAD)" = "${REQUIRED_AUTODATA_SHA}" ] || { echo "wrong AutoData revision" >&2; exit 2; }
[ "$(git -C "${AUTODATA_CHECKOUT}" branch --show-current)" = main ] || { echo "AutoData checkout must be on branch main" >&2; exit 2; }
for proof in preflight.json canary-report.json target-binding.json; do
  [ -s "${CANARY_ROOT}/${proof}" ] || { echo "missing Run 13 canary proof ${proof}" >&2; exit 2; }
done
jq -e '
  .success == true
  and .broker_status == "SUCCEEDED"
  and .task_result_outcome == "succeeded"
  and .task_result_schema_valid == true
  and .provider_call_count == 3
  and ([.provider_usage[].role] == ["generator", "target", "judge"])
' "${CANARY_ROOT}/canary-report.json" >/dev/null || {
  echo "Run 13 canary did not prove successful three-provider routing" >&2
  exit 2
}

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/autodata_runtime_profile.sh"
aar_set_autodata_runtime_profile
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
for name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!name:-}" ] || { echo "missing ${name}" >&2; exit 2; }
done
CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH:-/usr/local/bin/claude}"
[ -x "${CLAUDE_CLI_PATH}" ] || { echo "missing Claude CLI" >&2; exit 2; }
"${CLAUDE_CLI_PATH}" --help 2>&1 | grep -q -- --secure-internet-mode || {
  echo "Claude CLI lacks secure-internet mode" >&2
  exit 2
}

source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" --output-root "${source_root}" --verify-only >/dev/null
export LLM_UNCERTAINTY_SRC="${source_root}/data" LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
"${REPO}/.venv/bin/python" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" >/dev/null

commit="$(git -C "${REPO}" rev-parse HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt="/storage/home/${USER}/aar-runs/run13-full/${attempt_id}"
checkpoint_root="/checkpoint/ram/aar/${USER}/run13-full/${attempt_id}"
mkdir -p "${attempt}/"{metadata,logs,secrets,chains,runtime}
mkdir -p "${checkpoint_root}/chains"
chmod 700 "${attempt}" "${attempt}/"{metadata,logs,secrets,chains}
chmod 700 "${checkpoint_root}" "${checkpoint_root}/chains"
"${REPO}/experiments/dishonest_sycophancy_concealing/run_10/snapshot_vllm_runtime.sh" "${attempt}" \
  > "${attempt}/metadata/vllm_runtime_path.txt"

model_env="${attempt}/secrets/model-api.env"
printf 'MODEL_API_KEY=%s\n' "${MODEL_API_KEY}" > "${model_env}"
approval_private="${attempt}/secrets/autodata-approval-private.pem"
approval_public="${attempt}/metadata/autodata-approval-public.pem"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "${approval_private}" >/dev/null 2>&1
openssl pkey -in "${approval_private}" -pubout -out "${approval_public}" >/dev/null 2>&1
chmod 600 "${model_env}" "${approval_private}" "${approval_public}"
approval_digest="sha256:$(sha256sum "${approval_public}" | awk '{print $1}')"

export PATH=/storage/home/${USER}/tools/node-v22.22.0-linux-arm64/bin:"${PATH}"
export KIMI_CLI_PATH=/storage/home/${USER}/tools/kimi-code-2.1.1/node_modules/.bin/kimi
export AAR_AGENT_BACKEND=kimi AAR_WEB_MODE=native_web
export AAR_KIMI_SERVE_DEPLOYMENT="${GENERATOR_DEPLOYMENT}" AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT="${SV}" KIMI_MODEL_CAPABILITIES=tool_use
unset KIMI_AGENT_MODEL
"${REPO}/.venv/bin/python" "${REPO}/experiments/dishonest_sycophancy_concealing/run_10/verify_kimi_endpoint.py" \
  --workspace "${REPO}" --output "${attempt}/metadata/kimi_mcp_preflight.json"
export AAR_AGENT_BACKEND=claude AAR_AGENT_MODEL=claude-opus-4-8
export AAR_WEB_MODE=meta_secure CLAUDE_CLI_PATH

suffix="$(printf '%s' "${attempt_id}" | sha256sum | cut -c1-8)"
deployments=()
for seed in alpha beta gamma delta epsilon; do
  chain_root="${attempt}/chains/${seed}"
  mkdir -p "${chain_root}/"{bindings,deployments,logs,metadata,secrets}
  mkdir -p "${checkpoint_root}/chains/${seed}/merged_candidates"
  chmod 700 "${chain_root}" "${chain_root}/secrets"
  "${BROKER_PYTHON}" -c 'import secrets; print(secrets.token_hex(32))' > "${chain_root}/secrets/capability"
  printf '{"schema":"aar.autodata.proposal-bindings/v1","proposals":{},"workspaces":{}}\n' \
    > "${chain_root}/secrets/proposal-bindings.json"
  chmod 600 "${chain_root}/secrets/"*
  deployment="winnieyangwn-r13-${seed}-i1-${suffix}"
  deployments+=("${deployment}")
  env -u SSL_CERT_FILE -u NODE_EXTRA_CA_CERTS \
    -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u NO_PROXY -u no_proxy \
    "${SV}/serve.sh" deploy "${deployment}" --model gemma-4-31B-it \
      --checkpoint "${BASE_CHECKPOINT}" --endpoints 1 --cluster fair-cw-use2-1 \
      --image docker.io/vllm/vllm-openai:v0.25.1 \
      --partition g3 --account ram --qos g3_ram_high \
      --gateway-register --lifetime 7d --no-watch
  "${REPO}/.venv/bin/python" -m aar.autodata_campaign_policy create-base-target \
    --base-checkpoint "${BASE_CHECKPOINT}" \
    --target-url http://fair-cw-use2-1-ingress-slurm-ingress/v1 \
    --target-host-header ram-inference-gateway.ingress. --target-model gemma-4-31B-it \
    --target-deployment-id "${deployment}" --output "${chain_root}/bindings/iteration-1.json"
  cp -- "${chain_root}/bindings/iteration-1.json" "${chain_root}/metadata/incumbent.json"
  "${REPO}/.venv/bin/python" -m aar.autodata_campaign_policy create-policy \
    --campaign-id "run13-${seed}" --target-manifest "${chain_root}/bindings/iteration-1.json" \
    --generator-deployment-id "${GENERATOR_DEPLOYMENT}" --max-cost-usd 299 \
    --runtime-profile "${AAR_AUTODATA_PROFILE}" \
    --output "${chain_root}/metadata/campaign-policy.json"
  "${REPO}/.venv/bin/python" -m aar.infrastructure.autodata_contract \
    --create --campaign-policy "${chain_root}/metadata/campaign-policy.json" \
    --required-rows 1000 --minimum-successful-task-fraction 0.95 \
    --judge-rubric-version run9-axis-conditioned-v2 \
    --output "${chain_root}/metadata/autodata-training-data-contract.json" >/dev/null
done

for deployment in "${deployments[@]}"; do
  ready=0
  for _ in $(seq 1 160); do
    [ -d "/checkpoint/ram/shared/vllm_deployments_v2/${deployment}" ] || {
      echo "deployment was archived before serving: ${deployment}" >&2
      break
    }
    phase="$("${SV}/serve.sh" status "${deployment}" --json 2>/dev/null | jq -r '.phase // empty' || true)"
    if [ "${phase}" = serving ]; then ready=1; break; fi
    case "${phase}" in failed|stopped|expired) break;; esac
    sleep 15
  done
  [ "${ready}" = 1 ] || { echo "base deployment failed: ${deployment}" >&2; exit 1; }
  "${SV}/serve.sh" test "${deployment}" >/dev/null
done
printf '%s\n' "${deployments[@]}" > "${attempt}/metadata/base-deployments.txt"

export AAR_RUN_ATTEMPT_DIR="${attempt}" AAR_RUNTIME_ROOT="${attempt}"
export AAR_RUN13_CHECKPOINT_ROOT="${checkpoint_root}"
export AAR_BASELINE_GIT_COMMIT="${commit}" AAR_REUSED_BASELINE="${REUSED_BASELINE}"
export AAR_RECOVERED_BASELINE_SOURCES="${RECOVERED_SOURCES}"
export AAR_AUTODATA_CHECKOUT="${AUTODATA_CHECKOUT}"
export AAR_AUTODATA_PLUGIN_ROOT="${AUTODATA_CHECKOUT}/plugin/autodata"
export AAR_AUTODATA_SHA="${REQUIRED_AUTODATA_SHA}"
export AAR_AUTODATA_BROKER_PYTHON="${BROKER_PYTHON}"
export AAR_AUTODATA_MODEL_ENV_FILE="${model_env}"
export AAR_AUTODATA_APPROVAL_PRIVATE_KEY="${approval_private}"
export AAR_AUTODATA_APPROVAL_PUBLIC_KEY="${approval_public}"
export AAR_AUTODATA_APPROVAL_PUBLIC_KEY_SHA256="${approval_digest}"
export AAR_AUTODATA_APPROVAL_ACTOR=aar-integrity-monitor
export AAR_AUTODATA_APPROVAL_POLICY_VERSION=aar-autodata/run13-full-v1
export AAR_AUTODATA_RESOURCES_READY=1
export AAR_MONITOR_MODEL_API_KEY="${MODEL_API_KEY}"

job="$(sbatch --parsable --output="${attempt}/logs/pipeline-%j.out" --export=ALL \
  "${SCRIPT_DIR}/run_13_full_pipeline.sbatch")"
printf 'launch_job_id=%s\nattempt_dir=%s\ncheckpoint_root=%s\ngit_commit=%s\nresearch_backend=claude\nresearch_model=claude-opus-4-8\nkimi_generator_deployment=%s\nautodata_profile=%s\nautodata_concurrency=%s\nautodata_model_request_attempts=%s\nchains=5\ntarget_pairs_per_chain=5\nbase_deployments=%s\n' \
  "${job}" "${attempt}" "${checkpoint_root}" "${commit}" "${GENERATOR_DEPLOYMENT}" \
  "${AAR_AUTODATA_PROFILE}" "${AAR_AUTODATA_CONCURRENCY}" \
  "${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS}" "${deployments[*]}" \
  | tee "${attempt}/metadata/submission.txt"
unset MODEL_API_KEY HF_TOKEN ANTHROPIC_API_KEY
