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
    assert "export AAR_REQUIRE_PHASE_TIMINGS=1" in pipeline


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


def test_merge_failure_is_terminal_instead_of_retried() -> None:
    worker = (ROOT / "scripts" / "eval_worker.sh").read_text()

    assert 'publish_terminal_failure "${rid}"' in worker
    assert "adapter merge failed; candidate checkpoint is invalid" in worker
    assert "adapter_merge_failed" in worker
    assert "merge_manifest_missing" in worker
    assert "evaluator_runtime_failed" in worker


def test_run6_times_queue_merge_and_eval_phases() -> None:
    worker = (ROOT / "scripts" / "eval_worker.sh").read_text()
    train = (ROOT / "scripts" / "slurm_train_submit.sh").read_text()

    assert "eval.queue_wait" in worker
    assert "eval.adapter_merge" in worker
    assert "train.queue_wait" in train
    assert "train.method_total" in train
    assert "train.model_submission" in train
    assert "require_successful_phases" in train
