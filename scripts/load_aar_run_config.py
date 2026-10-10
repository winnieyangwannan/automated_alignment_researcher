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


def load_run_config(path: Path) -> dict[str, str]:
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("run config must be a mapping")
    _reject_unknown(payload, {"version", "storage", "evaluation", "agent"}, "top-level")
    if payload.get("version") != 1:
        raise ValueError("run config version must be 1")

    storage = _mapping(payload.get("storage"), "storage")
    evaluation = _mapping(payload.get("evaluation"), "evaluation")
    agent = _mapping(payload.get("agent"), "agent")
    _reject_unknown(storage, {"root", "keep_checkpoints"}, "storage")
    _reject_unknown(evaluation, {"memory", "max_truncation_rate"}, "evaluation")
    _reject_unknown(agent, {"backend", "turn_timeout_seconds"}, "agent")

    environment: dict[str, str] = {}
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
