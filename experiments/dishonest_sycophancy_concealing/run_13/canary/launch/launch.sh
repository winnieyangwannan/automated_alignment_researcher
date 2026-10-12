#!/bin/bash
# Launch the source-pinned Run 13 one-chain AutoData training-smoke canary.
set -euo pipefail
umask 077

# Canonicalize the checkout before comparing resolved configuration paths.
# FAIR exposes the same worktree through /home and /storage/home; retaining a
# logical /home spelling here made in-repo files look external after realpath.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RUN13_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
REPO="$(cd -- "${RUN13_DIR}/../../../.." && pwd -P)"
[ "${AAR_EXPERIMENT_RUN_ID:-run13}" = run13 ] || {
  echo "Run 13 launcher rejects an overridden experiment ID" >&2; exit 2;
}
EXPERIMENT_RUN_ID=run13
AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/checkpoint/ram/${USER:?}/source-worktrees/autodata-51c18fd}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
SECRET_ENV="$(realpath -e -- "${AAR_RUN13_SECRET_ENV:-${REPO}/.env}")"
RECOVERY_BUNDLE="$(realpath -e -- "${AAR_RUN13_RECOVERY_BUNDLE:-/storage/home/${USER}/aar-recovery/run7_20261007T004406Z-1b3303d02821/baseline_salvage}")"
REUSED_BASELINE="${RECOVERY_BUNDLE}/gemma4_31b_multidimensional_baseline.json"
RECOVERED_SOURCES="${RECOVERY_BUNDLE}/source_artifacts"
SV="/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2"
BASE_CHECKPOINT=/checkpoint/ram/shared/models/google/gemma-4-31B-it
# Preserves provider provenance and enforces atomic, terminal budget handling.
REQUIRED_AUTODATA_SHA=51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1
: "${AAR_RUN13_TRIAL_CONFIG:?launch through a validated run_13/canary/trial_N/submit_canary.sh wrapper}"
RUN_CONFIG="$(realpath -e -- "${AAR_RUN13_TRIAL_CONFIG}")"
trial_relative="${RUN_CONFIG#"${RUN13_DIR}/"}"
if [[ ! "${trial_relative}" =~ ^trial_([1-9][0-9]*)/autodata_run\.yaml$ ]]; then
  echo "Run 13 trial config must be canary/trial_N/autodata_run.yaml" >&2
  exit 2
