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


def test_full_continuation_uses_recovered_history_and_remaining_budgets() -> None:
    submitter = (RUN7 / "submit_storage_continuation.sh").read_text()
    pipeline = (RUN7 / "storage_continuation.sbatch").read_text()
    launcher = (ROOT / "scripts" / "launch_team.sh").read_text()
    chain = (ROOT / "scripts" / "slurm_aar_chain.sh").read_text()

    assert "AAR_RUN7_CANARY_PROOF" in submitter
    assert "merge-base --is-ancestor" in submitter
    assert "reconstruct_recovery_seed.py" in pipeline
    assert "--expected-entries 14" in pipeline
    assert 'launch_team.sh" "alpha beta gamma delta epsilon" 50 167' in pipeline
    assert "alpha=43,beta=44,gamma=45,delta=44,epsilon=44" in pipeline
    assert "export AAR_EVAL_WORKERS=5" in pipeline
    assert "export AAR_VLLM_EPHEMERAL_MERGED=1" in pipeline
    assert "AAR_MAX_ITERATIONS_BY_SEED" in launcher
    assert "AAR_RECOVERED_AGENT_LOG_DIR" in chain


def test_eval_workers_are_single_node_and_storage_recoverable() -> None:
    launcher = (ROOT / "scripts" / "launch_eval_worker.sh").read_text()
    replacement = (
        RUN7 / "submit_storage_evaluator_replacements.sh"
    ).read_text()

    assert '--nodes=1 --ntasks=1 --gpus="${GPUS}"' in launcher
    assert "AAR_VLLM_EPHEMERAL_MERGED=1" in replacement
    assert "single_node_evaluator_replacement" in replacement
    assert 'AAR_EVAL_WORKERS="${WORKERS}"' in replacement


def test_storage_attempt_snapshots_the_vllm_launcher_runtime() -> None:
    snapshotter = (RUN7 / "snapshot_vllm_runtime.sh").read_text()
    canary_submitter = (RUN7 / "submit_storage_recovery_canary.sh").read_text()
    full_submitter = (RUN7 / "submit_storage_continuation.sh").read_text()
    canary = (RUN7 / "storage_recovery_canary.sbatch").read_text()
    full = (RUN7 / "storage_continuation.sbatch").read_text()
    replacement = (RUN7 / "submit_storage_evaluator_replacements.sh").read_text()

    assert "EXPECTED_TREE_SHA256=" in snapshotter
    assert "cp -a --" in snapshotter
    assert "mv --" in snapshotter
    assert "snapshot_vllm_runtime.sh" in canary_submitter
    assert "snapshot_vllm_runtime.sh" in full_submitter
    durable_worker = '${ATTEMPT_DIR}/runtime/serve_api_v2/worker/worker_vllm.sh'
    assert durable_worker in canary
    assert durable_worker in full
    assert durable_worker in replacement
