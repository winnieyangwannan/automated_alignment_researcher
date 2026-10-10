"""Tests for declarative operational AAR run configuration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUN10 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_10"


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
