"""Static launch-contract checks for the 50-iteration Run 7 workflow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN7 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_7"


def test_run7_requests_five_50_iteration_research_chains() -> None:
    pipeline = (RUN7 / "run_7_pipeline.sbatch").read_text()

    assert 'launch_team.sh" "alpha beta gamma delta epsilon" 50 167' in pipeline
    assert "export AAR_MAX_CONCURRENT_TRAIN_JOBS=5" in pipeline
    assert "max_iterations_per_chain=50" in pipeline
    assert "expected five research-chain job IDs" in pipeline
    assert "research-chain job IDs are not distinct" in pipeline
    assert "export AAR_REQUIRE_PHASE_TIMINGS=1" in pipeline


def test_run7_requests_five_long_lived_four_gpu_evaluators() -> None:
    pipeline = (RUN7 / "run_7_pipeline.sbatch").read_text()

    assert "export AAR_EVAL_WORKERS=5" in pipeline
    assert "export AAR_EVAL_GPUS=4" in pipeline
    assert "export AAR_EVAL_GPU_CAP=4" in pipeline
    assert "export AAR_EVAL_TIME=7-00:00:00" in pipeline
    assert "export AAR_EVAL_IDLE_SECONDS=604200" in pipeline
    assert "export EVAL_INFERENCE_BACKEND=vllm" in pipeline
    assert "export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint" in pipeline
    assert "export EVAL_VLLM_REQUIRE_MERGED=1" in pipeline
    assert "expected five evaluator job IDs" in pipeline
    assert "evaluator job IDs are not distinct" in pipeline


def test_run7_submitter_records_iteration_contract() -> None:
    submitter = (RUN7 / "submit_run_7.sh").read_text()

    assert "run7_attempts" in submitter
    assert "max_iterations_per_chain=50" in submitter
    assert "research_chains=5" in submitter
    assert "evaluator_jobs=5" in submitter


def test_run7_evaluator_recovery_replaces_five_workers_fail_closed() -> None:
    recovery = (RUN7 / "run_7_eval_recovery.sbatch").read_text()

    assert "eval-gemma-4-31b-it" in recovery
    assert "AAR_VLLM_WORKER_SHA256=" in recovery
    assert 'sha256sum "${AAR_VLLM_WORKER_SH}"' in recovery
    assert "export EVAL_INFERENCE_BACKEND=vllm" in recovery
    assert "export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint" in recovery
    assert "export EVAL_VLLM_REQUIRE_MERGED=1" in recovery
    assert "export AAR_EVAL_WORKERS=5" in recovery
    assert "export AAR_EVAL_GPUS=4" in recovery
    assert "expected five evaluator recovery job IDs" in recovery
    assert "evaluator recovery job IDs are not distinct" in recovery
