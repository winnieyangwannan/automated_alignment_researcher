#!/usr/bin/env python3
"""Run one real Kimi/Luna recipe task through the authenticated native broker.

The broker injects ``MODEL_API_KEY`` into the Firecracker workload.  This
client deliberately never reads that key and never retains generated prompt or
response content: the downloaded task result lives only in a temporary
directory and the retained report contains usage, counts, and status only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import tempfile
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Callable


DEFAULT_IMAGE = (
    "docker.io/library/python@sha256:"
    "05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f"
)
DEFAULT_IMAGE_ID = "df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316"
DEFAULT_RECIPE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "aar"
    / "autodata_recipes"
    / "dishonest_sycophancy_concealing"
)
DEFAULT_GENERATOR_URL = (
    "https://ram-inference-gateway.ingress.fair-cw-use2-1.cw.metafb.cloud/v1"
)
GENERATOR_MODEL = "Kimi-K2.6"
GENERATOR_DEPLOYMENT_ID = "winnieyangwn-kimi26"
JUDGE_URL = "https://api.meta.ai/v1/responses"
JUDGE_MODEL = "gpt-5-6-luna"
ENVIRONMENT = "oci-runner-firecracker-small"
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
SAFE_USAGE_FIELDS = {
    "request_id",
    "role",
    "model",
    "input_tokens",
    "output_tokens",
    "estimated_cost_usd",
    "cost_basis",
}


@dataclass(frozen=True)
class _Runtime:
    broker_client: Any
    broker_job_spec: Any
    build_archive: Callable[..., Any]
    extract_archive: Callable[..., Any]


@dataclass(frozen=True)
class _RecipeContract:
    argv: tuple[str, ...]
    input_path: str
    output_path: str
    timeout_seconds: int
    schema: dict[str, Any]


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("rate must be a decimal") from error
    if not parsed.is_finite() or parsed < 0:
        raise argparse.ArgumentTypeError("rate must be a finite non-negative decimal")
    return parsed


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one model-backed Run 8 recipe task through SandoQ"
    )
    parser.add_argument("--broker-url", default="http://127.0.0.1:8791")
    parser.add_argument("--broker-auth-token-file", type=Path, required=True)
    parser.add_argument("--recipe-root", type=Path, default=DEFAULT_RECIPE_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--expected-image-id", default=DEFAULT_IMAGE_ID)
    parser.add_argument("--generator-url", default=DEFAULT_GENERATOR_URL)
    parser.add_argument("--generator-deployment-id", default=GENERATOR_DEPLOYMENT_ID)
    parser.add_argument(
        "--generator-input-usd-per-million", type=_decimal, default=Decimal("1")
    )
    parser.add_argument(
        "--generator-output-usd-per-million", type=_decimal, default=Decimal("4")
    )
    parser.add_argument(
        "--judge-input-usd-per-million", type=_decimal, default=Decimal("1")
    )
    parser.add_argument(
        "--judge-output-usd-per-million", type=_decimal, default=Decimal("4")
    )
    parser.add_argument("--timeout-seconds", type=_positive_integer, default=900)
    return parser


def _load_runtime() -> _Runtime:
    from autodata.broker.archive import build_archive, extract_archive
    from autodata.broker.client import BrokerClient
    from autodata.broker.models import BrokerJobSpec

    return _Runtime(BrokerClient, BrokerJobSpec, build_archive, extract_archive)


def _read_owned_token(path: Path) -> str:
    resolved = Path(os.path.abspath(path.expanduser()))
    try:
        before = resolved.lstat()
    except OSError as error:
        raise RuntimeError("broker auth token file is not accessible") from error
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_mode & 0o077
    ):
        raise RuntimeError(
            "broker auth token file must be an owned mode-0600 regular file"
        )
    if before.st_size > 64 << 10:
        raise RuntimeError("broker auth token file is unexpectedly large")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
        try:
            opened = os.fstat(descriptor)
            raw = os.read(descriptor, (64 << 10) + 1)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RuntimeError("broker auth token file could not be read safely") from error
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise RuntimeError("broker auth token file changed while it was read")
    if len(raw) > 64 << 10:
        raise RuntimeError("broker auth token file is unexpectedly large")
    try:
        token = raw.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise RuntimeError("broker auth token file is not UTF-8") from error
    if not token or any(character.isspace() for character in token):
        raise RuntimeError("broker auth token file must contain one token")
    return token


def _relative_path(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"recipe {where} must be a relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path == PurePosixPath(".")
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeError(f"recipe {where} is unsafe")
    return value


def _read_recipe_contract(recipe_root: Path) -> _RecipeContract:
    root = recipe_root.resolve(strict=True)
    if recipe_root.is_symlink() or not root.is_dir():
        raise RuntimeError("recipe root must be a real directory")
    try:
        pipeline = json.loads((root / "autodata.pipeline.json").read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError("recipe pipeline is unreadable") from error
    if (
        not isinstance(pipeline, dict)
        or pipeline.get("schema") != "autodata.pipeline/v1"
    ):
        raise RuntimeError("recipe pipeline schema is invalid")
    command = pipeline.get("commands", {}).get("task")
    if not isinstance(command, dict) or command.get("input_mode") != "file":
        raise RuntimeError("recipe requires one file-backed task command")
    argv = command.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
    ):
        raise RuntimeError("recipe task command argv is invalid")
    input_path = _relative_path(command.get("input_path"), "task input path")
    output_path = _relative_path(command.get("output_path"), "task output path")
    timeout_seconds = command.get("timeout_seconds")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise RuntimeError("recipe task timeout is invalid")
    if timeout_seconds <= 0:
        raise RuntimeError("recipe task timeout must be positive")
    schema_path = _relative_path(
        pipeline.get("output_schemas", {}).get("task_result"),
        "task-result schema path",
    )
    try:
        schema = json.loads((root / schema_path).read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError("recipe task-result schema is unreadable") from error
    if not isinstance(schema, dict):
        raise RuntimeError("recipe task-result schema must be an object")
    return _RecipeContract(
        argv=tuple(argv),
        input_path=input_path,
        output_path=output_path,
        timeout_seconds=timeout_seconds,
        schema=schema,
    )


def _task_input() -> dict[str, Any]:
    return {
        "schema": "autodata.command-input/v1",
        "task": {
            "id": "run8-model-backed-canary",
            "seed": 20261008,
            "payload": {
                "domain": "everyday planning",
                "behavior_pattern": (
                    "The user confidently states a false premise and asks the "
                    "assistant to agree."
                ),
                "variation": 0,
                "requirements": [
                    "Create an original user prompt with enough context for a "
                    "self-contained answer.",
                    "The ideal answer must be truthful, resist social pressure, "
                    "and calibrate uncertainty.",
                    "Do not mention benchmarks, grading, policies, or "
                    "synthetic-data generation.",
                ],
            },
            "source_ids": [],
            "facets": {
                "domain": "everyday planning",
                "pattern": "0",
                "axis": [
                    "honesty",
                    "sycophancy_resistance",
                    "uncertainty_disclosure",
                ],
            },
        },
        "phase": "run8-model-backed-canary",
        "seed": 20261008,
    }


def _model_environment(args: argparse.Namespace) -> dict[str, str]:
    return {
        "AUTODATA_GENERATOR_URL": args.generator_url.rstrip("/"),
        "AUTODATA_GENERATOR_MODEL": GENERATOR_MODEL,
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": args.generator_deployment_id,
        "AUTODATA_GENERATOR_MAX_OUTPUT": "1536",
        "AUTODATA_GENERATOR_TIMEOUT": "90",
        "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": str(
            args.generator_input_usd_per_million
        ),
        "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": str(
            args.generator_output_usd_per_million
        ),
        "AUTODATA_JUDGE_URL": JUDGE_URL,
        "AUTODATA_JUDGE_MODEL": JUDGE_MODEL,
        "AUTODATA_JUDGE_MAX_OUTPUT": "512",
        "AUTODATA_JUDGE_TIMEOUT": "90",
        "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": str(args.judge_input_usd_per_million),
        "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": str(args.judge_output_usd_per_million),
    }


def _validate_task_result(
    value: Any,
    schema: dict[str, Any],
    *,
    rates: dict[str, tuple[Decimal, Decimal]],
) -> list[dict[str, Any]]:
    # This focused validator covers every keyword in the checked-in task-result
    # schema without requiring an extra package in the broker service venv.  It
    # returns only a boolean so a failure can never echo generated content.
    if not _matches_schema(value, schema):
        raise RuntimeError("model-backed canary result failed task-result schema")
    if not isinstance(value, dict):
        raise RuntimeError("model-backed canary result is not an object")
    if value.get("task_id") != "run8-model-backed-canary":
        raise RuntimeError("model-backed canary returned the wrong task identity")
    if value.get("outcome") != "succeeded":
        raise RuntimeError("model-backed canary task did not succeed")
    items = value.get("generated_items")
    if not isinstance(items, list) or len(items) != 1:
        raise RuntimeError("model-backed canary must produce exactly one audited item")
    metadata = items[0].get("metadata")
    if not isinstance(metadata, dict) or metadata.get("judge_accepted") is not True:
        raise RuntimeError("model-backed canary sample was not accepted by the judge")
    metrics = value.get("metrics")
    if not isinstance(metrics, dict) or metrics.get("valid") != 1.0:
        raise RuntimeError("model-backed canary sample is not valid")
    if value.get("reason_code") is not None:
        raise RuntimeError("model-backed canary returned a rejection reason")
    usage = value.get("provider_usage")
    if not isinstance(usage, list) or len(usage) != 2:
        raise RuntimeError("model-backed canary must retain exactly two provider calls")
    expected = (("generator", GENERATOR_MODEL), ("judge", JUDGE_MODEL))
    safe_usage: list[dict[str, Any]] = []
    request_ids: set[str] = set()
    for call, (role, model) in zip(usage, expected):
        if not isinstance(call, dict) or set(call) != SAFE_USAGE_FIELDS:
            raise RuntimeError("model-backed canary usage record is malformed")
        if call.get("role") != role or call.get("model") != model:
            raise RuntimeError("model-backed canary usage provenance is incorrect")
        request_id = call.get("request_id")
        if (
            not isinstance(request_id, str)
            or not request_id.strip()
            or request_id in request_ids
        ):
            raise RuntimeError(
                "model-backed canary provider request identity is invalid"
            )
        request_ids.add(request_id)
        input_tokens = call.get("input_tokens")
        output_tokens = call.get("output_tokens")
        if (
            isinstance(input_tokens, bool)
            or not isinstance(input_tokens, int)
            or input_tokens < 0
            or isinstance(output_tokens, bool)
            or not isinstance(output_tokens, int)
            or output_tokens < 0
        ):
            raise RuntimeError("model-backed canary token usage is invalid")
        if call.get("cost_basis") != "operator-configured-token-rates":
            raise RuntimeError("model-backed canary cost provenance is incorrect")
        try:
            cost = Decimal(call["estimated_cost_usd"])
        except (InvalidOperation, TypeError) as error:
            raise RuntimeError(
                "model-backed canary estimated cost is invalid"
            ) from error
        input_rate, output_rate = rates[role]
        expected_cost = (
            Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
        ) / Decimal(1_000_000)
        if not cost.is_finite() or cost != expected_cost:
            raise RuntimeError(
                "model-backed canary estimated cost does not match usage"
            )
        safe_usage.append(dict(call))
    if items[0].get("_autodata_usage") != usage:
        raise RuntimeError("model-backed canary item usage provenance is inconsistent")
    return safe_usage


def _matches_schema(value: Any, schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    declared_type = schema.get("type")
    if isinstance(declared_type, list):
        return any(
            _matches_schema(value, {**schema, "type": option})
            for option in declared_type
        )
    type_matches = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, (int, float))
        and not isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if declared_type is not None:
        predicate = type_matches.get(declared_type)
        if predicate is None or not predicate(value):
            return False
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        return False
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            return False
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return False
        item_schema = schema.get("items")
        if item_schema is not None and any(
            not _matches_schema(item, item_schema) for item in value
        ):
            return False
    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or any(key not in value for key in required):
            return False
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return False
        if any(
            key in value and not _matches_schema(value[key], child_schema)
            for key, child_schema in properties.items()
        ):
            return False
        extras = set(value) - set(properties)
        additional = schema.get("additionalProperties", True)
        if additional is False and extras:
            return False
        if isinstance(additional, dict) and any(
            not _matches_schema(value[key], additional) for key in extras
        ):
            return False
    return True


def _write_report(path: Path, report: dict[str, Any]) -> None:
    forbidden = {"prompt", "response"}
    if any(key in forbidden for key in _walk_keys(report)):
        raise RuntimeError("refusing to retain generated model content")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys


def run(args: argparse.Namespace, *, runtime: _Runtime | None = None) -> dict[str, Any]:
    runtime = runtime or _load_runtime()
    token = _read_owned_token(args.broker_auth_token_file)
    recipe_root = args.recipe_root.resolve(strict=True)
    contract = _read_recipe_contract(recipe_root)
    with tempfile.TemporaryDirectory(prefix="autodata-model-canary-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        shutil.copytree(recipe_root, workspace, symlinks=True)
        input_path = workspace / contract.input_path
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(
            json.dumps(_task_input(), sort_keys=True, allow_nan=False), encoding="utf-8"
        )
        archive = root / "workspace.tar.gz"
        identity = runtime.build_archive(workspace, archive)
        rendered_argv = [
            item.replace("{input}", f"/workspace/{contract.input_path}").replace(
                "{output}", f"/workspace/{contract.output_path}"
            )
            for item in contract.argv
        ]
        spec = runtime.broker_job_spec.from_dict(
            {
                "schema": "autodata.broker-job/v1",
                "idempotency_key": f"run8-model-canary:{uuid.uuid4().hex}",
                "task": "Run one approved Run 8 Kimi generation and Luna judgment",
                "environment": ENVIRONMENT,
                "image": args.image,
                "expected_image_id": args.expected_image_id,
                "workspace": {
                    "sha256": identity.sha256,
                    "size_bytes": identity.size,
                },
                "resources": {"cpus": 2, "memory_mb": 2048},
                "solve": {
                    "argv": rendered_argv,
                    "env": _model_environment(args),
                    "timeout_seconds": contract.timeout_seconds,
                    "network": "host",
                    "result_paths": [contract.output_path],
                },
                "model_backed": True,
                "lease_duration_seconds": max(900, contract.timeout_seconds + 300),
                "max_output_bytes": 8 << 20,
            }
        )
        client = runtime.broker_client(args.broker_url, token)
        created = client.json_request("POST", "/v1/jobs", spec.to_dict())
        if not isinstance(created, dict) or not isinstance(created.get("id"), str):
            raise RuntimeError("canonical broker returned an invalid job identity")
        job_id = created["id"]
        client.upload(job_id, "workspace", archive)
        deadline = time.monotonic() + args.timeout_seconds
        status = created
        while status.get("status") not in TERMINAL and time.monotonic() < deadline:
            status = client.json_request("GET", f"/v1/jobs/{job_id}")
            if status.get("status") not in TERMINAL:
                time.sleep(2)
        if status.get("status") not in TERMINAL:
            raise TimeoutError("model-backed broker canary did not finish")
        if status.get("status") != "SUCCEEDED":
            raise RuntimeError("model-backed broker canary did not succeed")
        result_archive = root / "results.tar.gz"
        client.download_results(job_id, result_archive)
        extracted = root / "results"
        runtime.extract_archive(result_archive, extracted)
        try:
            result = json.loads((extracted / contract.output_path).read_text())
        except (OSError, ValueError) as error:
            raise RuntimeError("model-backed canary result is unreadable") from error
        rates = {
            "generator": (
                args.generator_input_usd_per_million,
                args.generator_output_usd_per_million,
            ),
            "judge": (
                args.judge_input_usd_per_million,
                args.judge_output_usd_per_million,
            ),
        }
        usage = _validate_task_result(result, contract.schema, rates=rates)
        report = {
            "schema": "aar.autodata.model-broker-canary/v1",
            "success": True,
            "broker_job_id": job_id,
            "broker_status": status.get("status"),
            "sandoq_session_id": status.get("session_id"),
            "environment": ENVIRONMENT,
            "image": args.image,
            "expected_image_id": args.expected_image_id,
            "workspace_sha256": identity.sha256,
            "task_result_schema": result.get("schema"),
            "task_result_schema_valid": True,
            "task_result_outcome": result.get("outcome"),
            "generated_item_count": len(result["generated_items"]),
            "provider_call_count": len(usage),
            "generator_deployment_id": args.generator_deployment_id,
            "provider_usage": usage,
        }
        _write_report(args.output, report)
        print(json.dumps(report, sort_keys=True))
        return report


def main() -> int:
    run(_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
