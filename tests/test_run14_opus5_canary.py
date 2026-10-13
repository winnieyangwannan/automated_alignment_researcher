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
GATE_LAUNCHER = CANDIDATE_DIR / "launch/launch.sh"
PROOF_LAUNCHER = CANDIDATE_DIR / "launch/prepare_proof.sh"
SHARED_LAUNCHER = (
    ROOT / "experiments/dishonest_sycophancy_concealing/run_14/canary/launch/launch.sh"
)
PIPELINE = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_14/canary/slurm/pipeline.sbatch"
)
CONTROLLER = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_14/canary/slurm/chain_controller.sbatch"
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


def test_run14_readmes_have_required_sections() -> None:
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


def test_run14_has_a_thin_executable_gate_launcher() -> None:
    launcher = GATE_LAUNCHER.read_text(encoding="utf-8")

    assert GATE_LAUNCHER.stat().st_mode & 0o111
    assert "AAR_RUN14_LIFECYCLE_COORDINATOR_COMMIT" in launcher
    assert "AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST" in launcher
    assert 'AAR_RUN14_CANARY_CONFIG="${GATE_DIR}/config/run.yaml"' in launcher
    assert 'exec "${CANARY_DIR}/launch/launch.sh" "$@"' in launcher


def test_run14_has_an_exact_provider_proof_launcher() -> None:
    launcher = PROOF_LAUNCHER.read_text(encoding="utf-8")
    shared = (
        ROOT
        / "experiments/dishonest_sycophancy_concealing/run_12/canary/canary_1/submit_target_canary.sh"
    ).read_text(encoding="utf-8")

    assert PROOF_LAUNCHER.stat().st_mode & 0o111
    assert "AAR_EXPERIMENT_RUN_ID=run14" in launcher
    assert "target_aware_model_api_claude_opus_5_c8_v1.yaml" in launcher
    assert "f53bc2136905461ffdbba0a203a12e351e184aaf" in launcher
    assert "AAR_RUN14_REUSE_BASE_DEPLOYMENT" in launcher
    assert 'run12|run14|run17' in shared


def test_run14_shared_launcher_enforces_opus5_contract() -> None:
    launcher = SHARED_LAUNCHER.read_text(encoding="utf-8")

    assert SHARED_LAUNCHER.stat().st_mode & 0o111
    assert "run14-canary-opus5-autodata-comparison" in launcher
    assert "target_aware_model_api_claude_opus_5_c8_v1.yaml" in launcher
    assert '[ "${AGENT_MODEL}" = claude-opus-5 ]' in launcher
    assert '[ "${RESEARCHER_DEPLOYMENT}" = meta-claude-cli-opus-5 ]' in launcher
    assert '[ "${GENERATOR_MODEL}" = claude-5-opus ]' in launcher
    assert (
        '[ "${GENERATOR_DEPLOYMENT}" = meta-model-api-claude-5-opus ]'
        in launcher
    )
    assert "--target-experiment-run-id run14" in launcher
    assert "prepare_run14_preautodata_recovery.py" not in launcher
    assert "claude-opus-4-8" not in launcher
    assert "claude-4-8-opus" not in launcher


def test_run14_slurm_payloads_are_isolated_and_fail_closed() -> None:
    pipeline = PIPELINE.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")
    combined = pipeline + controller

    assert '[ "${AAR_EXPERIMENT_RUN_ID:?missing experiment identity}" = run14 ]' in combined
    assert "AAR_RUN14_CANARY_ID" in pipeline
    assert "AAR_RUN14_CANARY_ID" in controller
    assert "opus5-autodata-comparison" in pipeline
    assert "opus5-autodata-comparison" in controller
    assert "AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST" in pipeline
    assert "run14-${TRIAL_ID}-${seed}-iteration-1" in pipeline
    assert "run14-${TRIAL_ID}-${SEED}-iteration-${next_iteration}" in controller
    assert "claude-opus-5" in pipeline
    assert "run_14/canary/slurm/chain_controller.sbatch" in pipeline
    assert "run13" not in combined.lower()


def test_shared_recovery_path_explicitly_allowlists_run14() -> None:
    launch_team = (ROOT / "scripts/launch_team.sh").read_text(encoding="utf-8")
    runtime = (ROOT / "scripts/aar_runtime_env.sh").read_text(encoding="utf-8")

    assert "AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST" in launch_team
    assert "AAR_RUN14_TRIAL_ID" in launch_team
    assert "AAR_RUN14_CANARY_ID" in launch_team
    assert '--target-experiment-run-id "${_recovery_target_run}"' in launch_team
    assert "AAR_RUN14_TRIAL_ID AAR_RUN14_CANARY_ID" in runtime
