from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUN12 = ROOT / "experiments/dishonest_sycophancy_concealing/run_12"
RUN17 = ROOT / "experiments/dishonest_sycophancy_concealing/run_17"
RUN17_CANARY = RUN17 / "canary/canary_2"
RUN12_CONFIG = RUN12 / "canary/canary_2/trial_12/autodata_run.yaml"
RUN17_CONFIG = RUN17 / "config/run.yaml"
RUN12_PROFILE = ROOT / "configs/autodata/target_aware_local_c32_v1.yaml"
RUN17_PROFILE = (
    ROOT / "configs/autodata/target_aware_model_api_claude_opus_4_8_c32_v1.yaml"
)


def test_run17_changes_only_the_two_requested_model_paths() -> None:
    run12 = yaml.safe_load(RUN12_CONFIG.read_text())
    run17 = yaml.safe_load(RUN17_CONFIG.read_text())

    unchanged = {
        key: value
        for key, value in run12.items()
        if key not in {"run_id", "runtime_profile", "deployments", "agent"}
    }
    assert {
        key: value
        for key, value in run17.items()
        if key not in {"run_id", "runtime_profile", "deployments", "agent"}
    } == unchanged
    assert run17["run_id"] == "run17-canary2"
    assert run17["deployments"] == {
        "researcher": "meta-claude-cli-opus-4-8",
        "generator": "meta-model-api-claude-4-8-opus",
    }
    assert run17["agent"] == {
        "backend": "claude",
        "model": "claude-opus-4-8",
        "effort": "max",
        "turn_timeout_seconds": 1800,
    }


def test_run17_profile_changes_only_the_generator_route() -> None:
    run12 = yaml.safe_load(RUN12_PROFILE.read_text())
    run17 = yaml.safe_load(RUN17_PROFILE.read_text())

    assert run17["target"] == run12["target"]
    assert run17["broker"] == run12["broker"]
    assert run17["execution"] == run12["execution"]
    assert run17["providers"]["judge"] == run12["providers"]["judge"]
    assert run17["providers"]["target"] == run12["providers"]["target"]
    expected_generator = {
        **run12["providers"]["generator"],
        "protocol": "model_api_responses",
        "url": "https://api.meta.ai/v1/responses",
        "host_header": "",
        "model": "claude-4-8-opus",
    }
    assert run17["providers"]["generator"] == expected_generator


def test_run17_has_proof_and_launch_entrypoints() -> None:
    proof = (RUN17_CANARY / "launch/prepare_proof.sh").read_text()
    launch = (RUN17_CANARY / "launch/launch.sh").read_text()
    shared = (RUN12 / "launch/submit_full.sh").read_text()

    assert "AAR_EXPERIMENT_RUN_ID=run17" in proof
    assert "target_aware_model_api_claude_opus_4_8_c32_v1.yaml" in proof
    assert "judge-repair-28a9c22" in proof
    assert "28a9c22125dc0cf101ebabc1b22408b4e974678a" in proof
    assert "AAR_EXPERIMENT_RUN_ID=run17" in launch
    assert "AAR_RUN17_CANARY_ROOT" in launch
    assert "AAR_RUN12_MODE=bootstrap-canary" in launch
    assert "EXPERIMENT_RUN_ID" in shared
    assert "GENERATOR_PROTOCOL" in shared
    assert "unset AAR_KIMI_PROXY_INFO" in shared
    assert "claude_research_preflight.json" in shared
    assert (RUN17_CANARY / "launch/prepare_proof.sh").stat().st_mode & 0o111
    assert (RUN17_CANARY / "launch/launch.sh").stat().st_mode & 0o111


def test_run17_documentation_records_required_contract_and_unlaunched_state() -> None:
    for path in (RUN17 / "README.md", RUN17_CANARY / "README.md"):
        document = path.read_text()
        for heading in (
            "## Goal",
            "## Context",
            "## Launch",
            "## Pass criteria",
            "## Stop criteria",
        ):
            assert heading in document
        for identity in (
            "claude-opus-4-8",
            "claude-4-8-opus",
            "gemma-4-31B-it",
            "gpt-5-6-luna",
        ):
            assert identity in document

    progress = (RUN17_CANARY / "PROGRESS.md").read_text()
    assert "No jobs or attempts exist" in progress
    assert "Explicit model/config confirmation" in progress
