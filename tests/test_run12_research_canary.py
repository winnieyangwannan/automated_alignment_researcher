from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN12 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_12"


def test_run12_research_canary_is_one_scored_kimi_iteration() -> None:
    launcher = (RUN12 / "submit_research_canary.sh").read_text()

    assert "AAR_EXPECTED_BRANCH=autodata" in launcher
    assert "AAR_KIMI_SERVE_DEPLOYMENT=aar_8-kimi26" in launcher
    assert "AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6" in launcher
    assert "AAR_KEEP_CHECKPOINTS=1" in launcher
    assert "/checkpoint/ram/${USER:?}/aar-runs/" in launcher
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


def test_only_bootstrap_canary_may_reuse_a_verified_base_deployment() -> None:
    launcher = (RUN12 / "submit_run_12_full.sh").read_text()

    assert "AAR_RUN12_REUSE_BASE_DEPLOYMENT" in launcher
    assert "full mode forbids reusing a canary base deployment" in launcher
    assert "base_deployment_reused=%s" in launcher


def test_run12_artifacts_default_to_checkpoint_storage() -> None:
    full = (RUN12 / "submit_run_12_full.sh").read_text()
    target = (RUN12 / "submit_run_12.sh").read_text()

    for launcher in (full, target):
        assert "AAR_RUN12_STORAGE_ROOT" in launcher
        assert "/checkpoint/ram/${USER" in launcher
        assert "Run 12 storage root must be" in launcher
    assert 'attempt="${RUN12_STORAGE_ROOT}/aar-runs/' in full
    assert 'checkpoint_root="${RUN12_STORAGE_ROOT}/aar-checkpoints/' in full


def test_run12_deferred_launch_waits_for_a_working_gateway_route() -> None:
    gate = (RUN12 / "run_12_gateway_deferred_launch.sbatch").read_text()

    assert 'STORAGE_ROOT="${AAR_RUN12_STORAGE_ROOT:-/checkpoint/ram/${USER:?}}"' in gate
    assert '"${STORAGE_ROOT}" = "/checkpoint/ram/${USER}"' in gate
    assert 'GENERATOR_DEPLOYMENT="autodata_8-kimi26"' in gate
    assert 'GENERATOR_MODEL="Kimi-K2.6"' in gate
    assert '"enable_thinking":false' in gate
    assert '"${INGRESS}/health"' in gate
    assert '"${INGRESS}/status"' in gate
    assert '"${INGRESS}/v1/models"' in gate
    assert '"${INGRESS}/v1/chat/completions"' in gate
    assert "submit_run_12_full.sh" in gate


def test_run12_uses_separate_kimi_deployments_and_maximum_token_allowances() -> None:
    launcher = (RUN12 / "submit_run_12_full.sh").read_text()
    pipeline = (RUN12 / "run_12_full_pipeline.sbatch").read_text()
    canary_submitter = (RUN12 / "submit_run_12.sh").read_text()
    canary_job = (RUN12 / "run_12_target_canary.sbatch").read_text()

    assert "RESEARCHER_DEPLOYMENT=aar_8-kimi26" in launcher
    assert "GENERATOR_DEPLOYMENT=autodata_8-kimi26" in launcher
    assert 'AAR_KIMI_SERVE_DEPLOYMENT="${RESEARCHER_DEPLOYMENT}"' in launcher
    assert "KIMI_MODEL_MAX_OUTPUT_SIZE=65536" in launcher
    assert "KIMI_MODEL_MAX_COMPLETION_TOKENS=65536" in launcher
    assert "KIMI_MODEL_MAX_CONTEXT_SIZE=262144" in pipeline
    assert "KIMI_MODEL_MAX_OUTPUT_SIZE=65536" in pipeline
    assert "KIMI_MODEL_MAX_COMPLETION_TOKENS=65536" in pipeline
    assert '"AUTODATA_GENERATOR_MAX_INPUT": "196608"' in canary_submitter
    assert '"AUTODATA_GENERATOR_MAX_OUTPUT": "65536"' in canary_submitter
    assert '"AUTODATA_JUDGE_MAX_INPUT": "1000000"' in canary_submitter
    assert '"AUTODATA_JUDGE_MAX_OUTPUT": "65536"' in canary_submitter
    assert "--generator-max-output-tokens 65536" in canary_job
    assert "--judge-max-output-tokens 65536" in canary_job
