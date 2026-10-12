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


def _policy(
    attempts: str = "3", protocol: str | None = "openai_chat_completions"
) -> dict:
    solve_environment = {
        "AUTODATA_TARGET_ENABLED": "1",
        "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": attempts,
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": "kimi-generation",
    }
    if protocol is not None:
        solve_environment["AUTODATA_GENERATOR_PROTOCOL"] = protocol
    return {
        "runner": "local-bwrap",
        "environment": "oci-runner-firecracker-large",
        "required_solve_env": solve_environment,
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


def test_runtime_validation_allows_model_api_responses_without_proxy(
    tmp_path: Path,
) -> None:
    checkout = _optimized_checkout(tmp_path / "autodata")
    policy = tmp_path / "policy.json"
    value = _policy(protocol="model_api_responses")
    value["required_solve_env"]["AUTODATA_GENERATOR_DEPLOYMENT_ID"] = (
        "meta-model-api-claude-4-8-opus"
    )
    policy.write_text(json.dumps(value))

    result = validate_runtime(
        profile_name=TARGET_AWARE_LOCAL_PROFILE,
        campaign_policy_path=policy,
        autodata_checkout=checkout,
        kimi_proxy_info=None,
        generator_deployment_id="meta-model-api-claude-4-8-opus",
    )

    assert result["generator_protocol"] == "model_api_responses"


def test_runtime_validation_rejects_missing_kimi_proxy(tmp_path: Path) -> None:
    checkout = _optimized_checkout(tmp_path / "autodata")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_policy()))

    with pytest.raises(ValueError, match="requires a Kimi proxy"):
        validate_runtime(
            profile_name=TARGET_AWARE_LOCAL_PROFILE,
            campaign_policy_path=policy,
            autodata_checkout=checkout,
            kimi_proxy_info=None,
            generator_deployment_id="kimi-generation",
        )


@pytest.mark.parametrize("protocol", [None, "unknown_protocol"])
def test_runtime_validation_rejects_missing_or_unknown_protocol(
    tmp_path: Path, protocol: str | None
) -> None:
    checkout = _optimized_checkout(tmp_path / "autodata")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_policy(protocol=protocol)))

    with pytest.raises(ValueError, match="protocol is missing or unsupported"):
        validate_runtime(
            profile_name=TARGET_AWARE_LOCAL_PROFILE,
            campaign_policy_path=policy,
            autodata_checkout=checkout,
            kimi_proxy_info=None,
            generator_deployment_id="kimi-generation",
        )


def test_runtime_validation_rejects_kimi_proxy_for_model_api_responses(
    tmp_path: Path,
) -> None:
    checkout = _optimized_checkout(tmp_path / "autodata")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_policy(protocol="model_api_responses")))
    proxy = tmp_path / "proxy_info.json"
    proxy.write_text("{}\n")

    with pytest.raises(ValueError, match="does not use a Kimi proxy"):
        validate_runtime(
            profile_name=TARGET_AWARE_LOCAL_PROFILE,
            campaign_policy_path=policy,
            autodata_checkout=checkout,
            kimi_proxy_info=proxy,
            generator_deployment_id="kimi-generation",
        )


def test_shell_profile_skips_kimi_proxy_for_model_api_responses(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_policy(protocol="model_api_responses")))
    script = ROOT / "scripts/autodata_runtime_profile.sh"
    command = f'''
set -euo pipefail
export AAR_AUTODATA=1
export AAR_AUTODATA_PROFILE=target-aware-local-v1
export AAR_AUTODATA_CAMPAIGN_POLICY="{policy}"
export AAR_KIMI_PROXY_INFO="{tmp_path / 'missing-proxy.json'}"
source "{script}"
aar_set_autodata_runtime_profile
printf '%s %s\n' "$AAR_AUTODATA_GENERATOR_PROTOCOL" "${{AAR_KIMI_PROXY_INFO-unset}}"
'''
    completed = subprocess.run(
        ["bash", "-c", command], check=True, capture_output=True, text=True
    )

    assert completed.stdout.strip() == "model_api_responses unset"


def test_shell_profile_sets_target_aware_defaults(tmp_path: Path) -> None:
    proxy = tmp_path / "proxy_info.json"
    proxy.write_text("{}\n")
    script = ROOT / "scripts/autodata_runtime_profile.sh"
    command = f'''
set -euo pipefail
export AAR_AUTODATA=1
export AAR_AUTODATA_PROFILE=target-aware-local-v1
export AAR_AUTODATA_GENERATOR_PROTOCOL=openai_chat_completions
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


def test_shell_profile_rejects_missing_kimi_proxy(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_policy()))
    script = ROOT / "scripts/autodata_runtime_profile.sh"
    command = f'''
set -euo pipefail
export AAR_AUTODATA=1
export AAR_AUTODATA_PROFILE=target-aware-local-v1
export AAR_AUTODATA_CAMPAIGN_POLICY="{policy}"
export AAR_AUTODATA_GENERATOR_DEPLOYMENT=missing-kimi-deployment
source "{script}"
aar_set_autodata_runtime_profile
'''
    completed = subprocess.run(
        ["bash", "-c", command], check=False, capture_output=True, text=True
    )

    assert completed.returncode != 0
    assert "missing AutoData Kimi proxy contract" in completed.stderr


@pytest.mark.parametrize(
    ("protocol", "message"),
    [
        (None, "omitted generator protocol"),
        ("unknown_protocol", "unsupported AutoData generator protocol"),
    ],
)
def test_shell_profile_rejects_missing_or_unknown_protocol(
    tmp_path: Path, protocol: str | None, message: str
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_policy(protocol=protocol)))
    script = ROOT / "scripts/autodata_runtime_profile.sh"
    command = f'''
set -euo pipefail
export AAR_AUTODATA=1
export AAR_AUTODATA_PROFILE=target-aware-local-v1
export AAR_AUTODATA_CAMPAIGN_POLICY="{policy}"
source "{script}"
aar_set_autodata_runtime_profile
'''
    completed = subprocess.run(
        ["bash", "-c", command], check=False, capture_output=True, text=True
    )

    assert completed.returncode != 0
    assert message in completed.stderr


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
export AAR_AUTODATA_GENERATOR_PROTOCOL=openai_chat_completions
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
