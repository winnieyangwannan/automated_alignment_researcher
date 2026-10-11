"""Trusted construction and validation for native AutoData executions.

The research agent may propose an execution document, but it is not an
authority for iteration budgets, task partitions, concurrency, or production
completion thresholds.  Those values come from the operator-compiled Run
configuration and are reconstructed here before the native CLI is invoked.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    return value


def _positive_integer(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{where} must be a positive integer")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _meta_evaluation_attempts(meta: Mapping[str, Any]) -> int:
    """Return native model-evaluation attempts without pipeline checks/retry."""
    tuning = int(meta["tuning_tasks"])
    validation = int(meta["validation_tasks"])
    iterations = int(meta["maximum_iterations"])
    test = int(meta["test_tasks"])
    # Baseline tuning+validation, paired validation plus visible tuning for
    # every candidate, then final test and final full meta corpus.
    return (
        tuning
        + validation
        + iterations * (2 * validation + tuning)
        + test
        + tuning
        + validation
    )


def _partition_seed(grounding: Mapping[str, str]) -> int:
    return int(grounding["digest"].removeprefix("sha256:")[:8], 16)


def _load_json(path: Path, where: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{where} must be a regular non-symlink file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{where} is not valid JSON") from error
    return _object(value, where)


def operator_execution_settings(
    resolved: Mapping[str, Any],
    *,
    campaign_policy: Mapping[str, Any],
    training_data_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract the execution authority from a verified compiled config."""
    run = _object(resolved.get("run"), "resolved run config")
    profile = _object(resolved.get("profile"), "resolved runtime profile")
    meta = _object(run.get("meta_optimization"), "meta optimization config")
    production = _object(run.get("production"), "production config")
    generation = _object(run.get("generation"), "generation config")
    execution = _object(profile.get("execution"), "runtime execution config")
    providers = _object(profile.get("providers"), "runtime providers config")
    contract = _object(dict(training_data_contract), "training-data contract")

    settings = {
        "meta": {
            "maximum_iterations": _positive_integer(
                meta.get("maximum_iterations"), "maximum_iterations"
            ),
            "minimum_iterations": _positive_integer(
                meta.get("minimum_iterations"), "minimum_iterations"
            ),
            "early_stop_patience": _positive_integer(
                meta.get("early_stop_patience"), "early_stop_patience"
            ),
            "tuning_tasks": _positive_integer(meta.get("tuning_tasks"), "tuning_tasks"),
            "validation_tasks": _positive_integer(
                meta.get("validation_tasks"), "validation_tasks"
            ),
            "test_tasks": _positive_integer(meta.get("test_tasks"), "test_tasks"),
        },
        "production": {
            "initial_tasks": _positive_integer(
                production.get("initial_tasks"), "production initial_tasks"
            ),
            "required_rows": _positive_integer(
                production.get("required_rows"), "production required_rows"
            ),
            "minimum_successful_task_fraction": production.get(
                "minimum_successful_task_fraction"
            ),
        },
        "concurrency": _positive_integer(
            execution.get("concurrency_per_chain"), "execution concurrency"
        ),
        "campaign_policy": dict(campaign_policy),
    }
    if settings["meta"]["minimum_iterations"] > settings["meta"]["maximum_iterations"]:
        raise ValueError("minimum_iterations exceeds maximum_iterations")
    fraction = settings["production"]["minimum_successful_task_fraction"]
    if (
        isinstance(fraction, bool)
        or not isinstance(fraction, (int, float))
        or not 0 < float(fraction) <= 1
    ):
        raise ValueError("production success fraction must be in (0,1]")
    if (
        contract.get("required_rows") != settings["production"]["required_rows"]
        or contract.get("minimum_successful_task_fraction") != fraction
    ):
        raise ValueError("resolved production settings do not match training contract")
    stage_timing = run.get("stage_timing")
    native_wall = (
        _positive_integer(
            _object(stage_timing, "stage timing").get("native_schema_wall_seconds"),
            "native schema wall seconds",
        )
        if stage_timing is not None
        else None
    )
    settings["meta_wall_seconds"] = native_wall or 6300
    settings["production_wall_seconds"] = native_wall or 28200
    role_costs: dict[str, Decimal] = {}
    try:
        for role in ("generator", "judge", "target"):
            provider = _object(providers.get(role), f"{role} provider")
            role_costs[role] = (
                Decimal(str(provider["max_input_tokens"]))
                * Decimal(str(provider["input_usd_per_million"]))
                + Decimal(str(provider["max_output_tokens"]))
                * Decimal(str(provider["output_usd_per_million"]))
            ) / Decimal(1_000_000)
        campaign_cap = Decimal(str(campaign_policy["max_cost_usd"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("campaign cost policy is incomplete") from error
    meta_evaluations = _meta_evaluation_attempts(settings["meta"])
    # Native finalization performs one initial full-corpus pass and may retry
    # every tuning+validation task once.  Partial retry capacity is unsafe:
    # native batches are concurrent, and exhausting the ledger mid-batch can
    # otherwise leave an execution without a complete terminal transition.
    full_meta_retry = int(settings["meta"]["tuning_tasks"]) + int(
        settings["meta"]["validation_tasks"]
    )
    meta_model_attempts = meta_evaluations + full_meta_retry
    production_attempts = 2 * settings["production"]["initial_tasks"]
    finalization_rounds = _positive_integer(
        generation.get("target_feedback_max_attempts"),
        "target feedback max attempts",
    )
    if finalization_rounds > 5:
        raise ValueError("target feedback max attempts must not exceed 5")
    judge_format_attempts = _positive_integer(
        generation.get("judge_format_max_attempts"),
        "judge format max attempts",
    )
    if judge_format_attempts > 2:
        raise ValueError("judge format max attempts must not exceed 2")
    if generation.get("judge_structured_output_mode") != "responses_json_schema":
        raise ValueError("judge structured-output mode is not operator-supported")
    required_environment = _object(
        campaign_policy.get("required_solve_env"),
        "campaign required_solve_env",
    )
    if required_environment.get("AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS") != "1":
        raise ValueError(
            "trusted campaigns require exactly one transport attempt per model request"
        )
    if required_environment.get("AUTODATA_JUDGE_FORMAT_MAX_ATTEMPTS") != str(
        judge_format_attempts
    ):
        raise ValueError("campaign judge format attempts do not match run config")
    if (
        required_environment.get("AUTODATA_JUDGE_STRUCTURED_OUTPUT_MODE")
        != "responses_json_schema"
    ):
        raise ValueError("campaign judge structured-output mode is not trusted")
    recipe_relative = Path(str(run.get("recipe_root", "")))
    if (
        not recipe_relative.parts
        or recipe_relative.is_absolute()
        or ".." in recipe_relative.parts
    ):
        raise ValueError("resolved recipe_root is unsafe")
    workspace_spec = _load_json(
        Path(__file__).resolve().parents[2]
        / recipe_relative
        / "autodata.workspace.json",
        "trusted workspace spec",
    )
    authoring_budget = _object(
        workspace_spec.get("authoring_budget"), "trusted authoring budget"
    )
    authoring_model_attempts = _positive_integer(
        authoring_budget.get("max_task_attempts"),
        "authoring max_task_attempts",
    )
    full_meta_corpus = int(settings["meta"]["tuning_tasks"]) + int(
        settings["meta"]["validation_tasks"]
    )
    meta_round_reservations = (
        meta_evaluations
        - full_meta_corpus
        + (full_meta_corpus + full_meta_retry) * finalization_rounds
    )
    production_round_reservations = production_attempts * finalization_rounds
    required_round_reservations = (
        authoring_model_attempts
        + meta_round_reservations
        + production_round_reservations
    )
    per_semantic_round = (
        role_costs["generator"]
        + role_costs["target"]
        + Decimal(judge_format_attempts) * role_costs["judge"]
    )
    per_round_microusd = int(
        (per_semantic_round * Decimal(1_000_000)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    required_microusd = per_round_microusd * required_round_reservations
    campaign_microusd = int(
        (campaign_cap * Decimal(1_000_000)).to_integral_value(rounding=ROUND_CEILING)
    )
    required_cost = Decimal(required_microusd) / Decimal(1_000_000)
    if campaign_microusd < required_microusd:
        raise ValueError(
            "campaign max_cost_usd is insufficient: "
            f"requires at least {required_cost} for "
            f"{required_round_reservations} worst-case model-call reservations "
            "including authoring and finalization feedback"
        )
    required_attempts = meta_model_attempts + production_attempts
    settings["per_model_task_cost_usd"] = format(per_semantic_round, "f")
    settings["per_model_round_microusd"] = per_round_microusd
    settings["required_campaign_cost_usd"] = format(required_cost, "f")
    settings["required_campaign_task_attempts"] = required_attempts
    settings["required_campaign_round_reservations"] = required_round_reservations
    settings["authoring_model_task_attempts"] = authoring_model_attempts
    settings["finalization_model_rounds_per_task"] = finalization_rounds
    settings["judge_format_max_attempts"] = judge_format_attempts
    settings["required_generator_calls"] = required_round_reservations
    settings["required_target_calls"] = required_round_reservations
    settings["required_judge_calls"] = (
        required_round_reservations * judge_format_attempts
    )
    settings["meta_evaluation_attempts"] = meta_evaluations
    settings["meta_finalization_retry_attempts"] = full_meta_retry
    settings["meta_model_task_attempts"] = meta_model_attempts
    # Trusted pipeline check attempts are added after the exact operator
    # pipeline is loaded by the lifecycle supervisor.
    settings["meta_task_attempts"] = meta_model_attempts
    settings["production_task_attempts"] = production_attempts
    return settings


def validate_runtime_campaign_policy_rewrite(
    compiled_policy: Mapping[str, Any], runtime_policy: Mapping[str, Any]
) -> dict[str, Any]:
    """Accept only the launcher's authenticated loopback generator rewrite."""
    compiled = deepcopy(dict(compiled_policy))
    runtime = deepcopy(dict(runtime_policy))
    compiled_environment = _object(
        compiled.pop("required_solve_env", None), "compiled required_solve_env"
    )
    runtime_environment = _object(
        runtime.pop("required_solve_env", None), "runtime required_solve_env"
    )
    if runtime != compiled:
        raise ValueError("runtime campaign policy changed outside required_solve_env")
    allowed = {"AUTODATA_GENERATOR_URL", "AUTODATA_GENERATOR_HOST_HEADER"}
    changed = {
        key
        for key in set(compiled_environment) | set(runtime_environment)
        if compiled_environment.get(key) != runtime_environment.get(key)
    }
    if not changed.issubset(allowed):
        raise ValueError("runtime campaign policy contains an unauthorized mutation")
    if changed:
        url = runtime_environment.get("AUTODATA_GENERATOR_URL")
        parsed = urlparse(url) if isinstance(url, str) else None
        try:
            port = parsed.port if parsed is not None else None
        except ValueError:
            port = None
        if (
            parsed is None
            or parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or port is None
            or not 1 <= port <= 65535
            or parsed.path != "/v1"
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "runtime generator URL is not an authorized loopback bridge"
            )
        if runtime_environment.get("AUTODATA_GENERATOR_HOST_HEADER") != "":
            raise ValueError("runtime generator host header must be empty for loopback")
    result = deepcopy(dict(runtime_policy))
    result["required_solve_env"] = runtime_environment
    return result


def _grounding_ids(
    pipeline_root: Path, reference: Any, where: str
) -> tuple[dict[str, str], list[str]]:
    value = _object(reference, where)
    if set(value) != {"manifest_path", "digest"}:
        raise ValueError(f"{where} must contain only manifest_path and digest")
    relative = value.get("manifest_path")
    if (
        not isinstance(relative, str)
        or not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ValueError(f"{where}.manifest_path is unsafe")
    root = pipeline_root.resolve(strict=True)
    candidate = root / relative
    current = root
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{where}.manifest_path contains a symlink")
    path = candidate.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{where}.manifest_path escapes the pipeline") from error
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{where} does not name a regular manifest")
    digest = _sha256(path)
    if value.get("digest") != digest:
        raise ValueError(f"{where} digest does not match its manifest")
    manifest = _load_json(path, where)
    if manifest.get("schema") != "autodata.grounding/v1":
        raise ValueError(f"{where} has the wrong grounding schema")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError(f"{where} tasks must be an array")
    identifiers: list[str] = []
    for index, task in enumerate(tasks):
        if (
            not isinstance(task, dict)
            or not isinstance(task.get("id"), str)
            or not task["id"]
        ):
            raise ValueError(f"{where} task {index} has no valid id")
        identifiers.append(task["id"])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{where} contains duplicate task ids")
    return {"manifest_path": relative, "digest": digest}, identifiers


def bound_grounding_task_ids(
    pipeline_root: Path, reference: Any, where: str
) -> list[str]:
    """Return IDs only after validating a native grounding reference."""
    return _grounding_ids(pipeline_root, reference, where)[1]


def _validate_executor(
    executor: Any, policy: Mapping[str, Any], *, broker_url: Any
) -> dict[str, Any]:
    value = _object(executor, "execution executor")
    required_environment = _object(
        policy.get("required_solve_env"), "campaign required_solve_env"
    )
    expected = {
        "kind": "sandoq-firecracker",
        "environment": policy.get("environment"),
        "image": policy.get("image"),
        "expected_image_id": policy.get("expected_image_id"),
        "broker_url": broker_url,
        "broker_auth_secret_ref": "AAR_AUTODATA_CAPABILITY",
        "model_backed": True,
        "cpus": policy.get("max_cpus"),
        "memory_mb": policy.get("max_memory_mb"),
        "network": "host",
        "workdir": "/workspace",
        "non_secret_env": required_environment,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise ValueError(f"execution executor does not match trusted {key}")
    if not isinstance(broker_url, str) or not broker_url.strip():
        raise ValueError("trusted execution settings have no broker_url")
    if set(value) != set(expected):
        raise ValueError("execution executor has unknown or missing fields")
    return deepcopy(value)


def canonical_execution_manifest(
    *,
    proposed_manifest: Path,
    pipeline_manifest: Path,
    settings: Mapping[str, Any],
    reserved_task_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the operator-authoritative native execution manifest.

    The proposed document must already agree with every controlled value.  It
    is then reconstructed from verified grounding order and operator settings,
    ensuring a malformed default document fails rather than being repaired and
    silently accepted.
    """
    proposed = _load_json(proposed_manifest, "proposed execution manifest")
    if proposed.get("schema") != "autodata.execution/v1":
        raise ValueError("execution has the wrong schema")
    pipeline_root = pipeline_manifest.resolve(strict=True).parent
    grounding, grounding_ids = _grounding_ids(
        pipeline_root, proposed.get("grounding"), "execution grounding"
    )
    expected_concurrency = settings.get("concurrency")
    if proposed.get("concurrency") != expected_concurrency:
        raise ValueError("execution concurrency does not match operator config")
    policy = _object(settings.get("campaign_policy"), "trusted campaign policy")
    executor = _validate_executor(
        proposed.get("executor"), policy, broker_url=settings.get("broker_url")
    )
    if proposed.get("secret_references") != ["AAR_AUTODATA_CAPABILITY"]:
        raise ValueError("execution secret references do not match operator config")

    mode = proposed.get("mode")
    common_fields = {
        "schema",
        "mode",
        "grounding",
        "split_seed",
        "executor",
        "budget",
        "concurrency",
        "secret_references",
    }
    mode_fields = (
        {"tuning_task_ids", "validation_task_ids", "test_grounding"}
        if mode == "meta_optimize"
        else {"finalization"}
    )
    if set(proposed) != common_fields | mode_fields:
        raise ValueError("execution manifest has unknown or missing fields")
    expected_seed = _partition_seed(grounding)
    if proposed.get("split_seed") != expected_seed:
        raise ValueError("execution split_seed does not match canonical grounding")
    canonical = {
        "schema": "autodata.execution/v1",
        "mode": mode,
        "grounding": grounding,
        "split_seed": expected_seed,
        "executor": executor,
        "concurrency": expected_concurrency,
        "secret_references": ["AAR_AUTODATA_CAPABILITY"],
    }
    budget = _object(proposed.get("budget"), "execution budget")

    if mode == "meta_optimize":
        meta = _object(settings.get("meta"), "trusted meta config")
        tuning_count = int(meta["tuning_tasks"])
        validation_count = int(meta["validation_tasks"])
        test_count = int(meta["test_tasks"])
        test_grounding, referenced_test_ids = _grounding_ids(
            pipeline_root, proposed.get("test_grounding"), "meta test grounding"
        )
        expected_total = tuning_count + validation_count + test_count
        if test_grounding == grounding:
            raise ValueError("meta and test grounding must use separate manifests")
        if len(grounding_ids) != tuning_count + validation_count:
            raise ValueError(
                "meta grounding must contain exactly tuning and validation tasks"
            )
        if len(referenced_test_ids) != test_count:
            raise ValueError("meta test grounding has the wrong task count")
        tuning_ids = grounding_ids[:tuning_count]
        validation_ids = grounding_ids[tuning_count:]
        test_ids = referenced_test_ids
        partitions = [set(tuning_ids), set(validation_ids), set(test_ids)]
        if any(
            partitions[left] & partitions[right]
            for left in range(3)
            for right in range(left + 1, 3)
        ):
            raise ValueError("meta tuning, validation, and test tasks must be disjoint")
        if len(set().union(*partitions)) != expected_total:
            raise ValueError("meta grounding set does not equal its three partitions")
        if proposed.get("tuning_task_ids") != tuning_ids:
            raise ValueError("meta tuning_task_ids do not match canonical partition")
        if proposed.get("validation_task_ids") != validation_ids:
            raise ValueError(
                "meta validation_task_ids do not match canonical partition"
            )
        controlled_budget = {
            "max_iterations": meta["maximum_iterations"],
            "min_iterations": meta["minimum_iterations"],
            "early_stop_patience": meta["early_stop_patience"],
            "max_task_attempts": settings.get(
                "meta_task_attempts", _meta_evaluation_attempts(meta)
            ),
            "max_wall_seconds": settings.get("meta_wall_seconds", 6300),
        }
        if set(budget) != set(controlled_budget):
            raise ValueError("meta budget has unknown or missing fields")
        for key, expected in controlled_budget.items():
            if budget.get(key) != expected:
                raise ValueError(f"meta budget {key} does not match operator config")
        canonical["budget"] = controlled_budget
        canonical["tuning_task_ids"] = tuning_ids
        canonical["validation_task_ids"] = validation_ids
        canonical["test_grounding"] = test_grounding
    elif mode == "production":
        production = _object(settings.get("production"), "trusted production config")
        if len(grounding_ids) != production["initial_tasks"]:
            raise ValueError(
                "production grounding task count does not match operator config"
            )
        overlap = set(grounding_ids) & set(reserved_task_ids)
        if overlap:
            raise ValueError(
                "production grounding overlaps meta tuning/validation/test tasks"
            )
        controlled_budget = {
            "max_iterations": 0,
            "max_task_attempts": settings.get(
                "production_task_attempts", 2 * int(production["initial_tasks"])
            ),
            "max_wall_seconds": settings.get("production_wall_seconds", 28200),
        }
        allowed_budget = {
            **controlled_budget,
            # Native ExecutionSpec.to_dict() materializes these dataclass
            # defaults on persistence. They carry no production authority.
            "min_iterations": 0,
            "early_stop_patience": None,
        }
        if (
            not set(budget).issubset(allowed_budget)
            or any(
                budget.get(key) != allowed_budget[key]
                for key in budget
                if key in allowed_budget
            )
            or any(
                budget.get(key) != expected
                for key, expected in controlled_budget.items()
            )
        ):
            raise ValueError("production budget does not match operator config")
        canonical["budget"] = controlled_budget
        finalization = _object(
            proposed.get("finalization"), "production finalization policy"
        )
        expected_finalization = {
            "minimum_generated_items": production["required_rows"],
            "minimum_successful_task_fraction": production[
                "minimum_successful_task_fraction"
            ],
        }
        if finalization != expected_finalization:
            raise ValueError("production finalization does not match operator config")
        canonical["finalization"] = expected_finalization
        for forbidden in ("tuning_task_ids", "validation_task_ids", "test_grounding"):
            if forbidden in proposed:
                raise ValueError(f"production execution must not contain {forbidden}")
    else:
        raise ValueError("execution mode must be meta_optimize or production")

    return canonical


def canonical_meta_manifest_from_default(
    *,
    default_manifest: Mapping[str, Any],
    pipeline_manifest: Path,
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    """Construct meta control fields without a researcher-authored manifest."""
    default = deepcopy(dict(default_manifest))
    allowed_default = {
        "schema",
        "mode",
        "grounding",
        "split_seed",
        "executor",
        "budget",
        "concurrency",
        "secret_references",
        "test_grounding",
        # Native AutoData materializes these fields when a workspace freezes.
        # They are accepted only as known input shape: the trusted operator
        # partition below replaces both values from the digest-bound grounding.
        "tuning_task_ids",
        "validation_task_ids",
    }
    if not set(default).issubset(allowed_default):
        raise ValueError("freeze-created execution has unknown fields")
    if default.get("schema") != "autodata.execution/v1":
        raise ValueError("freeze-created execution has the wrong schema")
    if default.get("mode") != "meta_optimize":
        raise ValueError("freeze-created execution is not meta_optimize")
    pipeline_root = pipeline_manifest.resolve(strict=True).parent
    grounding, grounding_ids = _grounding_ids(
        pipeline_root, default.get("grounding"), "freeze-created grounding"
    )
    test_grounding, test_ids = _grounding_ids(
        pipeline_root,
        default.get("test_grounding"),
        "supervisor-created test grounding",
    )
    meta = _object(settings.get("meta"), "trusted meta config")
    tuning_count = int(meta["tuning_tasks"])
    validation_count = int(meta["validation_tasks"])
    test_count = int(meta["test_tasks"])
    if len(grounding_ids) != tuning_count + validation_count:
        raise ValueError(
            "supervisor meta grounding must exactly cover tuning and validation"
        )
    if len(test_ids) != test_count:
        raise ValueError("supervisor test grounding must contain exactly test tasks")
    if set(grounding_ids) & set(test_ids):
        raise ValueError("supervisor meta and test grounding must be disjoint")
    if len(set(grounding_ids) | set(test_ids)) != (
        tuning_count + validation_count + test_count
    ):
        raise ValueError(
            "supervisor grounding does not form the full trusted partition"
        )
    expected_concurrency = settings.get("concurrency")
    if default.get("concurrency") != expected_concurrency:
        raise ValueError("freeze-created concurrency does not match operator config")
    policy = _object(settings.get("campaign_policy"), "trusted campaign policy")
    executor = _validate_executor(
        default.get("executor"), policy, broker_url=settings.get("broker_url")
    )
    if default.get("secret_references") != ["AAR_AUTODATA_CAPABILITY"]:
        raise ValueError(
            "freeze-created secret references do not match operator config"
        )
    budget = _object(default.get("budget"), "freeze-created execution budget")
    # Native freeze emits the complete budget shape. These values are shape-
    # checked only and never provide authority; ``canonical`` below replaces
    # every field with trusted operator settings.
    allowed_default_budget = {
        "max_iterations",
        "min_iterations",
        "early_stop_patience",
        "max_task_attempts",
        "max_wall_seconds",
    }
    if not set(budget).issubset(allowed_default_budget):
        raise ValueError("freeze-created execution budget has unknown fields")
    canonical = {
        "schema": "autodata.execution/v1",
        "mode": "meta_optimize",
        "grounding": grounding,
        "test_grounding": test_grounding,
        "split_seed": _partition_seed(grounding),
        "executor": executor,
        "concurrency": expected_concurrency,
        "secret_references": ["AAR_AUTODATA_CAPABILITY"],
        "budget": {
            "max_iterations": meta["maximum_iterations"],
            "min_iterations": meta["minimum_iterations"],
            "early_stop_patience": meta["early_stop_patience"],
            "max_task_attempts": settings.get(
                "meta_task_attempts", _meta_evaluation_attempts(meta)
            ),
            "max_wall_seconds": settings.get("meta_wall_seconds", 6300),
        },
        "tuning_task_ids": grounding_ids[:tuning_count],
        "validation_task_ids": grounding_ids[
            tuning_count : tuning_count + validation_count
        ],
    }
    return canonical


def canonical_production_manifest_from_meta(
    *,
    meta_manifest: Mapping[str, Any],
    pipeline_manifest: Path,
    production_grounding: Mapping[str, Any],
    settings: Mapping[str, Any],
    reserved_task_ids: Sequence[str],
) -> dict[str, Any]:
    """Construct fixed-winner production without a researcher-authored document.

    ``meta_manifest`` contributes only the already validated executor contract.
    Counts, budgets, concurrency, split identity, and finalization thresholds are
    reconstructed from operator settings and the digest-bound production corpus.
    """
    pipeline_root = pipeline_manifest.resolve(strict=True).parent
    grounding, grounding_ids = _grounding_ids(
        pipeline_root, production_grounding, "supervisor production grounding"
    )
    production = _object(settings.get("production"), "trusted production config")
    if len(grounding_ids) != production["initial_tasks"]:
        raise ValueError(
            "supervisor production grounding task count does not match operator config"
        )
    if set(grounding_ids) & set(reserved_task_ids):
        raise ValueError(
            "supervisor production grounding overlaps meta tuning/validation/test tasks"
        )
    policy = _object(settings.get("campaign_policy"), "trusted campaign policy")
    executor = _validate_executor(
        meta_manifest.get("executor"),
        policy,
        broker_url=settings.get("broker_url"),
    )
    if meta_manifest.get("secret_references") != ["AAR_AUTODATA_CAPABILITY"]:
        raise ValueError("meta secret references do not match operator config")
    concurrency = settings.get("concurrency")
    finalization = {
        "minimum_generated_items": production["required_rows"],
        "minimum_successful_task_fraction": production[
            "minimum_successful_task_fraction"
        ],
    }
    return {
        "schema": "autodata.execution/v1",
        "mode": "production",
        "grounding": grounding,
        "split_seed": _partition_seed(grounding),
        "executor": executor,
        "budget": {
            "max_iterations": 0,
            "max_task_attempts": settings.get(
                "production_task_attempts", 2 * int(production["initial_tasks"])
            ),
            "max_wall_seconds": settings.get("production_wall_seconds", 28200),
        },
        "concurrency": concurrency,
        "secret_references": ["AAR_AUTODATA_CAPABILITY"],
        "finalization": finalization,
    }
