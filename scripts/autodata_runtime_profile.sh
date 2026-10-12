#!/bin/bash
# Apply one measured AutoData runtime profile. Launch parents may call the
# settings function before selecting a per-chain policy. Research jobs call the
# combined function after AAR_AUTODATA_CAMPAIGN_POLICY is set.

aar_load_compiled_autodata_runtime() {
  [ -n "${AAR_AUTODATA_RUNTIME_ENV:-}" ] || return 1
  [ -f "${AAR_AUTODATA_RUNTIME_ENV}" ] && [ ! -L "${AAR_AUTODATA_RUNTIME_ENV}" ] || {
    echo "compiled AutoData runtime environment is missing or is a symlink" >&2
    return 2
  }
  [ "$(stat -c %u "${AAR_AUTODATA_RUNTIME_ENV}")" = "$(id -u)" ] && \
    [ "$(stat -c %a "${AAR_AUTODATA_RUNTIME_ENV}")" = 600 ] || {
      echo "compiled AutoData runtime environment must be owner-only" >&2
      return 2
    }
  # This file is written atomically by aar.autodata_run_config from strictly
  # validated scalar values; it is never authored by the research process.
  # shellcheck disable=SC1090
  source "${AAR_AUTODATA_RUNTIME_ENV}"
  return 0
}

aar_set_autodata_runtime_profile() {
  if [ "${AAR_AUTODATA:-0}" != 1 ]; then
    return 0
  fi

  if [ -n "${AAR_AUTODATA_RUNTIME_ENV:-}" ]; then
    aar_load_compiled_autodata_runtime
    : "${AAR_AUTODATA_PROFILE:?compiled runtime omitted profile name}"
    : "${AAR_AUTODATA_CONCURRENCY:?compiled runtime omitted concurrency}"
    : "${AAR_AUTODATA_BROKER_RUNNER:?compiled runtime omitted broker runner}"
    : "${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS:?compiled runtime omitted retries}"
  elif [ -z "${AAR_AUTODATA_PROFILE:-}" ]; then
    return 0
  else
    case "${AAR_AUTODATA_PROFILE}" in
      target-aware-local-v1)
        export AAR_AUTODATA_BROKER_RUNNER=local-bwrap
        export AAR_AUTODATA_ENVIRONMENT=oci-runner-firecracker-large
        export AAR_AUTODATA_CONCURRENCY=8
        export AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS=3
        ;;
      target-aware-local-c32-v1)
        export AAR_AUTODATA_BROKER_RUNNER=local-bwrap
        export AAR_AUTODATA_ENVIRONMENT=oci-runner-firecracker-large
        export AAR_AUTODATA_CONCURRENCY=32
        export AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS=1
        ;;
      question-only-local-v1)
        export AAR_AUTODATA_BROKER_RUNNER=local-bwrap
        export AAR_AUTODATA_ENVIRONMENT=oci-runner-firecracker-large
        export AAR_AUTODATA_CONCURRENCY=64
        export AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS=1
        ;;
      *)
        echo "unknown AAR_AUTODATA_PROFILE: ${AAR_AUTODATA_PROFILE}" >&2
        return 2
        ;;
    esac
    export AAR_AUTODATA_LIFECYCLE_SUPERVISED=1
    export AAR_AUTODATA_REUSE_POLICY=digest-verified
  fi

  local generator_protocol="${AAR_AUTODATA_GENERATOR_PROTOCOL:-}"
  if [ -n "${AAR_AUTODATA_CAMPAIGN_POLICY:-}" ]; then
    [ -f "${AAR_AUTODATA_CAMPAIGN_POLICY}" ] || {
      echo "missing AutoData campaign policy: ${AAR_AUTODATA_CAMPAIGN_POLICY}" >&2
      return 2
    }
    generator_protocol="$(jq -er \
      '.required_solve_env.AUTODATA_GENERATOR_PROTOCOL | select(type == "string" and length > 0)' \
      "${AAR_AUTODATA_CAMPAIGN_POLICY}")" || {
      echo "AutoData campaign policy omitted generator protocol" >&2
      return 2
    }
  elif [ -z "${generator_protocol}" ]; then
    echo "AutoData generator protocol is required" >&2
    return 2
  fi
  export AAR_AUTODATA_GENERATOR_PROTOCOL="${generator_protocol}"

  case "${generator_protocol}" in
    openai_chat_completions)
      if [ -z "${AAR_KIMI_PROXY_INFO:-}" ] && \
          [ -n "${AAR_AUTODATA_GENERATOR_DEPLOYMENT:-}" ]; then
        export AAR_KIMI_PROXY_INFO="/checkpoint/ram/shared/vllm_deployments_v2/${AAR_AUTODATA_GENERATOR_DEPLOYMENT}/proxy_info.json"
      fi
      : "${AAR_KIMI_PROXY_INFO:?chat-completions AutoData profile requires AAR_KIMI_PROXY_INFO or AAR_AUTODATA_GENERATOR_DEPLOYMENT}"
      [ -f "${AAR_KIMI_PROXY_INFO}" ] || {
        echo "missing AutoData Kimi proxy contract: ${AAR_KIMI_PROXY_INFO}" >&2
        return 2
      }
      ;;
    model_api_responses)
      unset AAR_KIMI_PROXY_INFO
      ;;
    *)
      echo "unsupported AutoData generator protocol: ${generator_protocol}" >&2
      return 2
      ;;
  esac
}

aar_validate_autodata_runtime_profile() {
  if [ -z "${AAR_AUTODATA_PROFILE:-}" ]; then
    return 0
  fi
  : "${AAR_AUTODATA_CAMPAIGN_POLICY:?missing AutoData campaign policy}"
  : "${AAR_AUTODATA_CHECKOUT:?missing canonical AutoData checkout}"
  : "${AAR_AUTODATA_GENERATOR_DEPLOYMENT:?missing AutoData generator deployment}"
  local runtime_args=(
    --profile "${AAR_AUTODATA_PROFILE}"
    --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY}"
    --autodata-checkout "${AAR_AUTODATA_CHECKOUT}"
    --generator-deployment-id "${AAR_AUTODATA_GENERATOR_DEPLOYMENT}"
  )
  if [ -n "${AAR_KIMI_PROXY_INFO:-}" ]; then
    runtime_args+=(--kimi-proxy-info "${AAR_KIMI_PROXY_INFO}")
  fi
  PYTHONPATH="${REPO:?missing AAR repository}" \
    "${HARNESS_PY:?missing harness Python}" -m aar.autodata_runtime_profile \
      "${runtime_args[@]}" >/dev/null
  if [ -n "${AAR_AUTODATA_RESOLVED_CONFIG:-}" ]; then
    PYTHONPATH="${REPO}" "${HARNESS_PY}" -m aar.autodata_run_config validate \
      --resolved "${AAR_AUTODATA_RESOLVED_CONFIG}" \
      --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY}" \
      --training-data-contract "${AAR_AUTODATA_TRAINING_DATA_CONTRACT}" >/dev/null
  fi
}

aar_apply_autodata_runtime_profile() {
  aar_set_autodata_runtime_profile
  aar_validate_autodata_runtime_profile
}
