"""Tests for declarative operational AAR run configuration."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUN10 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_10"
RUN14 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_14"
LIFECYCLE = RUN10 / "canary" / "one_chain_lifecycle_check"


def test_run10_config_has_quota_safe_production_defaults() -> None:
    config = yaml.safe_load((RUN10 / "config" / "run.yaml").read_text())

    assert config["storage"] == {
        "root": "/checkpoint/ram/aar/{user}/run10_kimi",
        "keep_checkpoints": False,
    }
    assert config["evaluation"]["memory"] == "max"
    assert config["evaluation"]["max_truncation_rate"] == 0.20
    assert config["agent"] == {
        "backend": "kimi",
        "turn_timeout_seconds": 1800,
    }


def test_run10_config_emits_validated_environment() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "load_aar_run_config.py"),
            str(RUN10 / "config" / "run.yaml"),
        ],
        env={**os.environ, "USER": "test-user"},
        check=True,
        capture_output=True,
        text=True,
    )

    assert (
        "export AAR_RUN_STORAGE_ROOT=/checkpoint/ram/aar/test-user/run10_kimi"
        in result.stdout
    )
    assert "export AAR_KEEP_CHECKPOINTS=0" in result.stdout
    assert "export AAR_EVAL_MEM=0" in result.stdout
    assert "export EVAL_MAX_TRUNCATION_RATE=0.2" in result.stdout
    assert "export AAR_EXPECTED_MAX_TRUNCATION_RATE=0.2" in result.stdout
    assert "export AAR_KIMI_TURN_TIMEOUT_SECONDS=1800" in result.stdout


def test_lifecycle_config_is_bounded_and_emits_runtime_contract() -> None:
    config_path = LIFECYCLE / "config" / "run.yaml"
    config = yaml.safe_load(config_path.read_text())

    assert config["lifecycle"] == {
        "name": "one_chain_lifecycle_check",
        "prerequisite_chain_count": 0,
    }

    assert config["research"] == {
        "seeds": ["lifecycle"],
        "max_sessions_per_chain": 1,
        "walltime_hours": 2,
    }
    assert config["training"] == {
        "mode": "one_step_gpu_preflight",
        "time_limit": "00:15:00",
        "max_concurrent_jobs": 1,
    }
    assert config["evaluation"]["benchmarks"] == ["verbalized_ece"]
    assert config["evaluation"]["items_per_benchmark"] == 2
    assert config["evaluation"]["workers"] == 1
    assert config["evaluation"]["gpus_per_worker"] == 1
    assert config["evaluation"]["on_demand"] is True
    assert config["agent"] == {
        "backend": "kimi",
        "turn_timeout_seconds": 1800,
        "preflight_timeout_seconds": 300,
        "preflight_cache_ttl_seconds": 21600,
    }

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
    expected = {
        "export AAR_RESEARCH_SEEDS=lifecycle",
        "export AAR_MAX_ITERATIONS_PER_CHAIN=1",
        "export AAR_CHAIN_HOURS=2",
        "export AAR_METHOD_SMOKE=1",
        "export AAR_TRAIN_TIME=00:15:00",
        "export AAR_MAX_CONCURRENT_TRAIN_JOBS=1",
        "export AAR_LIFECYCLE_NAME=one_chain_lifecycle_check",
        "export AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT=0",
        "export AAR_SUITE_BENCHMARKS=verbalized_ece",
        "export AAR_PUBLISH_FORCE_N=2",
        "export AAR_EVAL_WORKERS=1",
        "export AAR_EVAL_GPUS=1",
        "export AAR_EVAL_TIME=01:00:00",
        "export AAR_EVAL_IDLE_SECONDS=120",
        "export AAR_EVAL_ON_DEMAND=1",
        "export AAR_KIMI_PREFLIGHT_TIMEOUT_SECONDS=300",
        "export AAR_KIMI_PREFLIGHT_CACHE_TTL_SECONDS=21600",
    }
    assert expected <= set(result.stdout.splitlines())


def test_five_chain_lifecycle_config_is_bounded_and_concurrent() -> None:
    config_path = (
        RUN10 / "canary" / "five_chain_lifecycle_check" / "config" / "run.yaml"
    )
    config = yaml.safe_load(config_path.read_text())
    assert config["lifecycle"] == {
        "name": "five_chain_lifecycle_check",
        "prerequisite_chain_count": 1,
    }
    assert config["research"]["seeds"] == [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
    ]
    assert config["research"]["max_sessions_per_chain"] == 1
    assert config["training"]["max_concurrent_jobs"] == 5
    assert config["evaluation"]["workers"] == 5
    assert config["evaluation"]["gpus_per_worker"] == 1
    assert config["evaluation"]["items_per_benchmark"] == 2

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/load_aar_run_config.py"),
            str(config_path),
        ],
        env={**os.environ, "USER": "test-user"},
        check=True,
        capture_output=True,
        text=True,
    )
    assert "export AAR_MAX_CONCURRENT_TRAIN_JOBS=5" in result.stdout
    assert "export AAR_EVAL_WORKERS=5" in result.stdout
    assert "export AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT=1" in result.stdout


def test_evaluator_defaults_to_all_allocated_node_memory() -> None:
    launcher = (ROOT / "scripts" / "launch_eval_worker.sh").read_text()
    worker = (ROOT / "scripts" / "eval_worker.sh").read_text()

    assert 'MEMORY="${AAR_EVAL_MEM:-0}"' in launcher
    assert '--mem="${MEMORY}"' in launcher
    assert "#SBATCH --mem=0" in worker


def test_training_prunes_redundant_staging_by_default() -> None:
    trainer = (ROOT / "scripts" / "slurm_train_submit.sh").read_text()
    multidimensional = (ROOT / "replication" / "env_multidimensional.sh").read_text()
    legacy = (ROOT / "replication" / "env_v0.sh").read_text()

    assert 'if [ "${AAR_KEEP_CHECKPOINTS:-0}" != "1" ]; then' in trainer
    assert 'rm -rf -- "${STAGING:?}"' in trainer
    assert "retaining staging checkpoint" in trainer
    default = 'AAR_KEEP_CHECKPOINTS="${AAR_KEEP_CHECKPOINTS:-0}"'
    assert default in multidimensional
    assert default in legacy


def test_run14_declares_native_data_generation_and_5x50_budget() -> None:
    config_path = RUN14 / "config" / "run.yaml"
    config = yaml.safe_load(config_path.read_text())

    assert config["data_generation"] == {"backend": "native"}
    assert config["research"]["seeds"] == [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
    ]
    assert config["research"]["target_score_result_pairs"] == 50
    assert config["research"]["max_sessions_per_chain"] == 60

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/load_aar_run_config.py"),
            str(config_path),
        ],
        env={**os.environ, "USER": "test-user"},
        check=True,
        capture_output=True,
        text=True,
    )

    assert "export AAR_AUTODATA=0" in result.stdout
    assert "export AAR_TARGET_SUCCESSFUL_ITERATIONS=50" in result.stdout
    assert "export AAR_MAX_ITERATIONS_PER_CHAIN=60" in result.stdout


def test_run14_full_launch_requires_and_binds_both_lifecycle_proofs() -> None:
    launcher = (RUN14 / "launch" / "submit_full.sh").read_text()

    assert 'usage: $0 <one-chain-proof.json> <five-chain-proof.json>' in launcher
    assert 'validate_lifecycle_proof "${ONE_CHAIN_PROOF}" 1' in launcher
    assert 'validate_lifecycle_proof "${FIVE_CHAIN_PROOF}" 5' in launcher
    assert "prerequisite_proof_sha256" in launcher
    assert "five-chain proof is not bound to the supplied one-chain proof" in launcher
    assert "one_chain_lifecycle_passed.json" in launcher
    assert "five_chain_lifecycle_passed.json" in launcher
    assert "lifecycle_proofs.sha256" in launcher


def test_run14_launch_path_fails_closed_without_autodata() -> None:
    launcher = (RUN14 / "launch" / "submit_full.sh").read_text()
    pipeline = (RUN14 / "slurm" / "pipeline.sbatch").read_text()
    combined = launcher + pipeline

    assert combined.count('export AAR_AUTODATA=0') >= 2
    assert '"${AAR_AUTODATA:?missing data-generation backend}" = 0' in launcher
    assert '"${AAR_AUTODATA:?missing data-generation backend}" = 0' in pipeline
    assert "AAR_AUTODATA=1" not in combined
    assert "autodata_run_config" not in combined
    assert "AAR_AUTODATA_PLUGIN_ROOT" not in combined
    assert combined.count(
        "AAR_KIMI_SERVE_DEPLOYMENT=steerability_8-kimi26"
    ) >= 2
    assert "AAR_KIMI_SERVE_DEPLOYMENT=aar_8-kimi26" not in combined


def test_run14_canary_stages_smoke_adapter_before_on_demand_evaluation() -> None:
    config = yaml.safe_load(
        (
            RUN14
            / "canary"
            / "one_chain_lifecycle_check"
            / "config"
            / "run.yaml"
        ).read_text()
    )
    launcher = (RUN14 / "launch" / "submit_full.sh").read_text()
    pipeline = (RUN14 / "slurm" / "pipeline.sbatch").read_text()

    assert config["training"]["mode"] == "one_step_gpu_preflight"
    assert config["evaluation"]["on_demand"] is True
    assert 'pipeline_time=04:00:00' in launcher
    assert "monitor_method_smoke.py" in pipeline
    assert "from aar.transport import put_model" in pipeline
    assert pipeline.index("monitor_method_smoke.py") < pipeline.index(
        "from aar.transport import put_model"
    ) < pipeline.index("launch-on-demand-evaluator.txt")


def test_run14_five_chain_lifecycle_is_bounded_and_keeps_queue_settings() -> None:
    lifecycle = RUN14 / "canary" / "five_chain_lifecycle_check"
    config_path = lifecycle / "config" / "run.yaml"
    config = yaml.safe_load(config_path.read_text())

    assert config["lifecycle"] == {
        "name": "five_chain_lifecycle_check",
        "prerequisite_chain_count": 1,
    }
    assert config["research"] == {
        "seeds": ["alpha", "beta", "gamma", "delta", "epsilon"],
        "target_score_result_pairs": 1,
        "max_sessions_per_chain": 1,
        "walltime_hours": 2,
    }
    assert config["training"] == {
        "mode": "one_step_gpu_preflight",
        "time_limit": "00:15:00",
        "max_concurrent_jobs": 1,
    }
    assert config["evaluation"]["workers"] == 1
    assert config["evaluation"]["gpus_per_worker"] == 1
    assert config["evaluation"]["items_per_benchmark"] == 2
    assert config["evaluation"]["on_demand"] is True
    assert config["data_generation"] == {"backend": "native"}

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/load_aar_run_config.py"), str(config_path)],
        env={**os.environ, "USER": "test-user"},
        check=True,
        capture_output=True,
        text=True,
    )
    expected = {
        "export AAR_LIFECYCLE_NAME=five_chain_lifecycle_check",
        "export AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT=1",
        "export AAR_RESEARCH_SEEDS='alpha beta gamma delta epsilon'",
        "export AAR_TARGET_SUCCESSFUL_ITERATIONS=1",
        "export AAR_MAX_CONCURRENT_TRAIN_JOBS=1",
        "export AAR_EVAL_WORKERS=1",
        "export AAR_EVAL_GPUS=1",
        "export AAR_AUTODATA=0",
    }
    assert expected <= set(result.stdout.splitlines())


def test_run14_five_chain_lifecycle_binds_proof_and_stages_every_adapter() -> None:
    lifecycle = RUN14 / "canary" / "five_chain_lifecycle_check"
    wrapper = (lifecycle / "launch" / "launch.sh").read_text()
    submitter = (RUN14 / "launch" / "submit_full.sh").read_text()
    pipeline = (RUN14 / "slurm" / "pipeline.sbatch").read_text()
    verifier = (RUN14 / "canary" / "verify_run_14_canary.py").read_text()

    assert '"$#" -eq 1' in wrapper
    assert "AAR_RUN14_PREREQUISITE_PROOF" in wrapper
    assert "validate_lifecycle_proof" in submitter
    assert "prerequisite_lifecycle_passed.json" in submitter
    assert "merge-base --is-ancestor" in submitter
    assert '"${#seeds[@]}" -eq 1 ] || [ "${#seeds[@]}" -eq 5' in pipeline
    assert 'launch_team.sh" "${AAR_RESEARCH_SEEDS}"' in pipeline
    assert '--expected-chains "${#seeds[@]}"' in pipeline
    assert 'for index in "${!run_ids[@]}"' in pipeline
    assert pipeline.index("monitor_method_smoke.py") < pipeline.index(
        'for index in "${!run_ids[@]}"'
    ) < pipeline.index("launch-on-demand-evaluator.txt")
    assert '"autodata_disabled": autodata_disabled' in verifier
    assert 'if chain_count == 5 and prerequisite_hash is None' in verifier


def test_run14_five_chain_proof_accepts_one_shared_evaluator(tmp_path: Path) -> None:
    attempt = tmp_path / "five"
    metadata = attempt / "metadata"
    team = attempt / "aar_teams" / "team"
    eval_private = team / "_eval_private"
    manifests = eval_private / "merge_manifests"
    for path in (metadata, team / "scores", team / "forum", manifests):
        path.mkdir(parents=True, exist_ok=True)

    (metadata / "submission.txt").write_text(
        "git_commit=abc123\n"
        "lifecycle_name=five_chain_lifecycle_check\n"
        "data_generation_backend=native\n"
        "autodata=0\n"
    )
    (metadata / "run.yaml").write_text(
        "research:\n"
        "  seeds: [alpha, beta, gamma, delta, epsilon]\n"
        "evaluation:\n"
        "  workers: 1\n"
        "data_generation:\n"
        "  backend: native\n"
    )
    (metadata / "kimi_mcp_preflight.json").write_text(
        json.dumps({"mcp_tool_roundtrip": True})
    )
    runs = [
        {
            "run_id": f"run-{index}",
            "real_gpu_smoke": True,
            "adapter_reload_validation": True,
        }
        for index in range(5)
    ]
    (metadata / "method_smoke_passed.json").write_text(json.dumps({"runs": runs}))
    (metadata / "lifecycle_evaluation_contract.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "expected_benchmarks": ["verbalized_ece"],
                "expected_items_per_benchmark": 2,
            }
        )
    )
    (metadata / "children.env").write_text(
        "on_demand_evaluator=1\n"
        "evaluator_jobs=123\n"
        "expected_evaluator_jobs=1\n"
    )
    prerequisite = metadata / "prerequisite_lifecycle_passed.json"
    prerequisite.write_text('{"status":"passed","lifecycle_chain_count":1}\n')
    for index in range(5):
        run_id = f"run-{index}"
        (team / "scores" / f"{run_id}.json").write_text(
            json.dumps({"per_benchmark": {"verbalized_ece": {"n": 2}}})
        )
        (team / "forum" / f"{run_id}.json").write_text(
            json.dumps({"run_id": run_id})
        )
        (manifests / f"{run_id}.json").write_text("{}\n")
    (eval_private / "eval_worker_123.out").write_text(
        "backend=vllm image=docker.io/vllm/vllm-openai:v0.25.1 "
        "lora_strategy=merged_checkpoint\n"
        "runtime backend=vllm version=0.25.1 language_model_only=True\n"
        + "removed ephemeral merged checkpoint\n" * 5
    )

    verifier = RUN14 / "canary" / "verify_run_14_canary.py"
    subprocess.run([sys.executable, str(verifier), str(attempt)], check=True)
    proof = json.loads((metadata / "canary_passed.json").read_text())
    assert proof["status"] == "passed"
    assert proof["lifecycle_chain_count"] == 5
    assert proof["successful_lifecycle_runs"] == 5
    assert proof["on_demand_evaluator"] is True
    assert proof["autodata_disabled"] is True
    assert proof["prerequisite_proof_sha256"] == hashlib.sha256(
        prerequisite.read_bytes()
    ).hexdigest()


def test_run14_finding_recovery_is_scored_run_only() -> None:
    finalizer = (
        RUN14 / "recovery" / "finalize_scored_run.py"
    ).read_text()
    launcher = (
        RUN14 / "recovery" / "finalize_scored_run.sh"
    ).read_text()

    assert '"AAR_RESUME_APPROVED_PROPOSAL": "1"' in finalizer
    assert '"AAR_REQUIRE_SUCCESSFUL_ITERATIONS": "1"' in finalizer
    assert '"AAR_AUTODATA": "0"' in finalizer
    assert 'completion_tool="share_finding"' in finalizer
    assert "force_completion_tool_first_turn=True" in finalizer
    assert "Recover only the missing final finding" in finalizer
    assert "Do not call literature, edit files, submit a " in finalizer
    assert "train, or evaluate" in finalizer
    assert 'export AAR_AUTODATA=0' in launcher
    assert "finalize_scored_run.py" in launcher
    assert "one_chain_lifecycle_check/config/run.yaml" in launcher
