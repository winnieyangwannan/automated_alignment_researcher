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


def test_run12_research_canary_can_continue_with_safe_memory() -> None:
    launcher = (RUN12 / "submit_research_canary.sh").read_text()

    assert 'AAR_RUN12_RESEARCH_MAX_ITERATIONS:-1' in launcher
    assert "AAR_RUN12_RECOVERED_AGENT_LOG_DIR" in launcher
    assert 'AAR_RUN10_RECOVERED_AGENT_LOG_DIR' in launcher


def test_run12_target_binding_accepts_a_newly_promoted_incumbent() -> None:
    launcher = (RUN12 / "submit_run_12.sh").read_text()

    assert "AAR_RUN12_INCUMBENT_RUN_ID" in launcher
    assert "AAR_RUN12_ADAPTER_CHECKPOINT" in launcher
    assert "AAR_RUN12_MERGED_CHECKPOINT" in launcher
    assert "AAR_RUN12_TARGET_ITERATION" in launcher
    assert '--iteration "${TARGET_ITERATION}"' in launcher


def test_run12_full_chain_rotates_the_training_contract_with_its_target() -> None:
    launcher = (RUN12 / "submit_run_12_full.sh").read_text()
    pipeline = (RUN12 / "run_12_full_pipeline.sbatch").read_text()
    controller = (RUN12 / "run_12_chain_controller.sbatch").read_text()

    contract = "autodata-training-data-contract.json"
    assert contract in launcher
    assert "aar.infrastructure.autodata_contract" in launcher
    assert "AAR_AUTODATA_TRAINING_DATA_CONTRACT" in pipeline
    assert contract in controller
    assert "aar.infrastructure.autodata_contract" in controller
    assert controller.index("create-policy") < controller.index(
        "aar.infrastructure.autodata_contract"
    ) < controller.index('job="$(submit_session)"')
