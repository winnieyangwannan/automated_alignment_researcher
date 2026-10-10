#!/bin/bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
source "${SCRIPT_DIR}/autodata_version.env"
AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/storage/home/${USER:?}/autodata_pipelines}"
SECRET_ENV="${AAR_RUN9_SECRET_ENV:-/storage/home/${USER}/aar-worktrees/autodata/.env}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
KIMI_PROXY_INFO="${AAR_KIMI_PROXY_INFO:-/checkpoint/ram/shared/vllm_deployments_v2/winnieyangwn-kimi26/proxy_info.json}"
AAR_AUTODATA_BROKER_RUNNER="${AAR_AUTODATA_BROKER_RUNNER:-local-bwrap}"
AAR_AUTODATA_ENVIRONMENT="${AAR_AUTODATA_ENVIRONMENT:-oci-runner-firecracker-large}"
AUTODATA_TARGET_ENABLED="${AUTODATA_TARGET_ENABLED:-1}"
case "${AUTODATA_TARGET_ENABLED}" in
  1)
    target_enabled=1
    default_autodata_concurrency=32
    default_model_request_max_attempts=3
    ;;
  0)
    target_enabled=0
    default_autodata_concurrency=64
    default_model_request_max_attempts=1
    ;;
  *) echo "AUTODATA_TARGET_ENABLED must be 1 or 0" >&2; exit 2 ;;
esac
AAR_AUTODATA_CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:-${default_autodata_concurrency}}"
AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS="${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS:-${default_model_request_max_attempts}}"
VLLM_WORKER_SHA256="913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361"
REUSED_BASELINE="${1:-/checkpoint/ram/aar/${USER}/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/metadata/gemma4_31b_multidimensional_baseline.json}"

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "run 9 requires branch autodata" >&2; exit 2; }
git -C "${REPO}" diff --quiet && git -C "${REPO}" diff --cached --quiet || { echo "tracked worktree is dirty" >&2; exit 2; }
[ -x "${BROKER_PYTHON}" ] || { echo "missing broker Python" >&2; exit 2; }
[ "${AAR_AUTODATA_BROKER_RUNNER}" = local-bwrap ] || {
  echo "Run 9 full launches require AAR_AUTODATA_BROKER_RUNNER=local-bwrap; use the capacity-canary launcher for intentional Firecracker tests" >&2
  exit 2
}
case "${AAR_AUTODATA_ENVIRONMENT}" in
  oci-runner-firecracker-small|oci-runner-firecracker-medium|oci-runner-firecracker-large|oci-runner-firecracker-xlarge) ;;
  *) echo "unsupported AutoData Firecracker environment: ${AAR_AUTODATA_ENVIRONMENT}" >&2; exit 2 ;;
esac
case "${AAR_AUTODATA_CONCURRENCY}" in
  ''|*[!0-9]*|0) echo "AutoData concurrency must be a positive integer" >&2; exit 2 ;;
esac
[ "${AAR_AUTODATA_CONCURRENCY}" -le 64 ] || {
  echo "AutoData concurrency must not exceed the validated maximum of 64" >&2
  exit 2
}
case "${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS}" in
  1|2|3|4|5) ;;
  *) echo "AutoData model request attempts must be an integer from 1 through 5" >&2; exit 2 ;;
esac
AUTODATA_GENERATOR_URL="http://fair-cw-use2-1-ingress-slurm-ingress/v1"
AUTODATA_GENERATOR_HOST_HEADER="ram-inference-gateway.ingress."
target_setting_names=(
  AUTODATA_TARGET_URL
  AUTODATA_TARGET_MODEL
  AUTODATA_TARGET_DEPLOYMENT_ID
  AUTODATA_TARGET_CHECKPOINT_HASH
)
target_setting_count=0
for name in "${target_setting_names[@]}"; do
  [ -z "${!name:-}" ] || target_setting_count=$((target_setting_count + 1))
done
if [ "${target_enabled}" = 1 ]; then
  [ "${target_setting_count}" = 4 ] || {
    echo "target-aware AutoData is enabled by default and requires all four AUTODATA_TARGET_* settings; set AUTODATA_TARGET_ENABLED=0 only for an intentional legacy/smoke run" >&2
    exit 2
  }
  case "${AUTODATA_TARGET_CHECKPOINT_HASH}" in
    sha256:*) target_digest="${AUTODATA_TARGET_CHECKPOINT_HASH#sha256:}" ;;
    *) target_digest="${AUTODATA_TARGET_CHECKPOINT_HASH}" ;;
  esac
  [[ "${target_digest}" =~ ^[0-9a-fA-F]{64}$ ]] || {
    echo "AUTODATA_TARGET_CHECKPOINT_HASH must be a SHA-256 digest" >&2
    exit 2
  }
  AUTODATA_TARGET_CHECKPOINT_HASH="sha256:${target_digest,,}"
  export AUTODATA_TARGET_CHECKPOINT_HASH
elif [ "${target_setting_count}" != 0 ]; then
  echo "AUTODATA_TARGET_* settings must be absent when AUTODATA_TARGET_ENABLED=0" >&2
  exit 2
