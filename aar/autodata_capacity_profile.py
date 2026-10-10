"""Validated YAML configuration for AutoData capacity canaries."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

import yaml


SCHEMA = "aar.autodata.capacity-profile/v1"


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise ValueError(f"{label} must be nonempty single-line text")
    return value


def _rate(value: Any, label: str) -> str:
    text = _text(value, label)
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"{label} must be a decimal") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{label} must be a finite non-negative decimal")
    return text


def _mapping(value: Any, label: str, expected: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    unexpected = set(value) - expected
    missing = expected - set(value)
    if unexpected or missing:
        raise ValueError(
            f"{label} keys differ; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    return value


@dataclass(frozen=True, slots=True)
class ProviderLimits:
    model: str
    max_input_tokens: int
    max_output_tokens: int
    timeout_seconds: int
    input_usd_per_million: str
    output_usd_per_million: str
    url: str | None = None

    @classmethod
    def from_mapping(
        cls, value: Any, label: str, *, require_url: bool = False
    ) -> "ProviderLimits":
        keys = {
            "model",
            "max_input_tokens",
            "max_output_tokens",
            "timeout_seconds",
            "input_usd_per_million",
            "output_usd_per_million",
        }
        if require_url:
            keys.add("url")
        data = _mapping(value, label, keys)
        return cls(
            model=_text(data["model"], f"{label}.model"),
            max_input_tokens=_positive_integer(
                data["max_input_tokens"], f"{label}.max_input_tokens"
            ),
            max_output_tokens=_positive_integer(
                data["max_output_tokens"], f"{label}.max_output_tokens"
            ),
            timeout_seconds=_positive_integer(
                data["timeout_seconds"], f"{label}.timeout_seconds"
            ),
            input_usd_per_million=_rate(
                data["input_usd_per_million"],
                f"{label}.input_usd_per_million",
            ),
            output_usd_per_million=_rate(
                data["output_usd_per_million"],
                f"{label}.output_usd_per_million",
            ),
            url=_text(data["url"], f"{label}.url") if require_url else None,
        )


@dataclass(frozen=True, slots=True)
class CapacityProfile:
    name: str
    target_enabled: bool
    runner: str
    environment: str
    image: str
    expected_image_id: str
    max_cpus: int
    max_memory_mb: int
    concurrency: int
    task_count: int
    model_request_max_attempts: int
    max_cost_usd: str
    generator: ProviderLimits
    judge: ProviderLimits
    target: ProviderLimits

    def solve_environment(
        self,
        *,
        generator_url: str,
        generator_host_header: str,
        generator_deployment_id: str,
        target_environment: Mapping[str, str] | None,
    ) -> dict[str, str]:
        if self.target_enabled != (target_environment is not None):
            raise ValueError("capacity profile target mode does not match target binding")
        if (
            target_environment is not None
            and target_environment.get("AUTODATA_TARGET_MODEL") != self.target.model
        ):
            raise ValueError("capacity profile target model does not match target binding")
        environment = {
            "AUTODATA_TARGET_ENABLED": "1" if self.target_enabled else "0",
            "AUTODATA_GENERATOR_URL": _text(generator_url, "generator URL").rstrip("/"),
            "AUTODATA_GENERATOR_MODEL": self.generator.model,
            "AUTODATA_GENERATOR_DEPLOYMENT_ID": _text(
                generator_deployment_id, "generator deployment id"
            ),
            "AUTODATA_GENERATOR_MAX_INPUT": str(self.generator.max_input_tokens),
            "AUTODATA_GENERATOR_MAX_OUTPUT": str(self.generator.max_output_tokens),
            "AUTODATA_GENERATOR_TIMEOUT": str(self.generator.timeout_seconds),
            "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": self.generator.input_usd_per_million,
            "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": self.generator.output_usd_per_million,
            "AUTODATA_JUDGE_URL": self.judge.url or "",
            "AUTODATA_JUDGE_MODEL": self.judge.model,
            "AUTODATA_JUDGE_MAX_INPUT": str(self.judge.max_input_tokens),
            "AUTODATA_JUDGE_MAX_OUTPUT": str(self.judge.max_output_tokens),
            "AUTODATA_JUDGE_TIMEOUT": str(self.judge.timeout_seconds),
            "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": self.judge.input_usd_per_million,
            "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": self.judge.output_usd_per_million,
            "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": str(
                self.model_request_max_attempts
            ),
        }
        if generator_host_header:
            environment["AUTODATA_GENERATOR_HOST_HEADER"] = _text(
                generator_host_header, "generator host header"
            )
        if target_environment is not None:
            environment.update(target_environment)
            environment.update(
                {
                    "AUTODATA_TARGET_MAX_INPUT": str(
                        self.target.max_input_tokens
                    ),
                    "AUTODATA_TARGET_MAX_OUTPUT": str(
                        self.target.max_output_tokens
                    ),
                    "AUTODATA_TARGET_TIMEOUT": str(self.target.timeout_seconds),
                    "AUTODATA_TARGET_INPUT_USD_PER_MILLION": self.target.input_usd_per_million,
                    "AUTODATA_TARGET_OUTPUT_USD_PER_MILLION": self.target.output_usd_per_million,
                }
            )
        return environment


def load_capacity_profile(path: Path) -> CapacityProfile:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _mapping(
        value,
        "capacity profile",
        {"schema", "name", "target_enabled", "broker", "load", "providers"},
    )
    if root["schema"] != SCHEMA:
        raise ValueError(f"unsupported capacity profile schema: {root['schema']!r}")
    if not isinstance(root["target_enabled"], bool):
        raise ValueError("target_enabled must be boolean")
    broker = _mapping(
        root["broker"],
        "broker",
        {
            "runner",
            "environment",
            "image",
            "expected_image_id",
            "max_cpus",
            "max_memory_mb",
        },
    )
    load = _mapping(
        root["load"],
        "load",
        {
            "concurrency",
            "task_count",
            "model_request_max_attempts",
            "max_cost_usd",
        },
    )
    providers = _mapping(
        root["providers"], "providers", {"generator", "judge", "target"}
    )
    concurrency = _positive_integer(load["concurrency"], "load.concurrency")
    task_count = _positive_integer(load["task_count"], "load.task_count")
    if task_count < concurrency:
        raise ValueError("load.task_count must be at least load.concurrency")
    if concurrency > 64 or task_count > 512:
        raise ValueError("capacity profile exceeds canary safety limits")
    attempts = _positive_integer(
        load["model_request_max_attempts"], "load.model_request_max_attempts"
    )
    if attempts > 5:
        raise ValueError("model request max attempts must be at most five")
    return CapacityProfile(
        name=_text(root["name"], "name"),
        target_enabled=root["target_enabled"],
        runner=_text(broker["runner"], "broker.runner"),
        environment=_text(broker["environment"], "broker.environment"),
        image=_text(broker["image"], "broker.image"),
        expected_image_id=_text(
            broker["expected_image_id"], "broker.expected_image_id"
        ),
        max_cpus=_positive_integer(broker["max_cpus"], "broker.max_cpus"),
        max_memory_mb=_positive_integer(
            broker["max_memory_mb"], "broker.max_memory_mb"
        ),
        concurrency=concurrency,
        task_count=task_count,
        model_request_max_attempts=attempts,
        max_cost_usd=_rate(load["max_cost_usd"], "load.max_cost_usd"),
        generator=ProviderLimits.from_mapping(providers["generator"], "generator"),
        judge=ProviderLimits.from_mapping(
            providers["judge"], "judge", require_url=True
        ),
        target=ProviderLimits.from_mapping(providers["target"], "target"),
    )


def apply_profile_to_args(args: argparse.Namespace) -> argparse.Namespace:
    path = getattr(args, "capacity_profile", None)
    if path is None:
        return args
    profile = load_capacity_profile(path)
    values = vars(args).copy()
    values.update(
        {
            "environment": profile.environment,
            "image": profile.image,
            "expected_image_id": profile.expected_image_id,
            "generator_max_input_tokens": profile.generator.max_input_tokens,
            "generator_max_output_tokens": profile.generator.max_output_tokens,
            "generator_input_usd_per_million": Decimal(
                profile.generator.input_usd_per_million
            ),
            "generator_output_usd_per_million": Decimal(
                profile.generator.output_usd_per_million
            ),
            "judge_max_input_tokens": profile.judge.max_input_tokens,
            "judge_max_output_tokens": profile.judge.max_output_tokens,
            "judge_input_usd_per_million": Decimal(
                profile.judge.input_usd_per_million
            ),
            "judge_output_usd_per_million": Decimal(
                profile.judge.output_usd_per_million
            ),
            "target_max_input_tokens": profile.target.max_input_tokens,
            "target_max_output_tokens": profile.target.max_output_tokens,
            "model_request_max_attempts": profile.model_request_max_attempts,
        }
    )
    return argparse.Namespace(**values)


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    values = subparsers.add_parser("values")
    values.add_argument("--profile", required=True, type=Path)
    policy = subparsers.add_parser("render-policy")
    policy.add_argument("--profile", required=True, type=Path)
    policy.add_argument("--campaign-id", required=True)
    policy.add_argument("--generator-url", required=True)
    policy.add_argument("--generator-host-header", default="")
    policy.add_argument("--generator-deployment-id", required=True)
    policy.add_argument("--target-binding", required=True, type=Path)
    policy.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    profile = load_capacity_profile(args.profile)
    if args.command == "values":
        for value in (
            profile.runner,
            profile.environment,
            profile.concurrency,
            profile.task_count,
            profile.model_request_max_attempts,
        ):
            print(value)
        return 0

    from aar.autodata_target_binding import load_binding

    target = load_binding(args.target_binding)
    required = profile.solve_environment(
        generator_url=args.generator_url,
        generator_host_header=args.generator_host_header,
        generator_deployment_id=args.generator_deployment_id,
        target_environment=target.solve_environment(),
    )
    payload = {
        "schema": "autodata.broker-campaign-policy/v1",
        "campaign_id": args.campaign_id,
        "max_cost_usd": profile.max_cost_usd,
        "runner": profile.runner,
        "environment": profile.environment,
        "image": profile.image,
        "expected_image_id": profile.expected_image_id,
        "max_cpus": profile.max_cpus,
        "max_memory_mb": profile.max_memory_mb,
        "required_solve_env": required,
    }
    atomic_write_json(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
