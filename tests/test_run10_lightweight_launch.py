"""Contracts for Run 10's bounded one-chain lifecycle check."""

import json
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUN10 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_10"
LIFECYCLE = RUN10 / "canary" / "one_chain_lifecycle_check"


def test_run10_uses_responsibility_based_directory_layout() -> None:
    expected = {
        "analysis",
        "canary",
        "config",
        "launch",
        "recovery",
        "runtime",
        "slurm",
    }
    assert expected <= {path.name for path in RUN10.iterdir() if path.is_dir()}
    assert (RUN10 / "launch" / "submit_run_10.sh").is_file()
    assert (RUN10 / "slurm" / "run_10_pipeline.sbatch").is_file()
    assert (RUN10 / "config" / "run.yaml").is_file()


def test_smoke_mode_uses_one_chain_and_no_evaluator() -> None:
    pipeline = (
        (RUN10 / "config" / "configure_run_10_environment.sh").read_text()
        + (RUN10 / "slurm" / "run_10_pipeline.sbatch").read_text()
    )
    submitter = (RUN10 / "launch" / "submit_run_10.sh").read_text()

    assert "smoke|canary|full" in submitter
    assert 'RUN10_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"' in submitter
    assert '${RUN10_DIR}/config/run.yaml' in submitter
    assert '${RUN10_DIR}/slurm/run_10_pipeline.sbatch' in submitter
    assert 'AAR_START_EVAL_WORKER=0' in pipeline
    assert 'AAR_EVAL_WORKERS=0' in pipeline
    assert 'AAR_METHOD_SMOKE="${AAR_METHOD_SMOKE:-1}"' in pipeline
    assert 'AAR_REQUIRE_METHOD_SMOKE=1' in pipeline
    assert 'AAR_TRAIN_TIME="${AAR_TRAIN_TIME:-00:15:00}"' in pipeline
    assert 'expected_evaluators=0' in pipeline


def test_lifecycle_canary_has_a_thin_launcher_and_own_config() -> None:
    launcher = (LIFECYCLE / "launch.sh").read_text()

    assert 'AAR_RUN_CONFIG="${SCRIPT_DIR}/run.yaml"' in launcher
    assert 'exec "${RUN10_DIR}/launch/submit_run_10.sh" smoke' in launcher
    assert "sbatch" not in launcher


def test_training_smoke_validates_real_peft_adapter_without_submission() -> None:
    trainer = (ROOT / "scripts" / "slurm_train_submit.sh").read_text()

    assert 'config_kwargs["smoke_run"] = True' in trainer
    assert "PeftConfig.from_pretrained(model_path)" in trainer
    assert "validate_model_submission(out[\"model_path\"])" in trainer
    assert '"adapter_model.safetensors"' in trainer
    assert 'method_smoke' in trainer
    assert 'if [ "${AAR_METHOD_SMOKE:-0}" = "1" ]; then' in trainer
    assert 'pretrain_smoke = "${AAR_PRETRAIN_SMOKE:-0}"' in trainer
    assert 'phase("train.preflight_smoke")' in trainer
    assert "per-method one-step GPU preflight passed" in trainer


def test_training_failure_handoff_contains_safe_actionable_context() -> None:
    trainer = (ROOT / "scripts" / "slurm_train_submit.sh").read_text()

    assert "install_uncaught_exception_failure_hook" in trainer
    assert "training_python_exception" in trainer
    assert "training_process_failed" in trainer
    assert "AAR_TRAIN_LOG_PATH" in trainer


def test_evaluator_is_launched_only_after_method_smoke_passes() -> None:
    pipeline = (RUN10 / "slurm" / "run_10_pipeline.sbatch").read_text()
    verifier = (RUN10 / "canary" / "verify_run_10_canary.py").read_text()

    smoke_wait = pipeline.index("monitor_method_smoke.py")
    evaluator_launch = pipeline.index("launch_eval_worker.sh", smoke_wait)
    assert evaluator_launch > smoke_wait
    assert "method_smoke_passed=1" in pipeline
    assert "on_demand_evaluator=1" in pipeline
    assert '"method_gpu_smoke"' in verifier
    assert '"on_demand_evaluator"' in verifier
    assert 'load_json(path).get("run_id")' in verifier
    assert 'path.name.endswith(".failed.json")' in verifier
    assert '"evaluation_item_contract"' in verifier


