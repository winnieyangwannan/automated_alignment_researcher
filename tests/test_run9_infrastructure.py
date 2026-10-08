"""Safety contracts ported from the proven multi-dimensional Run 7 stack."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN9 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_9"


def test_run9_snapshots_the_complete_hash_bound_vllm_runtime() -> None:
    snapshotter = (RUN9 / "snapshot_vllm_runtime.sh").read_text()
    submitter = (RUN9 / "submit_run_9.sh").read_text()

    assert "EXPECTED_TREE_SHA256=" in snapshotter
    assert 'worker/container.sh' in snapshotter
    assert 'worker/engine_common.sh' in snapshotter
    assert 'cp -a -- "${SOURCE}/." "${STAGING}/"' in snapshotter
    assert 'mv -- "${STAGING}" "${DEST}"' in snapshotter
    assert 'snapshot_vllm_runtime.sh" "${attempt_dir}"' in submitter
    assert 'install -m 700 "${VLLM_WORKER_SOURCE}"' not in submitter


def test_run9_uses_safe_ephemeral_merged_checkpoints() -> None:
    pipeline = (RUN9 / "run_9_pipeline.sbatch").read_text()
    worker = (ROOT / "scripts" / "eval_worker.sh").read_text()

    assert "AAR_VLLM_EPHEMERAL_MERGED=1" in pipeline
    assert "AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680" in pipeline
    assert "aar-vllm-merged-${WORKER_ID}" in worker
    assert ".aar-ephemeral-merged-root" in worker
    assert "refusing cleanup before terminal handoff" in worker
    assert "merge_manifests/${rid}.json" in worker
    assert 'rm -rf --one-file-system -- "${cleanup_target}" "${cleanup_staging}"' in worker


def test_generic_launchers_include_run7_first_use_fixes() -> None:
    trainer = (ROOT / "scripts" / "submit_train_job.sh").read_text()
    evaluator = (ROOT / "scripts" / "launch_eval_worker.sh").read_text()

    assert "_lanes=()" in trainer
    assert '--nodes=1 --ntasks=1 --gpus="${GPUS}"' in evaluator
