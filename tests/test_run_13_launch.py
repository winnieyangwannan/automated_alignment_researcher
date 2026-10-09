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
    assert '[\n    "generator", "target", "judge"\n]' in canary
    assert "run12" not in (preflight + canary).lower()
