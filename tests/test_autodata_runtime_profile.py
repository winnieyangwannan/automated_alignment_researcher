from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from aar.autodata_runtime_profile import (
    TARGET_AWARE_LOCAL_C32_PROFILE,
    TARGET_AWARE_LOCAL_PROFILE,
    runtime_profile,
    validate_campaign_policy,
    validate_runtime,
)


ROOT = Path(__file__).resolve().parents[1]


def _policy(attempts: str = "3") -> dict:
    return {
        "runner": "local-bwrap",
        "environment": "oci-runner-firecracker-large",
        "required_solve_env": {
            "AUTODATA_TARGET_ENABLED": "1",
            "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": attempts,
            "AUTODATA_GENERATOR_DEPLOYMENT_ID": "kimi-generation",
        },
    }


def _optimized_checkout(root: Path) -> Path:
    for relative in (
        "src/autodata/broker",
        "plugin/autodata/scripts",
        "schemas",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "src/autodata/broker/local_bwrap.py").write_text("# local\n")
    (root / "src/autodata/broker/cli.py").write_text('option = "--database"\n')
    (root / "plugin/autodata/scripts/bootstrap.py").write_text(
        "venv.EnvBuilder(with_pip=False)\n"
    )
    (root / "schemas/autodata.execution.v1.schema.json").write_text(
        json.dumps({"properties": {"finalization": {"type": "object"}}})
    )
    return root


def test_target_aware_profile_has_measured_defaults() -> None:
    profile = runtime_profile(TARGET_AWARE_LOCAL_PROFILE)

    assert profile.broker_runner == "local-bwrap"
    assert profile.concurrency == 8
    assert profile.model_request_max_attempts == 3
    assert profile.lifecycle_supervised is True
    assert profile.reuse_policy == "digest-verified"


def test_profile_rejects_campaign_attempt_drift() -> None:
    with pytest.raises(ValueError, match="model-request attempts"):
        validate_campaign_policy(
            _policy(attempts="1"), runtime_profile(TARGET_AWARE_LOCAL_PROFILE)
        )


def test_runtime_validation_requires_optimized_checkout_and_proxy(
    tmp_path: Path,
) -> None:
    checkout = _optimized_checkout(tmp_path / "autodata")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_policy()))
    proxy = tmp_path / "proxy_info.json"
    proxy.write_text("{}\n")

    result = validate_runtime(
        profile_name=TARGET_AWARE_LOCAL_PROFILE,
        campaign_policy_path=policy,
        autodata_checkout=checkout,
        kimi_proxy_info=proxy,
        generator_deployment_id="kimi-generation",
    )

    assert result["concurrency"] == 8
    (checkout / "schemas/autodata.execution.v1.schema.json").write_text(
        json.dumps({"properties": {}})
    )
    with pytest.raises(ValueError, match="selective production finalization"):
        validate_runtime(
            profile_name=TARGET_AWARE_LOCAL_PROFILE,
            campaign_policy_path=policy,
            autodata_checkout=checkout,
            kimi_proxy_info=proxy,
            generator_deployment_id="kimi-generation",
        )


def test_shell_profile_sets_target_aware_defaults(tmp_path: Path) -> None:
    proxy = tmp_path / "proxy_info.json"
    proxy.write_text("{}\n")
    script = ROOT / "scripts/autodata_runtime_profile.sh"
    command = f'''
set -euo pipefail
export AAR_AUTODATA=1
export AAR_AUTODATA_PROFILE=target-aware-local-v1
export AAR_KIMI_PROXY_INFO="{proxy}"
source "{script}"
aar_set_autodata_runtime_profile
printf '%s %s %s %s %s\n' "$AAR_AUTODATA_BROKER_RUNNER" \
  "$AAR_AUTODATA_CONCURRENCY" "$AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS" \
  "$AAR_AUTODATA_LIFECYCLE_SUPERVISED" "$AAR_AUTODATA_REUSE_POLICY"
'''
    completed = subprocess.run(
        ["bash", "-c", command], check=True, capture_output=True, text=True
    )

    assert completed.stdout.strip() == "local-bwrap 8 3 1 digest-verified"


def test_c32_profile_is_an_explicit_load_canary_profile(tmp_path: Path) -> None:
    profile = runtime_profile(TARGET_AWARE_LOCAL_C32_PROFILE)

    assert profile.concurrency == 32
    assert profile.model_request_max_attempts == 1
    proxy = tmp_path / "proxy_info.json"
    proxy.write_text("{}\n")
    script = ROOT / "scripts/autodata_runtime_profile.sh"
    command = f'''
set -euo pipefail
export AAR_AUTODATA=1
export AAR_AUTODATA_PROFILE=target-aware-local-c32-v1
export AAR_KIMI_PROXY_INFO="{proxy}"
source "{script}"
aar_set_autodata_runtime_profile
printf '%s\n' "$AAR_AUTODATA_CONCURRENCY"
printf '%s\n' "$AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS"
'''
    completed = subprocess.run(
        ["bash", "-c", command], check=True, capture_output=True, text=True
    )

    assert completed.stdout.splitlines() == ["32", "1"]