fi

for required in "${SECRET_ENV}" "${REUSED_BASELINE}" "${SCRIPT_DIR}/snapshot_vllm_runtime.sh" "${KIMI_PROXY_INFO}"; do
  [ -f "${required}" ] || { echo "missing required input: ${required}" >&2; exit 2; }
done
[ "$(stat -c %a "${SECRET_ENV}")" = 600 ] || { echo "secret env must be mode 600" >&2; exit 2; }
export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
source "${REPO}/scripts/aar_runtime_env.sh"
for name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!name:-}" ] || { echo "missing ${name}" >&2; exit 2; }
done

"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${REPO}/data/LLM-Uncertainty-Bench" --verify-only >/dev/null
"${REPO}/.venv/bin/python" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" >/dev/null

commit="$(git -C "${REPO}" rev-parse HEAD)"
autodata_sha="$(git -C "${AUTODATA_CHECKOUT}" rev-parse HEAD)"
[ "${autodata_sha}" = "${RUN9_REQUIRED_AUTODATA_SHA}" ] || {
  echo "Run 9 requires AutoData ${RUN9_REQUIRED_AUTODATA_SHA}; found ${autodata_sha}" >&2
  exit 2
}
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_dir="/storage/home/${USER}/aar-runs/run9-five-iteration/${attempt_id}"
mkdir -p "${attempt_dir}"/{metadata,logs,secrets}
chmod 700 "${attempt_dir}" "${attempt_dir}/secrets"
vllm_worker="$("${SCRIPT_DIR}/snapshot_vllm_runtime.sh" "${attempt_dir}")"
[ "$(sha256sum "${vllm_worker}" | awk '{print $1}')" = "${VLLM_WORKER_SHA256}" ] || {
  echo "snapshotted vLLM worker digest mismatch" >&2
  exit 2
}

model_env="${attempt_dir}/secrets/model-api.env"
printf 'MODEL_API_KEY=%s\n' "${MODEL_API_KEY}" > "${model_env}"
chmod 600 "${model_env}"
capability="$(${BROKER_PYTHON} -c 'import secrets; print(secrets.token_hex(32))')"
proposal_bindings="${attempt_dir}/secrets/autodata-proposal-bindings.json"
printf '{"schema":"aar.autodata.proposal-bindings/v1","proposals":{},"workspaces":{}}\n' > "${proposal_bindings}"
chmod 600 "${proposal_bindings}"
approval_private="${attempt_dir}/secrets/autodata-approval-private.pem"
approval_public="${attempt_dir}/metadata/autodata-approval-public.pem"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "${approval_private}" >/dev/null 2>&1
openssl pkey -in "${approval_private}" -pubout -out "${approval_public}" >/dev/null 2>&1
chmod 600 "${approval_private}" "${approval_public}"
approval_public_digest="sha256:$(sha256sum "${approval_public}" | awk '{print $1}')"
policy="${attempt_dir}/metadata/autodata-campaign-policy.json"
cat > "${policy}" <<EOF
{
  "schema": "autodata.broker-campaign-policy/v1",
  "campaign_id": "run9-five-iteration",
  "max_cost_usd": "299",
  "runner": "${AAR_AUTODATA_BROKER_RUNNER}",
  "environment": "${AAR_AUTODATA_ENVIRONMENT}",
  "image": "docker.io/library/python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f",
  "expected_image_id": "df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316",
  "max_cpus": 2,
  "max_memory_mb": 2048,
  "required_solve_env": {
    "AUTODATA_GENERATOR_URL": "${AUTODATA_GENERATOR_URL}",
    "AUTODATA_GENERATOR_HOST_HEADER": "${AUTODATA_GENERATOR_HOST_HEADER}",
    "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
    "AUTODATA_GENERATOR_DEPLOYMENT_ID": "winnieyangwn-kimi26",
    "AUTODATA_GENERATOR_MAX_INPUT": "4096",
    "AUTODATA_GENERATOR_MAX_OUTPUT": "768",
    "AUTODATA_GENERATOR_TIMEOUT": "90",
    "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
    "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
    "AUTODATA_JUDGE_URL": "https://api.meta.ai/v1/responses",
    "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
    "AUTODATA_JUDGE_MAX_INPUT": "4096",
    "AUTODATA_JUDGE_MAX_OUTPUT": "512",
    "AUTODATA_JUDGE_TIMEOUT": "90",
    "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
    "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "4",
    "AUTODATA_TARGET_ENABLED": "${target_enabled}",
    "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS}"
  }
}
EOF
if [ "${target_enabled}" = 1 ]; then
  "${REPO}/.venv/bin/python" - "${policy}" <<'PY'
import json
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
value = json.loads(path.read_text(encoding="utf-8"))
required = value["required_solve_env"]
for name in (
    "AUTODATA_TARGET_URL",
    "AUTODATA_TARGET_MODEL",
    "AUTODATA_TARGET_DEPLOYMENT_ID",
    "AUTODATA_TARGET_CHECKPOINT_HASH",
):
    required[name] = os.environ[name]
