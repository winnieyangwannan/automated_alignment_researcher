"""Safety contracts ported from the proven multi-dimensional Run 7 stack."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN9 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_9"
FULL_SUBMIT = RUN9 / "launch" / "submit_full.sh"
PIPELINE = RUN9 / "slurm" / "pipeline.sbatch"
CAPACITY = RUN9 / "canary" / "provider_capacity"
NATIVE = RUN9 / "canary" / "native_lifecycle"
RECOVERY = RUN9 / "recovery"


def test_run9_snapshots_the_complete_hash_bound_vllm_runtime() -> None:
    snapshotter = (RUN9 / "runtime" / "snapshot_vllm_runtime.sh").read_text()
    submitter = FULL_SUBMIT.read_text()

    assert "EXPECTED_TREE_SHA256=" in snapshotter
    assert 'worker/container.sh' in snapshotter
    assert 'worker/engine_common.sh' in snapshotter
    assert 'cp -a -- "${SOURCE}/." "${STAGING}/"' in snapshotter
    assert 'mv -- "${STAGING}" "${DEST}"' in snapshotter
    assert 'snapshot_vllm_runtime.sh" "${attempt_dir}"' in submitter
    assert 'install -m 700 "${VLLM_WORKER_SOURCE}"' not in submitter


def test_run9_uses_safe_ephemeral_merged_checkpoints() -> None:
    pipeline = PIPELINE.read_text()
    worker = (ROOT / "scripts" / "eval_worker.sh").read_text()

    assert "AAR_VLLM_EPHEMERAL_MERGED=1" in pipeline
    assert "AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680" in pipeline
    assert "aar-vllm-merged-${WORKER_ID}" in worker
    assert ".aar-ephemeral-merged-root" in worker
    assert "refusing cleanup before terminal handoff" in worker
    assert "merge_manifests/${rid}.json" in worker
    assert 'rm -rf --one-file-system -- "${cleanup_target}" "${cleanup_staging}"' in worker


def test_run9_pins_local_bwrap_and_safe_concurrency() -> None:
    submitter = FULL_SUBMIT.read_text()
    pipeline = PIPELINE.read_text()
    runtime = (ROOT / "scripts" / "aar_runtime_env.sh").read_text()

    assert "AAR_AUTODATA_BROKER_RUNNER:-local-bwrap" in submitter
    assert 'AAR_AUTODATA_BROKER_RUNNER}" = local-bwrap' in submitter
    assert "use the capacity-canary launcher for intentional Firecracker tests" in submitter
    assert "ram-inference-gateway.ingress.fair-cw-use2-1.cw.metafb.cloud" not in submitter
    assert "AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE" not in submitter
    assert "AAR_AUTODATA_ENVIRONMENT:-oci-runner-firecracker-large" in submitter
    assert "default_autodata_concurrency=32" in submitter
    assert "default_autodata_concurrency=64" in submitter
    assert "default_model_request_max_attempts=3" in submitter
    assert "default_model_request_max_attempts=1" in submitter
    assert '"AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS}"' in submitter
    assert "validated maximum of 64" in submitter
    assert '"runner": "${AAR_AUTODATA_BROKER_RUNNER}"' in submitter
    assert '"environment": "${AAR_AUTODATA_ENVIRONMENT}"' in submitter
    assert 'export AAR_AUTODATA_BROKER_RUNNER="${AAR_AUTODATA_BROKER_RUNNER:?}"' in pipeline
    assert 'export AAR_AUTODATA_ENVIRONMENT="${AAR_AUTODATA_ENVIRONMENT:?}"' in pipeline
    assert "AAR_AUTODATA_BROKER_RUNNER" in runtime
    assert "AAR_AUTODATA_ENVIRONMENT" in runtime


def test_agent_prompt_distinguishes_native_adapter_from_physical_runner() -> None:
    prompt = (ROOT / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()

    assert "broker-client adapter `kind: sandoq-firecracker`" in prompt
    assert "do not prove that a Firecracker VM is used" in prompt
    assert "campaign policy's `runner` field and the broker startup log are authoritative" in prompt
    assert "Cold Firecracker starts and multi-hour generation are expected" not in prompt


def test_run9_capacity_canary_uses_requested_real_model_backed_jobs() -> None:
    submitter = (CAPACITY / "launch" / "submit.sh").read_text()
    canary = (CAPACITY / "slurm" / "capacity.sbatch").read_text()

    assert '--max-concurrent "${CONCURRENCY}"' in canary
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
    assert 'export AAR_AUTODATA_CANARY_TASK_COUNT="${TASK_COUNT}"' in submitter
    assert 'export AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS="${MODEL_REQUEST_MAX_ATTEMPTS}"' in submitter
    assert 'export AAR_AUTODATA_GENERATOR_DEPLOYMENT="${GENERATOR_DEPLOYMENT}"' in submitter
    assert '"AUTODATA_GENERATOR_DEPLOYMENT_ID": "${GENERATOR_DEPLOYMENT}"' in submitter
    assert "generator_deployment_id=%s" in submitter
    assert 'CAPACITY_PROFILE="${CANARY_DIR}/config/run.yaml"' in submitter
    assert "aar.autodata_capacity_profile render-policy" in submitter
    assert '--capacity-profile "${CAPACITY_PROFILE}"' in canary
    assert 'export AAR_AUTODATA_TARGET_BINDING="${target_binding}"' in submitter
    assert "binding.solve_environment()" in submitter
    assert 'for index in $(seq 1 "${TASK_COUNT}")' in canary
    assert 'if [ "${#pids[@]}" -eq "${CONCURRENCY}" ]' in canary
    assert '"max_cost_usd": "10"' in submitter
    assert 'KIMI_PROXY_INFO="${AAR_KIMI_PROXY_INFO:-' in submitter
    assert 'install -m 600 "${KIMI_PROXY_INFO}" "${kimi_proxy_info}"' in submitter
    assert 'sbatch_args+=(--dependency="${SLURM_DEPENDENCY}")' in submitter
    assert "loopback_model_auth_bridge.py" in canary
    assert '--generator-deployment-id "${GENERATOR_DEPLOYMENT}"' in canary
    assert 'environment.pop("AUTODATA_GENERATOR_HOST_HEADER", None)' in canary
    assert "--allow-judge-rejection" in canary
    assert '"accepted_rows_per_minute"' in canary
    assert '"task_result_failed_count"' in canary
    assert '"judge_call_count"' in canary
    assert '"target_call_count"' in canary
    assert "--target-binding" in canary
    assert "--export=ALL" in submitter


def test_run9_native_preflight_covers_the_real_lifecycle() -> None:
    submitter = (NATIVE / "launch" / "submit.sh").read_text()
    preflight = (NATIVE / "slurm" / "preflight.sbatch").read_text()

    assert "autodata_native_real_e2e.py" in preflight
    assert '--task-count 16' in preflight
    assert '--concurrency 16' in preflight
    assert '--max-cost-usd 2' in preflight
    assert "AAR_AUTODATA_WRAPPER_PYTHON" in preflight
    assert "native-preflight/v1" in preflight
    assert "RUN9_NATIVE_PREFLIGHT_PASS" in preflight
    assert 'report.get("elapsed_seconds", 9999) > 1200' in preflight
    assert '"runner": "${RUNNER}"' in submitter
    assert '"AUTODATA_GENERATOR_HOST_HEADER"' in submitter


def test_run9_bounds_meta_work_and_has_production_acceptance_headroom() -> None:
    pipeline = PIPELINE.read_text()

    assert "AAR_AUTODATA_META_MIN_ITERATIONS=3" in pipeline
    assert "AAR_AUTODATA_META_MAX_ITERATIONS=3" in pipeline
    assert "AAR_AUTODATA_PRODUCTION_ROWS=1000" in pipeline
    assert "AAR_AUTODATA_PRODUCTION_INITIAL_TASKS=1250" in pipeline
    assert "AAR_AUTODATA_PRODUCTION_MAX_TASKS=2000" in pipeline


def test_run9_requires_target_aware_autodata_by_default() -> None:
    submitter = FULL_SUBMIT.read_text()
    recipe = (
        ROOT
        / "aar"
        / "autodata_recipes"
        / "dishonest_sycophancy_concealing"
        / "recipe"
        / "task.py"
    ).read_text()

    for name in (
        "AUTODATA_TARGET_URL",
        "AUTODATA_TARGET_MODEL",
        "AUTODATA_TARGET_DEPLOYMENT_ID",
        "AUTODATA_TARGET_CHECKPOINT_HASH",
    ):
        assert name in submitter
        assert name in recipe
    assert "target_setting_count" in submitter
    assert 'AUTODATA_TARGET_ENABLED="${AUTODATA_TARGET_ENABLED:-1}"' in submitter
    assert '"AUTODATA_TARGET_ENABLED": "${target_enabled}"' in submitter
    assert "enabled by default" in submitter
    assert "target_aware=%s" in submitter
    assert 'role="target"' in recipe
    assert 'metrics["challenge"]' in recipe


def test_generic_launchers_include_run7_first_use_fixes() -> None:
    trainer = (ROOT / "scripts" / "submit_train_job.sh").read_text()
    evaluator = (ROOT / "scripts" / "launch_eval_worker.sh").read_text()

    assert "_lanes=()" in trainer
    assert '--nodes=1 --ntasks=1 --gpus="${GPUS}"' in evaluator


def test_agent_prompt_requires_chat_template_token_normalization() -> None:
    prompt = (ROOT / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()

    assert "normalize_chat_template_ids" in prompt
    assert "BatchEncoding" in prompt


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
    canary = (CAPACITY / "slurm" / "capacity.sbatch").read_text()

    assert '${SLURM_TMPDIR:-/tmp}/aar-autodata-broker-' in chain
    assert '--database "${_autodata_broker_database}"' in chain
    assert 'snapshot_autodata_broker_database' in chain
    assert '_autodata_broker_archive="${_autodata_root}/attempt-ledgers"' in chain
    assert '_autodata_broker_database_retained="${_autodata_broker_archive}/campaign-ledger.db"' in chain
    assert 'autodata_broker_ledger.py" restore' in chain
    assert 'autodata_broker_ledger.py" snapshot' in chain
    assert "another session owns the AutoData campaign ledger" in chain
    assert '${SLURM_TMPDIR:-/tmp}/aar-run9-canary-broker-' in canary
    assert '--database "${broker_database}"' in canary
    assert 'snapshot_broker_database' in canary
    assert "wal_checkpoint(TRUNCATE)" in canary


def test_run9_production_recovery_uses_an_attempt_local_broker_ledger() -> None:
    recovery = (RECOVERY / "production.sbatch").read_text()

    assert 'LOCAL_BROKER="${LOCAL_ROOT}/broker/broker.db"' in recovery
    assert 'BROKER_ARCHIVE_DIR="${BROKER_ROOT}/attempt-ledgers"' in recovery
    assert 'BROKER_ATTEMPT_RETAINED="${BROKER_ARCHIVE_DIR}/${ATTEMPT_LABEL}.db"' in recovery
    assert '"${LOCAL_BROKER}" "${BROKER_ATTEMPT_RETAINED}"' in recovery
    assert 'cp -- "${BROKER_RETAINED}" "${LOCAL_BROKER}"' not in recovery
    assert '[[ "${supervisor_state}" = Z* ]]' in recovery


def test_run9_chain_can_route_kimi_through_the_authenticated_loopback_bridge() -> None:
    chain = (ROOT / "scripts" / "slurm_aar_chain.sh").read_text()
    runtime = (ROOT / "scripts" / "aar_runtime_env.sh").read_text()
    submitter = FULL_SUBMIT.read_text()
    agent = (ROOT / "aar" / "research_loop" / "agent.py").read_text()

    assert 'if [ -n "${AAR_KIMI_PROXY_INFO:-}" ]; then' in chain
    assert 'scripts/loopback_model_auth_bridge.py' in chain
    assert 'environment["AUTODATA_GENERATOR_URL"] = f"http://127.0.0.1:{port}/v1"' in chain
    assert 'environment["AUTODATA_GENERATOR_HOST_HEADER"] = ""' in chain
    assert 'environment.setdefault("AUTODATA_TARGET_ENABLED", "0")' in chain
    assert 'export AAR_AUTODATA_CAMPAIGN_POLICY="${_autodata_repaired_policy}"' in chain
    assert "aar.infrastructure.autodata_resume_ports" in chain
    assert "reusing retained AutoData loopback ports" in chain
    assert 'stop_child_bounded "${_autodata_bridge_pid}"' in chain
    assert "AAR_KIMI_PROXY_INFO" in runtime
    assert 'export AAR_KIMI_PROXY_INFO="${KIMI_PROXY_INFO}"' in submitter
    assert '"AAR_KIMI_PROXY_INFO"' in agent


def test_run9_uses_one_supervised_node_local_autodata_lifecycle() -> None:
    chain = (ROOT / "scripts" / "slurm_aar_chain.sh").read_text()
    submit_train = (ROOT / "scripts" / "submit_train_job.sh").read_text()
    pipeline = PIPELINE.read_text()
    prompt = (ROOT / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()

    assert "AAR_AUTODATA_LIFECYCLE_SUPERVISED=1" in pipeline
    assert '${SLURM_TMPDIR:-/tmp}/aar-autodata-native-' in chain
    assert "AAR_AUTODATA_RETAINED_STATE" in chain
    assert "AAR_AUTODATA_SUPERVISOR_CONTROL" in chain
    assert "autodata_lifecycle_supervisor.py\" run" in chain
    assert "autodata_lifecycle_supervisor.py\" restore" in chain
    assert "--require-manifest" in chain
    assert '--control-file "${AAR_AUTODATA_SUPERVISOR_CONTROL}"' in chain
    assert "autodata_lifecycle_supervisor.py\" snapshot" in submit_train
    assert "Trusted orchestration owns every deterministic lifecycle transition" in prompt
    assert "do not create or edit an execution config" in prompt
    assert "you never control the iteration count or the 64/32/32 split" in prompt
    assert "poll with Bash or `sleep`" in prompt
    assert "AAR_AUTODATA_RETAINED_STATE" in prompt
    version = (RUN9 / "config" / "autodata_version.env").read_text()
    assert "823c5948854df14664f3168bc5e6c49a2cecb975" in version
    for launcher in (
        FULL_SUBMIT,
        NATIVE / "launch" / "submit.sh",
        CAPACITY / "launch" / "submit.sh",
    ):
        text = launcher.read_text()
        assert "config/autodata_version.env" in text
        assert "RUN9_REQUIRED_AUTODATA_SHA" in text
