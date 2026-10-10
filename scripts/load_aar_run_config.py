#!/usr/bin/env python3
"""Validate an AAR run YAML and emit its runtime environment.

The schema intentionally covers operational settings that must be shared by
initial launches and recovery launches.  It is not the evaluator suite YAML,
which remains evaluator-private.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
from pathlib import Path
from typing import Any

import yaml


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _reject_unknown(values: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"unsupported {name} setting(s): {', '.join(unknown)}")


def _boolean(value: Any, name: str) -> str:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return "1" if value else "0"


def _integer(
    value: Any, name: str, *, minimum: int = 1, maximum: int | None = None
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        suffix = f" and {maximum}" if maximum is not None else ""
        raise ValueError(f"{name} must be between {minimum}{suffix}")
    return value


def _time_limit(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[1-9][0-9]*-)?(?:[0-9]|[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]",
        value,
    ):
        raise ValueError(f"{name} must be a Slurm time value such as 01:00:00")
    return value


def load_run_config(path: Path) -> dict[str, str]:
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("run config must be a mapping")
    _reject_unknown(
        payload,
        {
            "version",
            "lifecycle",
            "storage",
            "research",
            "training",
            "evaluation",
            "agent",
        },
        "top-level",
    )
    if payload.get("version") != 1:
        raise ValueError("run config version must be 1")

    lifecycle = _mapping(payload.get("lifecycle"), "lifecycle")
    storage = _mapping(payload.get("storage"), "storage")
    research = _mapping(payload.get("research"), "research")
    training = _mapping(payload.get("training"), "training")
    evaluation = _mapping(payload.get("evaluation"), "evaluation")
    agent = _mapping(payload.get("agent"), "agent")
    _reject_unknown(
        lifecycle, {"name", "prerequisite_chain_count"}, "lifecycle"
    )
    _reject_unknown(storage, {"root", "keep_checkpoints"}, "storage")
    _reject_unknown(
        research,
        {"seeds", "max_sessions_per_chain", "walltime_hours"},
        "research",
    )
    _reject_unknown(
        training, {"mode", "time_limit", "max_concurrent_jobs"}, "training"
    )
    _reject_unknown(
        evaluation,
        {
            "memory",
            "max_truncation_rate",
            "benchmarks",
            "items_per_benchmark",
            "workers",
            "gpus_per_worker",
            "time_limit",
            "idle_seconds",
            "on_demand",
        },
        "evaluation",
    )
    _reject_unknown(
        agent,
        {
            "backend",
            "turn_timeout_seconds",
            "preflight_timeout_seconds",
            "preflight_cache_ttl_seconds",
        },
        "agent",
    )

    environment: dict[str, str] = {}
    if "name" in lifecycle:
        name = lifecycle["name"]
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*", name
        ):
            raise ValueError("lifecycle.name must be a safe non-empty name")
        environment["AAR_LIFECYCLE_NAME"] = name
    if "prerequisite_chain_count" in lifecycle:
        prerequisite = lifecycle["prerequisite_chain_count"]
        if isinstance(prerequisite, bool) or not isinstance(prerequisite, int):
            raise ValueError("lifecycle.prerequisite_chain_count must be an integer")
        if prerequisite not in {0, 1}:
            raise ValueError(
                "lifecycle.prerequisite_chain_count must be zero or one"
            )
        environment["AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT"] = str(prerequisite)
    if "root" in storage:
        root = storage["root"]
        if not isinstance(root, str):
            raise ValueError("storage.root must be a string")
        user = os.environ.get("USER", "")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", user):
            raise ValueError("USER is missing or unsafe")
        root = root.replace("{user}", user)
        if re.search(r"\{[^{}]+\}", root):
            raise ValueError("storage.root supports only the {user} template")
        if not root.startswith("/"):
            raise ValueError("storage.root must be an absolute path")
        environment["AAR_RUN_STORAGE_ROOT"] = root.rstrip("/")
    if "keep_checkpoints" in storage:
        environment["AAR_KEEP_CHECKPOINTS"] = _boolean(
            storage["keep_checkpoints"], "storage.keep_checkpoints"
        )

    if "seeds" in research:
        seeds = research["seeds"]
        if not isinstance(seeds, list) or not seeds:
            raise ValueError("research.seeds must be a non-empty list")
        if any(
            not isinstance(seed, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", seed)
            for seed in seeds
        ):
            raise ValueError("research.seeds entries must be safe non-empty names")
        if len(set(seeds)) != len(seeds):
            raise ValueError("research.seeds entries must be unique")
        environment["AAR_RESEARCH_SEEDS"] = " ".join(seeds)
    if "max_sessions_per_chain" in research:
        environment["AAR_MAX_ITERATIONS_PER_CHAIN"] = str(
            _integer(
                research["max_sessions_per_chain"],
                "research.max_sessions_per_chain",
                maximum=10000,
            )
        )
    if "walltime_hours" in research:
        environment["AAR_CHAIN_HOURS"] = str(
            _integer(
                research["walltime_hours"],
                "research.walltime_hours",
                maximum=1000,
            )
        )

    if "mode" in training:
        mode = training["mode"]
        if mode != "one_step_gpu_preflight":
            raise ValueError("training.mode must be one_step_gpu_preflight")
        environment["AAR_METHOD_SMOKE"] = "1"
        environment["AAR_REQUIRE_METHOD_SMOKE"] = "1"
    if "time_limit" in training:
        environment["AAR_TRAIN_TIME"] = _time_limit(
            training["time_limit"], "training.time_limit"
        )
    if "max_concurrent_jobs" in training:
        environment["AAR_MAX_CONCURRENT_TRAIN_JOBS"] = str(
            _integer(
                training["max_concurrent_jobs"],
                "training.max_concurrent_jobs",
                maximum=32,
            )
        )

    if "memory" in evaluation:
        memory = evaluation["memory"]
        if memory == "max":
            memory = "0"
        elif isinstance(memory, int) and not isinstance(memory, bool):
            memory = str(memory)
        if not isinstance(memory, str) or not re.fullmatch(
            r"(?:0|[1-9][0-9]*[KMGTP]?)", memory
        ):
            raise ValueError("evaluation.memory must be max or a Slurm memory value")
        environment["AAR_EVAL_MEM"] = memory
    if "max_truncation_rate" in evaluation:
        rate = evaluation["max_truncation_rate"]
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            raise ValueError("evaluation.max_truncation_rate must be numeric")
        rate = float(rate)
        if not 0 <= rate <= 1:
            raise ValueError("evaluation.max_truncation_rate must be between 0 and 1")
        rendered_rate = format(rate, ".12g")
        environment["EVAL_MAX_TRUNCATION_RATE"] = rendered_rate
        environment["AAR_EXPECTED_MAX_TRUNCATION_RATE"] = rendered_rate
    if "benchmarks" in evaluation:
        benchmarks = evaluation["benchmarks"]
        if not isinstance(benchmarks, list) or not benchmarks:
            raise ValueError("evaluation.benchmarks must be a non-empty list")
        if any(
            not isinstance(benchmark, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", benchmark)
            for benchmark in benchmarks
        ):
            raise ValueError(
                "evaluation.benchmarks entries must be safe non-empty names"
            )
        if len(set(benchmarks)) != len(benchmarks):
            raise ValueError("evaluation.benchmarks entries must be unique")
        environment["AAR_SUITE_BENCHMARKS"] = ",".join(benchmarks)
    if "items_per_benchmark" in evaluation:
        environment["AAR_PUBLISH_FORCE_N"] = str(
            _integer(
                evaluation["items_per_benchmark"],
                "evaluation.items_per_benchmark",
                maximum=100000,
            )
        )
    if "workers" in evaluation:
        environment["AAR_EVAL_WORKERS"] = str(
            _integer(evaluation["workers"], "evaluation.workers", maximum=32)
        )
    if "gpus_per_worker" in evaluation:
        environment["AAR_EVAL_GPUS"] = str(
            _integer(
                evaluation["gpus_per_worker"],
                "evaluation.gpus_per_worker",
                maximum=64,
            )
        )
    if "time_limit" in evaluation:
        environment["AAR_EVAL_TIME"] = _time_limit(
            evaluation["time_limit"], "evaluation.time_limit"
        )
    if "idle_seconds" in evaluation:
        environment["AAR_EVAL_IDLE_SECONDS"] = str(
            _integer(
                evaluation["idle_seconds"],
                "evaluation.idle_seconds",
                maximum=604800,
            )
        )
    if "on_demand" in evaluation:
        environment["AAR_EVAL_ON_DEMAND"] = _boolean(
            evaluation["on_demand"], "evaluation.on_demand"
        )

    if "backend" in agent:
        backend = agent["backend"]
        if backend not in {"claude", "kimi"}:
            raise ValueError("agent.backend must be claude or kimi")
        environment["AAR_AGENT_BACKEND"] = backend
    if "turn_timeout_seconds" in agent:
        timeout = agent["turn_timeout_seconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, int):
            raise ValueError("agent.turn_timeout_seconds must be an integer")
        if not 1 <= timeout <= 86400:
            raise ValueError("agent.turn_timeout_seconds must be between 1 and 86400")
        environment["AAR_KIMI_TURN_TIMEOUT_SECONDS"] = str(timeout)
    if "preflight_timeout_seconds" in agent:
        environment["AAR_KIMI_PREFLIGHT_TIMEOUT_SECONDS"] = str(
            _integer(
                agent["preflight_timeout_seconds"],
                "agent.preflight_timeout_seconds",
                maximum=3600,
            )
        )
    if "preflight_cache_ttl_seconds" in agent:
        environment["AAR_KIMI_PREFLIGHT_CACHE_TTL_SECONDS"] = str(
            _integer(
                agent["preflight_cache_ttl_seconds"],
                "agent.preflight_cache_ttl_seconds",
                maximum=604800,
            )
        )

    return environment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    try:
        environment = load_run_config(args.config)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.error(str(error))
    for name, value in sorted(environment.items()):
        print(f"export {name}={shlex.quote(value)}")


if __name__ == "__main__":
    main()
