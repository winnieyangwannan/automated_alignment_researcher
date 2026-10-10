from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from aar.autodata_capacity_profile import (
    apply_profile_to_args,
    load_capacity_profile,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_9"
    / "target_aware_capacity.yaml"
)


def test_capacity_profile_is_one_source_for_policy_and_task_defaults() -> None:
    profile = load_capacity_profile(PROFILE)
    target = {
        "AUTODATA_TARGET_ENABLED": "1",
        "AUTODATA_TARGET_URL": "http://target/v1",
        "AUTODATA_TARGET_MODEL": "gemma-4-31B-it",
        "AUTODATA_TARGET_DEPLOYMENT_ID": "target-deployment",
        "AUTODATA_TARGET_CHECKPOINT_HASH": "sha256:abc",
    }

    environment = profile.solve_environment(
        generator_url="http://generator/v1",
        generator_host_header="",
        generator_deployment_id="generator-deployment",
        target_environment=target,
    )
    args = apply_profile_to_args(
        argparse.Namespace(
            capacity_profile=PROFILE,
            environment="wrong",
            image="wrong",
            expected_image_id="wrong",
            generator_max_input_tokens=1,
            generator_max_output_tokens=1,
            generator_input_usd_per_million=None,
            generator_output_usd_per_million=None,
            judge_max_input_tokens=1,
            judge_max_output_tokens=1,
            judge_input_usd_per_million=None,
            judge_output_usd_per_million=None,
            target_max_input_tokens=1,
            target_max_output_tokens=1,
            model_request_max_attempts=1,
        )
    )

    assert profile.concurrency == 32
    assert profile.task_count == 32
    assert environment["AUTODATA_GENERATOR_MAX_INPUT"] == "4096"
    assert environment["AUTODATA_TARGET_MAX_INPUT"] == "8192"
    assert environment["AUTODATA_JUDGE_MAX_INPUT"] == "4096"
    assert args.generator_max_input_tokens == 4096
    assert args.target_max_input_tokens == 8192
    assert args.judge_max_input_tokens == 4096
    assert args.model_request_max_attempts == 3


def test_capacity_profile_rejects_target_model_drift() -> None:
    profile = load_capacity_profile(PROFILE)
    with pytest.raises(ValueError, match="target model"):
        profile.solve_environment(
            generator_url="http://generator/v1",
            generator_host_header="",
            generator_deployment_id="generator-deployment",
            target_environment={
                "AUTODATA_TARGET_ENABLED": "1",
                "AUTODATA_TARGET_MODEL": "wrong-model",
            },
        )


def test_capacity_profile_rejects_unknown_yaml_fields(tmp_path: Path) -> None:
    value = yaml.safe_load(PROFILE.read_text())
    value["load"]["unreviewed_setting"] = 1
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(yaml.safe_dump(value), encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected"):
        load_capacity_profile(invalid)
