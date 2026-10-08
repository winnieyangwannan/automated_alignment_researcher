#!/usr/bin/env python3
"""Run the real AAR AutoData workspace -> meta-optimize -> production lifecycle.

This is the operator-owned implementation behind ``LiveModelLifecycleBackend``.
It invokes the pinned AutoData CLI as the public operational contract, binds the
AAR scientific request to the checked-in recipe, and executes every generation
task through AutoData's native SandoQ Firecracker executor. Provider credentials
remain broker/service-side.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import threading
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping


RESEARCH_AGENT = "aar-research-agent"
INTEGRITY_MONITOR = "aar-integrity-monitor"
TUNING_COUNT = 64
VALIDATION_COUNT = 32
MINIMUM_VALID_RATE = 0.75
APPROVAL_POLICY_DIGEST = hashlib.sha256(
    b"aar-run8-unattended-production/v1:synthetic-only:no-benchmark-mimicry"
).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required operator setting is missing: {name}")
    return value


def _positive_decimal_env(name: str, *, allow_zero: bool = False) -> Decimal:
    try:
        value = Decimal(_required_env(name))
    except InvalidOperation as error:
        raise RuntimeError(f"{name} must be a finite decimal") from error
    if not value.is_finite() or value < 0 or (not allow_zero and value == 0):
        raise RuntimeError(f"{name} must be {'non-negative' if allow_zero else 'positive'}")
    return value


def _positive_int_setting(name: str, default: str) -> int:
    raw = os.environ.get(name, default).strip()
    if not raw.isdigit() or int(raw) < 1:
        raise RuntimeError(f"{name} must be a positive integer")
    return int(raw)


def _install_autodata(root: Path) -> None:
    source = root / "src"
    if not (source / "autodata" / "engine.py").is_file():
        raise RuntimeError(f"not an AutoData checkout: {root}")
    sys.path.insert(0, str(source))


def _autodata_cli(
    paths: Mapping[str, Path],
    *arguments: str,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Invoke one fixed native AutoData CLI operation and parse its JSON result.

    Callers construct ``arguments`` from server-owned paths and validated native
    identifiers. No agent-supplied shell command or free-form argv is accepted.
    """

    checkout = Path(_required_env("AUTODATA_SOURCE_ROOT")).resolve()
    source = checkout / "src"
    if not (source / "autodata" / "cli.py").is_file():
        raise RuntimeError(f"not an AutoData checkout: {checkout}")
    environment = os.environ.copy()
    python_path = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        str(source) if not python_path else str(source) + os.pathsep + python_path
    )
    command = [
        sys.executable,
        "-m",
        "autodata.cli",
        "--state",
        str(paths["database"]),
        "--artifacts",
        str(paths["artifacts"]),
        "--workspaces",
        str(paths["workspaces"]),
        *arguments,
    ]
    completed = subprocess.run(
        command,
        cwd=paths["root"],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=(
            timeout
            if timeout is not None
            else int(os.environ.get("AAR_AUTODATA_MAX_WALL_SECONDS", "10800")) + 300
        ),
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            "native AutoData CLI failed "
            f"({completed.returncode}) for {' '.join(arguments[:2])}: {detail}"
        )
    try:
        value = json.loads(completed.stdout)
    except ValueError as error:
        raise RuntimeError(
            "native AutoData CLI returned invalid JSON for "
            + " ".join(arguments[:2])
        ) from error
    if not isinstance(value, dict):
        raise RuntimeError("native AutoData CLI response must be a JSON object")
    return value


def _git_head(root: Path) -> str:
    value = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    if not all(character in "0123456789abcdef" for character in value) or len(value) != 40:
        raise RuntimeError("AutoData checkout did not resolve to a full Git SHA")
    return value


