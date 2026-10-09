"""Static contracts for Run 10's no-evaluator generated-method smoke."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN10 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_10"


def test_smoke_mode_uses_one_chain_and_no_evaluator() -> None:
    pipeline = (RUN10 / "run_10_pipeline.sbatch").read_text()
    submitter = (RUN10 / "submit_run_10.sh").read_text()

    assert "smoke|canary|full" in submitter
    assert 'AAR_START_EVAL_WORKER=0' in pipeline
    assert 'AAR_EVAL_WORKERS=0' in pipeline
    assert 'AAR_METHOD_SMOKE=1' in pipeline
    assert 'AAR_REQUIRE_METHOD_SMOKE=1' in pipeline
    assert 'AAR_TRAIN_TIME=00:15:00' in pipeline
    assert 'expected_evaluators=0' in pipeline


def test_training_smoke_validates_real_peft_adapter_without_submission() -> None:
    trainer = (ROOT / "scripts" / "slurm_train_submit.sh").read_text()

    assert 'config_kwargs["smoke_run"] = True' in trainer
    assert "PeftConfig.from_pretrained(model_path)" in trainer
    assert "validate_model_submission(out[\"model_path\"])" in trainer
    assert '"adapter_model.safetensors"' in trainer
    assert 'method_smoke' in trainer
    assert 'if [ "${AAR_METHOD_SMOKE:-0}" = "1" ]; then' in trainer


def test_evaluator_is_launched_only_after_method_smoke_passes() -> None:
    pipeline = (RUN10 / "run_10_pipeline.sbatch").read_text()
    verifier = (RUN10 / "verify_run_10_canary.py").read_text()

    smoke_wait = pipeline.index("monitor_method_smoke.py")
    evaluator_launch = pipeline.index("launch_eval_worker.sh", smoke_wait)
    assert evaluator_launch > smoke_wait
    assert "method_smoke_passed=1" in pipeline
    assert "on_demand_evaluator=1" in pipeline
    assert '"method_gpu_smoke"' in verifier
    assert '"on_demand_evaluator"' in verifier


def test_passed_smoke_can_resume_without_research_or_training_relaunch() -> None:
    pipeline = (RUN10 / "run_10_pipeline.sbatch").read_text()

    assert 'RESUME_SMOKE="${AAR_RUN10_RESUME_SMOKE:-0}"' in pipeline
    assert "no research or training relaunch" in pipeline
    assert 'if [ "${RESUME_SMOKE}" = 0 ]; then' in pipeline
    assert 'baseline_reuse_provenance.json" ] ||' in pipeline
    assert '${ATTEMPT_DIR}/eval/prompt_baselines.' in pipeline
    assert 'AAR_SUITE_BENCHMARKS=verbalized_ece AAR_PUBLISH_FORCE_N=2' in pipeline
    assert 'AAR_EVAL_IDLE_SECONDS=120' in pipeline
