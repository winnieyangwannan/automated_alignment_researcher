"""Fail-closed source contracts for the fresh Run 15 package."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUN15 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_15"


def _resolved_environment(config_path: Path) -> set[str]:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "load_aar_run_config.py"),
            str(config_path),
        ],
        env={**os.environ, "USER": "test-user"},
        check=True,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.splitlines())


def test_run15_is_fresh_native_5x50_configuration() -> None:
    config_path = RUN15 / "config" / "run.yaml"
    config = yaml.safe_load(config_path.read_text())

    assert config["storage"]["root"] == (
        "/checkpoint/ram/aar/{user}/run15_native_generation"
    )
    assert config["storage"]["adapter_retention"] == "all"
    assert config["research"] == {
        "seeds": ["alpha", "beta", "gamma", "delta", "epsilon"],
        "forum_scope": "shared",
        "target_score_result_pairs": 50,
        "max_sessions_per_chain": 60,
        "walltime_hours": 167,
    }
    assert config["data_generation"] == {
        "backend": "native",
        "max_sequential_target_generations": 256,
    }
    assert config["evaluation"]["workers"] == 1
    assert config["evaluation"]["gpus_per_worker"] == 4
    assert config["evaluation"]["vllm_log_stats"] is True
    assert config["agent"]["continuation_exhaustion_retryable"] is True
    assert config["agent"]["max_continuations"] == 32
    assert config["agent"]["progress_stall_limit"] == 3
    assert config["agent"]["progress_stall_grace_continuations"] == 8
    assert config["recovery"] == {
        "enabled": True,
        "max_controller_restarts_per_chain": 8,
        "max_plan_failures_per_chain": 3,
        "poll_seconds": 60,
        "backoff_seconds": 300,
        "unknown_state_timeout_seconds": 900,
        "time_limit": "7-00:00:00",
        "reuse_evaluator": True,
    }

    environment = _resolved_environment(config_path)
    assert "export AAR_AUTODATA=0" in environment
    assert "export AAR_ADAPTER_RETENTION=all" in environment
    assert "export AAR_TARGET_SUCCESSFUL_ITERATIONS=50" in environment
    assert "export AAR_MAX_ITERATIONS_PER_CHAIN=60" in environment
    assert "export AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS=256" in environment
    assert "export AAR_KIMI_CONTINUATION_EXHAUSTION_RETRYABLE=1" in environment
    assert "export AAR_KIMI_MAX_CONTINUATIONS=32" in environment
    assert "export AAR_KIMI_PROGRESS_STALL_LIMIT=3" in environment
    assert "export AAR_KIMI_PROGRESS_STALL_GRACE_CONTINUATIONS=8" in environment
    assert "export EVAL_VLLM_LOG_STATS=1" in environment
    assert "export AAR_CONTROLLER_RECOVERY_ENABLED=1" in environment
    assert "export AAR_CONTROLLER_MAX_RESTARTS=8" in environment
    assert "export AAR_CONTROLLER_MAX_PLAN_FAILURES=3" in environment
    assert "export AAR_RESUME_REUSE_EVALUATOR=1" in environment

    evaluator = (ROOT / "scripts" / "eval_worker.sh").read_text()
    assert "prune_submission_artifacts.py" in evaluator
    assert '--retention "${AAR_ADAPTER_RETENTION:-all}"' in evaluator
    assert evaluator.count('prune_terminal_submission "${rid}" "${d%/}"') == 5


def test_run15_canaries_are_fresh_bounded_and_ordered() -> None:
    one = yaml.safe_load(
        (
            RUN15
            / "canary"
            / "one_chain_lifecycle_check"
            / "config"
            / "run.yaml"
        ).read_text()
    )
    five = yaml.safe_load(
        (
            RUN15
            / "canary"
            / "five_chain_lifecycle_check"
            / "config"
            / "run.yaml"
        ).read_text()
    )

    assert one["lifecycle"] == {
        "name": "one_chain_native_generation",
        "prerequisite_chain_count": 0,
    }
    assert one["research"]["max_sessions_per_chain"] == 1
    assert one["evaluation"]["items_per_benchmark"] == 2
    assert one["evaluation"]["on_demand"] is True
    assert one["data_generation"]["max_sequential_target_generations"] == 256

    assert five["lifecycle"] == {
        "name": "five_chain_lifecycle_check",
        "prerequisite_chain_count": 1,
    }
    assert five["research"]["seeds"] == [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
    ]
    assert five["research"]["max_sessions_per_chain"] == 1
    assert five["training"]["max_concurrent_jobs"] == 1
    assert five["evaluation"]["workers"] == 1
    assert five["evaluation"]["on_demand"] is True
    assert five["data_generation"]["max_sequential_target_generations"] == 256


def test_run15_launch_and_recovery_are_isolated_from_run14() -> None:
    operational = [
        RUN15 / "launch" / "submit_full.sh",
        RUN15 / "slurm" / "pipeline.sbatch",
        RUN15 / "recovery" / "resume_full.sh",
        RUN15 / "recovery" / "finalize_scored_run.sh",
        RUN15 / "recovery" / "finalize_scored_run.py",
        RUN15 / "canary" / "verify_run_15_canary.py",
        RUN15
        / "canary"
        / "one_chain_lifecycle_check"
        / "launch"
        / "launch.sh",
        RUN15
        / "canary"
        / "five_chain_lifecycle_check"
        / "launch"
        / "launch.sh",
    ]
    combined = "\n".join(path.read_text() for path in operational)

    assert "run_14" not in combined
    assert "RUN14" not in combined
    assert "run14" not in combined
    assert "run15_native_generation" in combined
    assert "AAR_RUN15_MODE" in combined
    assert "run15-gemma4-31b-kimi26" in combined
    assert "AAR_RESUME_TEAM_PREFIX=\"run15-gemma4-31b-kimi26-\"" in combined

    launcher = (RUN15 / "launch" / "submit_full.sh").read_text()
    assert 'usage: $0 <one-chain-proof.json> <five-chain-proof.json>' in launcher
    assert "--user-authorized-without-lifecycle-proofs" in launcher
    assert "aar.run15-lifecycle-proof-override/v1" in launcher
    assert "full-five-chain-5x50" in launcher
    assert '"${ONE_CHAIN_PROOF}" 1 one_chain_native_generation' in launcher
    assert '"${FIVE_CHAIN_PROOF}" 5 five_chain_lifecycle_check' in launcher
    assert "five-chain proof is not bound to the supplied one-chain proof" in launcher
    assert "autodata2_8-kimi26" in combined
    assert "steerability_8-kimi26" not in combined

    pipeline = (RUN15 / "slurm" / "pipeline.sbatch").read_text()
    assert "AAR_RUN15_LIFECYCLE_PROOF_POLICY" in pipeline
    assert "user_authorized_bypass" in pipeline
    assert "lifecycle_proof_override.json" in pipeline
    assert '.git_commit == $git_commit' in pipeline
    assert '.researcher_deployment == "autodata2_8-kimi26"' in pipeline
    assert "full five-chain Run 15 requires retryable continuation exhaustion" in pipeline
    assert "supervise_aar_multiteam.py" in pipeline
    assert "AAR_CONTROLLER_MAX_RESTARTS" in pipeline
    assert "AAR_RESUME_REUSE_EVALUATOR" in pipeline
    assert "controller-supervisor-%j.out" in pipeline

    recovery = (RUN15 / "recovery" / "resume_full.sh").read_text()
    assert 'lifecycle_proof_policy="$(sed -n' in recovery
    assert "retained lifecycle-proof policies disagree" in recovery
    assert "user_authorized_bypass)" in recovery
    assert "proof-gated attempt unexpectedly retains an override" in recovery
    assert "override attempt unexpectedly retains lifecycle proof" in recovery
    assert "aar.run15-lifecycle-proof-override/v1" in recovery
    assert '.git_commit == $git_commit' in recovery


def test_run15_uses_attempt_local_detached_source_snapshot() -> None:
    launcher = (RUN15 / "launch" / "submit_full.sh").read_text()
    pipeline = (RUN15 / "slurm" / "pipeline.sbatch").read_text()
    runtime = (ROOT / "scripts" / "aar_runtime_env.sh").read_text()

    assert 'SOURCE_REPO="${attempt}/runtime/aar-source"' in launcher
    assert '"${REPO}/scripts/create_pinned_source_snapshot.sh"' in launcher
    assert launcher.index("create_pinned_source_snapshot.sh") < launcher.index(
        "verify_kimi_endpoint.py"
    )
    assert launcher.index("create_pinned_source_snapshot.sh") < launcher.index(
        "sbatch --parsable"
    )
    assert 'SNAPSHOT_RUN_CONFIG="${SOURCE_REPO}/${RUN_CONFIG#"${REPO}/"}"' in launcher
    assert 'cmp -s -- "${RUN_CONFIG}" "${SNAPSHOT_RUN_CONFIG}"' in launcher
    assert 'export AAR_REPO="${SOURCE_REPO}" AAR_SOURCE_SNAPSHOT="${SOURCE_REPO}"' in launcher
    assert 'export AAR_TRUSTED_HARNESS_PY="${SHARED_HARNESS_PY}"' in launcher
    assert 'export HARNESS_PY="${SHARED_HARNESS_PY}" HARNESS_ENV="${SECRET_ENV}"' in launcher
    assert 'export WORKSPACE_DIR="${SOURCE_REPO}" PYTHONPATH="${SOURCE_REPO}"' in launcher
    assert 'export AAR_BENCHMARK_DOCS="${SOURCE_REPO}/benchmark_docs"' in launcher
    assert 'export BENCHMARK_DOCS_DIR="${SOURCE_REPO}/benchmark_docs"' in launcher
    assert 'export AAR_RUN_CONFIG="${SNAPSHOT_RUN_CONFIG}"' in launcher
    assert 'LLM_UNCERTAINTY_SRC="${SNAPSHOT_SOURCE_ROOT}/data"' in launcher
    assert 'AAR_REUSED_BASELINE="${SNAPSHOT_REUSED_BASELINE}"' in launcher
    assert 'source_snapshot_root=%s' in launcher
    assert 'source_snapshots_sha256=%s' in launcher
    assert (
        '"${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/'
        'run_15/slurm/pipeline.sbatch"'
    ) in launcher

    for required in (
        '[ "${REPO}" = "${SOURCE_SNAPSHOT}" ]',
        '[ "${REPO}" = "${ATTEMPT}/runtime/aar-source" ]',
        'branch --show-current',
        'rev-parse HEAD',
        'status --porcelain --untracked-files=all',
        '.git/objects/info/alternates',
        'source snapshot retains a remote',
        'Run 15 config is not source-pinned',
    ):
        assert required in pipeline
    assert 'export AAR_EXPECTED_COMMIT="${EXPECTED_COMMIT}"' in pipeline
    assert "export AAR_EXPECTED_BRANCH=autodata" not in pipeline
    assert "AAR_EXPECTED_COMMIT AAR_SOURCE_SNAPSHOT" in runtime


def test_run15_proof_validation_rejects_run14_and_stale_source(tmp_path: Path) -> None:
    expected_root = tmp_path / "run15_native_generation" / "canary_attempts"
    attempt = expected_root / "attempt"
    metadata = attempt / "metadata"
    metadata.mkdir(parents=True)
    proof_path = metadata / "canary_passed.json"
    config = RUN15 / "canary" / "one_chain_lifecycle_check" / "config" / "run.yaml"
    commit = "a" * 40
    proof = {
        "schema_version": 1,
        "status": "passed",
        "run_namespace": "run15_native_generation",
        "canary_git_commit": commit,
        "attempt_dir": str(attempt),
        "lifecycle_name": "one_chain_native_generation",
        "lifecycle_chain_count": 1,
        "run_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "max_sequential_target_generations": 256,
        "score_result_pair": True,
        "fail_closed_markers": True,
        "merge_manifest_retained": True,
        "ephemeral_merge_removed": True,
        "kimi_mcp_tool_roundtrip": True,
        "method_gpu_smoke": True,
        "adapter_reload_validation": True,
        "on_demand_evaluator": True,
        "evaluation_item_contract": True,
        "autodata_disabled": True,
        "prerequisite_proof_sha256": None,
    }

    def validate() -> subprocess.CompletedProcess[str]:
        proof_path.write_text(json.dumps(proof))
        return subprocess.run(
            [
                sys.executable,
                str(RUN15 / "canary" / "verify_run_15_canary.py"),
                "--validate-proof",
                str(proof_path),
                "--expected-chains",
                "1",
                "--expected-lifecycle",
                "one_chain_native_generation",
                "--expected-config",
                str(config),
                "--expected-commit",
                commit,
                "--expected-storage-root",
                str(expected_root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    assert validate().returncode == 0
    valid_proof = dict(proof)
    invalid_cases = (
        ("run_namespace", "run14_native_generation"),
        ("canary_git_commit", "b" * 40),
        ("lifecycle_name", "five_chain_lifecycle_check"),
        ("run_config_sha256", "0" * 64),
        ("max_sequential_target_generations", 255),
    )
    for field, invalid_value in invalid_cases:
        proof.clear()
        proof.update(valid_proof, **{field: invalid_value})
        rejected = validate()
        assert rejected.returncode != 0
        assert field in rejected.stderr


def test_run15_recovery_accepts_identical_and_telemetry_only_configs(
    tmp_path: Path,
) -> None:
    recovery_helper = RUN15 / "recovery" / "config_compatibility.sh"
    canonical = RUN15 / "config" / "run.yaml"
    identical = tmp_path / "identical.yaml"
    identical.write_bytes(canonical.read_bytes())
    telemetry_legacy = tmp_path / "telemetry-legacy.yaml"
    telemetry_legacy.write_text(
        "\n".join(
            line
            for line in canonical.read_text().splitlines()
            if line
            not in {
                "  # Emit vLLM scheduler throughput, request, prefix-cache, and KV-cache stats.",
                "  vllm_log_stats: true",
            }
        )
        + "\n"
    )
    continuation_legacy = tmp_path / "continuation-legacy.yaml"
    continuation_legacy.write_text(
        "\n".join(
            line
            for line in canonical.read_text().splitlines()
            if line
            not in {
                "  # A full five-chain run must advance to a fresh session when one Kimi",
                "  # conversation exhausts its bounded continuation budget.",
                "  continuation_exhaustion_retryable: true",
                "  max_continuations: 32",
                "  progress_stall_limit: 3",
                "  progress_stall_grace_continuations: 8",
            }
        )
        + "\n"
    )
    recovery_legacy = tmp_path / "recovery-legacy.yaml"
    recovery_lines: list[str] = []
    skipping_recovery = False
    for line in canonical.read_text().splitlines():
        if line == "recovery:":
            skipping_recovery = True
            continue
        if skipping_recovery and line and not line.startswith((" ", "#")):
            skipping_recovery = False
        if not skipping_recovery:
            recovery_lines.append(line)
    recovery_legacy.write_text("\n".join(recovery_lines) + "\n")
    incompatible = tmp_path / "incompatible.yaml"
    incompatible.write_text(canonical.read_text().replace("workers: 1", "workers: 2"))

    def compatible(retained: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; run15_recovery_config_compatible "$2" "$3"',
                "bash",
                str(recovery_helper),
                str(retained),
                str(canonical),
            ],
            env=os.environ,
            check=False,
            capture_output=True,
            text=True,
        )

    assert compatible(identical).returncode == 0
    assert compatible(telemetry_legacy).returncode == 0
    assert compatible(continuation_legacy).returncode == 0
    assert compatible(recovery_legacy).returncode == 0
    assert compatible(incompatible).returncode != 0


def test_run15_operator_scripts_are_executable_and_parse() -> None:
    scripts = [
        RUN15 / "launch" / "submit_full.sh",
        RUN15 / "slurm" / "pipeline.sbatch",
        RUN15 / "recovery" / "resume_full.sh",
        RUN15 / "recovery" / "finalize_scored_run.sh",
        RUN15
        / "canary"
        / "one_chain_lifecycle_check"
        / "launch"
        / "launch.sh",
        RUN15
        / "canary"
        / "five_chain_lifecycle_check"
        / "launch"
        / "launch.sh",
    ]
    for script in scripts:
        assert os.access(script, os.X_OK), script
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_run15_readmes_have_required_operator_sections() -> None:
    readmes = [
        RUN15 / "README.md",
        RUN15 / "canary" / "README.md",
        RUN15 / "canary" / "one_chain_lifecycle_check" / "README.md",
        RUN15 / "canary" / "five_chain_lifecycle_check" / "README.md",
    ]
    for readme in readmes:
        source = readme.read_text()
        for heading in (
            "## Goal",
            "## Context",
            "## Launch",
            "## Pass criteria",
            "## Stop criteria",
        ):
            assert heading in source, (readme, heading)

    root = readmes[0].read_text()
    assert "**Experiment code branch:** `autodata`" in root
    assert "## Model and execution roles" in root
    assert "`autodata2_8-kimi26`" in root
    assert "explicitly authorized direct full attempt" in root
