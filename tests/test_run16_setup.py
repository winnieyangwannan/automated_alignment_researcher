"""Fail-closed source contracts for the fresh Run 16 package."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUN16 = ROOT / "experiments" / "dishonest_sycophancy_concealing" / "run_16"


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


def test_run16_is_fresh_native_5x50_configuration() -> None:
    config_path = RUN16 / "config" / "run.yaml"
    config = yaml.safe_load(config_path.read_text())

    assert config["storage"]["root"] == (
        "/checkpoint/ram/aar/{user}/run16_native_generation"
    )
    assert config["research"] == {
        "seeds": ["alpha", "beta", "gamma", "delta", "epsilon"],
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
    assert config["agent"]["backend"] == "claude"

    environment = _resolved_environment(config_path)
    assert "export AAR_AUTODATA=0" in environment
    assert "export AAR_TARGET_SUCCESSFUL_ITERATIONS=50" in environment
    assert "export AAR_MAX_ITERATIONS_PER_CHAIN=60" in environment
    assert "export AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS=256" in environment
    assert "export EVAL_VLLM_LOG_STATS=1" in environment
    assert "export AAR_AGENT_BACKEND=claude" in environment


def test_run16_canaries_are_fresh_bounded_and_ordered() -> None:
    one = yaml.safe_load(
        (
            RUN16
            / "canary"
            / "one_chain_lifecycle_check"
            / "config"
            / "run.yaml"
        ).read_text()
    )
    five = yaml.safe_load(
        (
            RUN16
            / "canary"
            / "five_chain_lifecycle_check"
            / "config"
            / "run.yaml"
        ).read_text()
    )

    assert one["lifecycle"] == {
        "name": "one_chain_lifecycle_check",
        "prerequisite_chain_count": 0,
    }
    assert one["research"]["max_sessions_per_chain"] == 1
    assert one["evaluation"]["items_per_benchmark"] == 2
    assert one["evaluation"]["on_demand"] is True
    assert one["data_generation"]["max_sequential_target_generations"] == 256
    assert one["agent"]["backend"] == "claude"

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
    assert five["agent"]["backend"] == "claude"


def test_run16_launch_and_recovery_pin_claude_opus_48() -> None:
    operational = [
        RUN16 / "launch" / "submit_full.sh",
        RUN16 / "slurm" / "pipeline.sbatch",
        RUN16 / "recovery" / "resume_full.sh",
        RUN16 / "recovery" / "finalize_scored_run.sh",
        RUN16 / "recovery" / "finalize_scored_run.py",
        RUN16 / "canary" / "verify_run_16_canary.py",
        RUN16
        / "canary"
        / "one_chain_lifecycle_check"
        / "launch"
        / "launch.sh",
        RUN16
        / "canary"
        / "five_chain_lifecycle_check"
        / "launch"
        / "launch.sh",
    ]
    combined = "\n".join(path.read_text() for path in operational)

    assert "run_14" not in combined
    assert "RUN14" not in combined
    assert "run14" not in combined
    assert "run16_native_generation" in combined
    assert "AAR_RUN16_MODE" in combined
    assert "run16-gemma4-31b-opus48" in combined
    assert "AAR_RESUME_TEAM_PREFIX=\"run16-gemma4-31b-opus48-\"" in combined
    assert "AAR_AGENT_MODEL=claude-opus-4-8" in combined
    assert "AAR_EFFORT=max" in combined
    assert "research_model=claude-opus-4-8" in combined
    assert "claude_research_preflight" in combined
    assert "KIMI_" not in combined
    assert "steerability_8-kimi26" not in combined

    launcher = (RUN16 / "launch" / "submit_full.sh").read_text()
    assert 'usage: $0 <one-chain-proof.json> <five-chain-proof.json>' in launcher
    assert 'validate_lifecycle_proof "${ONE_CHAIN_PROOF}" 1' in launcher
    assert 'validate_lifecycle_proof "${FIVE_CHAIN_PROOF}" 5' in launcher
    assert "five-chain proof is not bound to the supplied one-chain proof" in launcher


def test_run16_operator_scripts_are_executable_and_parse() -> None:
    scripts = [
        RUN16 / "launch" / "submit_full.sh",
        RUN16 / "slurm" / "pipeline.sbatch",
        RUN16 / "recovery" / "resume_full.sh",
        RUN16 / "recovery" / "finalize_scored_run.sh",
        RUN16
        / "canary"
        / "one_chain_lifecycle_check"
        / "launch"
        / "launch.sh",
        RUN16
        / "canary"
        / "five_chain_lifecycle_check"
        / "launch"
        / "launch.sh",
    ]
    for script in scripts:
        assert os.access(script, os.X_OK), script
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_run16_readmes_have_required_operator_sections() -> None:
    readmes = [
        RUN16 / "README.md",
        RUN16 / "canary" / "README.md",
        RUN16 / "canary" / "one_chain_lifecycle_check" / "README.md",
        RUN16 / "canary" / "five_chain_lifecycle_check" / "README.md",
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
    assert "not launched" in root
