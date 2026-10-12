from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANARY = ROOT / "experiments/dishonest_sycophancy_concealing/run_13/canary"
RUN_CONFIG = CANARY / "trial_3/autodata_run.yaml"
PROFILE = (
    ROOT
    / "configs/autodata/target_aware_model_api_claude_opus_4_8_c8_v1.yaml"
)
AUTODATA_SHA = "51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1"


def test_run13_canary_configuration_is_bounded_to_training_smoke() -> None:
    run = yaml.safe_load(RUN_CONFIG.read_text())
    profile = yaml.safe_load(PROFILE.read_text())

    assert run["run_id"] == "run13-canary-trial3"
    assert run["runtime_profile"] == str(PROFILE.relative_to(ROOT))
    assert run["chains"] == ["alpha"]
    assert run["target_pairs_per_chain"] == 1
    assert run["bootstrap_canary"] == {"stop_after": "training_smoke"}
    assert run["agent"] == {
        "backend": "claude",
        "model": "claude-opus-4-8",
        "effort": "max",
        "turn_timeout_seconds": 1800,
    }
    assert profile["execution"]["concurrency_per_chain"] == 8
    assert profile["execution"]["model_request_max_attempts"] == 3
    assert profile["providers"]["generator"]["protocol"] == "model_api_responses"
    assert profile["providers"]["generator"]["model"] == "claude-4-8-opus"
    assert profile["providers"]["judge"]["model"] == "gpt-5-6-luna"
    assert profile["providers"]["target"]["model"] == "gemma-4-31B-it"


def test_run13_owns_a_fail_closed_launcher_and_slurm_payloads() -> None:
    wrapper_path = CANARY / "trial_3/submit_canary.sh"
    launcher_path = CANARY / "launch/launch.sh"
    pipeline_path = CANARY / "slurm/pipeline.sbatch"
    controller_path = CANARY / "slurm/chain_controller.sbatch"
    launcher = launcher_path.read_text()
    pipeline = pipeline_path.read_text()
    controller = controller_path.read_text()
    wrapper = wrapper_path.read_text()

    assert f"REQUIRED_AUTODATA_SHA={AUTODATA_SHA}" in launcher
    assert "RUN_MODE=bootstrap-canary" in launcher
    assert "AAR_AUTODATA_STOP_AFTER=training_smoke" in launcher
    assert "Run 13 canary requires exactly the alpha chain" in launcher
    assert "Run 13 concurrency must be 8" in launcher
    assert "Run 13 model requests must allow three attempts" in launcher
    assert "AAR_RUN13_TRIAL_CONFIG" in launcher
    assert "trial_([1-9][0-9]*)/autodata_run" in launcher
    assert '${EXPERIMENT_RUN_ID}-${TRIAL_ID}-bootstrap-canary' in launcher
    assert "run13-${TRIAL_ID}-${SEED}-iteration-${next_iteration}" in controller
    assert 'AAR_RUN13_TRIAL_CONFIG="${SCRIPT_DIR}/autodata_run.yaml"' in wrapper
    assert 'exec "${CANARY_DIR}/launch/launch.sh"' in wrapper
    assert "run_12/launch/submit_full.sh" not in launcher
    assert "run17" not in launcher
    assert "permits only bootstrap-canary mode" in pipeline
    assert "must stop after training_smoke" in pipeline
    assert "must stop after training_smoke" in controller
    assert "run_12/slurm" not in pipeline
    assert launcher_path.stat().st_mode & 0o111
    assert pipeline_path.stat().st_mode & 0o111
    assert controller_path.stat().st_mode & 0o111
    assert wrapper_path.stat().st_mode & 0o111


def test_run13_documentation_records_trials_and_pin() -> None:
    readme = (CANARY / "README.md").read_text()
    progress = (CANARY / "PROGRESS.md").read_text()

    for heading in (
        "## Goal",
        "## Context",
        "## Launch",
        "## Pass criteria",
        "## Stop criteria",
    ):
        assert heading in readme
    assert AUTODATA_SHA in readme
    assert "does not invoke the Run 12 launcher" in " ".join(readme.split())
    assert "20261012T060647Z-67ab7629e12e" in progress
    assert "Trial 1 stopped" in progress
    assert "Protocol-aware Trial 2 prepared" in progress
    assert "Config-driven Trial 3 prepared" in progress
    assert "trial_3/submit_canary.sh" in readme
    assert "Direct root-launcher use is rejected" in (CANARY / "trial_3/README.md").read_text()


def test_trial5_enables_analysis_mutation_and_lifecycle_ownership() -> None:
    launcher = (ROOT / "scripts/launch_team.sh").read_text()
    runtime = (ROOT / "scripts/aar_runtime_env.sh").read_text()

    trial5 = launcher.split(
        'if [ "${AAR_RUN13_TRIAL_ID}" = trial5 ]; then', 1
    )[1].split("fi", 1)[0]
    assert "export AAR_AUTODATA_ANALYSIS_COORDINATOR=1" in trial5
    assert "export AAR_AUTODATA_MUTATION_COORDINATOR=1" in trial5
    assert "export AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE=1" in trial5
    assert "AAR_AUTODATA_MUTATION_COORDINATOR" in runtime
