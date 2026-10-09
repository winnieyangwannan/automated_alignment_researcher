#!/bin/bash
# Fail-closed defaults for every real AAR team launch, independent of whether
# Claude or Kimi is the research backend. Source this after resolving the target
# model and before submitting research-chain jobs.

_aar_method_safety_vars=(
  AAR_REQUIRE_METHOD_CONTRACT
  AAR_REQUIRE_METHOD_SMOKE
  AAR_PRETRAIN_SMOKE
  AAR_WRITE_TRAIN_FAILURE_MARKER
  AAR_REQUIRE_TRAIN_RECEIPT
)
case "${TARGET_MODEL_PATH:-${TARGET_MODEL:-}}" in
  *gemma-4*) _aar_method_safety_vars+=(AAR_REQUIRE_GEMMA4_TARGETS) ;;
esac

for _aar_method_safety_var in "${_aar_method_safety_vars[@]}"; do
  _aar_method_safety_value="${!_aar_method_safety_var:-1}"
  if [ "${_aar_method_safety_value}" != 1 ]; then
    echo "method safety: ${_aar_method_safety_var} must be 1 for a real team launch" >&2
    return 2 2>/dev/null || exit 2
  fi
  printf -v "${_aar_method_safety_var}" '%s' 1
  export "${_aar_method_safety_var}"
done

unset _aar_method_safety_var _aar_method_safety_value _aar_method_safety_vars
