from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_RUN = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_13/canary/trial_14/autodata_run.yaml"
)
CANDIDATE_DIR = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_14/canary/opus5_autodata_comparison"
)
CANDIDATE_RUN = CANDIDATE_DIR / "config/run.yaml"
REFERENCE_PROFILE = (
    ROOT / "configs/autodata/target_aware_model_api_claude_opus_4_8_c8_v1.yaml"
)
CANDIDATE_PROFILE = (
    ROOT / "configs/autodata/target_aware_model_api_claude_opus_5_c8_v1.yaml"
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _leaf_differences(reference: object, candidate: object, path: str = "") -> set[str]:
    if isinstance(reference, dict) and isinstance(candidate, dict):
        assert reference.keys() == candidate.keys(), path or "<root>"
        differences: set[str] = set()
        for key in reference:
            child = f"{path}.{key}" if path else str(key)
            differences.update(_leaf_differences(reference[key], candidate[key], child))
        return differences
    if isinstance(reference, list) and isinstance(candidate, list):
        assert len(reference) == len(candidate), path
        differences: set[str] = set()
        for index, (reference_item, candidate_item) in enumerate(
            zip(reference, candidate, strict=True)
        ):
            differences.update(
                _leaf_differences(reference_item, candidate_item, f"{path}[{index}]")
            )
        return differences
    return {path} if reference != candidate else set()


def test_run14_changes_only_models_and_isolated_identity() -> None:
    assert _leaf_differences(_load(REFERENCE_RUN), _load(CANDIDATE_RUN)) == {
        "agent.model",
        "deployments.generator",
        "deployments.researcher",
        "run_id",
        "runtime_profile",
    }


def test_opus5_profile_changes_only_profile_and_generator_model() -> None:
    assert _leaf_differences(_load(REFERENCE_PROFILE), _load(CANDIDATE_PROFILE)) == {
        "name",
        "providers.generator.model",
    }


def test_opus5_model_role_contract() -> None:
    run = _load(CANDIDATE_RUN)
    profile = _load(CANDIDATE_PROFILE)

    assert run["agent"] == {
        "backend": "claude",
        "model": "claude-opus-5",
        "effort": "max",
        "turn_timeout_seconds": 1800,
    }
    assert run["deployments"] == {
        "researcher": "meta-claude-cli-opus-5",
        "generator": "meta-model-api-claude-5-opus",
    }
    assert profile["providers"]["generator"]["protocol"] == "model_api_responses"
    assert profile["providers"]["generator"]["model"] == "claude-5-opus"
    assert profile["providers"]["judge"]["model"] == "gpt-5-6-luna"
    assert profile["providers"]["target"]["model"] == "gemma-4-31B-it"


def test_run14_readmes_have_required_sections_and_no_fake_launch_command() -> None:
    readmes = [
        ROOT / "experiments/dishonest_sycophancy_concealing/run_14/README.md",
        ROOT / "experiments/dishonest_sycophancy_concealing/run_14/canary/README.md",
        CANDIDATE_DIR / "README.md",
    ]
    required = {"## Goal", "## Context", "## Launch", "## Pass criteria", "## Stop criteria"}

    for readme in readmes:
        text = readme.read_text(encoding="utf-8")
        headings = {line for line in text.splitlines() if line.startswith("## ")}
        assert required <= headings
        assert "not launchable" in text.lower()

    assert not (CANDIDATE_DIR / "launch").exists()