host_header = os.environ.get("AUTODATA_TARGET_HOST_HEADER", "").strip()
if host_header:
    required["AUTODATA_TARGET_HOST_HEADER"] = host_header
temporary = path.with_name(path.name + ".tmp")
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
temporary.replace(path)
PY
fi

training_data_contract="${attempt_dir}/metadata/autodata-training-data-contract.json"
"${REPO}/.venv/bin/python" - "${policy}" "${training_data_contract}" <<'PY'
import json
import pathlib
import sys

policy_path = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
environment = json.loads(policy_path.read_text(encoding="utf-8"))["required_solve_env"]
target_required = environment["AUTODATA_TARGET_ENABLED"] == "1"
target = {"required": target_required}
if target_required:
    target.update(
        model=environment["AUTODATA_TARGET_MODEL"],
        deployment_id=environment["AUTODATA_TARGET_DEPLOYMENT_ID"],
        checkpoint_hash=environment["AUTODATA_TARGET_CHECKPOINT_HASH"],
    )
contract = {
    "schema": "aar.autodata.training-data-contract/v1",
    "training_objective": "sft",
    "required_item_fields": ["prompt", "response"],
    "required_rows": 1000,
    "minimum_successful_task_fraction": 0.95,
    "judge_rubric_version": "run9-axis-conditioned-v2",
    "generator": {
        "model": environment["AUTODATA_GENERATOR_MODEL"],
        "deployment_id": environment["AUTODATA_GENERATOR_DEPLOYMENT_ID"],
    },
    "judge": {"model": environment["AUTODATA_JUDGE_MODEL"]},
    "target": target,
}
destination.write_text(
    json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
destination.chmod(0o600)
PY
"${REPO}/.venv/bin/python" -m aar.infrastructure.autodata_contract \
  --contract "${training_data_contract}" \
  --campaign-policy "${policy}" >/dev/null

export LLM_UNCERTAINTY_SRC="${REPO}/data/LLM-Uncertainty-Bench/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${REPO}/data/LLM-Uncertainty-Bench/.aar-source.json"
export AAR_RUNTIME_ROOT="${attempt_dir}"
export AAR_RUN_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}"
export AAR_REUSED_BASELINE="${REUSED_BASELINE}"
export AAR_AUTODATA_CHECKOUT="${AUTODATA_CHECKOUT}"
export AAR_AUTODATA_PLUGIN_ROOT="${AUTODATA_CHECKOUT}/plugin/autodata"
export AAR_AUTODATA_SHA="${autodata_sha}"
export AAR_AUTODATA_BROKER_PYTHON="${BROKER_PYTHON}"
export AAR_AUTODATA_MODEL_ENV_FILE="${model_env}"
export AAR_AUTODATA_CAMPAIGN_POLICY="${policy}"
export AAR_AUTODATA_TRAINING_DATA_CONTRACT="${training_data_contract}"
export AAR_AUTODATA_CAPABILITY="${capability}"
export AAR_AUTODATA_APPROVAL_PRIVATE_KEY="${approval_private}"
export AAR_AUTODATA_APPROVAL_PUBLIC_KEY="${approval_public}"
export AAR_AUTODATA_APPROVAL_PUBLIC_KEY_SHA256="${approval_public_digest}"
export AAR_AUTODATA_APPROVAL_ACTOR="aar-integrity-monitor"
export AAR_AUTODATA_APPROVAL_POLICY_VERSION="aar-autodata/run9-v1"
export AAR_AUTODATA_PROPOSAL_BINDINGS="${proposal_bindings}"
export AAR_AUTODATA_RESOURCES_READY=1
export AAR_AUTODATA_BROKER_RUNNER AAR_AUTODATA_ENVIRONMENT AAR_AUTODATA_CONCURRENCY
export AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS
export AAR_KIMI_PROXY_INFO="${KIMI_PROXY_INFO}"
export AAR_VLLM_WORKER_SH="${vllm_worker}"

job_id="$(sbatch --parsable \
  --output="${attempt_dir}/logs/pipeline-%j.out" \
  --export=ALL \
  "${SCRIPT_DIR}/run_9_pipeline.sbatch")"
printf 'launch_job_id=%s\nattempt_dir=%s\naar_git_commit=%s\nautodata_git_commit=%s\nbroker_runner=%s\nenvironment=%s\nconcurrency=%s\nmodel_request_max_attempts=%s\ntarget_aware=%s\nvllm_worker_sha256=%s\n' \
  "${job_id}" "${attempt_dir}" "${commit}" "${autodata_sha}" "${AAR_AUTODATA_BROKER_RUNNER}" "${AAR_AUTODATA_ENVIRONMENT}" "${AAR_AUTODATA_CONCURRENCY}" "${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS}" "${target_enabled}" "${VLLM_WORKER_SHA256}" \
  | tee "${attempt_dir}/metadata/submission.txt"
unset capability MODEL_API_KEY ANTHROPIC_API_KEY HF_TOKEN
