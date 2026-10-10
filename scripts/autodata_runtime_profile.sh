#!/bin/bash
# Apply one measured AutoData runtime profile. Launch parents may call the
# settings function before selecting a per-chain policy. Research jobs call the
# combined function after AAR_AUTODATA_CAMPAIGN_POLICY is set.

aar_set_autodata_runtime_profile() {
  if [ "${AAR_AUTODATA:-0}" != 1 ]; then
    return 0
  fi

  if [ -z "${AAR_AUTODATA_PROFILE:-}" ]; then
    return 0
  fi
  case "${AAR_AUTODATA_PROFILE}" in
    target-aware-local-v1)
      export AAR_AUTODATA_BROKER_RUNNER=local-bwrap
      export AAR_AUTODATA_ENVIRONMENT=oci-runner-firecracker-large
      export AAR_AUTODATA_CONCURRENCY=32
      export AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS=3
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

  if [ -z "${AAR_KIMI_PROXY_INFO:-}" ] && [ -n "${AAR_AUTODATA_GENERATOR_DEPLOYMENT:-}" ]; then
    export AAR_KIMI_PROXY_INFO="/checkpoint/ram/shared/vllm_deployments_v2/${AAR_AUTODATA_GENERATOR_DEPLOYMENT}/proxy_info.json"
  fi
  : "${AAR_KIMI_PROXY_INFO:?optimized AutoData profile requires AAR_KIMI_PROXY_INFO or AAR_AUTODATA_GENERATOR_DEPLOYMENT}"
  [ -f "${AAR_KIMI_PROXY_INFO}" ] || {
    echo "missing AutoData Kimi proxy contract: ${AAR_KIMI_PROXY_INFO}" >&2
    return 2
  }
}

aar_validate_autodata_runtime_profile() {
  if [ -z "${AAR_AUTODATA_PROFILE:-}" ]; then
    return 0
  fi
  : "${AAR_AUTODATA_CAMPAIGN_POLICY:?missing AutoData campaign policy}"
  : "${AAR_AUTODATA_CHECKOUT:?missing canonical AutoData checkout}"
  : "${AAR_AUTODATA_GENERATOR_DEPLOYMENT:?missing AutoData generator deployment}"
  PYTHONPATH="${REPO:?missing AAR repository}" \
    "${HARNESS_PY:?missing harness Python}" -m aar.autodata_runtime_profile \
      --profile "${AAR_AUTODATA_PROFILE}" \
      --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY}" \
      --autodata-checkout "${AAR_AUTODATA_CHECKOUT}" \
      --generator-deployment-id "${AAR_AUTODATA_GENERATOR_DEPLOYMENT}" \
      --kimi-proxy-info "${AAR_KIMI_PROXY_INFO}" >/dev/null
}

aar_apply_autodata_runtime_profile() {
  aar_set_autodata_runtime_profile
  aar_validate_autodata_runtime_profile
}
