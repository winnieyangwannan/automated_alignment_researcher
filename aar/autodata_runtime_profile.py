"""Reusable, fail-closed runtime profiles for AAR AutoData generation."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


TARGET_AWARE_LOCAL_PROFILE = "target-aware-local-v1"
QUESTION_ONLY_LOCAL_PROFILE = "question-only-local-v1"


@dataclass(frozen=True, slots=True)
class AutoDataRuntimeProfile:
    name: str
    target_enabled: bool
    broker_runner: str
    environment: str
    concurrency: int
    model_request_max_attempts: int
    lifecycle_supervised: bool = True
    reuse_policy: str = "digest-verified"


_PROFILES = {
    TARGET_AWARE_LOCAL_PROFILE: AutoDataRuntimeProfile(
        name=TARGET_AWARE_LOCAL_PROFILE,
        target_enabled=True,
        broker_runner="local-bwrap",
        environment="oci-runner-firecracker-large",
        concurrency=32,
        model_request_max_attempts=3,
    ),
    QUESTION_ONLY_LOCAL_PROFILE: AutoDataRuntimeProfile(
        name=QUESTION_ONLY_LOCAL_PROFILE,
        target_enabled=False,
        broker_runner="local-bwrap",
        environment="oci-runner-firecracker-large",
        concurrency=64,
        model_request_max_attempts=1,
    ),
}


def runtime_profile(name: str) -> AutoDataRuntimeProfile:
    try:
        return _PROFILES[name]
    except KeyError as error:
        choices = ", ".join(sorted(_PROFILES))
        raise ValueError(
            f"unknown AutoData runtime profile {name!r}; choose {choices}"
        ) from error


def validate_campaign_policy(
    policy: Mapping[str, Any], profile: AutoDataRuntimeProfile
) -> None:
    if policy.get("runner") != profile.broker_runner:
        raise ValueError("campaign runner does not match the AutoData runtime profile")
    if policy.get("environment") != profile.environment:
        raise ValueError(
            "campaign environment does not match the AutoData runtime profile"
        )
    environment = policy.get("required_solve_env")
    if not isinstance(environment, dict):
        raise ValueError("campaign required_solve_env must be an object")
    expected_target = "1" if profile.target_enabled else "0"
    if environment.get("AUTODATA_TARGET_ENABLED") != expected_target:
        raise ValueError(
            "campaign target mode does not match the AutoData runtime profile"
        )
    expected_attempts = str(profile.model_request_max_attempts)
    if environment.get("AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS") != expected_attempts:
        raise ValueError(
            "campaign model-request attempts do not match the AutoData runtime profile"
        )


def validate_autodata_checkout(checkout: Path) -> None:
    root = checkout.expanduser().resolve(strict=True)
    required = (
        root / "src/autodata/broker/local_bwrap.py",
        root / "plugin/autodata/scripts/bootstrap.py",
        root / "schemas/autodata.execution.v1.schema.json",
    )
    for path in required:
        if not path.is_file():
            raise ValueError(
                f"AutoData checkout lacks required optimized feature: {path}"
            )
    schema = json.loads(required[-1].read_text(encoding="utf-8"))
    properties = schema.get("properties")
    if not isinstance(properties, dict) or "finalization" not in properties:
        raise ValueError("AutoData checkout lacks selective production finalization")
    bootstrap = required[1].read_text(encoding="utf-8")
    if "with_pip=False" not in bootstrap:
        raise ValueError("AutoData checkout lacks ensurepip-free plugin bootstrap")
    broker_cli = (root / "src/autodata/broker/cli.py").read_text(encoding="utf-8")
    if '"--database"' not in broker_cli:
        raise ValueError("AutoData checkout lacks node-local broker-ledger support")


def validate_runtime(
    *,
    profile_name: str,
    campaign_policy_path: Path,
    autodata_checkout: Path,
    kimi_proxy_info: Path | None,
    generator_deployment_id: str,
) -> dict[str, Any]:
    profile = runtime_profile(profile_name)
    policy = json.loads(campaign_policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ValueError("campaign policy must contain one JSON object")
    validate_campaign_policy(policy, profile)
    environment = policy["required_solve_env"]
    if environment.get("AUTODATA_GENERATOR_DEPLOYMENT_ID") != generator_deployment_id:
        raise ValueError(
            "campaign generator deployment does not match authenticated Kimi routing"
        )
    validate_autodata_checkout(autodata_checkout)
    if profile.broker_runner == "local-bwrap":
        if kimi_proxy_info is None or not kimi_proxy_info.is_file():
            raise ValueError("optimized local profile requires a Kimi proxy contract")
    return {
        "profile": profile.name,
        "broker_runner": profile.broker_runner,
        "concurrency": profile.concurrency,
        "lifecycle_supervised": profile.lifecycle_supervised,
        "model_request_max_attempts": profile.model_request_max_attempts,
        "reuse_policy": profile.reuse_policy,
        "target_enabled": profile.target_enabled,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--campaign-policy", required=True, type=Path)
    parser.add_argument("--autodata-checkout", required=True, type=Path)
    parser.add_argument("--kimi-proxy-info", type=Path)
    parser.add_argument("--generator-deployment-id", required=True)
    args = parser.parse_args()
    result = validate_runtime(
        profile_name=args.profile,
        campaign_policy_path=args.campaign_policy,
        autodata_checkout=args.autodata_checkout,
        kimi_proxy_info=args.kimi_proxy_info,
        generator_deployment_id=args.generator_deployment_id,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
