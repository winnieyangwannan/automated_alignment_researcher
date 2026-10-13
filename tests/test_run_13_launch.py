import subprocess
from pathlib import Path

from aar.autodata_run_config import load_run_config


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_13"


def test_trial14_runs_ten_iterations_with_full_coordinator_wiring() -> None:
    canary = RUN / "canary"
    trial = canary / "trial_14"
    config = load_run_config(trial / "autodata_run.yaml")

    assert config["run_id"] == "run13-canary-trial14"
    assert config["meta_optimization"] == {
        "maximum_iterations": 10,
        "minimum_iterations": 10,
        "early_stop_patience": 10,
        "tuning_tasks": 64,
        "validation_tasks": 32,
        "test_tasks": 32,
    }
    assert config["agent"] == {
        "backend": "claude",
        "model": "claude-opus-4-8",
        "effort": "max",
        "turn_timeout_seconds": 1800,
    }
    for path in (
        trial / "submit_canary.sh",
        canary / "launch" / "launch.sh",
        canary / "slurm" / "pipeline.sbatch",
        canary / "slurm" / "chain_controller.sbatch",
    ):
        subprocess.run(["bash", "-n", str(path)], check=True)
        assert "trial14" in path.read_text()
    launch = (canary / "launch" / "launch.sh").read_text()
    assert "trial13|trial14)" in launch
    assert launch.count("^trial(4|5|6|7|8|9|10|11|12|13|14)$") == 2


def test_run_13_submitter_is_isolated_and_selects_claude_opus_48() -> None:
    submitter = (RUN / "submit_run_13.sh").read_text()

    assert "AAR_AGENT_BACKEND=claude" in submitter
    assert "AAR_AGENT_MODEL=claude-opus-4-8" in submitter
    assert "run13-adapter-target" in submitter
    assert "winnieyangwn-run13-gemma4-cshc" in submitter
    assert "run13-adapter-target-canary" in submitter
    assert "aar_8-kimi26" in submitter
    assert "run12" not in submitter.lower()
    assert "AAR_RUN12" not in submitter


def test_run_13_jobs_use_run_13_namespace_and_expected_provider_order() -> None:
    preflight = (RUN / "run_13_endpoint_preflight.sbatch").read_text()
    canary = (RUN / "run_13_target_canary.sbatch").read_text()

    assert "AAR_RUN13_ROOT" in preflight
    assert "AAR_RUN13_TARGET_BINDING" in preflight
    assert '"research_backend": "claude"' in preflight
    assert '"research_model": "claude-opus-4-8"' in preflight
    assert "AAR_RUN13_ROOT" in canary
    assert "AAR_RUN13_TARGET_BINDING" in canary
    assert 'CANARY_PYTHONPATH="${AUTODATA}/src:${REPO}"' in canary
    deployment_argument = (
        '--generator-deployment-id "${AAR_RUN13_GENERATOR_DEPLOYMENT_ID:?}"'
    )
    assert deployment_argument in canary
    assert "--target-canary-id-prefix run13-adapter-target-canary" in canary
    assert '[\n    "generator", "target", "judge"\n]' in canary
    assert "run12" not in (preflight + canary).lower()


def test_research_canary_explicitly_launches_one_claude_opus_chain() -> None:
    submitter = (RUN / "submit_run_13_research_canary.sh").read_text()
    pipeline = (RUN / "run_13_research_canary.sbatch").read_text()

    assert "research_backend=claude" in submitter
    assert "research_model=claude-opus-4-8" in submitter
    assert "AAR_AGENT_BACKEND=claude" in pipeline
    assert "AAR_AGENT_MODEL=claude-opus-4-8" in pipeline
    assert 'launch_team.sh" canary "${MAX_ITERATIONS}" 17' in pipeline
    assert "AAR_KEEP_CHECKPOINTS=1" in pipeline
    assert "EVAL_INFERENCE_BACKEND=vllm" in pipeline
    assert "EVAL_VLLM_LORA_STRATEGY=merged_checkpoint" in pipeline
    assert 'AAR_RESEARCH_TOOL_DIR="${ATTEMPT_DIR}/research-tools"' in pipeline
    assert 'MAX_ITERATIONS="${AAR_RUN13_RESEARCH_MAX_ITERATIONS:-1}"' in submitter
    assert "AAR_RUN13_RECOVERED_AGENT_LOG_DIR" in submitter
    assert "### METHOD VALIDATION FOR THIS CONTINUATION" in submitter
    assert "Keep AAR_REQUIRE_METHOD_CONTRACT=1" in submitter
    assert 'metadata/recovered-agent-log' in submitter


def test_full_run_checkpoint_recovery_is_duplicate_safe_and_resumes_state() -> None:
    recovery_path = RUN / "resume_run_13_full.sh"
    recovery = recovery_path.read_text()
    readme = (RUN / "README.md").read_text()

    subprocess.run(["bash", "-n", str(recovery_path)], check=True)
    assert "/checkpoint/ram/${USER}/aar-runs/run13-full" in recovery
    assert "AAR_RUNTIME_ARTIFACT_ROOT" in recovery
    assert "refusing duplicate active jobs" in recovery
    assert "resolve_team" in recovery
    assert "metadata/children.tsv" in recovery
    assert "run_13_chain_controller.sbatch" in recovery
    assert "launch_eval_worker.sh" in recovery
    assert "checkpoint-resume-jobs.tsv" in recovery
    assert "--gateway-register --lifetime 7d --no-watch" in recovery
    assert (
        "/checkpoint/ram/winnieyangwn/aar-runs/run13-full/"
        "20261009T230106Z-4c7a5b059cf0"
    ) in readme


def test_future_full_run_uses_shared_optimized_autodata_profile() -> None:
    submitter = (RUN / "submit_run_13_full.sh").read_text()
    pipeline = (RUN / "run_13_full_pipeline.sbatch").read_text()
    controller = (RUN / "run_13_chain_controller.sbatch").read_text()

    assert "AAR_AUTODATA_PROFILE=target-aware-local-v1" in submitter
    assert "AAR_AUTODATA_GENERATOR_DEPLOYMENT" in submitter
    assert "AAR_KIMI_PROXY_INFO" in submitter
    assert "823c5948854df14664f3168bc5e6c49a2cecb975" in submitter
    assert "aar_set_autodata_runtime_profile" in pipeline
    assert "AAR_RUN13_AUTODATA_CONCURRENCY:-8" not in pipeline
    assert '--runtime-profile "${AAR_AUTODATA_PROFILE}"' in controller