def test_passed_smoke_can_resume_without_research_or_training_relaunch() -> None:
    pipeline = (RUN10 / "slurm" / "run_10_pipeline.sbatch").read_text()

    assert 'RESUME_SMOKE="${AAR_RUN10_RESUME_SMOKE:-0}"' in pipeline
    assert "no research or training relaunch" in pipeline
    assert 'if [ "${RESUME_SMOKE}" = 0 ]; then' in pipeline
    assert 'baseline_reuse_provenance.json" ] ||' in pipeline
    assert '${ATTEMPT_DIR}/eval/prompt_baselines_v3.' in pipeline
    assert '${ATTEMPT_DIR}/eval/lifecycle_holdout_v3/gemma4_31b' in pipeline
    assert 'AAR_SUITE_BENCHMARKS="${AAR_SUITE_BENCHMARKS:-verbalized_ece}"' in pipeline
    assert 'AAR_PUBLISH_FORCE_N="${AAR_PUBLISH_FORCE_N:-2}"' in pipeline
    assert "verify_evaluation_contract.py" in pipeline
    assert 'AAR_EVAL_RETRY_FAILED=1' in pipeline
    assert "reusing staged immutable adapter" in pipeline


def test_published_lifecycle_suite_must_contain_exactly_two_items(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    suite_path = suite_dir / "suite.yaml"
    suite_path.write_text(
        yaml.safe_dump(
            {
                "suite": "test",
                "benchmarks": [
                    {"name": "verbalized_ece", "subset_size": 2}
                ],
            }
        )
    )
    data_path = suite_dir / "verbalized_ece.jsonl"
    data_path.write_text('{"id": 1}\n{"id": 2}\n')
    output = tmp_path / "proof.json"
    command = [
        sys.executable,
        str(LIFECYCLE / "verify_evaluation_contract.py"),
        "--suite",
        str(suite_path),
        "--benchmarks",
        "verbalized_ece",
        "--items",
        "2",
        "--output",
        str(output),
    ]

    subprocess.run(command, check=True)
    proof = json.loads(output.read_text())
    assert proof["status"] == "passed"
    assert proof["published_data"]["verbalized_ece"]["records"] == 2

    data_path.write_text('{"id": 1}\n')
    failed = subprocess.run(command, capture_output=True, text=True)
    assert failed.returncode != 0
    assert "contains 1 records, expected 2" in failed.stderr


def _write_lifecycle_attempt(root: Path, *, scored_items: int) -> Path:
    metadata = root / "metadata"
    scores = root / "aar_teams" / "team" / "scores"
    forum = root / "aar_teams" / "team" / "forum"
    eval_private = root / "aar_teams" / "team" / "_eval_private"
    manifests = eval_private / "merge_manifests"
    for path in (metadata, scores, forum, manifests):
        path.mkdir(parents=True, exist_ok=True)
    (metadata / "submission.txt").write_text("git_commit=abc123\n")
    (metadata / "kimi_mcp_preflight.json").write_text(
        json.dumps({"mcp_tool_roundtrip": True})
    )
    (metadata / "method_smoke_passed.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "real_gpu_smoke": True,
                "adapter_reload_validation": True,
            }
        )
    )
    (metadata / "lifecycle_evaluation_contract.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "expected_benchmarks": ["verbalized_ece"],
                "expected_items_per_benchmark": 2,
            }
        )
    )
    (metadata / "children.env").write_text("on_demand_evaluator=1\n")
    (scores / "run-1.json").write_text(
        json.dumps(
            {
                "per_benchmark": {
                    "verbalized_ece": {"n": scored_items}
                }
            }
        )
    )
    (forum / "finding.json").write_text(json.dumps({"run_id": "run-1"}))
    (manifests / "run-1.json").write_text("{}\n")
    (eval_private / "eval_worker_1.out").write_text(
        "backend=vllm image=docker.io/vllm/vllm-openai:v0.25.1 "
        "lora_strategy=merged_checkpoint\n"
        "runtime backend=vllm version=0.25.1 language_model_only=True\n"
        "removed ephemeral merged checkpoint\n"
    )
    return root


