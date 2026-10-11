"""Compile strict AutoData profile/run YAML into immutable runtime artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

import yaml

from aar.autodata_campaign_policy import target_environment_from_manifest
from aar.infrastructure.autodata_contract import (
    training_data_contract_from_campaign_policy,
    validate_training_data_contract,
)


PROFILE_SCHEMA = "aar.autodata.runtime-profile/v2"
RUN_SCHEMA = "aar.autodata.run-config/v1"
RESOLVED_SCHEMA = "aar.autodata.resolved-run-config/v1"
DEFAULT_TARGET_FEEDBACK_MAX_ATTEMPTS = 5
DEFAULT_JUDGE_FORMAT_MAX_ATTEMPTS = 2
JUDGE_STRUCTURED_OUTPUT_MODES = {"prompt_json"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


def _mapping(value: Any, label: str, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    missing = expected - set(value)
    unexpected = set(value) - expected
    if missing or unexpected:
        raise ValueError(
            f"{label} keys differ; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    return dict(value)


def _mapping_with_optional(
    value: Any,
    label: str,
    required: set[str],
    optional: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    missing = required - set(value)
    unexpected = set(value) - required - optional
    if missing or unexpected:
        raise ValueError(
            f"{label} keys differ; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    return dict(value)


def _text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        raise ValueError(f"{label} must be single-line text")
    if not allow_empty and not value:
        raise ValueError(f"{label} must be nonempty")
    return value


def _identifier(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _IDENTIFIER.fullmatch(text):
        raise ValueError(f"{label} is invalid")
    return text


def _positive_integer(value: Any, label: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} must be at most {maximum}")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _decimal(value: Any, label: str) -> str:
    text = _text(value, label)
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"{label} must be a decimal string") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return text


def _fraction(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not 0 < result <= 1:
        raise ValueError(f"{label} must be greater than zero and at most one")
    return result


def _bounded_fraction(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not 0 <= result <= 1:
        raise ValueError(f"{label} must be between zero and one")
    return result


def _storage_root(value: Any, label: str) -> str:
    root = _text(value, label)
    user = os.environ.get("USER", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", user):
        raise ValueError("USER is missing or unsafe")
    root = root.replace("{user}", user)
    if re.search(r"\{[^{}]+\}", root):
        raise ValueError(f"{label} supports only the {{user}} template")
    path = Path(root)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be an absolute path without traversal")
    return root.rstrip("/") or "/"


def _slurm_memory(value: Any, label: str) -> str:
    if value == "max":
        return "0"
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]*[KMGTP]?)", value
    ):
        raise ValueError(f"{label} must be max or a Slurm memory value")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _judge_rubric_identity(
    repo: Path, run: Mapping[str, Any]
) -> tuple[Path, dict[str, str]]:
    recipe_root = (repo / str(run["recipe_root"])).resolve(strict=True)
    if not recipe_root.is_dir() or repo not in recipe_root.parents:
        raise ValueError("recipe_root must resolve to a repository directory")
    relative = Path(str(run["training_contract"]["judge_rubric"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("judge rubric must be relative to recipe_root")
    if relative != Path("recipe/judge_rubric.json"):
        raise ValueError("recipe task requires recipe/judge_rubric.json")
    unresolved_rubric_path = recipe_root / relative
    if unresolved_rubric_path.is_symlink():
        raise ValueError("judge rubric must not be a symlink")
    rubric_path = unresolved_rubric_path.resolve(strict=True)
    if not rubric_path.is_file() or recipe_root not in rubric_path.parents:
        raise ValueError("judge rubric must resolve to a regular recipe file")
    try:
        rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("judge rubric is not valid JSON") from error
    if (
        not isinstance(rubric, dict)
        or rubric.get("schema") != "aar.autodata.judge-rubric/v1"
        or not isinstance(rubric.get("version"), str)
        or not rubric["version"].strip()
    ):
        raise ValueError("judge rubric identity is invalid")
    pipeline = json.loads(
        (recipe_root / "autodata.pipeline.json").read_text(encoding="utf-8")
    )
    protected = pipeline.get("protected_paths") if isinstance(pipeline, dict) else None
    if not isinstance(protected, list) or relative.as_posix() not in protected:
        raise ValueError("judge rubric is not protected by the AutoData pipeline")
    return rubric_path, {
        "version": rubric["version"].strip(),
        "sha256": _sha256(rubric_path),
    }


def _load_yaml(path: Path, label: str) -> dict[str, Any]:
    if path.expanduser().is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} must be a real file")
    try:
        value = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ValueError(f"{label} is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one mapping")
    return value


def _provider(
    value: Any, label: str, *, route: bool, host_header: bool = False
) -> dict[str, Any]:
    expected = {
        "model",
        "max_input_tokens",
        "max_output_tokens",
        "timeout_seconds",
        "input_usd_per_million",
        "output_usd_per_million",
    }
    if route:
        expected.add("url")
    if host_header:
        expected.add("host_header")
    data = _mapping(value, label, expected)
    result: dict[str, Any] = {
        "model": _text(data["model"], f"{label}.model"),
        "max_input_tokens": _positive_integer(
            data["max_input_tokens"], f"{label}.max_input_tokens", maximum=1_000_000
        ),
        "max_output_tokens": _positive_integer(
            data["max_output_tokens"], f"{label}.max_output_tokens", maximum=65_536
        ),
        "timeout_seconds": _positive_integer(
            data["timeout_seconds"], f"{label}.timeout_seconds", maximum=3_600
        ),
        "input_usd_per_million": _decimal(
            data["input_usd_per_million"], f"{label}.input_usd_per_million"
        ),
        "output_usd_per_million": _decimal(
            data["output_usd_per_million"], f"{label}.output_usd_per_million"
        ),
    }
    if route:
        url = _text(data["url"], f"{label}.url").rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"{label}.url must be absolute HTTP(S)")
        result["url"] = url
    if host_header:
        result["host_header"] = _text(
            data["host_header"], f"{label}.host_header", allow_empty=True
        )
    return result


def load_runtime_profile(path: Path) -> dict[str, Any]:
    root = _mapping(
        _load_yaml(path, "AutoData runtime profile"),
        "AutoData runtime profile",
        {"schema", "name", "target", "broker", "execution", "providers"},
    )
    if root["schema"] != PROFILE_SCHEMA:
        raise ValueError(f"unsupported runtime profile schema: {root['schema']!r}")
    target = _mapping(
        root["target"],
        "target",
        {
            "enabled",
            "binding_policy",
            "update_after_promotion",
            "require_checkpoint_hash",
            "require_completion_probe",
            "require_challenge_provenance",
        },
    )
    for key in (
        "enabled",
        "update_after_promotion",
        "require_checkpoint_hash",
        "require_completion_probe",
        "require_challenge_provenance",
    ):
        target[key] = _boolean(target[key], f"target.{key}")
    target["binding_policy"] = _text(target["binding_policy"], "target.binding_policy")
    if target != {
        "enabled": True,
        "binding_policy": "previous-promoted-incumbent",
        "update_after_promotion": True,
        "require_checkpoint_hash": True,
        "require_completion_probe": True,
        "require_challenge_provenance": True,
    }:
        raise ValueError(
            "target-aware profile must enable every fail-closed target gate"
        )
    broker = _mapping(
        root["broker"],
        "broker",
        {
            "runner",
            "environment",
            "image",
            "expected_image_id",
            "max_cpus",
            "max_memory_mb",
        },
    )
    broker = {
        "runner": _text(broker["runner"], "broker.runner"),
        "environment": _text(broker["environment"], "broker.environment"),
        "image": _text(broker["image"], "broker.image"),
        "expected_image_id": _text(
            broker["expected_image_id"], "broker.expected_image_id"
        ),
        "max_cpus": _positive_integer(broker["max_cpus"], "broker.max_cpus"),
        "max_memory_mb": _positive_integer(
            broker["max_memory_mb"], "broker.max_memory_mb"
        ),
    }
    if broker["runner"] != "local-bwrap":
        raise ValueError("target-aware local profile requires local-bwrap")
    execution = _mapping(
        root["execution"],
        "execution",
        {
            "concurrency_per_chain",
            "model_request_max_attempts",
            "lifecycle_supervised",
            "reuse_policy",
        },
    )
    execution = {
        "concurrency_per_chain": _positive_integer(
            execution["concurrency_per_chain"],
            "execution.concurrency_per_chain",
            maximum=64,
        ),
        "model_request_max_attempts": _positive_integer(
            execution["model_request_max_attempts"],
            "execution.model_request_max_attempts",
            maximum=5,
        ),
        "lifecycle_supervised": _boolean(
            execution["lifecycle_supervised"], "execution.lifecycle_supervised"
        ),
        "reuse_policy": _text(execution["reuse_policy"], "execution.reuse_policy"),
    }
    providers = _mapping(
        root["providers"], "providers", {"generator", "judge", "target"}
    )
    return {
        "schema": PROFILE_SCHEMA,
        "name": _identifier(root["name"], "profile name"),
        "target": target,
        "broker": broker,
        "execution": execution,
        "providers": {
            "generator": _provider(
                providers["generator"],
                "providers.generator",
                route=True,
                host_header=True,
            ),
            "judge": _provider(providers["judge"], "providers.judge", route=True),
            "target": _provider(providers["target"], "providers.target", route=False),
        },
    }


def load_run_config(path: Path) -> dict[str, Any]:
    loaded = _load_yaml(path, "AutoData run config")
    if isinstance(loaded, dict) and "generation" not in loaded:
        loaded = {**loaded, "generation": {}}
    if isinstance(loaded, dict) and "bootstrap_canary" not in loaded:
        loaded = {**loaded, "bootstrap_canary": {"stop_after": "production"}}
    root_keys = {
        "schema",
        "run_id",
        "chains",
        "target_pairs_per_chain",
        "bootstrap_canary",
        "deployments",
        "budget",
        "authoring",
        "generation",
        "meta_optimization",
        "production",
        "storage",
        "evaluation",
        "agent",
        "recipe_root",
        "training_contract",
    }
    if "runtime_profile" in loaded:
        root_keys.add("runtime_profile")
    if "stage_timing" in loaded:
        root_keys.add("stage_timing")
    root = _mapping(
        loaded,
        "AutoData run config",
        root_keys,
    )
    if root["schema"] != RUN_SCHEMA:
        raise ValueError(f"unsupported run config schema: {root['schema']!r}")
    if not isinstance(root["chains"], list) or not root["chains"]:
        raise ValueError("chains must be a nonempty list")
    chains = [_identifier(value, "chain") for value in root["chains"]]
    if len(chains) != len(set(chains)):
        raise ValueError("chains must be unique")
    bootstrap_canary = _mapping(
        root["bootstrap_canary"],
        "bootstrap_canary",
        {"stop_after"},
    )
    if bootstrap_canary["stop_after"] not in {"production", "training_smoke"}:
        raise ValueError(
            "bootstrap_canary.stop_after must be production or training_smoke"
        )
    deployments = _mapping(
        root["deployments"], "deployments", {"researcher_kimi", "generator_kimi"}
    )
    budget = _mapping(root["budget"], "budget", {"max_cost_usd"})
    authoring = _mapping(root["authoring"], "authoring", {"max_wall_seconds"})
    authoring = {
        "max_wall_seconds": _positive_integer(
            authoring["max_wall_seconds"],
            "authoring.max_wall_seconds",
            maximum=2_592_000,
        )
    }
    stage_timing = None
    if "stage_timing" in root:
        stage_timing = _mapping(
            root["stage_timing"],
            "stage_timing",
            {"mode", "native_schema_wall_seconds"},
        )
        if stage_timing["mode"] != "observe_only":
            raise ValueError("stage_timing.mode must be observe_only")
        stage_timing = {
            "mode": "observe_only",
            "native_schema_wall_seconds": _positive_integer(
                stage_timing["native_schema_wall_seconds"],
                "stage_timing.native_schema_wall_seconds",
                maximum=2_592_000,
            ),
        }
        if authoring["max_wall_seconds"] != stage_timing["native_schema_wall_seconds"]:
            raise ValueError(
                "observe-only authoring max_wall_seconds must equal the native "
                "schema wall value"
            )
    generation = root["generation"]
    if not isinstance(generation, dict):
        raise ValueError("generation must be a mapping")
    unexpected_generation = set(generation) - {
        "target_feedback_max_attempts",
        "judge_format_max_attempts",
        "judge_structured_output_mode",
    }
    if unexpected_generation:
        raise ValueError(
            "generation keys differ; missing=[], "
            f"unexpected={sorted(unexpected_generation)}"
        )
    judge_structured_output_mode = _identifier(
        generation.get("judge_structured_output_mode", "prompt_json"),
        "generation.judge_structured_output_mode",
    )
    if judge_structured_output_mode not in JUDGE_STRUCTURED_OUTPUT_MODES:
        raise ValueError(
            "generation.judge_structured_output_mode is not operator-supported"
        )
    generation = {
        "target_feedback_max_attempts": _positive_integer(
            generation.get(
                "target_feedback_max_attempts",
                DEFAULT_TARGET_FEEDBACK_MAX_ATTEMPTS,
            ),
            "generation.target_feedback_max_attempts",
            maximum=5,
        ),
        "judge_format_max_attempts": _positive_integer(
            generation.get(
                "judge_format_max_attempts",
                DEFAULT_JUDGE_FORMAT_MAX_ATTEMPTS,
            ),
            "generation.judge_format_max_attempts",
            maximum=2,
        ),
        "judge_structured_output_mode": judge_structured_output_mode,
    }
    meta = _mapping(
        root["meta_optimization"],
        "meta_optimization",
        {
            "maximum_iterations",
            "minimum_iterations",
            "early_stop_patience",
            "tuning_tasks",
            "validation_tasks",
            "test_tasks",
        },
    )
    meta = {
        key: _positive_integer(value, f"meta_optimization.{key}")
        for key, value in meta.items()
    }
    if meta["minimum_iterations"] > meta["maximum_iterations"]:
        raise ValueError("minimum meta-optimization iterations exceed maximum")
    production = _mapping(
        root["production"],
        "production",
        {
            "required_rows",
            "initial_tasks",
            "minimum_successful_task_fraction",
        },
    )
    production = {
        "required_rows": _positive_integer(
            production["required_rows"], "production.required_rows"
        ),
        "initial_tasks": _positive_integer(
            production["initial_tasks"], "production.initial_tasks"
        ),
        "minimum_successful_task_fraction": _fraction(
            production["minimum_successful_task_fraction"],
            "production.minimum_successful_task_fraction",
        ),
    }
    if production["required_rows"] > production["initial_tasks"]:
        raise ValueError("production source tasks must cover required rows")
    storage = _mapping_with_optional(
        root["storage"],
        "storage",
        {"root", "keep_checkpoints"},
        {"adapter_retention"},
    )
    storage = {
        "root": _storage_root(storage["root"], "storage.root"),
        "keep_checkpoints": _boolean(
            storage["keep_checkpoints"], "storage.keep_checkpoints"
        ),
        "adapter_retention": storage.get("adapter_retention", "all"),
    }
    if storage["adapter_retention"] != "all":
        raise ValueError("storage.adapter_retention currently supports only 'all'")
    evaluation = _mapping(
        root["evaluation"], "evaluation", {"memory", "max_truncation_rate"}
    )
    evaluation = {
        "memory": _slurm_memory(evaluation["memory"], "evaluation.memory"),
        "max_truncation_rate": _bounded_fraction(
            evaluation["max_truncation_rate"],
            "evaluation.max_truncation_rate",
        ),
    }
    agent = _mapping(root["agent"], "agent", {"backend", "turn_timeout_seconds"})
    backend = _text(agent["backend"], "agent.backend")
    if backend not in {"claude", "kimi"}:
        raise ValueError("agent.backend must be claude or kimi")
    agent = {
        "backend": backend,
        "turn_timeout_seconds": _positive_integer(
            agent["turn_timeout_seconds"],
            "agent.turn_timeout_seconds",
            maximum=86_400,
        ),
    }
    training = _mapping(
        root["training_contract"],
        "training_contract",
        {"objective", "judge_rubric"},
    )
    if training["objective"] != "sft":
        raise ValueError("Run 12 AutoData supports only the sft objective")
    recipe_root = _text(root["recipe_root"], "recipe_root")
    recipe_path = Path(recipe_root)
    if recipe_path.is_absolute() or ".." in recipe_path.parts:
        raise ValueError("recipe_root must be a repository-relative path")
    result = {
        "schema": RUN_SCHEMA,
        "run_id": _identifier(root["run_id"], "run_id"),
        "chains": chains,
        "target_pairs_per_chain": _positive_integer(
            root["target_pairs_per_chain"], "target_pairs_per_chain"
        ),
        "bootstrap_canary": {"stop_after": bootstrap_canary["stop_after"]},
        "deployments": {
            "researcher_kimi": _identifier(
                deployments["researcher_kimi"], "deployments.researcher_kimi"
            ),
            "generator_kimi": _identifier(
                deployments["generator_kimi"], "deployments.generator_kimi"
            ),
        },
        "budget": {
            "max_cost_usd": _decimal(budget["max_cost_usd"], "budget.max_cost_usd")
        },
        "authoring": authoring,
        "generation": generation,
        "meta_optimization": meta,
        "production": production,
        "storage": storage,
        "evaluation": evaluation,
        "agent": agent,
        "recipe_root": recipe_root,
        "training_contract": {
            "objective": "sft",
            "judge_rubric": _text(
                training["judge_rubric"],
                "training_contract.judge_rubric",
            ),
        },
    }
    if "runtime_profile" in root:
        runtime_profile = _text(root["runtime_profile"], "runtime_profile")
        runtime_profile_path = Path(runtime_profile)
        if runtime_profile_path.is_absolute() or ".." in runtime_profile_path.parts:
            raise ValueError(
                "runtime_profile must be a repository-relative path without traversal"
            )
        result["runtime_profile"] = runtime_profile_path.as_posix()
    if stage_timing is not None:
        result["stage_timing"] = stage_timing
    return result


def resolve_runtime_profile_path(
    *,
    run_path: Path,
    repo: Path,
    profile_path: Path | None = None,
    fallback_path: Path | None = None,
) -> Path:
    """Resolve a run-declared profile and reject a conflicting shell override."""

    repo = repo.resolve(strict=True)
    run = load_run_config(run_path)
    declared_reference = run.get("runtime_profile")
    declared_path: Path | None = None
    if declared_reference is not None:
        declared_path = (repo / declared_reference).resolve(strict=True)
        if repo not in declared_path.parents or not declared_path.is_file():
            raise ValueError(
                "runtime_profile must resolve to a regular file inside the repository"
            )

    explicit_path = profile_path.resolve(strict=True) if profile_path else None
    if declared_path is not None and explicit_path is not None:
        if declared_path != explicit_path:
            raise ValueError(
                "explicit runtime profile does not match the run config declaration"
            )
    selected = declared_path or explicit_path
    if selected is None and fallback_path is not None:
        selected = fallback_path.resolve(strict=True)
    if selected is None:
        raise ValueError("run config does not declare a runtime_profile")
    if not selected.is_file():
        raise ValueError("runtime profile must resolve to a regular file")
    return selected


def _target_manifest_chain(value: Mapping[str, Any]) -> str | None:
    chain = value.get("chain_id")
    return chain if isinstance(chain, str) else None


def _atomic_text(path: Path, content: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_text(path, json.dumps(dict(value), indent=2, sort_keys=True) + "\n")


def _atomic_yaml(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_text(path, yaml.safe_dump(dict(value), sort_keys=False))


def _solve_environment(
    profile: Mapping[str, Any], run: Mapping[str, Any], target: Mapping[str, str]
) -> dict[str, str]:
    providers = profile["providers"]
    generator = providers["generator"]
    judge = providers["judge"]
    target_limits = providers["target"]
    if target.get("AUTODATA_TARGET_ENABLED") != "1":
        raise ValueError(
            "target-aware configuration requires an enabled target binding"
        )
    if target.get("AUTODATA_TARGET_MODEL") != target_limits["model"]:
        raise ValueError("target binding model does not match the runtime profile")
    environment = {
        "AUTODATA_GENERATOR_URL": generator["url"],
        "AUTODATA_GENERATOR_HOST_HEADER": generator["host_header"],
        "AUTODATA_GENERATOR_MODEL": generator["model"],
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": run["deployments"]["generator_kimi"],
        "AUTODATA_GENERATOR_MAX_INPUT": str(generator["max_input_tokens"]),
        "AUTODATA_GENERATOR_MAX_OUTPUT": str(generator["max_output_tokens"]),
        "AUTODATA_GENERATOR_TIMEOUT": str(generator["timeout_seconds"]),
        "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": generator["input_usd_per_million"],
        "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": generator[
            "output_usd_per_million"
        ],
        "AUTODATA_JUDGE_URL": judge["url"],
        "AUTODATA_JUDGE_MODEL": judge["model"],
        "AUTODATA_JUDGE_MAX_INPUT": str(judge["max_input_tokens"]),
        "AUTODATA_JUDGE_MAX_OUTPUT": str(judge["max_output_tokens"]),
        "AUTODATA_JUDGE_TIMEOUT": str(judge["timeout_seconds"]),
        "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": judge["input_usd_per_million"],
        "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": judge["output_usd_per_million"],
        "AUTODATA_TARGET_MAX_INPUT": str(target_limits["max_input_tokens"]),
        "AUTODATA_TARGET_MAX_OUTPUT": str(target_limits["max_output_tokens"]),
        "AUTODATA_TARGET_TIMEOUT": str(target_limits["timeout_seconds"]),
        "AUTODATA_TARGET_INPUT_USD_PER_MILLION": target_limits["input_usd_per_million"],
        "AUTODATA_TARGET_OUTPUT_USD_PER_MILLION": target_limits[
            "output_usd_per_million"
        ],
        "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": str(
            profile["execution"]["model_request_max_attempts"]
        ),
        "AUTODATA_TARGET_FEEDBACK_MAX_ATTEMPTS": str(
            run["generation"]["target_feedback_max_attempts"]
        ),
        "AUTODATA_JUDGE_FORMAT_MAX_ATTEMPTS": str(
            run["generation"]["judge_format_max_attempts"]
        ),
        "AUTODATA_JUDGE_STRUCTURED_OUTPUT_MODE": run["generation"][
            "judge_structured_output_mode"
        ],
        **target,
    }
    return environment


def _runtime_environment(
    *,
    profile: Mapping[str, Any],
    run: Mapping[str, Any],
    repo: Path,
    profile_path: Path,
    run_path: Path,
    output_dir: Path,
) -> dict[str, str]:
    meta = run["meta_optimization"]
    production = run["production"]
    storage = run["storage"]
    evaluation = run["evaluation"]
    agent = run["agent"]
    recipe_root = (repo / run["recipe_root"]).resolve(strict=True)
    if not recipe_root.is_dir() or repo not in recipe_root.parents:
        raise ValueError("recipe_root must resolve to a repository directory")
    environment = {
        "AAR_AUTODATA_PROFILE": profile["name"],
        "AAR_AUTODATA_PROFILE_CONFIG": str(profile_path),
        "AAR_AUTODATA_RUN_CONFIG": str(run_path),
        "AAR_AUTODATA_RUNTIME_ENV": str(output_dir / "autodata-runtime.env"),
        "AAR_AUTODATA_RESOLVED_CONFIG": str(output_dir / "resolved-config.yaml"),
        "AAR_AUTODATA_CAMPAIGN_POLICY": str(output_dir / "campaign-policy.json"),
        "AAR_AUTODATA_TRAINING_DATA_CONTRACT": str(
            output_dir / "autodata-training-data-contract.json"
        ),
        "AAR_AUTODATA_GENERATOR_DEPLOYMENT": run["deployments"]["generator_kimi"],
        "AAR_AUTODATA_AUTHORING_MAX_WALL_SECONDS": str(
            run["authoring"]["max_wall_seconds"]
        ),
        "AAR_AUTODATA_BROKER_RUNNER": profile["broker"]["runner"],
        "AAR_AUTODATA_ENVIRONMENT": profile["broker"]["environment"],
        "AAR_AUTODATA_CONCURRENCY": str(profile["execution"]["concurrency_per_chain"]),
        "AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": str(
            profile["execution"]["model_request_max_attempts"]
        ),
        "AAR_AUTODATA_TARGET_FEEDBACK_MAX_ATTEMPTS": str(
            run["generation"]["target_feedback_max_attempts"]
        ),
        "AAR_AUTODATA_JUDGE_FORMAT_MAX_ATTEMPTS": str(
            run["generation"]["judge_format_max_attempts"]
        ),
        "AAR_AUTODATA_JUDGE_STRUCTURED_OUTPUT_MODE": run["generation"][
            "judge_structured_output_mode"
        ],
        "AAR_AUTODATA_LIFECYCLE_SUPERVISED": (
            "1" if profile["execution"]["lifecycle_supervised"] else "0"
        ),
        "AAR_AUTODATA_REUSE_POLICY": profile["execution"]["reuse_policy"],
        "AAR_AUTODATA_TARGET_REQUIRED": "1",
        "AAR_AUTODATA_META_MAX_ITERATIONS": str(meta["maximum_iterations"]),
        "AAR_AUTODATA_META_MIN_ITERATIONS": str(meta["minimum_iterations"]),
        "AAR_AUTODATA_META_EARLY_STOP_PATIENCE": str(meta["early_stop_patience"]),
        "AAR_AUTODATA_TUNING_TASKS": str(meta["tuning_tasks"]),
        "AAR_AUTODATA_VALIDATION_TASKS": str(meta["validation_tasks"]),
        "AAR_AUTODATA_TEST_TASKS": str(meta["test_tasks"]),
        "AAR_AUTODATA_PRODUCTION_ROWS": str(production["required_rows"]),
        "AAR_AUTODATA_PRODUCTION_INITIAL_TASKS": str(production["initial_tasks"]),
        "AAR_AUTODATA_PRODUCTION_MIN_SUCCESS_FRACTION": format(
            production["minimum_successful_task_fraction"], ".12g"
        ),
        "AAR_AUTODATA_BOOTSTRAP_CANARY_STOP_AFTER": run["bootstrap_canary"][
            "stop_after"
        ],
        "AAR_AUTODATA_RECIPE_ROOT": str(recipe_root),
        "AAR_RUN_STORAGE_ROOT": storage["root"],
        "AAR_KEEP_CHECKPOINTS": "1" if storage["keep_checkpoints"] else "0",
        "AAR_ADAPTER_RETENTION": storage["adapter_retention"],
        "AAR_EVAL_MEM": evaluation["memory"],
        "EVAL_MAX_TRUNCATION_RATE": format(evaluation["max_truncation_rate"], ".12g"),
        "AAR_EXPECTED_MAX_TRUNCATION_RATE": format(
            evaluation["max_truncation_rate"], ".12g"
        ),
        "AAR_AGENT_BACKEND": agent["backend"],
        "AAR_KIMI_TURN_TIMEOUT_SECONDS": str(agent["turn_timeout_seconds"]),
    }
    stage_timing = run.get("stage_timing")
    if stage_timing is None:
        environment["AAR_AUTODATA_STAGE_TIMEOUT_POLICY"] = "enforce"
    else:
        environment["AAR_AUTODATA_STAGE_TIMEOUT_POLICY"] = "observe-only"
        environment["AAR_AUTODATA_NATIVE_SCHEMA_WALL_SECONDS"] = str(
            stage_timing["native_schema_wall_seconds"]
        )
    return environment


def compile_run_config(
    *,
    profile_path: Path,
    run_path: Path,
    target_binding_path: Path,
    chain: str,
    repo: Path,
    output_dir: Path,
) -> dict[str, Any]:
    run_path = run_path.resolve(strict=True)
    target_binding_path = target_binding_path.resolve(strict=True)
    repo = repo.resolve(strict=True)
    profile_path = resolve_runtime_profile_path(
        run_path=run_path,
        repo=repo,
        profile_path=profile_path,
    )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile = load_runtime_profile(profile_path)
    run = load_run_config(run_path)
    if chain not in run["chains"] and chain != "canary":
        raise ValueError(f"chain {chain!r} is not declared by the run config")
    manifest = json.loads(target_binding_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("target binding must contain one JSON object")
    manifest_chain = _target_manifest_chain(manifest)
    if manifest_chain != chain:
        raise ValueError("target binding chain does not match the compiled chain")
    target_environment = target_environment_from_manifest(target_binding_path)
    solve_environment = _solve_environment(profile, run, target_environment)
    rubric_path, rubric_identity = _judge_rubric_identity(repo, run)
    policy = {
        "schema": "autodata.broker-campaign-policy/v1",
        "campaign_id": f"{run['run_id']}-{chain}",
        "max_cost_usd": run["budget"]["max_cost_usd"],
        "runner": profile["broker"]["runner"],
        "environment": profile["broker"]["environment"],
        "image": profile["broker"]["image"],
        "expected_image_id": profile["broker"]["expected_image_id"],
        "max_cpus": profile["broker"]["max_cpus"],
        "max_memory_mb": profile["broker"]["max_memory_mb"],
        "required_solve_env": solve_environment,
    }
    contract = training_data_contract_from_campaign_policy(
        policy,
        required_rows=run["production"]["required_rows"],
        minimum_successful_task_fraction=run["production"][
            "minimum_successful_task_fraction"
        ],
        judge_rubric=rubric_identity,
    )
    if contract["target"].get("required") is not True:
        raise ValueError("compiled training contract is not target-aware")
    policy_path = output_dir / "campaign-policy.json"
    contract_path = output_dir / "autodata-training-data-contract.json"
    runtime_path = output_dir / "autodata-runtime.env"
    resolved_path = output_dir / "resolved-config.yaml"
    _atomic_json(policy_path, policy)
    _atomic_json(contract_path, contract)
    runtime = _runtime_environment(
        profile=profile,
        run=run,
        repo=repo,
        profile_path=profile_path,
        run_path=run_path,
        output_dir=output_dir,
    )
    _atomic_text(
        runtime_path,
        "".join(
            f"export {name}={shlex.quote(value)}\n"
            for name, value in sorted(runtime.items())
        ),
    )
    resolved = {
        "schema": RESOLVED_SCHEMA,
        "chain": chain,
        "profile_source": str(profile_path),
        "profile_source_sha256": _sha256(profile_path),
        "run_source": str(run_path),
        "run_source_sha256": _sha256(run_path),
        "target_binding": str(target_binding_path),
        "target_binding_sha256": _sha256(target_binding_path),
        "judge_rubric_source": str(rubric_path),
        "judge_rubric_source_sha256": rubric_identity["sha256"],
        "target": {
            "iteration": manifest.get("iteration"),
            "deployment_id": solve_environment["AUTODATA_TARGET_DEPLOYMENT_ID"],
            "checkpoint_hash": solve_environment["AUTODATA_TARGET_CHECKPOINT_HASH"],
            "challenge_provenance_required": True,
            "provider_order": ["generator", "target", "judge"],
        },
        "profile": profile,
        "run": run,
        "artifacts": {
            "campaign_policy": str(policy_path),
            "campaign_policy_sha256": _sha256(policy_path),
            "training_data_contract": str(contract_path),
            "training_data_contract_sha256": _sha256(contract_path),
            "runtime_environment": str(runtime_path),
            "runtime_environment_sha256": _sha256(runtime_path),
        },
    }
    _atomic_yaml(resolved_path, resolved)
    return resolved


def validate_compiled_config(
    resolved_path: Path, campaign_policy_path: Path, contract_path: Path
) -> dict[str, Any]:
    resolved = _load_yaml(resolved_path, "resolved AutoData config")
    if resolved.get("schema") != RESOLVED_SCHEMA:
        raise ValueError("resolved AutoData config schema is invalid")
    checks = {
        Path(resolved["profile_source"]): resolved["profile_source_sha256"],
        Path(resolved["run_source"]): resolved["run_source_sha256"],
        Path(resolved["target_binding"]): resolved["target_binding_sha256"],
        Path(resolved["judge_rubric_source"]): resolved["judge_rubric_source_sha256"],
        campaign_policy_path: resolved["artifacts"]["campaign_policy_sha256"],
        contract_path: resolved["artifacts"]["training_data_contract_sha256"],
        Path(resolved["artifacts"]["runtime_environment"]): resolved["artifacts"][
            "runtime_environment_sha256"
        ],
    }
    for path, expected in checks.items():
        if _sha256(path.resolve(strict=True)) != expected:
            raise ValueError(f"compiled AutoData artifact changed: {path}")
    profile = load_runtime_profile(Path(resolved["profile_source"]))
    run = load_run_config(Path(resolved["run_source"]))
    policy = json.loads(campaign_policy_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    validate_training_data_contract(contract, campaign_policy=policy)
    rubric_source = Path(resolved["judge_rubric_source"]).resolve(strict=True)
    rubric_document = json.loads(rubric_source.read_text(encoding="utf-8"))
    rubric_identity = {
        "version": rubric_document.get("version"),
        "sha256": _sha256(rubric_source),
    }
    if contract.get("judge_rubric") != rubric_identity:
        raise ValueError("compiled judge rubric identity changed")
    environment = policy.get("required_solve_env", {})
    if environment.get("AUTODATA_TARGET_ENABLED") != "1":
        raise ValueError("compiled campaign is no longer target-aware")
    if (
        environment.get("AUTODATA_GENERATOR_DEPLOYMENT_ID")
        != run["deployments"]["generator_kimi"]
    ):
        raise ValueError("compiled generator deployment changed")
    if policy.get("runner") != profile["broker"]["runner"]:
        raise ValueError("compiled broker runner changed")
    return resolved


def inspect_configs(profile_path: Path, run_path: Path) -> dict[str, Any]:
    profile = load_runtime_profile(profile_path)
    run = load_run_config(run_path)
    return {
        "profile_name": profile["name"],
        "concurrency_per_chain": profile["execution"]["concurrency_per_chain"],
        "model_request_max_attempts": profile["execution"][
            "model_request_max_attempts"
        ],
        "target_feedback_max_attempts": run["generation"][
            "target_feedback_max_attempts"
        ],
        "judge_format_max_attempts": run["generation"]["judge_format_max_attempts"],
        "judge_structured_output_mode": run["generation"][
            "judge_structured_output_mode"
        ],
        "authoring_max_wall_seconds": run["authoring"]["max_wall_seconds"],
        "researcher_kimi_deployment": run["deployments"]["researcher_kimi"],
        "generator_kimi_deployment": run["deployments"]["generator_kimi"],
        "chains": run["chains"],
        "target_pairs_per_chain": run["target_pairs_per_chain"],
        "bootstrap_canary_stop_after": run["bootstrap_canary"]["stop_after"],
        "target_enabled": profile["target"]["enabled"],
        "generator_url": profile["providers"]["generator"]["url"],
        "generator_host_header": profile["providers"]["generator"]["host_header"],
        "generator_model": profile["providers"]["generator"]["model"],
        "target_model": profile["providers"]["target"]["model"],
        "storage_root": run["storage"]["root"],
        "keep_checkpoints": run["storage"]["keep_checkpoints"],
        "adapter_retention": run["storage"]["adapter_retention"],
        "evaluation_memory": run["evaluation"]["memory"],
        "max_truncation_rate": run["evaluation"]["max_truncation_rate"],
        "agent_backend": run["agent"]["backend"],
        "turn_timeout_seconds": run["agent"]["turn_timeout_seconds"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--profile", required=True, type=Path)
    inspect.add_argument("--run", required=True, type=Path)
    resolve_profile = subparsers.add_parser("resolve-profile")
    resolve_profile.add_argument("--run", required=True, type=Path)
    resolve_profile.add_argument("--repo", required=True, type=Path)
    resolve_profile.add_argument("--profile", type=Path)
    resolve_profile.add_argument("--fallback-profile", type=Path)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--profile", required=True, type=Path)
    compile_parser.add_argument("--run", required=True, type=Path)
    compile_parser.add_argument("--target-binding", required=True, type=Path)
    compile_parser.add_argument("--chain", required=True)
    compile_parser.add_argument("--repo", required=True, type=Path)
    compile_parser.add_argument("--output-dir", required=True, type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--resolved", required=True, type=Path)
    validate.add_argument("--campaign-policy", required=True, type=Path)
    validate.add_argument("--training-data-contract", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "inspect":
        result = inspect_configs(args.profile, args.run)
    elif args.command == "resolve-profile":
        print(
            resolve_runtime_profile_path(
                run_path=args.run,
                repo=args.repo,
                profile_path=args.profile,
                fallback_path=args.fallback_profile,
            )
        )
        return 0
    elif args.command == "compile":
        result = compile_run_config(
            profile_path=args.profile,
            run_path=args.run,
            target_binding_path=args.target_binding,
            chain=args.chain,
            repo=args.repo,
            output_dir=args.output_dir,
        )
    else:
        result = validate_compiled_config(
            args.resolved, args.campaign_policy, args.training_data_contract
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
