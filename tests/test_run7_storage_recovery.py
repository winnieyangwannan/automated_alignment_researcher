"""Static safety contracts for the storage-backed Run 7 recovery canary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN7 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_7"


def test_canary_uses_storage_and_one_candidate_before_full_switch() -> None:
    submitter = (RUN7 / "submit_storage_recovery_canary.sh").read_text()
    pipeline = (RUN7 / "storage_recovery_canary.sbatch").read_text()

    assert "/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts" in submitter
    assert 'launch_team.sh" "canary" 1 17' in pipeline
    assert "export AAR_EVAL_WORKERS=1" in pipeline
    assert "export AAR_EVAL_GPUS=4" in pipeline
    assert "export AAR_VLLM_EPHEMERAL_MERGED=1" in pipeline
    assert "docker.io/vllm/vllm-openai:v0.25.1" in pipeline
    assert "lora_strategy=merged_checkpoint" not in pipeline
    assert "EVAL_VLLM_LORA_STRATEGY=merged_checkpoint" in pipeline


def test_ephemeral_merge_cleanup_is_fail_closed() -> None:
    worker = (ROOT / "scripts" / "eval_worker.sh").read_text()

    assert "aar-vllm-merged-${WORKER_ID}" in worker
    assert ".aar-ephemeral-merged-root" in worker
    assert "refusing cleanup before terminal handoff" in worker
    assert "merge_manifests/${rid}.json" in worker
    assert 'rm -rf --one-file-system -- "${cleanup_target}" "${cleanup_staging}"' in worker


def test_recovered_baseline_requires_hash_bound_source_copies() -> None:
    validator = (
        ROOT / "scripts" / "validate_reused_multidimensional_baseline.py"
    ).read_text()

    assert "--recovered-source-dir" in validator
    assert 'f"{index:02d}_{original.name}"' in validator
    assert "_digest(readable_source) != expected_sha" in validator
    assert "_digest(readable_manifest) != expected_sha" in validator
