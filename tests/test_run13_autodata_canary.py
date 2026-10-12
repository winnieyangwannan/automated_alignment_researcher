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


def test_trial5_through_trial8_enable_full_lifecycle_ownership() -> None:
    launcher = (ROOT / "scripts/launch_team.sh").read_text()
    runtime = (ROOT / "scripts/aar_runtime_env.sh").read_text()

    owned_trials = launcher.split(
        'if [[ "${AAR_RUN13_TRIAL_ID}" =~ ^trial(5|6|7|8)$ ]]; then', 1
    )[1].split("fi", 1)[0]
    assert "export AAR_AUTODATA_ANALYSIS_COORDINATOR=1" in owned_trials
    assert "export AAR_AUTODATA_MUTATION_COORDINATOR=1" in owned_trials
    assert "export AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR=1" in owned_trials
    assert "export AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE=1" in owned_trials
    assert "AAR_AUTODATA_MUTATION_COORDINATOR" in runtime
    assert "AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR" in runtime
    assert 'if [[ "${AAR_RUN13_TRIAL_ID}" =~ ^trial(7|8)$ ]]; then' in launcher
    assert "export AAR_AUTODATA_GROUNDING_COORDINATOR=1" in launcher
    assert "export AAR_AUTODATA_PIPELINE_COORDINATOR=1" in launcher
    assert "author_pipeline coordinator enablement must come from" in launcher
    assert "AAR_AUTODATA_PIPELINE_COORDINATOR" in runtime
    assert "AAR_AUTODATA_GROUNDING_COORDINATOR" in runtime


def test_trial7_and_trial8_are_confirm_only_and_explicitly_allowlisted() -> None:
    trial = CANARY / "trial_8"
    run = yaml.safe_load((trial / "autodata_run.yaml").read_text())
    wrapper = (trial / "submit_canary.sh").read_text()
    launcher = (CANARY / "launch/launch.sh").read_text()
    pipeline = (CANARY / "slurm/pipeline.sbatch").read_text()
    controller = (CANARY / "slurm/chain_controller.sbatch").read_text()

    assert run["run_id"] == "run13-canary-trial8"
    assert run["bootstrap_canary"] == {"stop_after": "training_smoke"}
    assert run["agent"]["backend"] == "claude"
    assert run["agent"]["model"] == "claude-opus-4-8"
    assert "trial4|trial5|trial6|trial7|trial8)" in launcher
    assert "trial4|trial5|trial6|trial7|trial8)" in pipeline
    assert "AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT" in wrapper
    assert "confirm-only" in (trial / "README.md").read_text()
    retry_envelope = controller.split('case "${TRIAL_ID}" in', 1)[1].split(
        'for name in "${AAR_RESEARCH_CHAIN_ENV_ALLOWLIST[@]}"', 1
    )[0]
    for assignment in (
        "export AAR_AUTODATA_CLARIFY_COORDINATOR=1",
        "export AAR_AUTODATA_GROUNDING_COORDINATOR=1",
        "export AAR_AUTODATA_PIPELINE_COORDINATOR=1",
        "export AAR_AUTODATA_ANALYSIS_COORDINATOR=1",
        "export AAR_AUTODATA_MUTATION_COORDINATOR=1",
        "export AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR=1",
        "export AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE=1",
        "export AAR_AUTODATA_SEMANTIC_WORKER=claude",
    ):
        assert assignment in retry_envelope
