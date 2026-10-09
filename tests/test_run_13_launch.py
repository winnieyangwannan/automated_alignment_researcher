from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_13"


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
