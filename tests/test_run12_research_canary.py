from pathlib import Path

import yaml


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

    assert "AAR_RUN12_RESEARCH_MAX_ITERATIONS:-1" in launcher
    assert "AAR_RUN12_RECOVERED_AGENT_LOG_DIR" in launcher
    assert "AAR_RUN10_RECOVERED_AGENT_LOG_DIR" in launcher


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
    compiler = (ROOT / "aar" / "autodata_run_config.py").read_text()

    contract = "autodata-training-data-contract.json"
    assert "aar.autodata_run_config compile" in launcher
    assert contract in compiler
    assert "training_data_contract_from_campaign_policy" in compiler
    assert 'source "${AAR_AUTODATA_RUNTIME_ENV}"' in pipeline
    assert "AAR_AUTODATA_TRAINING_DATA_CONTRACT" in compiler
    assert contract in controller
    assert "aar.autodata_run_config compile" in controller
    assert controller.index("aar.autodata_run_config compile") < controller.index(
        'job="$(submit_session)"'
    )


def test_only_bootstrap_canary_may_reuse_a_verified_base_deployment() -> None:
    launcher = (RUN12 / "submit_run_12_full.sh").read_text()

    assert "AAR_RUN12_REUSE_BASE_DEPLOYMENT" in launcher
    assert "full mode forbids reusing a canary base deployment" in launcher
    assert "base_deployment_reused=%s" in launcher


def test_run12_artifacts_default_to_checkpoint_storage() -> None:
    full = (RUN12 / "submit_run_12_full.sh").read_text()
    target = (RUN12 / "submit_run_12.sh").read_text()
    run_config = yaml.safe_load((RUN12 / "autodata_run.yaml").read_text())

    for launcher in (full, target):
        assert "AAR_RUN12_STORAGE_ROOT" in launcher
        assert "/checkpoint/ram/${USER" in launcher
        assert "Run 12 storage root must be" in launcher
    assert 'attempt="${RUN12_STORAGE_ROOT}/aar-runs/' in full
    assert 'checkpoint_root="${RUN12_STORAGE_ROOT}/aar-checkpoints/' in full
    assert run_config["storage"] == {
        "root": "/checkpoint/ram/{user}",
        "keep_checkpoints": False,
    }


def test_run12_operational_defaults_flow_from_autodata_yaml() -> None:
    run_config = yaml.safe_load((RUN12 / "autodata_run.yaml").read_text())
    launcher = (RUN12 / "submit_run_12_full.sh").read_text()
    pipeline = (RUN12 / "run_12_full_pipeline.sbatch").read_text()
    compiler = (ROOT / "aar" / "autodata_run_config.py").read_text()

    assert run_config["evaluation"] == {
        "memory": "max",
        "max_truncation_rate": 0.20,
    }
    assert run_config["agent"] == {
        "backend": "kimi",
        "turn_timeout_seconds": 300,
    }
    for name in (
        "AAR_RUN_STORAGE_ROOT",
        "AAR_KEEP_CHECKPOINTS",
        "AAR_EVAL_MEM",
        "EVAL_MAX_TRUNCATION_RATE",
        "AAR_AGENT_BACKEND",
        "AAR_KIMI_TURN_TIMEOUT_SECONDS",
    ):
        assert name in compiler
    assert "'.storage_root'" in launcher
    assert 'source "${AAR_AUTODATA_RUNTIME_ENV}"' in pipeline
    assert "compiled Run 12 storage root drifted" in pipeline
    assert '"${AAR_KEEP_CHECKPOINTS:?missing checkpoint policy}" = 0' in pipeline
    assert '"${AAR_TRAIN_EXIT_AFTER_SUBMIT:?missing decoupled training policy}" = 1' in pipeline


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
    run_config = yaml.safe_load((RUN12 / "autodata_run.yaml").read_text())
    profile = yaml.safe_load(
        (ROOT / "configs/autodata/target_aware_local_v1.yaml").read_text()
    )

    assert run_config["deployments"]["researcher_kimi"] == "aar_8-kimi26"
    assert run_config["deployments"]["generator_kimi"] == "autodata_8-kimi26"
    assert "researcher_kimi_deployment" in launcher
    assert "generator_kimi_deployment" in launcher
    assert 'AAR_KIMI_SERVE_DEPLOYMENT="${RESEARCHER_DEPLOYMENT}"' in launcher
    assert "resolve_autodata_plugin" in launcher
    assert "--coord-qos cpu_x86_lowest --proxy-qos cpu_x86_lowest" in launcher
    assert (
        "--coord-qos cpu_x86_lowest --proxy-qos cpu_x86_lowest"
        in (RUN12 / "run_12_chain_controller.sbatch").read_text()
    )
    assert "KIMI_MODEL_MAX_OUTPUT_SIZE=65536" in launcher
    assert "KIMI_MODEL_MAX_COMPLETION_TOKENS=65536" in launcher
    assert "KIMI_MODEL_MAX_CONTEXT_SIZE=262144" in pipeline
    assert "KIMI_MODEL_MAX_OUTPUT_SIZE=65536" in pipeline
    assert "KIMI_MODEL_MAX_COMPLETION_TOKENS=65536" in pipeline
    assert profile["providers"]["generator"]["max_input_tokens"] == 196608
    assert profile["providers"]["generator"]["max_output_tokens"] == 65536
    assert profile["providers"]["judge"]["max_input_tokens"] == 1000000
    assert profile["providers"]["judge"]["max_output_tokens"] == 65536
    assert "aar.autodata_run_config compile" in canary_submitter
    assert "--campaign-policy" in canary_job
