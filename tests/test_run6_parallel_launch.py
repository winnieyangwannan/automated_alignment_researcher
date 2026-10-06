"""Static launch-contract checks for the five-agent Run 6 workflow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN6 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_6"


def test_run6_requests_five_one_iteration_research_chains() -> None:
    pipeline = (RUN6 / "run_6_pipeline.sbatch").read_text()

    assert 'launch_team.sh" "alpha beta gamma delta epsilon" 1 12' in pipeline
    assert "export AAR_MAX_CONCURRENT_TRAIN_JOBS=5" in pipeline
    assert "expected five research-chain job IDs" in pipeline
    assert "research-chain job IDs are not distinct" in pipeline


def test_run6_requests_five_four_gpu_merged_vllm_evaluators() -> None:
    pipeline = (RUN6 / "run_6_pipeline.sbatch").read_text()

    assert "export AAR_EVAL_WORKERS=5" in pipeline
    assert "export AAR_EVAL_GPUS=4" in pipeline
    assert "export AAR_EVAL_GPU_CAP=4" in pipeline
    assert "export EVAL_INFERENCE_BACKEND=vllm" in pipeline
    assert "export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint" in pipeline
    assert "export EVAL_VLLM_REQUIRE_MERGED=1" in pipeline
    assert "expected five evaluator job IDs" in pipeline
    assert "evaluator job IDs are not distinct" in pipeline


def test_shared_evaluator_queue_claim_is_atomic() -> None:
    worker = (ROOT / "scripts" / "eval_worker.sh").read_text()

    assert 'mkdir "${CLAIMS}/${rid}" 2>/dev/null || continue' in worker