fi
TRIAL_NUMBER="${BASH_REMATCH[1]}"
TRIAL_ID="trial${TRIAL_NUMBER}"
RECOVERY_MANIFEST_EXTERNAL=""
case "${TRIAL_ID}" in
  trial4|trial5|trial6|trial7)
    : "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST:?${TRIAL_ID} requires an external pre-AutoData recovery manifest}"
    if [ ! -f "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}" ] || \
        [ -L "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}" ]; then
      echo "${TRIAL_ID} recovery manifest must be a regular non-symlink file" >&2
      exit 2
    fi
    RECOVERY_MANIFEST_EXTERNAL="$(realpath -e -- "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}")"
    case "${RECOVERY_MANIFEST_EXTERNAL}" in
      "${REPO}"/*)
        echo "${TRIAL_ID} recovery manifest must remain outside the source checkout" >&2
        exit 2
        ;;
    esac
    if [ "$(stat -c '%u' -- "${RECOVERY_MANIFEST_EXTERNAL}")" != "$(id -u)" ] || \
        [ "$(stat -c '%a' -- "${RECOVERY_MANIFEST_EXTERNAL}")" != 600 ]; then
      echo "${TRIAL_ID} recovery manifest must be owned by this user with mode 0600" >&2
      exit 2
    fi
    PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" \
      "${REPO}/scripts/prepare_run13_preautodata_recovery.py" verify \
      --manifest "${RECOVERY_MANIFEST_EXTERNAL}" \
      --target-trial-id "${TRIAL_ID}" >/dev/null
    ;;
  *)
    [ -z "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST:-}" ] || {
      echo "pre-AutoData recovery is allowlisted only for Run 13 Trial 4/5/6/7" >&2
      exit 2
    }
    ;;
esac
[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "Run 13 requires branch autodata" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
SUBMITTED_COMMIT="$(git -C "${REPO}" rev-parse HEAD)"
[ -x "${REPO}/.venv/bin/python" ] || { echo "missing AAR runtime" >&2; exit 2; }
SHARED_HARNESS_PY="${REPO}/.venv/bin/python"
PROFILE_CONFIG="$(env PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" -m \
  aar.autodata_run_config resolve-profile --repo "${REPO}" --run "${RUN_CONFIG}" \
  --fallback-profile "${REPO}/configs/autodata/target_aware_model_api_claude_opus_4_8_c8_v1.yaml")"
config_json="$(PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" -m aar.autodata_run_config inspect \
  --profile "${PROFILE_CONFIG}" --run "${RUN_CONFIG}")"
[ "$(jq -r '.run_id' <<<"${config_json}")" = "run13-canary-${TRIAL_ID}" ] || {
  echo "Run 13 config identity does not match ${TRIAL_ID}" >&2; exit 2;
}
[ "$(jq -r '.target_enabled' <<<"${config_json}")" = true ] || {
  echo "Run 13 requires target-aware AutoData YAML" >&2; exit 2;
}
RUN13_STORAGE_ROOT="${AAR_RUN13_STORAGE_ROOT:-$(jq -r '.storage_root' <<<"${config_json}")}"
mkdir -p "${RUN13_STORAGE_ROOT}/aar-runs" "${RUN13_STORAGE_ROOT}/aar-checkpoints"
RUN13_STORAGE_ROOT="$(realpath -e -- "${RUN13_STORAGE_ROOT}")"
case "${RUN13_STORAGE_ROOT}" in
  /checkpoint/ram/"${USER}") ;;
  *) echo "Run 13 storage root must be /checkpoint/ram/${USER}" >&2; exit 2 ;;
esac
: "${AAR_RUN13_CANARY_ROOT:?set AAR_RUN13_CANARY_ROOT to the compatible retained Opus/Gemma/Luna proof}"
CANARY_ROOT="$(realpath -e -- "${AAR_RUN13_CANARY_ROOT}")"
RESEARCHER_DEPLOYMENT="$(jq -r '.researcher_deployment' <<<"${config_json}")"
GENERATOR_DEPLOYMENT="$(jq -r '.generator_deployment' <<<"${config_json}")"
GENERATOR_MODEL="$(jq -r '.generator_model' <<<"${config_json}")"
GENERATOR_PROTOCOL="$(jq -r '.generator_protocol' <<<"${config_json}")"
JUDGE_MODEL="$(jq -r '.judge_model' <<<"${config_json}")"
AGENT_BACKEND="$(jq -r '.agent_backend' <<<"${config_json}")"
AGENT_MODEL="$(jq -r '.agent_model // empty' <<<"${config_json}")"
AGENT_EFFORT="$(jq -r '.agent_effort // empty' <<<"${config_json}")"
[ "${AGENT_BACKEND}" = claude ] || { echo "Run 13 requires the Claude agent backend" >&2; exit 2; }
[ "${AGENT_MODEL}" = claude-opus-4-8 ] || { echo "Run 13 requires Claude Opus 4.8" >&2; exit 2; }
[ "${AGENT_EFFORT}" = max ] || { echo "Run 13 requires maximum Claude effort" >&2; exit 2; }
[ "${RESEARCHER_DEPLOYMENT}" = meta-claude-cli-opus-4-8 ] || { echo "Run 13 researcher deployment drifted" >&2; exit 2; }
[ "${GENERATOR_MODEL}" = claude-4-8-opus ] || { echo "Run 13 generator model drifted" >&2; exit 2; }
[ "${GENERATOR_PROTOCOL}" = model_api_responses ] || { echo "Run 13 generator protocol drifted" >&2; exit 2; }
[ "${GENERATOR_DEPLOYMENT}" = meta-model-api-claude-4-8-opus ] || { echo "Run 13 generator deployment drifted" >&2; exit 2; }
[ "${JUDGE_MODEL}" = gpt-5-6-luna ] || { echo "Run 13 judge model drifted" >&2; exit 2; }
[ "$(jq -r '.target_model' <<<"${config_json}")" = gemma-4-31B-it ] || { echo "Run 13 target model drifted" >&2; exit 2; }
[ "$(jq -r '.concurrency_per_chain' <<<"${config_json}")" = 8 ] || { echo "Run 13 concurrency must be 8" >&2; exit 2; }
[ "$(jq -r '.model_request_max_attempts' <<<"${config_json}")" = 3 ] || { echo "Run 13 model requests must allow three attempts" >&2; exit 2; }
export AAR_RUN_STORAGE_ROOT="${RUN13_STORAGE_ROOT}"
AAR_KEEP_CHECKPOINTS="$(jq -r 'if .keep_checkpoints then "1" else "0" end' <<<"${config_json}")"
AAR_EVAL_MEM="$(jq -r '.evaluation_memory' <<<"${config_json}")"
EVAL_MAX_TRUNCATION_RATE="$(jq -r '.max_truncation_rate' <<<"${config_json}")"
export AAR_KEEP_CHECKPOINTS AAR_EVAL_MEM EVAL_MAX_TRUNCATION_RATE
export AAR_EXPECTED_MAX_TRUNCATION_RATE="${EVAL_MAX_TRUNCATION_RATE}"
export AAR_AGENT_BACKEND="${AGENT_BACKEND}"
AAR_AGENT_TURN_TIMEOUT_SECONDS="$(jq -r '.turn_timeout_seconds' <<<"${config_json}")"
export AAR_AGENT_TURN_TIMEOUT_SECONDS
[ "${AGENT_BACKEND}" != kimi ] || export AAR_KIMI_TURN_TIMEOUT_SECONDS="${AAR_AGENT_TURN_TIMEOUT_SECONDS}"
[ -z "${AGENT_MODEL}" ] || export AAR_AGENT_MODEL="${AGENT_MODEL}"
[ -z "${AGENT_EFFORT}" ] || export AAR_EFFORT="${AGENT_EFFORT}"
export AAR_AUTODATA=1
AAR_AUTODATA_PROFILE="$(jq -r '.profile_name' <<<"${config_json}")"
AAR_AUTODATA_PROFILE_CONFIG="$(realpath -e -- "${PROFILE_CONFIG}")"
AAR_AUTODATA_RUN_CONFIG="$(realpath -e -- "${RUN_CONFIG}")"
export AAR_AUTODATA_PROFILE AAR_AUTODATA_PROFILE_CONFIG AAR_AUTODATA_RUN_CONFIG
export AAR_AUTODATA_GENERATOR_DEPLOYMENT="${GENERATOR_DEPLOYMENT}"
if [ "${GENERATOR_PROTOCOL}" = openai_chat_completions ]; then
  export AAR_KIMI_PROXY_INFO="${AAR_KIMI_PROXY_INFO:-/checkpoint/ram/shared/vllm_deployments_v2/${GENERATOR_DEPLOYMENT}/proxy_info.json}"
else
  unset AAR_KIMI_PROXY_INFO
fi
RUN_MODE=bootstrap-canary
configured_seeds="$(jq -r '.chains | join(" ")' <<<"${config_json}")"
configured_pairs="$(jq -r '.target_pairs_per_chain' <<<"${config_json}")"
configured_canary_stop="$(jq -r '.bootstrap_canary_stop_after' <<<"${config_json}")"
SEEDS_RAW="${configured_seeds}"
TARGET_PAIRS="${configured_pairs}"
REUSE_BASE_DEPLOYMENT="${AAR_RUN13_REUSE_BASE_DEPLOYMENT:-}"

read -r -a seeds <<< "${SEEDS_RAW}"
if [ "${#seeds[@]}" -ne 1 ] || [ "${SEEDS_RAW}" != alpha ]; then
  echo "Run 13 canary requires exactly the alpha chain" >&2; exit 2;
fi
[ "${TARGET_PAIRS}" = 1 ] || {
  echo "Run 13 canary requires one structural target pair" >&2; exit 2;
}
[ "${configured_canary_stop}" = training_smoke ] || {
  echo "Run 13 canary must stop after training_smoke" >&2; exit 2;
}
export AAR_AUTODATA_STOP_AFTER=training_smoke
if [ -n "${REUSE_BASE_DEPLOYMENT}" ] && \
    [[ ! "${REUSE_BASE_DEPLOYMENT}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "invalid reusable base deployment ID" >&2; exit 2
fi

if [ ! -x "${BROKER_PYTHON}" ]; then
  echo "missing runtime" >&2
  exit 2
fi
[ "$(git -C "${AUTODATA_CHECKOUT}" rev-parse HEAD)" = "${REQUIRED_AUTODATA_SHA}" ] || { echo "wrong AutoData revision" >&2; exit 2; }
if ! git -C "${AUTODATA_CHECKOUT}" diff --quiet || \
    ! git -C "${AUTODATA_CHECKOUT}" diff --cached --quiet; then
  echo "tracked AutoData worktree is dirty" >&2
  exit 2
fi
AAR_AUTODATA=1 \
  AAR_AUTODATA_PLUGIN_ROOT="${AUTODATA_CHECKOUT}/plugin/autodata" \
  AAR_AUTODATA_SHA="${REQUIRED_AUTODATA_SHA}" \
  PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" -c \
  'from aar.research_loop.autodata_plugin import resolve_autodata_plugin; assert resolve_autodata_plugin() is not None'
for proof in preflight.json canary-report.json target-binding.json; do
  [ -s "${CANARY_ROOT}/${proof}" ] || { echo "missing Run 13 canary proof ${proof}" >&2; exit 2; }
done
proof_args=(
  --root "${CANARY_ROOT}"
  --generator-model "${GENERATOR_MODEL}"
  --generator-deployment-id "${GENERATOR_DEPLOYMENT}"
  --judge-model "${JUDGE_MODEL}"
)
if [ -n "${REUSE_BASE_DEPLOYMENT}" ]; then
  proof_args+=(--expected-target-deployment-id "${REUSE_BASE_DEPLOYMENT}")
fi
PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" \
  "${REPO}/scripts/verify_autodata_canary_proof.py" "${proof_args[@]}" >/dev/null || {
    echo "Run 13 canary proof is inconsistent with the launch configuration" >&2
    exit 2
  }

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
for name in HF_TOKEN MODEL_API_KEY; do [ -n "${!name:-}" ] || { echo "missing ${name}" >&2; exit 2; }; done
if [ "${GENERATOR_PROTOCOL}" != openai_chat_completions ]; then
  unset AAR_KIMI_PROXY_INFO
fi

commit="${SUBMITTED_COMMIT}"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${commit:0:12}"
run_namespace="${EXPERIMENT_RUN_ID}-${TRIAL_ID}-bootstrap-canary"
attempt="${RUN13_STORAGE_ROOT}/aar-runs/${run_namespace}/${attempt_id}"
checkpoint_root="${RUN13_STORAGE_ROOT}/aar-checkpoints/${run_namespace}/${attempt_id}"
mkdir -p "${attempt}/"{metadata,logs,secrets,chains,runtime}
mkdir -p "${checkpoint_root}/chains"
chmod 700 "${attempt}" "${attempt}/"{metadata,logs,secrets,chains}
chmod 700 "${checkpoint_root}" "${checkpoint_root}/chains"
if [[ "${TRIAL_ID}" =~ ^trial(4|5|6|7)$ ]]; then
  RECOVERY_MANIFEST_SNAPSHOT="${attempt}/metadata/preautodata-recovery-manifest.json"
  install -m 400 -- "${RECOVERY_MANIFEST_EXTERNAL}" "${RECOVERY_MANIFEST_SNAPSHOT}"
  [ "$(sha256sum "${RECOVERY_MANIFEST_EXTERNAL}" | awk '{print $1}')" = \
    "$(sha256sum "${RECOVERY_MANIFEST_SNAPSHOT}" | awk '{print $1}')" ] || {
      echo "${TRIAL_ID} recovery manifest snapshot drifted" >&2
      exit 2
    }
  PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" \
      "${REPO}/scripts/prepare_run13_preautodata_recovery.py" verify \
      --manifest "${RECOVERY_MANIFEST_SNAPSHOT}" --snapshot \
      --target-trial-id "${TRIAL_ID}" >/dev/null
  export AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST="${RECOVERY_MANIFEST_SNAPSHOT}"
fi
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${commit}" ] || {
  echo "AAR source changed during launch preflight" >&2; exit 2;
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "AAR source became dirty during launch preflight" >&2
  exit 2
fi
SOURCE_REPO="${attempt}/runtime/aar-source"
SOURCE_AUTODATA="${attempt}/runtime/autodata-source"
export PYTHONDONTWRITEBYTECODE=1
"${REPO}/scripts/create_pinned_source_snapshot.sh" \
  "${REPO}" "${commit}" "${SOURCE_REPO}" >/dev/null
"${SOURCE_REPO}/scripts/create_pinned_source_snapshot.sh" \
  "${AUTODATA_CHECKOUT}" "${REQUIRED_AUTODATA_SHA}" "${SOURCE_AUTODATA}" >/dev/null

case "${RUN_CONFIG}" in
  "${REPO}"/*) SNAPSHOT_RUN_CONFIG="${SOURCE_REPO}/${RUN_CONFIG#"${REPO}/"}" ;;
  *)
    SNAPSHOT_RUN_CONFIG="${attempt}/runtime/autodata-run.yaml"
    install -m 400 -- "${RUN_CONFIG}" "${SNAPSHOT_RUN_CONFIG}"
    ;;
esac
case "${PROFILE_CONFIG}" in
  "${REPO}"/*) SNAPSHOT_PROFILE_CONFIG="${SOURCE_REPO}/${PROFILE_CONFIG#"${REPO}/"}" ;;
  *)
    SNAPSHOT_PROFILE_CONFIG="${attempt}/runtime/autodata-profile.yaml"
    install -m 400 -- "${PROFILE_CONFIG}" "${SNAPSHOT_PROFILE_CONFIG}"
    ;;
esac
if [ ! -s "${SNAPSHOT_RUN_CONFIG}" ] || [ ! -s "${SNAPSHOT_PROFILE_CONFIG}" ]; then
  echo "attempt-local AutoData configuration snapshot is incomplete" >&2
  exit 2
fi
snapshot_config_json="$(PYTHONPATH="${SOURCE_REPO}" "${SHARED_HARNESS_PY}" -m \
  aar.autodata_run_config inspect --profile "${SNAPSHOT_PROFILE_CONFIG}" \
  --run "${SNAPSHOT_RUN_CONFIG}")"
[ "$(jq -S -c . <<<"${snapshot_config_json}")" = "$(jq -S -c . <<<"${config_json}")" ] || {
  echo "attempt-local AutoData configuration differs from validated launch configuration" >&2
  exit 2
}
jq -n \
  --arg aar_commit "${commit}" --arg aar_root "${SOURCE_REPO}" \
  --arg autodata_commit "${REQUIRED_AUTODATA_SHA}" --arg autodata_root "${SOURCE_AUTODATA}" \
  '{schema:"aar.source-snapshots/v1",aar:{commit:$aar_commit,root:$aar_root},autodata:{commit:$autodata_commit,root:$autodata_root}}' \
  > "${attempt}/metadata/source-snapshots.json"
chmod 400 "${attempt}/metadata/source-snapshots.json"

shared_source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${SHARED_HARNESS_PY}" "${SOURCE_REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${shared_source_root}" --verify-only >/dev/null
SNAPSHOT_SOURCE_ROOT="${attempt}/runtime/llm-uncertainty-source"
mkdir -p "${SNAPSHOT_SOURCE_ROOT}"
cp -a -- "${shared_source_root}/data" "${SNAPSHOT_SOURCE_ROOT}/data"
install -m 400 -- "${shared_source_root}/.aar-source.json" \
  "${SNAPSHOT_SOURCE_ROOT}/.aar-source.json"
"${SHARED_HARNESS_PY}" "${SOURCE_REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${SNAPSHOT_SOURCE_ROOT}" --verify-only >/dev/null
export LLM_UNCERTAINTY_SRC="${SNAPSHOT_SOURCE_ROOT}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${SNAPSHOT_SOURCE_ROOT}/.aar-source.json"

SNAPSHOT_RECOVERY_ROOT="${attempt}/runtime/baseline-recovery"
mkdir -p "${SNAPSHOT_RECOVERY_ROOT}"
install -m 400 -- "${REUSED_BASELINE}" "${SNAPSHOT_RECOVERY_ROOT}/baseline.json"
cp -a -- "${RECOVERED_SOURCES}" "${SNAPSHOT_RECOVERY_ROOT}/source-artifacts"
SNAPSHOT_REUSED_BASELINE="${SNAPSHOT_RECOVERY_ROOT}/baseline.json"
SNAPSHOT_RECOVERED_SOURCES="${SNAPSHOT_RECOVERY_ROOT}/source-artifacts"
"${SHARED_HARNESS_PY}" "${SOURCE_REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${SNAPSHOT_REUSED_BASELINE}" \
  --recovered-source-dir "${SNAPSHOT_RECOVERED_SOURCES}" >/dev/null

"${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_10/runtime/snapshot_vllm_runtime.sh" "${attempt}" \
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
export AAR_SERVE_API_V2_ROOT="${SV}"
case "${AGENT_BACKEND}" in
  kimi)
    export KIMI_CLI_PATH=/storage/home/${USER}/tools/kimi-code-2.1.1/node_modules/.bin/kimi
    export AAR_WEB_MODE=native_web
    export AAR_KIMI_SERVE_DEPLOYMENT="${RESEARCHER_DEPLOYMENT}" AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
    export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
    export KIMI_MODEL_CAPABILITIES=tool_use
    export KIMI_MODEL_MAX_OUTPUT_SIZE=65536 KIMI_MODEL_MAX_COMPLETION_TOKENS=65536
    export AAR_KIMI_PREFLIGHT_TIMEOUT_SECONDS=180
    unset KIMI_AGENT_MODEL
    PYTHONPATH="${SOURCE_REPO}" timeout 420 "${SHARED_HARNESS_PY}" "${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_10/canary/verify_kimi_endpoint.py" \
      --workspace "${SOURCE_REPO}" --output "${attempt}/metadata/kimi_mcp_preflight.json"
    ;;
  claude)
    [ "${AGENT_MODEL}" = claude-opus-4-8 ] || { echo "Run 13 requires Claude Opus 4.8" >&2; exit 2; }
    [ "${AGENT_EFFORT}" = max ] || { echo "Run 13 requires maximum Claude effort" >&2; exit 2; }
    export AAR_WEB_MODE=meta_secure
    CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH:-$(command -v claude || true)}"
    export CLAUDE_CLI_PATH
    [ -x "${CLAUDE_CLI_PATH}" ] || { echo "Claude CLI is missing" >&2; exit 2; }
    "${CLAUDE_CLI_PATH}" --help 2>&1 | grep -q -- --secure-internet-mode || {
      echo "Claude CLI lacks secure-internet mode" >&2; exit 2;
    }
    [ -x "${SOURCE_REPO}/scripts/aar-paper-search" ] || {
      echo "bounded paper-search helper is missing" >&2; exit 2;
    }
    "${SHARED_HARNESS_PY}" - "${attempt}/metadata/claude_research_preflight.json" "${CLAUDE_CLI_PATH}" <<'PY'
import json
import pathlib
import sys

pathlib.Path(sys.argv[1]).write_text(json.dumps({
    "schema": "aar.claude-research-preflight/v1",
    "status": "passed",
    "research_backend": "claude",
    "research_model": "claude-opus-4-8",
    "research_effort": "max",
    "claude_cli_path": sys.argv[2],
    "claude_cli_executable": True,
    "secure_internet_mode": True,
    "bounded_paper_search": True,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
    ;;
esac

suffix="$(printf '%s' "${attempt_id}" | sha256sum | cut -c1-8)"
deployments=()
for seed in "${seeds[@]}"; do
  chain_root="${attempt}/chains/${seed}"
  mkdir -p "${chain_root}/"{bindings,deployments,logs,metadata,secrets}
  mkdir -p "${checkpoint_root}/chains/${seed}/merged_candidates"
  chmod 700 "${chain_root}" "${chain_root}/secrets"
  "${BROKER_PYTHON}" -c 'import secrets; print(secrets.token_hex(32))' > "${chain_root}/secrets/capability"
  printf '{"schema":"aar.autodata.proposal-bindings/v1","proposals":{},"workspaces":{}}\n' \
    > "${chain_root}/secrets/proposal-bindings.json"
  chmod 600 "${chain_root}/secrets/"*
  deployment="${REUSE_BASE_DEPLOYMENT:-winnieyangwn-${EXPERIMENT_RUN_ID}-${seed}-i1-${suffix}}"
  deployments+=("${deployment}")
  if [ -z "${REUSE_BASE_DEPLOYMENT}" ]; then
    env -u SSL_CERT_FILE -u NODE_EXTRA_CA_CERTS \
      -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
      -u NO_PROXY -u no_proxy \
      "${SV}/serve.sh" deploy "${deployment}" --model gemma-4-31B-it \
        --checkpoint "${BASE_CHECKPOINT}" --endpoints 1 --cluster fair-cw-use2-1 \
        --image docker.io/vllm/vllm-openai:v0.25.1 \
        --partition g3 --account ram --qos g3_ram_high \
        --coord-qos cpu_x86_lowest --proxy-qos cpu_x86_lowest \
        --gateway-register --lifetime 7d --no-watch
  fi
  PYTHONPATH="${SOURCE_REPO}" "${SHARED_HARNESS_PY}" -m aar.autodata_campaign_policy create-base-target \
    --chain-id "${seed}" --base-checkpoint "${BASE_CHECKPOINT}" \
    --target-url http://fair-cw-use2-1-ingress-slurm-ingress/v1 \
    --target-host-header ram-inference-gateway.ingress. --target-model gemma-4-31B-it \
    --target-deployment-id "${deployment}" --output "${chain_root}/bindings/iteration-1.json"
  cp -- "${chain_root}/bindings/iteration-1.json" "${chain_root}/metadata/incumbent.json"
  PYTHONPATH="${SOURCE_REPO}" "${SHARED_HARNESS_PY}" -m aar.autodata_run_config compile \
    --profile "${SNAPSHOT_PROFILE_CONFIG}" --run "${SNAPSHOT_RUN_CONFIG}" \
    --target-binding "${chain_root}/bindings/iteration-1.json" --chain "${seed}" \
    --repo "${SOURCE_REPO}" --output-dir "${chain_root}/metadata" >/dev/null
done

# All chains share the same static YAML settings. Source one compiled copy for
# submission metadata; each chain receives and validates its own compiled copy.
export AAR_AUTODATA_RUNTIME_ENV="${attempt}/chains/${seeds[0]}/metadata/autodata-runtime.env"
# shellcheck disable=SC1090
source "${AAR_AUTODATA_RUNTIME_ENV}"

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

export AAR_REPO="${SOURCE_REPO}" AAR_SOURCE_SNAPSHOT="${SOURCE_REPO}"
export AAR_TRUSTED_HARNESS_PY="${SHARED_HARNESS_PY}"
export HARNESS_PY="${AAR_TRUSTED_HARNESS_PY}" HARNESS_ENV="${SECRET_ENV}"
export WORKSPACE_DIR="${SOURCE_REPO}" PYTHONPATH="${SOURCE_REPO}"
export AAR_BENCHMARK_DOCS="${SOURCE_REPO}/benchmark_docs"
export BENCHMARK_DOCS_DIR="${SOURCE_REPO}/benchmark_docs"
export AAR_RUN_ATTEMPT_DIR="${attempt}" AAR_RUNTIME_ROOT="${attempt}"
export AAR_RUN13_CHECKPOINT_ROOT="${checkpoint_root}"
export AAR_AUTODATA_CHECKPOINT_ROOT="${checkpoint_root}"
export AAR_EXPERIMENT_RUN_ID="${EXPERIMENT_RUN_ID}"
export AAR_BASELINE_GIT_COMMIT="${commit}" AAR_REUSED_BASELINE="${SNAPSHOT_REUSED_BASELINE}"
export AAR_RECOVERED_BASELINE_SOURCES="${SNAPSHOT_RECOVERED_SOURCES}"
export AAR_AUTODATA_CHECKOUT="${SOURCE_AUTODATA}"
export AAR_AUTODATA_PLUGIN_ROOT="${SOURCE_AUTODATA}/plugin/autodata"
export AAR_AUTODATA_SHA="${REQUIRED_AUTODATA_SHA}"
export AAR_AUTODATA_PROFILE_CONFIG="${SNAPSHOT_PROFILE_CONFIG}"
export AAR_AUTODATA_RUN_CONFIG="${SNAPSHOT_RUN_CONFIG}"
export AAR_AUTODATA_BROKER_PYTHON="${BROKER_PYTHON}"
export AAR_AUTODATA_MODEL_ENV_FILE="${model_env}"
export AAR_AUTODATA_APPROVAL_PRIVATE_KEY="${approval_private}"
export AAR_AUTODATA_APPROVAL_PUBLIC_KEY="${approval_public}"
export AAR_AUTODATA_APPROVAL_PUBLIC_KEY_SHA256="${approval_digest}"
export AAR_AUTODATA_APPROVAL_ACTOR=aar-integrity-monitor
export AAR_AUTODATA_APPROVAL_POLICY_VERSION="aar-autodata/${EXPERIMENT_RUN_ID}-v1"
export AAR_AUTODATA_RESOURCES_READY=1
export AAR_MONITOR_MODEL_API_KEY="${MODEL_API_KEY}"
export AAR_RUN13_MODE="${RUN_MODE}"
export AAR_RUN13_TRIAL_ID="${TRIAL_ID}"
export AAR_RUN13_SEEDS="${SEEDS_RAW}"
export AAR_RUN13_CHAIN_COUNT="${#seeds[@]}"
export AAR_RUN13_TARGET_PAIRS="${TARGET_PAIRS}"
export AAR_RUN13_MAX_CHAIN_ATTEMPTS=2

job="$(sbatch --parsable --job-name="${EXPERIMENT_RUN_ID}-${TRIAL_ID}-autodata-launch" \
  --output="${attempt}/logs/pipeline-%j.out" --export=ALL \
  "${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_13/canary/slurm/pipeline.sbatch")"
base_reused=false
[ -z "${REUSE_BASE_DEPLOYMENT}" ] || base_reused=true
source_snapshots_sha256="sha256:$(sha256sum "${attempt}/metadata/source-snapshots.json" | awk '{print $1}')"
recovery_manifest_sha256=none
if [[ "${TRIAL_ID}" =~ ^trial(4|5|6|7)$ ]]; then
  recovery_manifest_sha256="sha256:$(sha256sum "${AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST}" | awk '{print $1}')"
fi
printf 'launch_job_id=%s\nattempt_dir=%s\ncheckpoint_root=%s\ngit_commit=%s\nsource_snapshot_root=%s\nautodata_commit=%s\nautodata_snapshot_root=%s\nsource_snapshots_sha256=%s\nrecovery_manifest_sha256=%s\nexperiment_run_id=%s\ntrial_id=%s\nrun_config_id=%s\nmode=%s\nstop_after=%s\nproduction_required_rows=%s\nresearch_backend=%s\nresearch_model=%s\nresearch_effort=%s\nresearcher_deployment=%s\nautodata_generator_model=%s\nautodata_generator_protocol=%s\nautodata_generator_deployment=%s\nautodata_profile=%s\nautodata_concurrency=%s\nautodata_model_request_attempts=%s\nchains=%s\ntarget_pairs_per_chain=%s\nseeds=%s\nbase_deployments=%s\nbase_deployment_reused=%s\n' \
  "${job}" "${attempt}" "${checkpoint_root}" "${commit}" \
  "${SOURCE_REPO}" "${REQUIRED_AUTODATA_SHA}" "${SOURCE_AUTODATA}" \
  "${source_snapshots_sha256}" "${recovery_manifest_sha256}" \
  "${EXPERIMENT_RUN_ID}" "${TRIAL_ID}" \
  "$(jq -r '.run_id' <<<"${config_json}")" "${RUN_MODE}" \
  "${AAR_AUTODATA_STOP_AFTER:-score-result}" "${AAR_AUTODATA_PRODUCTION_ROWS}" \
  "${AGENT_BACKEND}" "${AGENT_MODEL:-Kimi-K2.6}" "${AGENT_EFFORT:-default}" \
  "${RESEARCHER_DEPLOYMENT}" "${GENERATOR_MODEL}" "${GENERATOR_PROTOCOL}" \
  "${GENERATOR_DEPLOYMENT}" "${AAR_AUTODATA_PROFILE}" \
  "${AAR_AUTODATA_CONCURRENCY}" "${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS}" \
  "${#seeds[@]}" "${TARGET_PAIRS}" "${SEEDS_RAW}" \
  "${deployments[*]}" "${base_reused}" \
  | tee "${attempt}/metadata/submission.txt"
unset MODEL_API_KEY HF_TOKEN
