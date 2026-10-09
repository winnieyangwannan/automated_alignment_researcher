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


def test_run9_pins_a_configurable_broker_runner_and_safe_concurrency() -> None:
    submitter = (RUN9 / "submit_run_9.sh").read_text()
    pipeline = (RUN9 / "run_9_pipeline.sbatch").read_text()
    runtime = (ROOT / "scripts" / "aar_runtime_env.sh").read_text()

    assert "AAR_AUTODATA_BROKER_RUNNER:-local-bwrap" in submitter
    assert "AAR_AUTODATA_ENVIRONMENT:-oci-runner-firecracker-large" in submitter
    assert "AAR_AUTODATA_CONCURRENCY:-16" in submitter
    assert '"runner": "${AAR_AUTODATA_BROKER_RUNNER}"' in submitter
    assert '"environment": "${AAR_AUTODATA_ENVIRONMENT}"' in submitter
    assert 'export AAR_AUTODATA_BROKER_RUNNER="${AAR_AUTODATA_BROKER_RUNNER:?}"' in pipeline
    assert 'export AAR_AUTODATA_ENVIRONMENT="${AAR_AUTODATA_ENVIRONMENT:?}"' in pipeline
    assert "AAR_AUTODATA_BROKER_RUNNER" in runtime
    assert "AAR_AUTODATA_ENVIRONMENT" in runtime


def test_run9_capacity_canary_uses_requested_real_model_backed_jobs() -> None:
    submitter = (RUN9 / "submit_run_9_capacity_canary.sh").read_text()
    canary = (RUN9 / "run_9_capacity_canary.sbatch").read_text()

    assert '--max-concurrent "${CONCURRENCY}"' in canary
    assert 'for index in $(seq 1 "${CONCURRENCY}")' in canary
    assert "autodata_model_broker_canary.py" in canary
    assert '--runner "${RUNNER}"' in canary
    assert '--environment "${ENVIRONMENT}"' in canary
    assert '"concurrency": concurrency' in canary
    assert 'job["status"] != "SUCCEEDED"' in canary
    assert '"audited_sample_count": len(reports)' in canary
    assert "--campaign-policy" in canary
    assert '"environment": "${ENVIRONMENT}"' in submitter
    assert '"runner": "${RUNNER}"' in submitter
    assert 'export AAR_AUTODATA_CONCURRENCY="${CONCURRENCY}"' in submitter
    assert "--export=ALL" in submitter


def test_run9_native_preflight_covers_the_real_lifecycle() -> None:
    submitter = (RUN9 / "submit_run_9_native_preflight.sh").read_text()
    preflight = (RUN9 / "run_9_native_preflight.sbatch").read_text()

    assert "autodata_native_real_e2e.py" in preflight
    assert '--task-count 16' in preflight
    assert '--concurrency 16' in preflight
    assert '--max-cost-usd 2' in preflight
    assert "AAR_AUTODATA_WRAPPER_PYTHON" in preflight
    assert "native-preflight/v1" in preflight
    assert "RUN9_NATIVE_PREFLIGHT_PASS" in preflight
    assert '"runner": "${RUNNER}"' in submitter
    assert '"AUTODATA_GENERATOR_HOST_HEADER"' in submitter


def test_generic_launchers_include_run7_first_use_fixes() -> None:
    trainer = (ROOT / "scripts" / "submit_train_job.sh").read_text()
    evaluator = (ROOT / "scripts" / "launch_eval_worker.sh").read_text()

    assert "_lanes=()" in trainer
    assert '--nodes=1 --ntasks=1 --gpus="${GPUS}"' in evaluator


def test_chain_initializes_python_before_autodata_health_probe() -> None:
    chain = (ROOT / "scripts" / "slurm_aar_chain.sh").read_text()

    assert chain.index('PY="${HARNESS_PY}"') < chain.index(
        'if "${PY}" -c \'import os,urllib.request'
    )


def test_chain_prebootstraps_and_pins_autodata_plugin_python() -> None:
    chain = (ROOT / "scripts" / "slurm_aar_chain.sh").read_text()
    runtime = (ROOT / "scripts" / "aar_runtime_env.sh").read_text()

    assert 'export AUTODATA_CACHE_DIR="${AUTODATA_CACHE_DIR:-' in chain
    assert '"${AAR_AUTODATA_PLUGIN_ROOT}/scripts/bootstrap.py"' in chain
    assert "export AAR_AUTODATA_WRAPPER_PYTHON" in chain
    assert "bootstrapped AutoData plugin import failed" in chain
    assert "AAR_AUTODATA_WRAPPER_PYTHON" in runtime
    assert "AUTODATA_CACHE_DIR" in runtime


def test_run9_keeps_the_hot_broker_database_on_node_local_storage() -> None:
    chain = (ROOT / "scripts" / "slurm_aar_chain.sh").read_text()
    canary = (RUN9 / "run_9_capacity_canary.sbatch").read_text()

    assert '${SLURM_TMPDIR:-/tmp}/aar-autodata-broker-' in chain
    assert '--database "${_autodata_broker_database}"' in chain
    assert 'snapshot_autodata_broker_database' in chain
    assert "wal_checkpoint(TRUNCATE)" in chain
    assert '${SLURM_TMPDIR:-/tmp}/aar-run9-canary-broker-' in canary
    assert '--database "${broker_database}"' in canary
    assert 'snapshot_broker_database' in canary
    assert "wal_checkpoint(TRUNCATE)" in canary
