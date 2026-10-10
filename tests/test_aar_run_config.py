"""Tests for declarative operational AAR run configuration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUN10 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_10"
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
