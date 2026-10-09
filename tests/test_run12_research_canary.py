from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN12 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_12"


def test_run12_research_canary_is_one_scored_kimi_iteration() -> None:
    launcher = (RUN12 / "submit_research_canary.sh").read_text()

    assert "AAR_EXPECTED_BRANCH=autodata" in launcher
    assert "AAR_KIMI_SERVE_DEPLOYMENT=aar_8-kimi26" in launcher
    assert "AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6" in launcher
    assert "AAR_KEEP_CHECKPOINTS=1" in launcher
    assert "run12-adapter-target/research_canary_attempts" in launcher
    assert 'submit_run_10.sh" canary' in launcher