def test_final_canary_proof_requires_two_scored_items(tmp_path: Path) -> None:
    verifier = RUN10 / "canary" / "verify_run_10_canary.py"
    passed_attempt = _write_lifecycle_attempt(
        tmp_path / "passed", scored_items=2
    )
    subprocess.run([sys.executable, str(verifier), str(passed_attempt)], check=True)
    proof = json.loads(
        (passed_attempt / "metadata" / "canary_passed.json").read_text()
    )
    assert proof["evaluation_item_contract"] is True
    assert proof["evaluated_items_per_benchmark"] == {"verbalized_ece": 2}

    failed_attempt = _write_lifecycle_attempt(tmp_path / "failed", scored_items=1)
    failed = subprocess.run(
        [sys.executable, str(verifier), str(failed_attempt)],
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
    failed_proof = json.loads(
        (failed_attempt / "metadata" / "canary_passed.json").read_text()
    )
    assert failed_proof["evaluation_item_contract"] is False


def test_full_mode_requires_per_method_gpu_preflight() -> None:
    pipeline = (RUN10 / "slurm" / "run_10_pipeline.sbatch").read_text()

    assert 'export AAR_PRETRAIN_SMOKE=1' in pipeline


def test_kimi_preflight_records_the_requested_deployment() -> None:
    verifier = (RUN10 / "verify_kimi_endpoint.py").read_text()

    assert 'deployment = os.environ.get("AAR_KIMI_SERVE_DEPLOYMENT"' in verifier
    assert 'expected_model = os.environ.get("AAR_KIMI_EXPECTED_MODEL"' in verifier
    assert '"deployment": deployment' in verifier
    assert '"model": expected_model' in verifier
    assert 'AAR_KIMI_PREFLIGHT_TIMEOUT_SECONDS' in verifier
    assert 'AAR_KIMI_PREFLIGHT_MAX_OUTPUT_TOKENS' in verifier
    assert 'KIMI_MODEL_MAX_OUTPUT_SIZE' in verifier
    assert 'force_checkpoint_tools=True' in verifier
    assert 'asyncio.wait_for(' in verifier
    assert 'Kimi MCP round trip exceeded' in verifier


def test_run10_canary_keeps_historical_defaults_but_allows_trusted_overrides() -> None:
    pipeline = (
        (RUN10 / "configure_run_10_environment.sh").read_text()
        + (RUN10 / "run_10_pipeline.sbatch").read_text()
    )
    submitter = (RUN10 / "submit_run_10.sh").read_text()

    assert 'EXPECTED_BRANCH="${AAR_EXPECTED_BRANCH:-multi_kimi}"' in submitter
    assert 'KIMI_DEPLOYMENT="${AAR_KIMI_SERVE_DEPLOYMENT:-steerability_8-kimi26}"' in submitter
    assert 'AAR_RUN10_ATTEMPT_PARENT:-${AAR_RUN_STORAGE_ROOT:' in submitter
    assert 'AAR_EXPECTED_BRANCH="${AAR_EXPECTED_BRANCH:-multi_kimi}"' in pipeline
    assert 'AAR_KIMI_SERVE_DEPLOYMENT="${AAR_KIMI_SERVE_DEPLOYMENT:-steerability_8-kimi26}"' in pipeline
    assert 'AAR_RUN10_TEAM_ID_PREFIX:-honesty-sycophancy-concealing-' in pipeline


def test_run10_canary_supports_bounded_recovered_continuation() -> None:
    pipeline = (RUN10 / "run_10_pipeline.sbatch").read_text()
    submitter = (RUN10 / "submit_run_10.sh").read_text()

    assert 'CANARY_ITERATIONS="${AAR_RUN10_CANARY_ITERATIONS:-1}"' in submitter
    assert 'CANARY_ITERATIONS="${AAR_RUN10_CANARY_ITERATIONS:-1}"' in pipeline
    assert '"${CANARY_ITERATIONS}" -le 5' in submitter
    assert 'seeds=canary; iterations="${CANARY_ITERATIONS}"' in pipeline
    assert 'RECOVERED_AGENT_LOG_DIR="${AAR_RUN10_RECOVERED_AGENT_LOG_DIR:-}"' in submitter
    assert 'recovered-agent-log' in submitter
    assert 'export AAR_RECOVERED_AGENT_LOG_DIR="${recovered_agent_log_for_launch}"' in submitter
    assert 'recovered_agent_log_dir=%s' in submitter


def test_initial_launch_and_targeted_resume_share_runtime_configuration() -> None:
    pipeline = (RUN10 / "slurm" / "run_10_pipeline.sbatch").read_text()
    resume = (RUN10 / "recovery" / "resume_run_10.sh").read_text()
    configuration = (
        RUN10 / "config" / "configure_run_10_environment.sh"
    ).read_text()
    run_config = (RUN10 / "config" / "run.yaml").read_text()
    shared = "configure_run_10_environment.sh"

    assert shared in pipeline
    assert shared in resume
    assert "load_aar_run_config.py" in configuration
    assert "max_truncation_rate: 0.20" in run_config
    assert "turn_timeout_seconds: 1800" in run_config
    assert 'AAR_RUN_CONFIG="${ATTEMPT_DIR}/metadata/run.yaml"' in resume


def test_targeted_resume_is_budgeted_and_duplicate_safe() -> None:
    resume = (RUN10 / "recovery" / "resume_run_10.sh").read_text()
    shared = (ROOT / "scripts" / "resume_aar_team.sh").read_text()

    assert 'exec "${REPO}/scripts/resume_aar_team.sh"' in resume
    assert "seed_has_active_job" in shared
    assert "refusing duplicate active chain" in shared
    assert "max_sessions - started" in shared
    assert 'session_*_${seed}_*.log' in shared
    assert "recovery_jobs.tsv" in shared
    assert "expected exactly one AAR team" in shared
    assert "launch_eval_worker.sh" in shared
    assert "AAR_RESUME_ALLOWED_SEEDS" in resume