def _tree_digest(root: Path) -> str:
    members = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    return hashlib.sha256(_canonical_json(members)).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _read_frozen_json(
    path: Path, expected_sha256: str, *, owner_only: bool
) -> dict[str, Any]:
    """Read an operator-owned JSON artifact without following or racing a link."""

    resolved = Path(os.path.abspath(path.expanduser()))
    info = resolved.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError("operator evidence must be a regular file")
    forbidden_mode = 0o077 if owner_only else 0o022
    if info.st_uid != os.geteuid() or info.st_mode & forbidden_mode:
        raise RuntimeError("operator evidence has unsafe ownership or mode")
    if info.st_size > 1 << 20:
        raise RuntimeError("operator evidence is unexpectedly large")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(resolved, flags)
    try:
        opened = os.fstat(descriptor)
        payload = os.read(descriptor, (1 << 20) + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )
    if identity(info) != identity(opened) or identity(opened) != identity(after):
        raise RuntimeError("operator evidence changed while it was read")
    if len(payload) > 1 << 20:
        raise RuntimeError("operator evidence is unexpectedly large")
    digest = hashlib.sha256(payload).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise RuntimeError("operator evidence no longer matches its startup digest")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("operator evidence is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("operator evidence must be a JSON object")
    return value


class _UsageLedger:
    """Durable usage-only side channel, including hidden validation calls."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._calls: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            info = self.path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise RuntimeError("usage ledger must be a regular file")
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise RuntimeError("usage ledger must be owner-only")
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self._record_value(json.loads(line), append=False)

    @staticmethod
    def _validated(raw: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(raw.get("request_id") or "")
        role = raw.get("role")
        model = raw.get("model")
        input_tokens = raw.get("input_tokens")
        output_tokens = raw.get("output_tokens")
        if not request_id or role not in {"generator", "judge"}:
            raise RuntimeError("provider usage record has invalid identity or role")
        if not isinstance(model, str) or not model.strip():
            raise RuntimeError("provider usage record omitted model identity")
        for name, value in (
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError(f"provider usage record has invalid {name}")
        cost = Decimal(str(raw.get("estimated_cost_usd", "")))
        if not cost.is_finite() or cost < 0:
            raise RuntimeError("provider usage record has invalid estimated cost")
        if raw.get("cost_basis") != "operator-configured-token-rates":
            raise RuntimeError("provider usage record has an unsupported cost basis")
        return {
            "request_id": request_id,
            "role": role,
            "model": model.strip(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": format(cost, "f"),
            "cost_basis": "operator-configured-token-rates",
        }

    def _record_value(self, raw: Mapping[str, Any], *, append: bool) -> None:
        value = self._validated(raw)
        request_id = value["request_id"]
        previous = self._calls.get(request_id)
        if previous is not None:
            if previous != value:
                raise RuntimeError(
                    "provider request_id was reused with conflicting usage"
                )
            return
        self._calls[request_id] = value
        if append:
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.path, flags, 0o600)
            try:
                payload = json.dumps(value, sort_keys=True) + "\n"
                os.write(descriptor, payload.encode())
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def record_payload(self, payload: bytes) -> None:
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, ValueError):
            return
        if not isinstance(value, dict) or value.get("schema") != "autodata.task-result/v1":
            return
        usage = value.get("provider_usage")
        if not isinstance(usage, list):
            raise RuntimeError("task result provider_usage must be an array")
        with self._lock:
            for call in usage:
                if not isinstance(call, dict):
                    raise RuntimeError("task result contains malformed provider usage")
                self._record_value(call, append=True)

    def calls(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(self._calls[key]) for key in sorted(self._calls)]

    def totals(self) -> dict[str, Any]:
        calls = self.calls()
        if not calls:
            raise RuntimeError("no metered provider usage was retained")
        return {
            "spent_cost_usd": format(
                sum(
                    (Decimal(str(call["estimated_cost_usd"])) for call in calls),
                    Decimal(0),
                ),
                "f",
            ),
            "model_calls": len(calls),
            "input_tokens": sum(int(call["input_tokens"]) for call in calls),
            "output_tokens": sum(int(call["output_tokens"]) for call in calls),
            "cost_basis": "operator-configured-token-rates",
        }


def _collect_native_usage(paths: Mapping[str, Path], ledger: _UsageLedger) -> None:
    """Collect provider usage from native immutable artifacts.

    The native CLI owns execution and artifact persistence. This collector keeps
    AAR's campaign ledger complete without wrapping or replacing the upstream
    executor. ``record_payload`` retains only validated provider usage fields;
    prompts, responses, hidden task ids, and other task-result content are never
    copied to the usage ledger or returned in an error.
    """

    objects = paths["artifacts"] / "objects" / "sha256"
    if not objects.exists():
        return
    if objects.is_symlink() or not objects.is_dir():
        raise RuntimeError("native AutoData artifact object root is unsafe")
    for path in sorted(objects.glob("*/*")):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("native AutoData artifact object is unsafe")
        ledger.record_payload(path.read_bytes())


def _source_task_count(required_rows: int) -> int:
    if required_rows < 1:
        raise ValueError("required_rows must be positive")
    return max(
        VALIDATION_COUNT + TUNING_COUNT,
        (required_rows * 4 + 2) // 3,
    )


def _require_valid_aggregate(
    dataset: Mapping[str, Any], *, execution_label: str
) -> float:
    """Fail closed unless the final full-corpus dataset meets the frozen floor."""

    aggregate = dataset.get("aggregate")
    metrics = aggregate.get("metrics") if isinstance(aggregate, dict) else None
    value = metrics.get("valid") if isinstance(metrics, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(
            f"{execution_label} final dataset omitted numeric aggregate.metrics.valid"
        )
    valid_rate = float(value)
    if not math.isfinite(valid_rate) or valid_rate < MINIMUM_VALID_RATE:
        raise RuntimeError(
            f"{execution_label} final valid rate {valid_rate!r} is below frozen "
            f"minimum {MINIMUM_VALID_RATE}"
        )
    return valid_rate


def _maximum_model_task_attempts(source_count: int) -> int:
    if source_count < TUNING_COUNT + VALIDATION_COUNT:
        raise ValueError("source_count is too small for the explicit meta split")
    return 2 + 2 * TUNING_COUNT + 3 * VALIDATION_COUNT + 7 * source_count


def _native_export_dataset(
    paths: Mapping[str, Path], execution_id: str, *, label: str
) -> dict[str, Any]:
    """Export a completed dataset through the native CLI and parse it."""

    output = paths["root"] / "native-exports" / f"{label}.json"
    result = _autodata_cli(
        paths,
        "export",
        execution_id,
        "--output",
        str(output),
        timeout=300,
    )
    if result.get("execution_id") != execution_id or not output.is_file():
        raise RuntimeError("native AutoData export returned an inconsistent result")
    try:
        value = json.loads(output.read_text())
    except ValueError as error:
        raise RuntimeError("native AutoData export is not valid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("native AutoData export must be a JSON object")
    return value


def _native_status(paths: Mapping[str, Path], subject_id: str) -> dict[str, Any]:
    """Return AutoData's own status/dashboard snapshot for an authorized subject."""

    return _autodata_cli(paths, "status", subject_id, timeout=300)


def _runtime_executor(args: argparse.Namespace) -> dict[str, Any]:
    generator_timeout = _positive_int_setting(
        "AAR_AUTODATA_GENERATOR_TIMEOUT", "90"
    )
    judge_timeout = _positive_int_setting("AAR_AUTODATA_JUDGE_TIMEOUT", "90")
    request_attempts = _positive_int_setting(
        "AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS", "3"
    )
    if request_attempts > 5:
        raise RuntimeError("model request attempts must not exceed five")
    # Each request has a bounded number of attempts and exponential backoff.
    # Keep the combined generator+judge worst case within the task command's
    # 600-second sandbox timeout, including a small serialization margin.
    retry_backoff = 2 * sum(2**attempt for attempt in range(request_attempts - 1))
    if request_attempts * (generator_timeout + judge_timeout) + retry_backoff > 570:
        raise RuntimeError(
            "generator and judge retry timeouts exceed the 600-second task envelope"
        )
    generator_max_output = _positive_int_setting(
        "AAR_AUTODATA_GENERATOR_MAX_TOKENS", "1536"
    )
    judge_max_output = _positive_int_setting(
        "AAR_AUTODATA_JUDGE_MAX_TOKENS", "512"
    )
    generator_max_input = _positive_int_setting(
        "AAR_AUTODATA_GENERATOR_MAX_INPUT_TOKENS", "4096"
    )
    judge_max_input = _positive_int_setting(
        "AAR_AUTODATA_JUDGE_MAX_INPUT_TOKENS", "4096"
    )
    executor: dict[str, Any] = {
        "kind": "sandoq-firecracker",
        "environment": _required_env("AAR_AUTODATA_SANDOQ_ENVIRONMENT"),
        "image": _required_env("AAR_AUTODATA_OCI_IMAGE"),
        "expected_image_id": _required_env("AAR_AUTODATA_OCI_EXPECTED_IMAGE_ID"),
        "broker_url": _required_env("AAR_AUTODATA_BROKER_URL"),
        "model_backed": True,
        "cpus": int(os.environ.get("AAR_AUTODATA_TASK_CPUS", "2")),
        "memory_mb": int(os.environ.get("AAR_AUTODATA_TASK_MEMORY_MB", "2048")),
        "network": "host",
        "workdir": "/workspace",
        "non_secret_env": {
            "AUTODATA_GENERATOR_URL": args.generator_url,
            "AUTODATA_GENERATOR_MODEL": args.generator_model,
            "AUTODATA_GENERATOR_DEPLOYMENT_ID": _required_env(
                "AAR_AUTODATA_GENERATOR_DEPLOYMENT_ID"
            ),
            "AUTODATA_GENERATOR_MAX_OUTPUT": str(generator_max_output),
            "AUTODATA_GENERATOR_MAX_INPUT": str(generator_max_input),
            "AUTODATA_GENERATOR_TIMEOUT": str(generator_timeout),
            "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": str(
                _positive_decimal_env(
                    "AAR_AUTODATA_GENERATOR_INPUT_USD_PER_MILLION", allow_zero=True
                )
            ),
            "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": str(
                _positive_decimal_env(
                    "AAR_AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION", allow_zero=True
                )
            ),
            "AUTODATA_JUDGE_URL": args.judge_url,
            "AUTODATA_JUDGE_MODEL": args.judge_model,
            "AUTODATA_JUDGE_MAX_OUTPUT": str(judge_max_output),
            "AUTODATA_JUDGE_MAX_INPUT": str(judge_max_input),
            "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": str(request_attempts),
            "AUTODATA_JUDGE_TIMEOUT": str(judge_timeout),
            "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": str(
                _positive_decimal_env("AAR_AUTODATA_JUDGE_INPUT_USD_PER_MILLION")
            ),
            "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": str(
                _positive_decimal_env("AAR_AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION")
            ),
        },
    }
    auth_ref = os.environ.get("AAR_AUTODATA_BROKER_AUTH_SECRET_REF", "").strip()
    if auth_ref:
        if not os.environ.get(auth_ref):
            raise RuntimeError(f"broker auth secret environment variable is unset: {auth_ref}")
        executor["broker_auth_secret_ref"] = auth_ref
    return executor


def _protocol_paths(args: argparse.Namespace) -> dict[str, Path]:
    root = args.state_root.resolve()
    return {
        "root": root,
        "state": root / "driver-state.json",
        "pending": root / "pending-action.json",
        "draft": root / "live-workspace",
        "staging": root / "staging-recipe",
        "database": root / "autodata-state.db",
        "artifacts": root / "autodata-artifacts",
        "workspaces": root / "autodata-workspaces",
        "usage": root / "provider-usage.jsonl",
        "audit": root / "action-audit.json",
    }


def _protocol_request(args: argparse.Namespace) -> dict[str, Any]:
    saved = json.loads(args.request.read_text())
    return saved.get("request", saved)


def _protocol_runtime(
    args: argparse.Namespace,
) -> tuple[Any, Any, _UsageLedger, dict[str, Path], dict[str, Any]]:
    """Open read-only orchestration views not exposed by the native CLI.

    The store is used to resolve frozen snapshot and winning-candidate roots
    while constructing operator-owned execution manifests. Every lifecycle
    mutation still goes through ``_autodata_cli``.
    """

    from autodata.artifacts import FileArtifactStore
    from autodata.sqlite_store import SQLiteStateStore

    paths = _protocol_paths(args)
    request = _protocol_request(args)
    store = SQLiteStateStore(paths["database"])
    artifacts = FileArtifactStore(paths["artifacts"])
    usage = _UsageLedger(paths["usage"])
    state = json.loads(paths["state"].read_text())
    return store, artifacts, usage, paths, {**state, "request": request}


def _protocol_usage_delta(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    known = {item["request_id"] for item in before}
    calls = [item for item in after if item["request_id"] not in known]
    return {
        "spent_cost_usd": format(
            sum((Decimal(str(item["estimated_cost_usd"])) for item in calls), Decimal(0)),
            "f",
        ),
        "model_calls": len(calls),
        "input_tokens": sum(int(item["input_tokens"]) for item in calls),
        "output_tokens": sum(int(item["output_tokens"]) for item in calls),
    }


def _safe_broker_readiness(executor: Mapping[str, Any]) -> dict[str, Any]:
    secret_ref = executor.get("broker_auth_secret_ref")
    if not isinstance(secret_ref, str) or not secret_ref:
        raise RuntimeError("pinned broker executor omitted its auth secret reference")
    token = os.environ.get(secret_ref, "")
    if not token:
        raise RuntimeError("pinned broker authentication is unavailable")
    request = urllib.request.Request(
        str(executor["broker_url"]).rstrip("/") + "/readyz",
        headers={"Authorization": "Bearer " + token},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = response.read((1 << 20) + 1)
    except Exception as exc:
        raise RuntimeError("current broker readiness could not be verified") from exc
    if len(payload) > 1 << 20:
        raise RuntimeError("broker readiness response is unexpectedly large")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("broker readiness response is invalid") from exc
    runner = value.get("runner") if isinstance(value, dict) else None
    registry = value.get("registry") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("ready") is not True
        or not isinstance(runner, dict)
        or runner.get("ready") is not True
        or runner.get("runner") != "sandoq-firecracker"
        or not isinstance(registry, dict)
        or registry.get("ready") is not True
        or isinstance(value.get("max_concurrent"), bool)
        or not isinstance(value.get("max_concurrent"), int)
        or value["max_concurrent"] < 1
    ):
        raise RuntimeError("canonical broker is not currently ready")
    # Retain only fields that are useful evidence and cannot contain a secret.
    return {
        "ready": True,
        "runner": {"ready": True, "runner": "sandoq-firecracker"},
        "registry_ready": True,
        "max_concurrent": value["max_concurrent"],
    }


def _resource_approval_evidence(
    args: argparse.Namespace, request: Mapping[str, Any]
) -> dict[str, Any]:
    profile = _read_frozen_json(args.resource_profile, "", owner_only=False)
    profile_digest = hashlib.sha256(_canonical_json(profile)).hexdigest()
    if profile_digest != args.resource_profile_sha256:
        raise RuntimeError("resource profile no longer matches its startup digest")
    controls = request["controls"]
    spec = request["spec"]
    draft = _protocol_paths(args)["draft"]
    workspace = json.loads((draft / "autodata.workspace.json").read_text())
    executor = workspace["execution_defaults"]["executor"]

    expected_profile = {
        "schema": "aar.autodata.resource-profile/v1",
        "name": controls["resource_profile"],
        "autodata_framework_commit": request["pipeline_sha"],
        "budget_scope_id": controls["budget_scope_id"],
        "required_retained_rows": controls["required_retained_rows"],
        "max_concurrency": workspace["execution_defaults"]["concurrency"],
        "max_wall_seconds": workspace["execution_defaults"]["budget"][
            "max_wall_seconds"
        ],
        "training_view": spec["training_view"],
    }
    if any(profile.get(key) != value for key, value in expected_profile.items()):
        raise RuntimeError("resource profile does not match the approved run controls")
    for key, expected in (
        ("max_cost_usd", controls["max_cost_usd"]),
        (
            "max_estimated_cost_per_task_usd",
            _maximum_estimated_cost_per_task_usd(),
        ),
    ):
        try:
            matches = Decimal(str(profile.get(key))) == Decimal(str(expected))
        except InvalidOperation:
            matches = False
        if not matches:
            raise RuntimeError(f"resource profile has a mismatched {key}")
    generator = profile.get("generator")
    judge = profile.get("judge")
    pinned_executor = profile.get("executor")
    if (
        not isinstance(generator, dict)
        or generator.get("model") != args.generator_model
        or generator.get("deployment_id")
        != executor["non_secret_env"]["AUTODATA_GENERATOR_DEPLOYMENT_ID"]
        or generator.get("url") != args.generator_url
        or generator.get("max_output_tokens")
        != int(executor["non_secret_env"]["AUTODATA_GENERATOR_MAX_OUTPUT"])
        or generator.get("max_input_tokens")
        != int(executor["non_secret_env"]["AUTODATA_GENERATOR_MAX_INPUT"])
        or not isinstance(judge, dict)
        or judge.get("model") != args.judge_model
        or judge.get("max_output_tokens")
        != int(executor["non_secret_env"]["AUTODATA_JUDGE_MAX_OUTPUT"])
        or judge.get("max_input_tokens")
        != int(executor["non_secret_env"]["AUTODATA_JUDGE_MAX_INPUT"])
        or profile.get("model_request_max_attempts")
        != int(executor["non_secret_env"]["AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS"])
        or not isinstance(pinned_executor, dict)
        or any(
            pinned_executor.get(key) != executor.get(key)
            for key in ("kind", "environment", "image", "expected_image_id")
        )
    ):
        raise RuntimeError("resource profile provider or executor pins do not match")

    canary = _read_frozen_json(
        args.model_canary_report, args.model_canary_sha256, owner_only=True
    )
    usage = canary.get("provider_usage")
    if (
        canary.get("schema") != "aar.autodata.model-broker-canary/v1"
        or canary.get("success") is not True
        or canary.get("broker_status") != "SUCCEEDED"
        or not isinstance(canary.get("broker_job_id"), str)
        or not canary["broker_job_id"]
        or not isinstance(canary.get("sandoq_session_id"), str)
        or not canary["sandoq_session_id"]
        or canary.get("environment") != executor.get("environment")
        or canary.get("image") != executor.get("image")
        or canary.get("expected_image_id") != executor.get("expected_image_id")
        or canary.get("task_result_schema_valid") is not True
        or canary.get("task_result_outcome") != "succeeded"
        or canary.get("generated_item_count") != 1
        or canary.get("provider_call_count") != 2
        or canary.get("generator_deployment_id") != generator.get("deployment_id")
        or not isinstance(usage, list)
        or len(usage) != 2
        or [(item.get("role"), item.get("model")) for item in usage]
        != [("generator", args.generator_model), ("judge", args.judge_model)]
    ):
        raise RuntimeError("startup model-backed broker canary is invalid")
    readiness = _safe_broker_readiness(executor)
    if readiness["max_concurrent"] < workspace["execution_defaults"]["concurrency"]:
        raise RuntimeError("current broker concurrency is below the pinned profile")
    executor_evidence = {
        key: executor[key]
        for key in ("kind", "environment", "image", "expected_image_id", "broker_url")
    }
    return {
        "resource_evidence_schema": "aar.autodata.resource-approval-evidence/v1",
        "resource_profile_sha256": profile_digest,
        "budget_scope_id": controls["budget_scope_id"],
        "model_canary_sha256": args.model_canary_sha256,
        "broker_ready_snapshot_sha256": hashlib.sha256(
            _canonical_json(readiness)
        ).hexdigest(),
        "executor_sha256": hashlib.sha256(
            _canonical_json(executor_evidence)
        ).hexdigest(),
        "checks": [
            {"name": "resource_profile_verified", "passed": True},
            {"name": "budget_scope_verified", "passed": True},
            {"name": "startup_model_canary_verified", "passed": True},
            {"name": "broker_ready_verified", "passed": True},
            {"name": "executor_pins_verified", "passed": True},
        ],
    }


def _public_action(
    action: Any,
    artifacts: Any,
    request: Mapping[str, Any],
    args: argparse.Namespace | None = None,
) -> dict[str, Any]:
    value = action.to_dict()
    value.pop("editable_root", None)
    kind = value["kind"]
    if kind == "analyze_results":
        value["required_result"] = {
            "type": "object",
            "required": ["proposal", "dashboard_summary"],
            "properties": {
                "proposal": {"type": "string", "minLength": 1},
                "dashboard_summary": {
                    "type": "object",
                    "required": ["headline", "summary", "next_step"],
                    "properties": {
                        key: {"type": "string", "minLength": 1}
                        for key in ("headline", "summary", "next_step")
                    },
                },
            },
        }
        value["instructions"] += (
            " Return proposal plus dashboard_summary containing headline, summary, "
            "and next_step."
        )
    elif kind == "mutate_candidate":
        value["required_result"] = {
            "type": "object",
            "required": ["prompt_variant", "summary"],
            "properties": {
                "prompt_variant": {
                    "type": "string",
                    "enum": ["baseline_v1", "contrastive_v2"],
                },
                "summary": {"type": "string", "minLength": 1},
            },
        }
        value["instructions"] += (
            " Select prompt_variant from baseline_v1 or contrastive_v2 and explain "
            "the choice in summary."
        )
    if kind in {"approve_grounding", "approve_baseline", "approve_resources"}:
        if not action.artifacts and kind != "approve_resources":
            raise RuntimeError("native approval action omitted its evidence artifact")
        ref = action.artifacts[0] if action.artifacts else None
        evidence_value = json.loads(artifacts.get_bytes(ref)) if ref else {}
        if kind == "approve_grounding":
            sources = evidence_value.get("sources", [])
            synthetic = (
                evidence_value.get("source_count") == 0
                and "synthetic" in str(evidence_value.get("description", "")).lower()
            )
            sourced = (
                isinstance(sources, list)
                and bool(sources)
                and all(
                    isinstance(source, dict)
                    and isinstance(source.get("origin_uri"), str)
                    and bool(source["origin_uri"].strip())
                    and isinstance(source.get("license"), str)
                    and bool(source["license"].strip())
                    for source in sources
                )
            )
            checks = [
                {
                    "name": "coverage_present",
                    "passed": int(evidence_value.get("task_count", 0)) > 0
                    and bool(evidence_value.get("coverage_dimensions")),
                },
                {"name": "provenance_valid", "passed": synthetic or sourced},
            ]
            extras = {"task_count": int(evidence_value.get("task_count", 0))}
        elif kind == "approve_baseline":
            samples = evidence_value.get("sample_results", [])
            checks = [
                {
                    "name": "dry_run_passed",
                    "passed": bool(samples)
                    and all(item.get("outcome") == "succeeded" for item in samples),
                },
                {
                    "name": "pipeline_checks_passed",
                    "passed": evidence_value.get("schema")
                    == "autodata.baseline-review/v1"
                    and isinstance(evidence_value.get("pipeline"), str)
                    and bool(evidence_value["pipeline"].strip()),
                },
            ]
            extras = {"sample_count": len(samples)}
        else:
            if args is None:
                raise RuntimeError("resource approval requires operator evidence bindings")
            verified = _resource_approval_evidence(args, request)
            checks = verified.pop("checks")
            extras = verified
        evidence_payload = {"checks": checks, **extras}
        value["evidence"] = {
            "schema": "aar.autodata.approval-evidence/v1",
            "artifact_digest": (
                ref.digest
                if ref
                else "sha256:"
                + hashlib.sha256(_canonical_json(evidence_payload)).hexdigest()
            ),
            **evidence_payload,
        }
    return value


def _protocol_create(args: argparse.Namespace) -> dict[str, Any]:
    request = _protocol_request(args)
    if request.get("spec", {}).get("training_view") != "sft":
        raise RuntimeError("the live recipe supports only the sft training view")
    paths = _protocol_paths(args)
    paths["root"].mkdir(parents=True, exist_ok=True)
    if paths["state"].is_file():
        state = json.loads(paths["state"].read_text())
        return {
            "state": "active",
            "phase": state["phase"],
            "workspace_id": state["workspace_id"],
            "native_status": _native_status(paths, str(state["workspace_id"])),
        }
    required_rows = int(request["controls"]["required_retained_rows"])
    source_count = _source_task_count(required_rows)
    checkout = Path(_required_env("AUTODATA_SOURCE_ROOT")).resolve()
    if _git_head(checkout) != request["pipeline_sha"]:
        raise RuntimeError("canonical AutoData checkout does not match the request pin")
    recipe_source = Path(
        os.environ.get(
            "AAR_AUTODATA_RECIPE_ROOT",
            Path(__file__).resolve().parents[1]
            / "aar"
            / "autodata_recipes"
            / "dishonest_sycophancy_concealing",
        )
    ).resolve()
    shutil.copytree(
        recipe_source,
        paths["staging"],
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    _write_json(
        paths["staging"] / "recipe" / "request.json",
        {
            "schema": "aar.autodata.recipe-request/v1",
            "safety_axis": request["spec"]["safety_axis"],
            "training_mechanism": request["spec"]["training_mechanism"],
            "goal": request["spec"]["goal"],
        },
    )
    subprocess.run(
        [
            sys.executable,
            str(paths["staging"] / "grounding" / "build_manifest.py"),
            "--count",
            str(source_count),
            "--seed",
            str(request["spec"]["seed"]),
            "--output",
            str(paths["staging"] / "grounding" / "manifest.json"),
        ],
        check=True,
    )
    runtime_executor = _runtime_executor(args)
    workspace_raw = json.loads(
        (paths["staging"] / "autodata.workspace.json").read_text()
    )
    workspace_raw["authoring_executor"] = runtime_executor
    workspace_raw["execution_defaults"]["executor"] = runtime_executor
    workspace_raw["execution_defaults"]["concurrency"] = int(
        os.environ.get("AAR_AUTODATA_MAX_CONCURRENCY", "4")
    )
    max_attempts = _maximum_model_task_attempts(source_count) + 64
    workspace_raw["execution_defaults"]["budget"] = {
        "max_iterations": 1,
        "max_task_attempts": max_attempts,
        "max_wall_seconds": int(os.environ.get("AAR_AUTODATA_MAX_WALL_SECONDS", "10800")),
    }
    paths["draft"].mkdir()
    _write_json(paths["draft"] / "autodata.workspace.json", workspace_raw)
    created = _autodata_cli(
        paths,
        "workspace",
        "create",
        "--brief",
        str(paths["draft"] / "autodata.workspace.json"),
        "--root",
        str(paths["draft"]),
        "--idempotency-key",
        f"{request['run_id']}:workspace",
        timeout=300,
    )
    workspace_id = str(created.get("workspace_id") or "")
    if not workspace_id.startswith("ws_"):
        raise RuntimeError("native workspace create omitted workspace_id")
    state = {
        "schema": "aar.autodata.live-driver-state/v1",
        "phase": "workspace",
        "workspace_id": workspace_id,
        "source_count": source_count,
        "required_rows": required_rows,
        "max_attempts": max_attempts,
    }
    _write_json(paths["state"], state)
    return {
        "state": "active",
        "phase": "workspace",
        "workspace_id": workspace_id,
        "native_status": _native_status(paths, workspace_id),
    }


def _protocol_create_meta(
    store: Any,
    paths: Mapping[str, Path],
    state: dict[str, Any],
    request: Mapping[str, Any],
    frozen: Mapping[str, Any],
) -> None:
    from autodata import ExecutionSpec

    _autodata_cli(paths, "cancel", str(frozen["execution_id"]), timeout=300)
    snapshot = store.latest_snapshot(str(state["workspace_id"]))
    if snapshot is None or not snapshot.get("id"):
        raise RuntimeError("frozen native workspace omitted its snapshot")
    snapshot_id = str(snapshot["id"])
    returned_snapshot_id = frozen.get("snapshot_id")
    if returned_snapshot_id is not None and returned_snapshot_id != snapshot_id:
        raise RuntimeError("native workspace freeze returned a different snapshot")
    snapshot_root = Path(str(snapshot["root"]))
    source_count = int(state["source_count"])
    task_ids = [f"safety-sft-{index + 1:04d}" for index in range(source_count)]
    grounding_path = snapshot_root / "grounding" / "manifest.json"
    workspace = json.loads((paths["draft"] / "autodata.workspace.json").read_text())
    defaults = dict(workspace["execution_defaults"])
    meta_spec = ExecutionSpec.from_dict(
        {
            "schema": "autodata.execution/v1",
            **defaults,
            "grounding": {
                "manifest_path": "grounding/manifest.json",
                "digest": "sha256:"
                + hashlib.sha256(grounding_path.read_bytes()).hexdigest(),
            },
            "mode": "meta_optimize",
            "tuning_task_ids": task_ids[:TUNING_COUNT],
            "validation_task_ids": task_ids[
                TUNING_COUNT : TUNING_COUNT + VALIDATION_COUNT
            ],
            "split_seed": int(request["spec"]["seed"]),
        }
    )
    meta_manifest = paths["root"] / "meta-execution.json"
    _write_json(meta_manifest, meta_spec.to_dict())
    _autodata_cli(
        paths,
        "pipeline",
        "validate",
        str(snapshot_root / "autodata.pipeline.json"),
        timeout=300,
    )
    created = _autodata_cli(
        paths,
        "execution",
        "create",
        "--pipeline",
        str(snapshot_root / "autodata.pipeline.json"),
        "--execution",
        str(meta_manifest),
        "--study-id",
        str(store.study_for_subject("workspace", str(state["workspace_id"]))),
        "--idempotency-key",
        f"{request['run_id']}:meta-explicit-64",
        timeout=300,
    )
    execution_id = str(created.get("execution_id") or "")
    if not execution_id.startswith("exec_"):
        raise RuntimeError("native execution create omitted meta execution_id")
    state.update(
        phase="meta_optimize",
        meta_execution_id=execution_id,
        workspace_snapshot_id=snapshot_id,
        snapshot_root=str(snapshot_root),
    )
    _write_json(paths["state"], state)


def _protocol_create_production(
    store: Any,
    paths: Mapping[str, Path],
    state: dict[str, Any],
    request: Mapping[str, Any],
    completed: Mapping[str, Any],
) -> None:
    from autodata import ExecutionSpec

    meta_row = store.get_execution(str(state["meta_execution_id"]))
    winner = store.get_candidate(str(completed["winner_candidate_id"]))
    winner_root = Path(str(winner["workspace"]))
    raw = json.loads(str(meta_row["executionJson"]))
    raw["mode"] = "production"
    raw.pop("tuning_task_ids", None)
    raw.pop("validation_task_ids", None)
    raw["budget"] = {
        **raw["budget"],
        "max_task_attempts": int(state["max_attempts"]),
    }
    production_spec = ExecutionSpec.from_dict(raw)
    production_manifest = paths["root"] / "production-execution.json"
    _write_json(production_manifest, production_spec.to_dict())
    _autodata_cli(
        paths,
        "pipeline",
        "validate",
        str(winner_root / "autodata.pipeline.json"),
        timeout=300,
    )
    created = _autodata_cli(
        paths,
        "execution",
        "create",
        "--pipeline",
        str(winner_root / "autodata.pipeline.json"),
        "--execution",
        str(production_manifest),
        "--study-id",
        str(store.study_for_subject("workspace", str(state["workspace_id"]))),
        "--idempotency-key",
        f"{request['run_id']}:production",
        timeout=300,
    )
    execution_id = str(created.get("execution_id") or "")
    if not execution_id.startswith("exec_"):
        raise RuntimeError("native execution create omitted production execution_id")
    state.update(
        phase="production",
        production_execution_id=execution_id,
        winner_root=str(winner_root),
    )
    _write_json(paths["state"], state)


def _protocol_final_result(
    store: Any,
    paths: Mapping[str, Path],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    meta_dataset = _native_export_dataset(
        paths, str(state["meta_execution_id"]), label="meta-optimize"
    )
    production_dataset = _native_export_dataset(
        paths, str(state["production_execution_id"]), label="production"
    )
    meta_valid = _require_valid_aggregate(meta_dataset, execution_label="meta-optimize")
    production_valid = _require_valid_aggregate(
        production_dataset, execution_label="production"
    )
    raw_rows = production_dataset.get("items")
    if not isinstance(raw_rows, list):
        raise RuntimeError("native production dataset omitted items")
    accepted = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row.pop("_autodata_usage", None)
        metadata = row.get("metadata")
        if (
            isinstance(metadata, dict)
            and metadata.get("judge_accepted") is True
            and all(
                isinstance(row.get(key), str) and row[key].strip()
                for key in ("prompt", "response")
            )
        ):
            accepted.append(row)
    required = int(state["required_rows"])
    if len(accepted) < required:
        raise RuntimeError(
            f"production retained {len(accepted)} accepted rows; required {required}"
        )
    rows = sorted(accepted, key=lambda row: str(row.get("id")))[:required]
    winner_root = Path(str(state["winner_root"]))
    return {
        "state": "complete",
        "rows": rows,
        "manifest_fields": {
            "study_id": store.study_for_subject("workspace", str(state["workspace_id"])),
            "execution_id": state["production_execution_id"],
            "workspace_id": state["workspace_id"],
            "workspace_snapshot_id": state["workspace_snapshot_id"],
            "meta_optimize_execution_id": state["meta_execution_id"],
            "production_execution_id": state["production_execution_id"],
            "recipe_digest": _tree_digest(paths["draft"]),
            "pipeline_digest": hashlib.sha256(
                (winner_root / "autodata.pipeline.json").read_bytes()
            ).hexdigest(),
            "meta_optimize_source_task_count": len(meta_dataset["source_task_ids"]),
            "meta_optimize_tuning_task_count": TUNING_COUNT,
            "meta_optimize_validation_task_count": VALIDATION_COUNT,
            "production_source_task_count": len(production_dataset["source_task_ids"]),
            "meta_optimize_valid_rate": meta_valid,
            "production_valid_rate": production_valid,
            "counts": {
                "generated": len(raw_rows),
                "rejected": len(raw_rows) - len(accepted),
                "retained": len(rows),
            },
            "modes_completed_in_order": ["meta_optimize", "production"],
            "approval_principal": INTEGRITY_MONITOR,
            "approval_policy_sha256": APPROVAL_POLICY_DIGEST,
            "action_provider": "aar-visible-agent-and-integrity-monitor",
            "action_audit": (
                json.loads(paths["audit"].read_text())
                if paths["audit"].is_file()
                else []
            ),
            "sandoq_executor": "SandoQFirecrackerExecutor",
            "unattended": True,
        },
        "status_fields": {
            "workspace_id": state["workspace_id"],
            "workspace_snapshot_id": state["workspace_snapshot_id"],
            "meta_execution_id": state["meta_execution_id"],
            "production_execution_id": state["production_execution_id"],
            "retained_rows": len(rows),
        },
        "native_status": _native_status(
            paths, str(state["production_execution_id"])
        ),
    }


def _protocol_step(args: argparse.Namespace) -> dict[str, Any]:
    from autodata import ActionSpec

    store, artifacts, _, paths, state = _protocol_runtime(args)
    request = state.pop("request")
    if paths["pending"].is_file():
        saved = json.loads(paths["pending"].read_text())
        return {
            "state": "waiting_action",
            "phase": state["phase"],
            "action": saved["public"],
            "native_status": _native_status(
                paths, str(saved["native"]["scope"]["id"])
            ),
        }
    if state["phase"] == "workspace":
        value = _autodata_cli(
            paths, "workspace", "step", str(state["workspace_id"])
        )
        if value.get("schema") == "autodata.action/v1":
            action = ActionSpec.from_dict(value)
            public = _public_action(action, artifacts, request, args)
            _write_json(paths["pending"], {"native": value, "public": public})
            return {
                "state": "waiting_action",
                "phase": "workspace",
                "action": public,
                "native_status": _native_status(paths, str(state["workspace_id"])),
            }
        if value.get("status") != "frozen":
            return {
                "state": "active",
                "phase": "workspace",
                "workspace_id": state["workspace_id"],
                "native_status": _native_status(paths, str(state["workspace_id"])),
            }
        _protocol_create_meta(store, paths, state, request, value)
        return {
            "state": "active",
            "phase": "meta_optimize",
            "workspace_id": state["workspace_id"],
            "execution_id": state["meta_execution_id"],
            "native_status": _native_status(
                paths, str(state["meta_execution_id"])
            ),
        }
    execution_id = (
        state["meta_execution_id"]
        if state["phase"] == "meta_optimize"
        else state["production_execution_id"]
    )
    value = _autodata_cli(paths, "execution", "step", str(execution_id))
    if value.get("schema") == "autodata.action/v1":
        action = ActionSpec.from_dict(value)
        public = _public_action(action, artifacts, request, args)
        _write_json(paths["pending"], {"native": value, "public": public})
        return {
            "state": "waiting_action",
            "phase": state["phase"],
            "action": public,
            "native_status": _native_status(paths, str(execution_id)),
        }
    if value.get("status") != "completed":
        return {
            "state": "active",
            "phase": state["phase"],
            "execution_id": execution_id,
            "native_status": _native_status(paths, str(execution_id)),
        }
    if state["phase"] == "meta_optimize":
        _protocol_create_production(store, paths, state, request, value)
        return {
            "state": "active",
            "phase": "production",
            "execution_id": state["production_execution_id"],
            "native_status": _native_status(
                paths, str(state["production_execution_id"])
            ),
        }
    return _protocol_final_result(store, paths, state)


def _copy_authored_tree(source: Path, destination: Path, *, grounding_only: bool) -> None:
    """Materialize operator-staged files only when the agent completes authoring."""

    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("operator recipe must not contain symbolic links")
        relative = path.relative_to(source)
        is_grounding = bool(relative.parts) and relative.parts[0] == "grounding"
        if grounding_only != is_grounding:
            continue
        if not grounding_only and relative.as_posix() == "autodata.workspace.json":
            # The draft already contains the operator-bound runtime executor and budget.
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _agent_action_result(
    action: Any,
    supplied: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> dict[str, Any]:
    """Validate and apply the semantic contribution made by the AAR agent."""

    kind = action.kind
    if kind in {"clarify_design", "author_grounding", "author_pipeline"}:
        summary = supplied.get("summary")
        decisions = supplied.get("decisions")
        if not isinstance(summary, str) or not summary.strip():
            raise RuntimeError(f"{kind} requires a non-empty agent summary")
        if not isinstance(decisions, list) or not decisions or any(
            not isinstance(item, str) or not item.strip() for item in decisions
        ):
            raise RuntimeError(f"{kind} requires non-empty agent decisions")
        if kind == "author_grounding":
            _copy_authored_tree(paths["staging"], paths["draft"], grounding_only=True)
        elif kind == "author_pipeline":
            _copy_authored_tree(paths["staging"], paths["draft"], grounding_only=False)
        return {"summary": summary.strip(), "decisions": list(decisions)}
    if kind == "analyze_results":
        proposal = supplied.get("proposal")
        dashboard = supplied.get("dashboard_summary")
        if not isinstance(proposal, str) or not proposal.strip():
            raise RuntimeError("analyze_results requires a non-empty agent proposal")
        if not isinstance(dashboard, dict) or any(
            not isinstance(dashboard.get(key), str) or not dashboard[key].strip()
            for key in ("headline", "summary", "next_step")
        ):
            raise RuntimeError(
                "analyze_results requires headline, summary, and next_step strings"
            )
        return {"proposal": proposal.strip(), "dashboard_summary": dict(dashboard)}
    if kind == "mutate_candidate":
        variant = supplied.get("prompt_variant")
        if variant not in {"baseline_v1", "contrastive_v2"}:
            raise RuntimeError(
                "mutate_candidate requires an allowlisted prompt_variant"
            )
        if not action.editable_root:
            raise RuntimeError("native mutation action omitted editable_root")
        _write_json(
            Path(action.editable_root) / "recipe" / "prompt_variant.json",
            {"variant": variant},
        )
        summary = supplied.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = f"The AAR agent selected the allowlisted {variant} prompt variant."
        return {"summary": summary.strip()}
    if kind in {"approve_grounding", "approve_baseline", "approve_resources"}:
        # AutoData v1 calls this field user_acknowledged. In this unattended
        # integration it is an integrity-monitor acknowledgement, retained for
        # native contract compatibility rather than evidence of a human action.
        result = dict(supplied)
        result["user_acknowledged"] = True
        return result
    raise RuntimeError(f"unsupported native action kind: {kind}")


def _pending_native_action(
    args: argparse.Namespace,
) -> tuple[Any, dict[str, Path], dict[str, Any]]:
    from autodata import ActionSpec

    _, _, _, paths, state = _protocol_runtime(args)
    state.pop("request")
    if not paths["pending"].is_file():
        raise RuntimeError("no native action is pending")
    pending = json.loads(paths["pending"].read_text())
    action = ActionSpec.from_dict(pending["native"])
    if args.action_id != action.id:
        raise RuntimeError("action id does not match the pending native action")
    return action, paths, state


def _protocol_action_begin(args: argparse.Namespace) -> dict[str, Any]:
    action, paths, state = _pending_native_action(args)
    begun = _autodata_cli(paths, "action", "begin", action.id, timeout=300)
    token = begun.get("lease_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("native action begin omitted lease_token")
    return {
        "state": "waiting_action",
        "phase": state["phase"],
        "workspace_id": state["workspace_id"],
        "action": begun.get("action"),
        "lease_token": token,
        "native_status": _native_status(paths, str(action.scope.id)),
    }


def _protocol_action(args: argparse.Namespace) -> dict[str, Any]:
    action, paths, state = _pending_native_action(args)
    payload = json.loads(args.payload.read_text())
    lease_token = payload.get("lease_token")
    if not isinstance(lease_token, str) or not lease_token:
        raise RuntimeError("native action completion requires its lease_token")
    if args.kind == "action_complete":
        supplied = payload.get("result")
        if not isinstance(supplied, dict):
            raise RuntimeError("action completion requires an object result")
        result = _agent_action_result(action, supplied, paths)
        result_path = paths["root"] / "action-results" / f"{action.id}.json"
        _write_json(result_path, result)
        _autodata_cli(
            paths,
            "action",
            "complete",
            action.id,
            "--lease-token",
            lease_token,
            "--result",
            str(result_path),
            timeout=300,
        )
        audit = json.loads(paths["audit"].read_text()) if paths["audit"].is_file() else []
        audit.append(
            {
                "action_id": action.id,
                "scope_kind": action.scope.kind,
                "scope_id": action.scope.id,
                "scope_revision": action.scope.revision,
                "kind": action.kind,
                "actor": (
                    INTEGRITY_MONITOR
                    if action.kind
                    in {"approve_grounding", "approve_baseline", "approve_resources"}
                    else RESEARCH_AGENT
                ),
                "result_sha256": hashlib.sha256(_canonical_json(result)).hexdigest(),
            }
        )
        _write_json(paths["audit"], audit)
    elif args.kind == "action_fail":
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise RuntimeError("action failure requires a non-empty reason")
        _autodata_cli(
            paths,
            "action",
            "fail",
            action.id,
            "--lease-token",
            lease_token,
            "--reason",
            reason.strip(),
            timeout=300,
        )
    else:
        raise RuntimeError(f"unsupported action operation: {args.kind}")
    paths["pending"].unlink()
    return {
        "state": "active",
        "phase": state["phase"],
        "workspace_id": state["workspace_id"],
        "native_status": _native_status(paths, str(action.scope.id)),
    }


def _protocol_step_model_tasks(args: argparse.Namespace) -> int:
    """Return a conservative task ceiling for exactly one native step call."""

    if args.kind != "step":
        return 0
    paths = _protocol_paths(args)
    if not paths["state"].is_file() or paths["pending"].is_file():
        return 0
    from autodata.sqlite_store import SQLiteStateStore

    state = json.loads(paths["state"].read_text())
    store = SQLiteStateStore(paths["database"])
    source_count = int(state["source_count"])
    if state["phase"] == "workspace":
        row = store.get_workspace(str(state["workspace_id"]))
        phase = str(row["phase"])
        reaches_dry_run = phase == "dry_run_pending"
        if phase == "pipeline_pending":
            reaches_dry_run = store.completed_action(
                "workspace",
                str(state["workspace_id"]),
                "author_pipeline",
                int(row["revision"]),
            ) is not None
        if phase == "resources_review":
            reaches_dry_run = store.completed_action(
                "workspace",
                str(state["workspace_id"]),
                "approve_resources",
                int(row["revision"]),
            ) is not None
        if not reaches_dry_run:
            return 0
        manifest = paths["draft"] / "grounding" / "manifest.json"
        if not manifest.is_file():
            return 3
        grounding = json.loads(manifest.read_text())
        dry_ids = grounding.get("dry_run_task_ids", [])
        return len(dry_ids) if isinstance(dry_ids, list) and dry_ids else 3
    execution_id = (
        state["meta_execution_id"]
        if state["phase"] == "meta_optimize"
        else state["production_execution_id"]
    )
    row = store.get_execution(str(execution_id))
    phase = str(row["phase"])
    if phase == "baseline_pending":
        return (
            TUNING_COUNT + VALIDATION_COUNT
            if state["phase"] == "meta_optimize"
            else source_count
        )
    if phase == "awaiting_mutation":
        selection = VALIDATION_COUNT if state["phase"] == "meta_optimize" else source_count
        # One paired comparison and a final full-corpus run which may retry once.
        return 2 * selection + 2 * source_count
    if phase == "final_pending":
        return 2 * source_count
    return 0


def _maximum_estimated_cost_per_task_usd() -> Decimal:
    """Derive the fail-closed task reservation from frozen model controls."""

    attempts = _positive_int_setting(
        "AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS", "3"
    )
    if attempts > 5:
        raise RuntimeError("model request attempts must not exceed five")
    generator_input = _positive_int_setting(
        "AAR_AUTODATA_GENERATOR_MAX_INPUT_TOKENS", "4096"
    )
    generator_output = _positive_int_setting(
        "AAR_AUTODATA_GENERATOR_MAX_TOKENS", "1536"
    )
    judge_input = _positive_int_setting(
        "AAR_AUTODATA_JUDGE_MAX_INPUT_TOKENS", "4096"
    )
    judge_output = _positive_int_setting(
        "AAR_AUTODATA_JUDGE_MAX_TOKENS", "512"
    )
    generator_input_rate = _positive_decimal_env(
        "AAR_AUTODATA_GENERATOR_INPUT_USD_PER_MILLION", allow_zero=True
    )
    generator_output_rate = _positive_decimal_env(
        "AAR_AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION", allow_zero=True
    )
    judge_input_rate = _positive_decimal_env(
        "AAR_AUTODATA_JUDGE_INPUT_USD_PER_MILLION"
    )
    judge_output_rate = _positive_decimal_env(
        "AAR_AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION"
    )
    one_attempt = (
        Decimal(generator_input) * generator_input_rate
        + Decimal(generator_output) * generator_output_rate
        + Decimal(judge_input) * judge_input_rate
        + Decimal(judge_output) * judge_output_rate
    ) / Decimal(1_000_000)
    return Decimal(attempts) * one_attempt


def _protocol_prepare(args: argparse.Namespace) -> dict[str, Any]:
    tasks = _protocol_step_model_tasks(args)
    maximum = (
        Decimal(tasks) * _maximum_estimated_cost_per_task_usd()
        if tasks
        else Decimal(0)
    )
    return {
        "maximum_cost_usd": format(maximum, "f"),
        "performs_model_call": tasks > 0,
        "maximum_model_tasks": tasks,
    }


def _protocol_execute(args: argparse.Namespace) -> dict[str, Any]:
    paths = _protocol_paths(args)
    ledger = _UsageLedger(paths["usage"])
    before = ledger.calls()
    result: dict[str, Any] | None = None
    failure: Exception | None = None
    usage_complete = True
    try:
        if args.kind == "create_workspace":
            result = _protocol_create(args)
        elif args.kind == "step":
            result = _protocol_step(args)
        elif args.kind == "action_begin":
            result = _protocol_action_begin(args)
        elif args.kind in {"action_complete", "action_fail"}:
            result = _protocol_action(args)
        else:
            raise RuntimeError(f"unsupported protocol operation kind: {args.kind}")
    except Exception as exc:
        failure = exc
    try:
        _collect_native_usage(paths, ledger)
    except Exception as exc:
        usage_complete = False
        failure = RuntimeError("native AutoData provider usage collection failed")
        failure.__cause__ = exc
    after = ledger.calls()
    usage = _protocol_usage_delta(before, after)
    if failure is not None:
        _write_json(
            args.output,
            {
                "state": "failed",
                "error": str(failure),
                "usage": usage,
                "usage_complete": usage_complete,
            },
        )
        raise failure
    if result is None:
        raise RuntimeError("native AutoData operation omitted its result")
    return {**result, "usage": usage, "usage_complete": usage_complete}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--operation", choices=("prepare", "execute"), required=True)
    result.add_argument(
        "--kind",
        choices=(
            "create_workspace",
            "step",
            "action_begin",
            "action_complete",
            "action_fail",
        ),
        required=True,
    )
    result.add_argument("--request", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--state-root", type=Path)
    result.add_argument("--payload", type=Path)
    result.add_argument("--action-id", default="")
    result.add_argument("--reservation-id", default="")
    result.add_argument("--model-canary-report", type=Path, required=True)
    result.add_argument("--model-canary-sha256", required=True)
    result.add_argument("--resource-profile", type=Path, required=True)
    result.add_argument("--resource-profile-sha256", required=True)
    result.add_argument("--generator-model")
    result.add_argument("--generator-url")
    result.add_argument("--judge-model")
    result.add_argument("--judge-url")
    result.add_argument("--generator-token-env")
    result.add_argument("--judge-token-env")
    return result


def main() -> int:
    args = parser().parse_args()
    checkout = Path(_required_env("AUTODATA_SOURCE_ROOT")).resolve()
    _install_autodata(checkout)
    if not args.state_root or not args.payload:
        raise RuntimeError("protocol mode requires --state-root and --payload")
    if args.operation == "prepare":
        value = _protocol_prepare(args)
    else:
        for name in (
            "generator_model",
            "generator_url",
            "judge_model",
            "judge_url",
            "generator_token_env",
            "judge_token_env",
        ):
            if not getattr(args, name):
                raise RuntimeError(f"protocol execution requires --{name.replace('_', '-')}")
        if not os.environ.get(args.generator_token_env):
            raise RuntimeError("configured generator credential environment variable is unset")
        if not os.environ.get(args.judge_token_env):
            raise RuntimeError("configured judge credential environment variable is unset")
        value = _protocol_execute(args)
    _write_json(args.output, value)
    print(json.dumps({"status": value.get("state", "prepared")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
