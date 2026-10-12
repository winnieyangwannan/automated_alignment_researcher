#!/usr/bin/env python3
"""Run one orchestration-owned controller for native AutoData subjects.

The research agent authors workspaces/executions and handles visible approval
requests.  This process is the sole owner of ``workspace step`` and
``execution step`` calls.  It keeps the hot SQLite database on node-local
storage and atomically snapshots it to retained storage while a step is in
flight and whenever a step returns.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, TextIO, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aar.failure_feedback import (
    FailureFeedbackError,
    build_failure_feedback,
    feedback_from_exception,
)
from aar.infrastructure.autodata_contract import validate_generation_inputs
from aar.infrastructure.autodata_execution_contract import (
    bound_grounding_task_ids,
    canonical_execution_manifest,
    canonical_meta_manifest_from_default,
    canonical_production_manifest_from_meta,
    operator_execution_settings,
    validate_runtime_campaign_policy_rewrite,
)
from aar.infrastructure.autodata_coordinator import (
    AutoDataActionReconciler,
    AutoDataCoordinatorError,
    ExecutionAnalysisReconciler,
    ExecutionMutationReconciler,
    NativeAutoDataControl,
    WorkspacePipelineReconciler,
)
from aar.infrastructure.autodata_coordinator.coordinator import (
    WorkspaceApprovalReconciler,
)
from aar.infrastructure.autodata_coordinator.claude_worker import ClaudeWorker
from aar.infrastructure.autodata_coordinator.kimi_worker import KimiWorker
from aar.infrastructure.autodata_coordinator.training_smoke import (
    TrainingSmokeCoordinator,
    TrainingSmokeCoordinatorError,
)

META_TIMEOUT_SECONDS = 2 * 60 * 60
PRODUCTION_TIMEOUT_SECONDS = 8 * 60 * 60
NATIVE_WALL_GRACE_SECONDS = 10 * 60
META_STALL_SECONDS = 20 * 60
PRODUCTION_STALL_SECONDS = 30 * 60
DEFAULT_SNAPSHOT_INTERVAL_SECONDS = 5 * 60
DEFAULT_SNAPSHOT_TIMEOUT_SECONDS = 60
DEFAULT_CONTROL_LOCK_TIMEOUT_SECONDS = 60
DEFAULT_STATUS_HEARTBEAT_SECONDS = 30
PROCESS_TERMINATE_GRACE_SECONDS = 30
PROCESS_KILL_GRACE_SECONDS = 10
CONTROL_SCHEMA = "aar.autodata.lifecycle-control/v1"
SUPERVISED_EXECUTION_KEY_SCHEMA = "aar.autodata.supervised-execution/v1"
WORKSPACE_RECONCILE_MAX_ATTEMPTS = 3
WORKSPACE_RECONCILE_SLA_SECONDS = 60
SUPERVISED_TRANSITION_SCHEMA = "aar.autodata.supervised-transition/v1"
PRODUCTION_GROUNDING_PATH = "grounding/production-manifest.json"
PRODUCTION_ID_PREFIX = "safety-prod"
PRODUCTION_SEED_OFFSET = 1000
_MAX_PRIVATE_PROCESS_OUTPUT_BYTES = 1024 * 1024
_MAX_NATIVE_DIAGNOSTIC_BYTES = 1024 * 1024
_PERMANENT_NATIVE_DIAGNOSTICS = {
    "task_attempts budget exceeded": "native_task_attempt_budget_exceeded",
    "iterations budget exceeded": "native_iteration_budget_exceeded",
    "wall-clock budget exceeded": "native_wall_clock_budget_exceeded",
    "workspace task-attempt budget exceeded": "native_workspace_task_attempt_budget_exceeded",
    "workspace revision budget exceeded": "native_workspace_revision_budget_exceeded",
}

_ResultT = TypeVar("_ResultT")


class NativeStepFailure(RuntimeError):
    """Terminal native-step failure with a content-safe public classification."""

    def __init__(
        self,
        detail: str | None = None,
        *,
        error_code: str | None = None,
        attempts: int = 3,
    ) -> None:
        self.detail = detail
        self.error_code = error_code or (
            "native_action_result_contract_failed"
            if detail is not None
            else "lifecycle_step_failed"
        )
        self.public_summary = "native AutoData lifecycle step failed"
        if detail is not None:
            self.public_summary += f": {detail}"
        message = (
            "native AutoData step failed permanently"
            if attempts == 1
            else "native AutoData step failed three times without state progress"
        )
        if detail is not None:
            message += f": {detail}"
        super().__init__(message)


def _retain_operator_process_evidence(
    completed: subprocess.CompletedProcess[str], *, error_code: str, stage: str
) -> None:
    """Best-effort mode-0600 evidence; never expose its path to research."""
    team_raw = os.environ.get("TEAM_DIR", "").strip()
    if not team_raw:
        return
    try:
        root = Path(team_raw) / "secrets" / "failure-evidence"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        path = root / (
            f"autodata-{stage}-{error_code}-{os.getpid()}-{time.time_ns()}.json"
        )
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        value = {
            "schema": "aar.autodata.private-process-failure/v1",
            "stage": stage,
            "error_code": error_code,
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "")[:_MAX_PRIVATE_PROCESS_OUTPUT_BYTES],
            "stderr": (completed.stderr or "")[:_MAX_PRIVATE_PROCESS_OUTPUT_BYTES],
            "truncated": bool(
                len(completed.stdout or "") > _MAX_PRIVATE_PROCESS_OUTPUT_BYTES
                or len(completed.stderr or "") > _MAX_PRIVATE_PROCESS_OUTPUT_BYTES
            ),
            "recorded_at": _utc_now(),
        }
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, sort_keys=True, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        # Evidence retention must not replace the original typed failure.
        return


def _subprocess_failure(
    completed: subprocess.CompletedProcess[str],
    *,
    error_code: str,
    stage: str,
    public_summary: str,
) -> FailureFeedbackError:
    _retain_operator_process_evidence(
        completed, error_code=error_code, stage=stage
    )
    feedback = build_failure_feedback(
        RuntimeError(public_summary),
        error_code=error_code,
        stage=stage,
        public_summary=f"{public_summary} (exit {completed.returncode})",
    )
    return FailureFeedbackError(feedback)


def _reconciliation_failure(
    error: BaseException,
    *,
    error_code: str,
    public_summary: str,
) -> FailureFeedbackError:
    """Return one content-free, stage-specific workspace failure."""
    if isinstance(error, FailureFeedbackError):
        return error
    return FailureFeedbackError(
        build_failure_feedback(
            error,
            error_code=error_code,
            stage="autodata_lifecycle",
            public_summary=public_summary,
        )
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pipeline_tree_digest(root: Path) -> str:
    """Return a deterministic digest for one safe, immutable pipeline tree."""
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("AutoData pipeline root must be a real directory")
    resolved = root.resolve(strict=True)
    files: dict[str, str] = {}
    for base, directories, names in os.walk(resolved, followlinks=False):
        for name in [*directories, *names]:
            path = Path(base, name)
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise RuntimeError("AutoData pipeline tree contains an unsafe entry")
        for name in names:
            path = Path(base, name)
            relative = path.relative_to(resolved).as_posix()
            if relative == ".autodata" or relative.startswith(".autodata/"):
                continue
            files[relative] = _sha256(path)
    payload = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} must be a real JSON file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must contain one JSON object")
    return value


def execution_creation_key(
    pipeline: Path,
    execution: Path,
    *,
    study_id: str,
    workspaces: Path,
) -> str:
    """Bind execution creation retries to one semantic, run-local request."""
    pipeline = pipeline.resolve(strict=True)
    execution = execution.resolve(strict=True)
    workspaces = workspaces.resolve(strict=True)
    identity = {
        "schema": SUPERVISED_EXECUTION_KEY_SCHEMA,
        "study_id": study_id,
        "pipeline_path": str(pipeline),
        "pipeline": _json_object(pipeline, "AutoData pipeline manifest"),
        "pipeline_tree_digest": _pipeline_tree_digest(pipeline.parent),
        "execution": _json_object(execution, "AutoData execution manifest"),
        "workspaces": str(workspaces),
    }
    encoded = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "aar-supervised:" + hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.chmod(0o600)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _fsync_tree(root: Path) -> None:
    """Make a newly staged immutable tree durable before publishing its rename."""
    directories = [root]
    for base, names, files in os.walk(root, followlinks=False):
        base_path = Path(base)
        directories.extend(base_path / name for name in names)
        for name in files:
            with (base_path / name).open("rb") as handle:
                os.fsync(handle.fileno())
    for directory in reversed(directories):
        _fsync_directory(directory)


def _verify_database(path: Path, *, deadline: float | None = None) -> None:
    if deadline is None:
        deadline = time.monotonic() + DEFAULT_SNAPSHOT_TIMEOUT_SECONDS

    def interrupt_if_expired() -> int:
        return int(time.monotonic() >= deadline)

    with sqlite3.connect(
        f"file:{path}?mode=ro&immutable=1",
        uri=True,
        timeout=max(0.001, min(5.0, deadline - time.monotonic())),
    ) as connection:
        connection.set_progress_handler(interrupt_if_expired, 10_000)
        try:
            quick = connection.execute("PRAGMA quick_check").fetchall()
            integrity = connection.execute("PRAGMA integrity_check").fetchall()
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        except sqlite3.OperationalError as error:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"SQLite snapshot verification exceeded its deadline for {path}"
                ) from error
            raise
        finally:
            connection.set_progress_handler(None, 0)
    if quick != [("ok",)]:
        raise RuntimeError(f"SQLite quick_check failed for {path}: {quick!r}")
    if integrity != [("ok",)]:
        raise RuntimeError(f"SQLite integrity_check failed for {path}: {integrity!r}")
    if foreign_keys:
        raise RuntimeError(
            f"SQLite foreign_key_check failed for {path}: {foreign_keys!r}"
        )


def snapshot_database(
    source: Path,
    retained: Path,
    *,
    reason: str,
    timeout_seconds: float | None = None,
) -> bool:
    """Create an atomic, self-contained SQLite backup on retained storage."""
    if not source.is_file():
        return False
    if timeout_seconds is None:
        raw_timeout = os.getenv(
            "AAR_AUTODATA_SNAPSHOT_TIMEOUT_SECONDS",
            str(DEFAULT_SNAPSHOT_TIMEOUT_SECONDS),
        )
        try:
            timeout_seconds = float(raw_timeout)
        except ValueError as error:
            raise RuntimeError(
                "AAR_AUTODATA_SNAPSHOT_TIMEOUT_SECONDS must be a positive number"
            ) from error
    if timeout_seconds <= 0:
        raise RuntimeError(
            "AAR_AUTODATA_SNAPSHOT_TIMEOUT_SECONDS must be a positive number"
        )
    deadline = time.monotonic() + timeout_seconds
    retained.parent.mkdir(parents=True, exist_ok=True)
    temporary = retained.with_name(f"{retained.name}.tmp.{os.getpid()}")
    try:
        sqlite_timeout = max(0.001, min(5.0, timeout_seconds))
        with sqlite3.connect(
            f"file:{source}?mode=ro", uri=True, timeout=sqlite_timeout
        ) as source_db:
            with sqlite3.connect(temporary, timeout=sqlite_timeout) as destination_db:
                def fail_if_expired(
                    _status: int, _remaining: int, _total: int
                ) -> None:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"SQLite snapshot backup exceeded its deadline for {source}"
                        )

                source_db.backup(
                    destination_db,
                    pages=256,
                    progress=fail_if_expired,
                    sleep=0.1,
                )
        _verify_database(temporary, deadline=deadline)
        temporary.chmod(0o600)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        new_digest = _sha256(temporary)
        previous_digest = _sha256(retained) if retained.is_file() else None
        # Publish a transition manifest first.  Recovery accepts either the old
        # or new digest, so a node failure on either side of os.replace never
        # leaves a valid database paired with an unusable manifest.
        transition = {
            "schema": "aar.autodata.state-snapshot/v1",
            "created_at": _utc_now(),
            "reason": reason,
            "sha256": new_digest,
            "size_bytes": temporary.stat().st_size,
        }
        if previous_digest is not None:
            transition["previous_sha256"] = previous_digest
        metadata_path = retained.with_name(f"{retained.name}.snapshot.json")
        _atomic_json(metadata_path, transition)
        os.replace(temporary, retained)
        # A retained snapshot is a self-contained main database, not a live WAL
        # database. Stale sidecars from an earlier network-hosted controller can
        # otherwise be replayed against the newly published file and make a
        # valid snapshot appear corrupt. The source is node-local in supervised
        # mode, so these retained-path sidecars never belong to the live writer.
        for suffix in ("-wal", "-shm"):
            Path(f"{retained}{suffix}").unlink(missing_ok=True)
        directory_fd = os.open(retained.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        transition.pop("previous_sha256", None)
        _atomic_json(metadata_path, transition)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def restore_database(
    retained: Path, destination: Path, *, require_manifest: bool = False
) -> bool:
    """Restore a verified retained snapshot into a fresh node-local database."""
    if not retained.is_file():
        return False
    metadata_path = retained.with_name(f"{retained.name}.snapshot.json")
    if not metadata_path.is_file() and require_manifest:
        raise RuntimeError("retained AutoData state is missing its snapshot manifest")
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("schema") != "aar.autodata.state-snapshot/v1":
            raise RuntimeError("retained AutoData state has an unknown snapshot schema")
        actual_digest = _sha256(retained)
        allowed_digests = {metadata.get("sha256"), metadata.get("previous_sha256")}
        if actual_digest not in allowed_digests:
            raise RuntimeError("retained AutoData state does not match its snapshot digest")
    _verify_database(retained)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.tmp.{os.getpid()}")
    try:
        with sqlite3.connect(
            f"file:{retained}?mode=ro&immutable=1", uri=True
        ) as source_db:
            with sqlite3.connect(temporary) as destination_db:
                source_db.backup(destination_db)
        _verify_database(temporary)
        temporary.chmod(0o600)
        os.replace(temporary, destination)
        return True
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Subject:
    kind: str
    subject_id: str
    phase: str
    timeout_seconds: int | None
    stall_seconds: int
    production: bool = False


def _empty_control() -> dict[str, Any]:
    return {"schema": CONTROL_SCHEMA, "subjects": []}


def _load_control(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _empty_control()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("AutoData lifecycle control file is not valid JSON") from error
    if not isinstance(value, dict) or set(value) != {"schema", "subjects"}:
        raise RuntimeError("AutoData lifecycle control file has unknown fields")
    if value.get("schema") != CONTROL_SCHEMA or not isinstance(
        value.get("subjects"), list
    ):
        raise RuntimeError("AutoData lifecycle control file has an invalid schema")
    seen: set[tuple[str, str]] = set()
    for entry in value["subjects"]:
        if not isinstance(entry, dict):
            raise RuntimeError("AutoData lifecycle registration must be an object")
        if entry.get("kind") not in {"workspace", "execution"}:
            raise RuntimeError("AutoData lifecycle registration has an invalid kind")
        subject_id = entry.get("subject_id")
        if not isinstance(subject_id, str) or not subject_id:
            raise RuntimeError("AutoData lifecycle registration has no subject id")
        if entry.get("status") not in {"registered", "completed"}:
            raise RuntimeError("AutoData lifecycle registration has an invalid status")
        key = (str(entry["kind"]), subject_id)
        if key in seen:
            raise RuntimeError("AutoData lifecycle control file has duplicate subjects")
        seen.add(key)
    return value


def _with_control_lock(
    path: Path, *, timeout_seconds: float = DEFAULT_CONTROL_LOCK_TIMEOUT_SECONDS
) -> TextIO:
    if timeout_seconds <= 0:
        raise RuntimeError("AutoData control lock timeout must be positive")
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return handle
            except BlockingIOError as error:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        f"timed out acquiring AutoData lifecycle control lock: {lock_path}"
                    ) from error
                time.sleep(min(0.1, remaining))
    except BaseException:
        handle.close()
        raise


def _native_subject(state: Path, kind: str, subject_id: str) -> dict[str, Any]:
    if kind not in {"workspace", "execution"}:
        raise RuntimeError(f"unsupported native AutoData subject kind: {kind}")
    table = "workspaces" if kind == "workspace" else "executions"
    if not state.is_file():
        raise RuntimeError("live AutoData state does not exist")
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        if table not in _table_names(connection):
            raise RuntimeError(f"live AutoData state has no {table} table")
        row = connection.execute(
            f"SELECT * FROM {table} WHERE id=?", (subject_id,)
        ).fetchone()
    if row is None:
        raise RuntimeError(f"native AutoData {kind} {subject_id} does not exist")
    return dict(row)


def _execution_identity(
    connection: sqlite3.Connection, row: sqlite3.Row
) -> str:
    columns = set(row.keys())
    study_id = None
    if "study_members" in _table_names(connection):
        membership = connection.execute(
            "SELECT studyId FROM study_members "
            "WHERE subjectKind='execution' AND subjectId=?",
            (str(row["id"]),),
        ).fetchone()
        study_id = str(membership[0]) if membership is not None else None

    def value(name: str) -> Any:
        return row[name] if name in columns else None

    def document(name: str) -> Any:
        raw = value(name)
        return json.loads(str(raw)) if raw is not None else None

    baseline_tree_digest = None
    workspace_root = value("workspaceRoot")
    if workspace_root is not None:
        baseline = (
            Path(str(workspace_root))
            / str(row["id"])
            / "candidates"
            / "r0000"
        )
        if baseline.is_dir():
            baseline_tree_digest = _pipeline_tree_digest(baseline)

    identity = {
        "study_id": study_id,
        "workspace_id": value("workspaceId"),
        "snapshot_id": value("snapshotId"),
        "pipeline": document("pipelineJson"),
        "pipeline_tree_digest": baseline_tree_digest,
        "execution": document("executionJson"),
        "pipeline_root": value("pipelineRoot"),
        "workspace_root": value("workspaceRoot"),
    }
    encoded = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _equivalent_executions(state: Path, execution_id: str) -> list[dict[str, Any]]:
    """List active/completed executions with the exact same semantic request."""
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        target = connection.execute(
            "SELECT * FROM executions WHERE id=?", (execution_id,)
        ).fetchone()
        if target is None:
            raise RuntimeError(f"native AutoData execution {execution_id} does not exist")
        identity = _execution_identity(connection, target)
        matches = [
            dict(row)
            for row in connection.execute("SELECT * FROM executions").fetchall()
            if str(row["status"]) in {"active", "completed"}
            and _execution_identity(connection, row) == identity
        ]
    return sorted(
        matches,
        key=lambda row: (
            0 if row["status"] == "completed" else 1,
            str(row.get("createdAt") or ""),
            str(row["id"]),
        ),
    )


def _native_cli(
    python: Path,
    state: Path,
    artifacts: Path,
    workspaces: Path,
    *arguments: str,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(python),
            "-m",
            "autodata.cli",
            "--state",
            str(state),
            "--artifacts",
            str(artifacts),
            "--workspaces",
            str(workspaces),
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=WORKSPACE_RECONCILE_SLA_SECONDS,
    )
    if completed.returncode != 0:
        raise _subprocess_failure(
            completed,
            error_code="autodata_native_cli_failed",
            stage="autodata_lifecycle",
            public_summary="native AutoData CLI failed",
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise _subprocess_failure(
            completed,
            error_code="autodata_native_cli_invalid_json",
            stage="autodata_lifecycle",
            public_summary="native AutoData CLI returned invalid JSON",
        ) from error
    if not isinstance(value, dict):
        raise RuntimeError("native AutoData CLI did not return one JSON object")
    return value


def _trusted_execution_settings(
    *,
    campaign_policy: Path,
    training_data_contract: Path,
    resolved_config: Path | None = None,
    resolved_config_sha256: str | None = None,
    campaign_policy_sha256: str | None = None,
) -> dict[str, Any]:
    """Load execution authority from the integrity-checked compiled config."""
    resolved_raw = (
        str(resolved_config)
        if resolved_config is not None
        else os.environ.get("AAR_AUTODATA_RESOLVED_CONFIG", "").strip()
    )
    if not resolved_raw:
        raise RuntimeError("trusted resolved AutoData config is required")
    from aar.autodata_run_config import validate_compiled_config

    resolved_path = Path(resolved_raw).expanduser().resolve(strict=True)
    if (
        resolved_config_sha256 is not None
        and _sha256(resolved_path) != resolved_config_sha256
    ):
        raise RuntimeError("resolved AutoData config changed after supervisor startup")
    if campaign_policy_sha256 is not None and _sha256(campaign_policy) != campaign_policy_sha256:
        raise RuntimeError("runtime campaign policy changed after supervisor startup")
    import yaml

    unverified = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(unverified, dict) or not isinstance(
        unverified.get("artifacts"), dict
    ):
        raise RuntimeError("resolved AutoData config has no artifact bindings")
    compiled_policy = Path(
        str(unverified["artifacts"].get("campaign_policy"))
    ).resolve(strict=True)
    resolved = validate_compiled_config(
        resolved_path, compiled_policy, training_data_contract
    )
    artifacts = resolved.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError("resolved AutoData config has no artifact bindings")
    expected_policy = Path(str(artifacts.get("campaign_policy"))).resolve(strict=True)
    expected_contract = Path(
        str(artifacts.get("training_data_contract"))
    ).resolve(strict=True)
    if compiled_policy != expected_policy:
        raise RuntimeError("compiled campaign policy binding changed")
    if training_data_contract.resolve(strict=True) != expected_contract:
        raise RuntimeError("training-data contract is not the compiled operator artifact")
    runtime_policy = validate_runtime_campaign_policy_rewrite(
        _json_object(compiled_policy, "compiled campaign policy"),
        _json_object(campaign_policy, "runtime campaign policy"),
    )
    settings = operator_execution_settings(
        resolved,
        campaign_policy=runtime_policy,
        training_data_contract=_json_object(
            training_data_contract, "training-data contract"
        ),
    )
    run_config = resolved.get("run")
    if not isinstance(run_config, dict):
        raise RuntimeError("resolved AutoData config has no run section")
    recipe_relative = Path(str(run_config.get("recipe_root", "")))
    if (
        not recipe_relative.parts
        or recipe_relative.is_absolute()
        or ".." in recipe_relative.parts
    ):
        raise RuntimeError("resolved AutoData recipe root is unsafe")
    trusted_pipeline_path = (
        Path(__file__).resolve().parents[1]
        / recipe_relative
        / "autodata.pipeline.json"
    ).resolve(strict=True)
    trusted_pipeline = _json_object(
        trusted_pipeline_path, "trusted operator pipeline"
    )
    checks = trusted_pipeline.get("checks")
    if not isinstance(checks, list) or not checks:
        raise RuntimeError("trusted operator pipeline has no checks")
    settings["trusted_pipeline_manifest"] = trusted_pipeline
    settings["pipeline_checks_per_iteration"] = len(checks)
    settings["meta_task_attempts"] = int(settings["meta_model_task_attempts"]) + (
        len(checks) * int(settings["meta"]["maximum_iterations"])
    )
    broker_url = os.environ.get("AAR_AUTODATA_BROKER_URL", "").strip()
    if not broker_url:
        raise RuntimeError("AAR_AUTODATA_BROKER_URL is required")
    settings["broker_url"] = broker_url
    return settings


def _study_reserved_task_ids(state: Path, study_id: str) -> list[str]:
    """Return verified task IDs reserved by a completed study meta execution."""
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        if not {"executions", "study_members"}.issubset(_table_names(connection)):
            return []
        rows = connection.execute(
            "SELECT e.* FROM executions e JOIN study_members s "
            "ON s.subjectKind='execution' AND s.subjectId=e.id "
            "WHERE s.studyId=?",
            (study_id,),
        ).fetchall()
    reserved: set[str] = set()
    completed_meta = 0
    for row in rows:
        spec = json.loads(str(row["executionJson"]))
        if spec.get("mode") != "meta_optimize":
            continue
        if row["status"] == "cancelled":
            if _execution_attempts(state, row) != 0:
                raise RuntimeError(
                    "cancelled study meta execution contains task-attempt evidence"
                )
            continue
        if row["status"] != "completed" or row["phase"] != "completed":
            raise RuntimeError(
                "production cannot start before the study meta execution completes"
            )
        completed_meta += 1
        tuning = spec.get("tuning_task_ids")
        validation = spec.get("validation_task_ids")
        if not isinstance(tuning, list) or not isinstance(validation, list):
            raise RuntimeError("study meta execution has invalid explicit partitions")
        reserved.update(str(value) for value in [*tuning, *validation])
        pipeline_root = Path(str(row["pipelineRoot"])).resolve(strict=True)
        reserved.update(
            bound_grounding_task_ids(
                pipeline_root, spec.get("test_grounding"), "study meta test grounding"
            )
        )
    if completed_meta != 1:
        raise RuntimeError(
            "production requires exactly one completed meta execution in its study"
        )
    return sorted(reserved)


def _json_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _semantic_operator_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Remove restart-local transports from durable transition identity."""
    stable = json.loads(json.dumps(dict(settings), sort_keys=True))
    stable.pop("broker_url", None)
    policy = stable.get("campaign_policy")
    if isinstance(policy, dict):
        environment = policy.get("required_solve_env")
        if isinstance(environment, dict):
            environment.pop("AUTODATA_GENERATOR_URL", None)
            environment.pop("AUTODATA_GENERATOR_HOST_HEADER", None)
    return stable


def _execution_study(state: Path, execution_id: str) -> str:
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        if "study_members" not in _table_names(connection):
            raise RuntimeError("native state has no study membership table")
        rows = connection.execute(
            "SELECT studyId FROM study_members "
            "WHERE subjectKind='execution' AND subjectId=?",
            (execution_id,),
        ).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"execution {execution_id} has no unique native study")
    return str(rows[0][0])


def _execution_finalization(state: Path, execution_id: str) -> dict[str, Any]:
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        if "events" not in _table_names(connection):
            raise RuntimeError("native state has no execution event evidence")
        rows = connection.execute(
            "SELECT payloadJson FROM events WHERE scopeKind='execution' "
            "AND scopeId=? AND kind='execution.finalized' ORDER BY sequence",
            (execution_id,),
        ).fetchall()
    if len(rows) != 1:
        raise RuntimeError(
            f"completed execution {execution_id} has no unique finalization event"
        )
    try:
        value = json.loads(str(rows[0][0]))
    except json.JSONDecodeError as error:
        raise RuntimeError("native execution finalization payload is invalid") from error
    if not isinstance(value, dict):
        raise RuntimeError("native execution finalization payload is not an object")
    return value


def _require_meta_final_test_evidence(
    finalization: Mapping[str, Any], *, winner_id: str
) -> None:
    """Require held-out evidence that independently clears the valid floor."""

    test_evaluation = finalization.get("test_evaluation")
    constraints = (
        test_evaluation.get("constraints")
        if isinstance(test_evaluation, dict)
        else None
    )
    if (
        not isinstance(test_evaluation, dict)
        or test_evaluation.get("candidate_id") != winner_id
        or not isinstance(constraints, dict)
        or constraints.get("valid") is not True
    ):
        raise RuntimeError(
            "completed meta execution lacks valid winner test evidence"
        )


def _artifact_json(
    artifacts: Path, reference: Any, *, label: str
) -> dict[str, Any]:
    """Read one native JSON artifact only after verifying its content digest."""

    if not isinstance(reference, dict):
        raise RuntimeError(f"{label} reference is invalid")
    digest = reference.get("digest")
    size = reference.get("size")
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise RuntimeError(f"{label} reference is invalid")
    hexadecimal = digest.removeprefix("sha256:")
    root = artifacts.resolve(strict=True)
    path = root / "objects" / "sha256" / hexadecimal[:2] / hexadecimal[2:]
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} object is unavailable")
    payload = path.read_bytes()
    if len(payload) != size or hashlib.sha256(payload).hexdigest() != hexadecimal:
        raise RuntimeError(f"{label} object failed integrity validation")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must contain one JSON object")
    return value


def _production_acceptance_attainability(
    state: Path, artifacts: Path, execution_id: str
) -> dict[str, int | bool]:
    """Compute a conservative, source-task-level production yield ceiling."""

    row = _native_subject(state, "execution", execution_id)
    try:
        spec = json.loads(str(row.get("executionJson")))
    except json.JSONDecodeError as error:
        raise RuntimeError("production execution manifest is invalid") from error
    if not isinstance(spec, dict) or spec.get("mode") != "production":
        raise RuntimeError("accepted-row attainability requires production mode")
    pipeline_root = Path(str(row.get("pipelineRoot") or "")).resolve(strict=True)
    source_task_ids = set(
        bound_grounding_task_ids(
            pipeline_root,
            spec.get("grounding"),
            "production acceptance grounding",
        )
    )
    finalization = spec.get("finalization")
    required_rows = (
        finalization.get("minimum_generated_items")
        if isinstance(finalization, dict)
        else None
    )
    if (
        isinstance(required_rows, bool)
        or not isinstance(required_rows, int)
        or required_rows < 1
    ):
        raise RuntimeError("production accepted-row requirement is invalid")

    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        if "events" not in _table_names(connection):
            raise RuntimeError("native state has no production task-result evidence")
        rows = connection.execute(
            "SELECT payloadJson FROM events WHERE scopeKind='execution' "
            "AND scopeId=? AND kind='task_attempt.completed'",
            (execution_id,),
        ).fetchall()

    results_by_task: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for (raw_payload,) in rows:
        try:
            event = json.loads(str(raw_payload))
        except json.JSONDecodeError as error:
            raise RuntimeError("production task-result event is invalid") from error
        task_id = event.get("task_id") if isinstance(event, dict) else None
        phase = event.get("phase") if isinstance(event, dict) else None
        if (
            not isinstance(task_id, str)
            or task_id not in source_task_ids
            or not isinstance(phase, str)
            or not phase
        ):
            raise RuntimeError("production task-result event has invalid lineage")
        result = _artifact_json(
            artifacts,
            event.get("artifact"),
            label="production task result",
        )
        generated_items = result.get("generated_items")
        if result.get("task_id") != task_id or not isinstance(generated_items, list):
            raise RuntimeError("production task result has invalid lineage")
        results_by_task.setdefault(task_id, []).append((phase, result))

    accepted: set[str] = set()
    exhausted: set[str] = set()
    for task_id, task_results in results_by_task.items():
        if any(
            result.get("outcome") == "succeeded" and bool(result["generated_items"])
            for _, result in task_results
        ):
            accepted.add(task_id)
            continue
        # Native production permits one full-corpus retry. A first empty result
        # therefore remains attainable. Exhaustion is proven only after that
        # retry, or for the contract-exhausted result that native deliberately
        # excludes from its retry set.
        if any(
            phase == "final-full-corpus-retry-2"
            or result.get("reason_code") == "judge_contract_exhausted"
            for phase, result in task_results
        ):
            exhausted.add(task_id)

    retry_eligible_or_unfinished = source_task_ids - accepted - exhausted
    maximum_possible_rows = len(accepted) + len(retry_eligible_or_unfinished)
    return {
        "required_rows": required_rows,
        "source_task_count": len(source_task_ids),
        "accepted_rows": len(accepted),
        "retry_eligible_or_unfinished_tasks": len(retry_eligible_or_unfinished),
        "exhausted_tasks": len(exhausted),
        "maximum_possible_rows": maximum_possible_rows,
        "attainable": maximum_possible_rows >= required_rows,
    }


def _require_production_acceptance_attainability(
    state: Path, artifacts: Path, execution_id: str
) -> dict[str, int | bool]:
    status = _production_acceptance_attainability(state, artifacts, execution_id)
    if status["attainable"] is not True:
        raise NativeStepFailure(
            "production accepted-row requirement is unattainable "
            f"(accepted={status['accepted_rows']}, "
            "retry-eligible-or-unfinished="
            f"{status['retry_eligible_or_unfinished_tasks']}, "
            f"required={status['required_rows']})",
            error_code="production_required_rows_unattainable",
            attempts=1,
        )
    return status


def _run_binding(
    state: Path, control_file: Path, meta_execution_id: str
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Authenticate one meta execution against its approved run workspace."""
    workspace_entries = [
        entry
        for entry in _load_control(control_file)["subjects"]
        if entry["kind"] == "workspace"
        and entry.get("canonical_execution_id") == meta_execution_id
    ]
    if len(workspace_entries) != 1:
        raise RuntimeError(
            "completed meta execution has no unique supervised workspace binding"
        )
    workspace_entry = workspace_entries[0]
    workspace_id = str(workspace_entry["subject_id"])
    workspace = _native_subject(state, "workspace", workspace_id)
    root_raw = workspace.get("root")
    if not isinstance(root_raw, str) or not root_raw:
        raise RuntimeError("bound native workspace has no run-scoped draft root")
    draft = Path(root_raw).resolve(strict=True)
    run_root = draft.parent
    if draft != run_root / "draft" or run_root.is_symlink() or not run_root.is_dir():
        raise RuntimeError("bound native workspace is outside a safe run root")
    team_raw = os.environ.get("TEAM_DIR", "").strip()
    if team_raw:
        team = Path(team_raw).resolve(strict=True)
        if run_root.parent != team / "autodata":
            raise RuntimeError("bound native workspace does not belong to TEAM_DIR")
    bootstrap = _json_object(
        run_root / "workspace-bootstrap.json", "workspace bootstrap binding"
    )
    expected = {
        "schema": "aar.autodata.workspace-bootstrap/v1",
        "workspace_id": workspace_id,
        "study_id": _execution_study(state, meta_execution_id),
        "run_root": str(run_root),
    }
    if any(bootstrap.get(key) != value for key, value in expected.items()):
        raise RuntimeError("workspace bootstrap does not bind this meta execution")
    run_id = bootstrap.get("run_id")
    code_hash = bootstrap.get("code_hash")
    idea_name = bootstrap.get("idea_name")
    if (
        not isinstance(run_id, str)
        or not run_id
        or run_root.name != run_id
        or not isinstance(code_hash, str)
        or len(code_hash) != 64
        or not isinstance(idea_name, str)
        or not idea_name
    ):
        raise RuntimeError("workspace bootstrap proposal binding is incomplete")
    return workspace_entry, bootstrap, run_root


def _write_immutable_json(path: Path, value: dict[str, Any], label: str) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"{label} destination is unsafe")
        if _json_object(path, label) != value:
            raise RuntimeError(f"existing {label} does not match the durable intent")
        return
    _atomic_json(path, value)


def _copy_tree_with_production_grounding(
    *,
    python: Path,
    winner: Path,
    destination: Path,
    task_count: int,
    seed: int,
    reserved_task_ids: list[str],
) -> tuple[Path, dict[str, Any]]:
    """Materialize winner + a deterministic fresh production source corpus."""
    winner = winner.resolve(strict=True)
    builder = winner / "grounding" / "build_manifest.py"
    coverage = winner / "grounding" / "coverage.json"
    if (
        builder.is_symlink()
        or coverage.is_symlink()
        or not builder.is_file()
        or not coverage.is_file()
    ):
        raise RuntimeError("completed meta winner lacks protected grounding sources")
    staging = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        shutil.copytree(winner, staging, symlinks=False)
        manifest = staging / PRODUCTION_GROUNDING_PATH
        completed = subprocess.run(
            [
                str(python),
                str(builder),
                "--count",
                str(task_count),
                "--seed",
                str(seed),
                "--id-prefix",
                PRODUCTION_ID_PREFIX,
                "--coverage",
                str(coverage),
                "--output",
                str(manifest),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            raise _subprocess_failure(
                completed,
                error_code="production_grounding_build_failed",
                stage="autodata_production",
                public_summary="trusted production grounding build failed",
            )
        value = _json_object(manifest, "production grounding manifest")
        tasks = value.get("tasks")
        if not isinstance(tasks, list) or len(tasks) != task_count:
            raise RuntimeError("trusted production grounding has the wrong task count")
        task_ids = [
            task.get("id") if isinstance(task, dict) else None for task in tasks
        ]
        if (
            any(not isinstance(task_id, str) or not task_id for task_id in task_ids)
            or len(set(task_ids)) != task_count
            or set(task_ids) & set(reserved_task_ids)
        ):
            raise RuntimeError(
                "trusted production grounding IDs are invalid or overlap meta tasks"
            )
        _atomic_json(manifest, value)
        expected_digest = _pipeline_tree_digest(staging)
        if destination.is_dir():
            if _pipeline_tree_digest(destination) != expected_digest:
                raise RuntimeError("existing production pipeline differs from durable intent")
        elif destination.exists() or destination.is_symlink():
            raise RuntimeError("production pipeline destination is unsafe")
        else:
            _fsync_tree(staging)
            os.replace(staging, destination)
            _fsync_directory(destination.parent)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    production_manifest = destination / PRODUCTION_GROUNDING_PATH
    return destination / "autodata.pipeline.json", {
        "manifest_path": PRODUCTION_GROUNDING_PATH,
        "digest": "sha256:" + _sha256(production_manifest),
    }


def _export_winner_idempotently(
    args: argparse.Namespace,
    *,
    execution_id: str,
    destination: Path,
    expected_digest: str,
) -> None:
    if destination.is_dir():
        if _pipeline_tree_digest(destination) != expected_digest:
            raise RuntimeError("existing winner export does not match native finalization")
        return
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("winner export destination is unsafe")
    temporary = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    if temporary.exists():
        shutil.rmtree(temporary)
    try:
        _native_cli(
            args.python,
            args.state,
            args.artifacts,
            args.workspaces,
            "execution",
            "export-winner",
            execution_id,
            "--output",
            str(temporary),
        )
        if _pipeline_tree_digest(temporary) != expected_digest:
            raise RuntimeError("native winner export digest does not match finalization")
        _fsync_tree(temporary)
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _export_dataset_idempotently(
    args: argparse.Namespace,
    *,
    execution_id: str,
    destination: Path,
    expected_digest: str,
) -> None:
    expected = expected_digest.removeprefix("sha256:")
    if destination.is_file() and not destination.is_symlink():
        if _sha256(destination) != expected:
            raise RuntimeError("existing production dataset digest changed")
        return
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("production dataset destination is unsafe")
    temporary = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    temporary.unlink(missing_ok=True)
    try:
        _native_cli(
            args.python,
            args.state,
            args.artifacts,
            args.workspaces,
            "export",
            execution_id,
            "--output",
            str(temporary),
        )
        if _sha256(temporary) != expected:
            raise RuntimeError("native production dataset digest does not match finalization")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _publish_canonical_execution(
    artifacts: Path, manifest: dict[str, Any]
) -> Path:
    encoded = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    root = artifacts.resolve(strict=True) / ".aar-supervised-executions"
    root.mkdir(mode=0o700, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("canonical execution directory is unsafe")
    destination = root / f"{digest}.json"
    if destination.is_file():
        if _json_object(destination, "canonical execution manifest") != manifest:
            raise RuntimeError("canonical execution manifest digest collision")
    else:
        _atomic_json(destination, manifest)
    return destination


def _existing_registration(
    control_file: Path, *, kind: str, subject_id: str
) -> dict[str, Any] | None:
    matches = [
        entry
        for entry in _load_control(control_file)["subjects"]
        if entry["kind"] == kind and entry["subject_id"] == subject_id
    ]
    if len(matches) > 1:
        raise RuntimeError(f"duplicate lifecycle registration for {subject_id}")
    return matches[0] if matches else None


def reconcile_completed_meta_execution(
    args: argparse.Namespace, meta_execution_id: str
) -> dict[str, Any]:
    """Converge completed meta evidence to one registered production execution."""
    meta_row = _native_subject(args.state, "execution", meta_execution_id)
    meta_spec = json.loads(str(meta_row.get("executionJson")))
    if (
        meta_row.get("status") != "completed"
        or meta_row.get("phase") != "completed"
        or meta_spec.get("mode") != "meta_optimize"
    ):
        raise RuntimeError("meta transition requires one completed meta execution")
    workspace_entry, bootstrap, run_root = _run_binding(
        args.state, args.control_file, meta_execution_id
    )
    study_id = str(bootstrap["study_id"])
    finalization = _execution_finalization(args.state, meta_execution_id)
    winner_id = str(finalization.get("winner_candidate_id") or "")
    winner_digest = str(finalization.get("winner_tree_digest") or "")
    if (
        not winner_id
        or winner_id != str(meta_row.get("winnerCandidateId") or "")
        or not winner_digest.startswith("sha256:")
    ):
        raise RuntimeError("completed meta execution has invalid winner evidence")
    _require_meta_final_test_evidence(finalization, winner_id=winner_id)
    settings = _trusted_execution_settings(
        campaign_policy=args.campaign_policy,
        training_data_contract=args.training_data_contract,
        resolved_config=args.resolved_config,
        resolved_config_sha256=args.resolved_config_sha256,
        campaign_policy_sha256=args.campaign_policy_sha256,
    )
    meta_pipeline_root = Path(str(meta_row.get("pipelineRoot"))).resolve(strict=True)
    expected_meta_spec = canonical_meta_manifest_from_default(
        default_manifest=meta_spec,
        pipeline_manifest=meta_pipeline_root / "autodata.pipeline.json",
        settings=settings,
    )
    if meta_spec != expected_meta_spec:
        raise RuntimeError(
            "completed meta execution no longer matches trusted operator settings"
        )
    reserved = _study_reserved_task_ids(args.state, study_id)
    expected_reserved = sum(
        int(settings["meta"][key])
        for key in ("tuning_tasks", "validation_tasks", "test_tasks")
    )
    if len(reserved) != expected_reserved:
        raise RuntimeError("completed meta execution does not bind the full partition")

    winner = run_root / "meta-winner"
    production_root = run_root / "production"
    dataset = run_root / "production-dataset.json"
    receipt = run_root / "training-consumption.json"
    handoff = run_root / "training-handoff.json"
    intent = {
        "schema": SUPERVISED_TRANSITION_SCHEMA,
        "run_id": bootstrap["run_id"],
        "idea_name": bootstrap["idea_name"],
        "code_hash": bootstrap["code_hash"],
        "workspace_id": workspace_entry["subject_id"],
        "study_id": study_id,
        "meta_execution_id": meta_execution_id,
        "meta_winner_candidate_id": winner_id,
        "meta_winner_tree_digest": winner_digest,
        "reserved_task_ids_sha256": _json_sha256({"task_ids": reserved}),
        "operator_settings_sha256": _json_sha256(
            _semantic_operator_settings(settings)
        ),
        "production_task_count": int(settings["production"]["initial_tasks"]),
        "production_seed": int(expected_meta_spec["split_seed"])
        + PRODUCTION_SEED_OFFSET,
        "production_id_prefix": PRODUCTION_ID_PREFIX,
        "winner_export": str(winner),
        "production_pipeline": str(production_root),
        "production_manifest": str(production_root / PRODUCTION_GROUNDING_PATH),
        "production_dataset": str(dataset),
        "consumption_receipt": str(receipt),
        "training_handoff": str(handoff),
    }
    intent_path = run_root / "supervised-transition-intent.json"
    _write_immutable_json(intent_path, intent, "supervised transition intent")
    intent_digest = "sha256:" + _sha256(intent_path)
    existing_intent = workspace_entry.get("transition_intent_sha256")
    if existing_intent not in {None, intent_digest}:
        raise RuntimeError("workspace transition intent changed during recovery")
    _update_registration(
        args.control_file,
        kind="workspace",
        subject_id=str(workspace_entry["subject_id"]),
        transition_intent_sha256=intent_digest,
    )

    _export_winner_idempotently(
        args,
        execution_id=meta_execution_id,
        destination=winner,
        expected_digest=winner_digest,
    )
    pipeline, grounding = _copy_tree_with_production_grounding(
        python=args.python,
        winner=winner,
        destination=production_root,
        task_count=int(settings["production"]["initial_tasks"]),
        seed=int(intent["production_seed"]),
        reserved_task_ids=reserved,
    )
    production_spec = canonical_production_manifest_from_meta(
        meta_manifest=meta_spec,
        pipeline_manifest=pipeline,
        production_grounding=grounding,
        settings=settings,
        reserved_task_ids=reserved,
    )
    production_spec_path = _publish_canonical_execution(
        args.artifacts, production_spec
    )
    contract = validate_generation_inputs(
        pipeline_manifest=pipeline,
        execution_manifest=production_spec_path,
        contract_path=args.training_data_contract,
        campaign_policy_path=args.campaign_policy,
        expected_concurrency=int(settings["concurrency"]),
    )
    key = execution_creation_key(
        pipeline,
        production_spec_path,
        study_id=study_id,
        workspaces=args.workspaces,
    )
    meta_registration = _existing_registration(
        args.control_file, kind="execution", subject_id=meta_execution_id
    )
    if meta_registration is None:
        raise RuntimeError("completed canonical meta execution lost its registration")
    for field, expected in {
        "production_idempotency_key": key,
        "production_manifest_sha256": "sha256:" + _sha256(production_spec_path),
        "production_pipeline_digest": _pipeline_tree_digest(production_root),
    }.items():
        current = meta_registration.get(field)
        if current not in {None, expected}:
            raise RuntimeError(f"meta transition changed durable {field}")
    _update_registration(
        args.control_file,
        kind="execution",
        subject_id=meta_execution_id,
        transition_intent_sha256=intent_digest,
        winner_export_digest=winner_digest,
        production_idempotency_key=key,
        production_manifest_sha256="sha256:" + _sha256(production_spec_path),
        production_pipeline_digest=_pipeline_tree_digest(production_root),
    )
    created = _native_cli(
        args.python,
        args.state,
        args.artifacts,
        args.workspaces,
        "execution",
        "create",
        "--pipeline",
        str(pipeline),
        "--execution",
        str(production_spec_path),
        "--study-id",
        study_id,
        "--idempotency-key",
        key,
    )
    production_id = created.get("execution_id")
    if not isinstance(production_id, str) or not production_id:
        raise RuntimeError("native production creation returned no execution id")
    equivalents = _equivalent_executions(args.state, production_id)
    if len(equivalents) != 1 or str(equivalents[0]["id"]) != production_id:
        raise RuntimeError("production creation produced an ambiguous semantic duplicate")
    if _execution_study(args.state, production_id) != study_id:
        raise RuntimeError("production execution escaped the meta native study")
    latest_meta = _registration_entry(
        args.control_file, kind="execution", subject_id=meta_execution_id
    )
    bound_production = latest_meta.get("production_execution_id")
    if bound_production not in {None, production_id}:
        raise RuntimeError("production execution identity changed during recovery")
    _update_registration(
        args.control_file,
        kind="execution",
        subject_id=meta_execution_id,
        production_execution_id=production_id,
    )
    if not snapshot_database(
        args.state,
        args.retained_state,
        reason=f"production-created:{meta_execution_id}:{production_id}",
    ):
        raise RuntimeError("cannot retain supervised production creation")
    production_row = _native_subject(args.state, "execution", production_id)
    registration = _existing_registration(
        args.control_file, kind="execution", subject_id=production_id
    )
    if registration is None:
        if production_row.get("status") != "active":
            raise RuntimeError("unregistered production execution is already terminal")
        registration = register_subject(
            args.state,
            args.control_file,
            kind="execution",
            subject_id=production_id,
        )
    _update_registration(
        args.control_file,
        kind="execution",
        subject_id=production_id,
        parent_meta_execution_id=meta_execution_id,
        run_id=bootstrap["run_id"],
        transition_intent_sha256=intent_digest,
    )
    _complete_registration(
        args.control_file,
        kind="execution",
        subject_id=meta_execution_id,
        native_status="completed",
    )
    return {
        "transition": "meta-to-production",
        "meta_execution_id": meta_execution_id,
        "production_execution_id": production_id,
        "production_registered": registration.get("status") == "registered",
        "training_data_contract": contract["schema"],
    }


def reconcile_completed_production_execution(
    args: argparse.Namespace, production_execution_id: str
) -> dict[str, Any]:
    """Export one completed production dataset and publish a verified handoff."""
    registration = _registration_entry(
        args.control_file, kind="execution", subject_id=production_execution_id
    )
    meta_execution_id = registration.get("parent_meta_execution_id")
    if not isinstance(meta_execution_id, str) or not meta_execution_id:
        raise RuntimeError("production registration has no canonical meta parent")
    _, bootstrap, run_root = _run_binding(
        args.state, args.control_file, meta_execution_id
    )
    study_id = str(bootstrap["study_id"])
    row = _native_subject(args.state, "execution", production_execution_id)
    spec = json.loads(str(row.get("executionJson")))
    if (
        row.get("status") != "completed"
        or row.get("phase") != "completed"
        or spec.get("mode") != "production"
        or _execution_study(args.state, production_execution_id) != study_id
    ):
        raise RuntimeError("production handoff requires completed same-study production")
    finalization = _execution_finalization(args.state, production_execution_id)
    dataset_ref = finalization.get("dataset")
    if not isinstance(dataset_ref, dict):
        raise RuntimeError("completed production has no native dataset reference")
    dataset_digest = dataset_ref.get("digest")
    if (
        not isinstance(dataset_digest, str)
        or not dataset_digest.startswith("sha256:")
    ):
        raise RuntimeError("completed production dataset has no digest")
    winner = run_root / "meta-winner"
    production_root = run_root / "production"
    production_manifest = production_root / PRODUCTION_GROUNDING_PATH
    dataset = run_root / "production-dataset.json"
    receipt = run_root / "training-consumption.json"
    intent_path = run_root / "supervised-transition-intent.json"
    intent_digest = "sha256:" + _sha256(intent_path)
    if registration.get("transition_intent_sha256") != intent_digest:
        raise RuntimeError("production registration lost its transition intent")
    if not snapshot_database(
        args.state,
        args.retained_state,
        reason=f"production-completed:{production_execution_id}",
    ):
        raise RuntimeError("cannot retain completed production state")
    _export_dataset_idempotently(
        args,
        execution_id=production_execution_id,
        destination=dataset,
        expected_digest=dataset_digest,
    )
    handoff = {
        "schema": "aar.autodata.training-handoff/v1",
        "run_id": bootstrap["run_id"],
        "state_db": str(args.retained_state.resolve(strict=True)),
        "dataset": str(dataset.resolve(strict=True)),
        "workspace_id": bootstrap["workspace_id"],
        "study_id": study_id,
        "meta_execution_id": meta_execution_id,
        "production_execution_id": production_execution_id,
        "winner_export": str(winner.resolve(strict=True)),
        "production_manifest": str(production_manifest.resolve(strict=True)),
        "consumption_receipt": str(receipt),
    }
    handoff_path = run_root / "training-handoff.json"
    _write_immutable_json(handoff_path, handoff, "training handoff")
    from aar.infrastructure.autodata_lifecycle import publish_verified_handoff_marker

    verification = publish_verified_handoff_marker(str(bootstrap["run_id"]))
    if (
        verification.get("production_execution_id") != production_execution_id
        or verification.get("meta_execution_id") != meta_execution_id
    ):
        raise RuntimeError("published training handoff verification changed lineage")
    handoff_digest = "sha256:" + _sha256(handoff_path)
    verified_marker = Path(str(verification["verified_marker"]))
    _update_registration(
        args.control_file,
        kind="execution",
        subject_id=production_execution_id,
        dataset_sha256=dataset_digest,
        training_handoff_sha256=handoff_digest,
    )
    _update_registration(
        args.control_file,
        kind="execution",
        subject_id=meta_execution_id,
        training_handoff_sha256=handoff_digest,
    )
    _complete_registration(
        args.control_file,
        kind="execution",
        subject_id=production_execution_id,
        native_status="completed",
    )
    return {
        "transition": "production-to-training-handoff",
        "meta_execution_id": meta_execution_id,
        "production_execution_id": production_execution_id,
        "training_handoff": str(handoff_path),
        "training_handoff_verified": str(verified_marker),
        "available_rows": verification["available_rows"],
    }


def _pending_completed_execution_transition(
    args: argparse.Namespace,
) -> tuple[str, str] | None:
    """Return the next completed execution edge without mutating retained state."""
    registrations = [
        entry
        for entry in _load_control(args.control_file)["subjects"]
        if entry["kind"] == "execution"
    ]
    for entry in registrations:
        execution_id = str(entry["subject_id"])
        row = _native_subject(args.state, "execution", execution_id)
        if row.get("status") != "completed" or row.get("phase") != "completed":
            continue
        spec = json.loads(str(row.get("executionJson")))
        mode = spec.get("mode")
        production_id = entry.get("production_execution_id")
        production_registrations = [
            candidate
            for candidate in registrations
            if candidate["subject_id"] == production_id
        ]
        meta_transition_complete = (
            entry["status"] == "completed"
            and isinstance(production_id, str)
            and bool(production_id)
            and len(production_registrations) == 1
            and production_registrations[0].get("parent_meta_execution_id")
            == execution_id
        )
        if mode == "meta_optimize" and not meta_transition_complete:
            return execution_id, mode
        if mode == "production" and not entry.get("training_handoff_sha256"):
            return execution_id, mode
    return None


def reconcile_completed_execution_transition(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Advance at most one completed supervised execution lifecycle edge."""
    pending = _pending_completed_execution_transition(args)
    if pending is None:
        return None
    execution_id, mode = pending
    if mode == "meta_optimize":
        try:
            return reconcile_completed_meta_execution(args, execution_id)
        except Exception as error:
            raise _reconciliation_failure(
                error,
                error_code="meta_to_production_transition_failed",
                public_summary="trusted meta-to-production transition failed",
            ) from error
    if mode == "production":
        try:
            return reconcile_completed_production_execution(args, execution_id)
        except Exception as error:
            raise _reconciliation_failure(
                error,
                error_code="production_to_handoff_transition_failed",
                public_summary="trusted production-to-handoff transition failed",
            ) from error
    raise RuntimeError(f"unsupported completed execution transition mode: {mode}")


def _materialize_canonical_meta_pipeline(
    *,
    source_pipeline: Path,
    default_manifest: Mapping[str, Any],
    artifacts: Path,
    settings: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    """Copy a frozen tree and add immutable 96-task/32-task manifests."""
    source_pipeline = source_pipeline.resolve(strict=True)
    source_root = source_pipeline.parent
    trusted_pipeline = settings.get("trusted_pipeline_manifest")
    if not isinstance(trusted_pipeline, dict):
        raise RuntimeError("trusted operator pipeline manifest is required")
    if _json_object(source_pipeline, "frozen workspace pipeline") != trusted_pipeline:
        raise RuntimeError("frozen workspace pipeline changed operator controls")
    checks = trusted_pipeline.get("checks")
    if (
        not isinstance(checks, list)
        or len(checks) != int(settings.get("pipeline_checks_per_iteration") or 0)
    ):
        raise RuntimeError("trusted pipeline check count changed")
    source_digest = _pipeline_tree_digest(source_root)
    identity = json.dumps(
        {
            "schema": "aar.autodata.canonical-meta-pipeline/v1",
            "source_tree_digest": source_digest,
            "meta": settings["meta"],
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    root = artifacts.resolve(strict=True) / ".aar-supervised-pipelines"
    root.mkdir(mode=0o700, exist_ok=True)
    destination = root / digest
    staging = root / f".{digest}.tmp.{os.getpid()}"
    grounding_ref = default_manifest.get("grounding")
    if not isinstance(grounding_ref, dict):
        raise RuntimeError("freeze-created execution has no grounding reference")
    relative = grounding_ref.get("manifest_path")
    if (
        not isinstance(relative, str)
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise RuntimeError("freeze-created grounding path is unsafe")
    full_manifest_path = (source_root / relative).resolve(strict=True)
    try:
        full_manifest_path.relative_to(source_root)
    except ValueError as error:
        raise RuntimeError("freeze-created grounding escapes its pipeline") from error
    if _sha256(full_manifest_path) != str(grounding_ref.get("digest", "")).removeprefix(
        "sha256:"
    ):
        raise RuntimeError("freeze-created grounding digest changed")
    full_manifest = _json_object(full_manifest_path, "freeze-created grounding")
    tasks = full_manifest.get("tasks")
    meta = settings["meta"]
    tuning_count = int(meta["tuning_tasks"])
    validation_count = int(meta["validation_tasks"])
    test_count = int(meta["test_tasks"])
    if not isinstance(tasks, list) or len(tasks) != (
        tuning_count + validation_count + test_count
    ):
        raise RuntimeError("freeze-created grounding has the wrong task count")
    identifiers = [task.get("id") if isinstance(task, dict) else None for task in tasks]
    if any(not isinstance(value, str) or not value for value in identifiers) or len(
        set(identifiers)
    ) != len(identifiers):
        raise RuntimeError("freeze-created grounding task IDs are invalid")
    meta_relative = "grounding/aar-supervised-meta.json"
    test_relative = "grounding/aar-supervised-test.json"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        shutil.copytree(
            source_root,
            staging,
            symlinks=False,
            ignore=shutil.ignore_patterns(".autodata"),
        )
        meta_manifest = dict(full_manifest)
        meta_manifest["tasks"] = tasks[: tuning_count + validation_count]
        meta_ids = {str(task["id"]) for task in meta_manifest["tasks"]}
        meta_dry_run = [
            task_id
            for task_id in full_manifest.get("dry_run_task_ids", [])
            if task_id in meta_ids
        ]
        meta_manifest["dry_run_task_ids"] = meta_dry_run or [
            str(task["id"]) for task in meta_manifest["tasks"][:3]
        ]
        test_manifest = dict(full_manifest)
        test_manifest["tasks"] = tasks[tuning_count + validation_count :]
        test_ids = {str(task["id"]) for task in test_manifest["tasks"]}
        test_dry_run = [
            task_id
            for task_id in full_manifest.get("dry_run_task_ids", [])
            if task_id in test_ids
        ]
        test_manifest["dry_run_task_ids"] = test_dry_run or [
            str(task["id"]) for task in test_manifest["tasks"][:3]
        ]
        _atomic_json(staging / meta_relative, meta_manifest)
        _atomic_json(staging / test_relative, test_manifest)
        expected_tree_digest = _pipeline_tree_digest(staging)
        if destination.is_dir():
            if _pipeline_tree_digest(destination) != expected_tree_digest:
                raise RuntimeError("retained canonical pipeline digest changed")
        elif destination.exists() or destination.is_symlink():
            raise RuntimeError("canonical pipeline destination is unsafe")
        else:
            os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    meta_path = destination / meta_relative
    test_path = destination / test_relative
    derived = dict(default_manifest)
    derived["grounding"] = {
        "manifest_path": meta_relative,
        "digest": "sha256:" + _sha256(meta_path),
    }
    derived["test_grounding"] = {
        "manifest_path": test_relative,
        "digest": "sha256:" + _sha256(test_path),
    }
    return destination / source_pipeline.name, derived


def _registration_entry(
    control_file: Path, *, kind: str, subject_id: str
) -> dict[str, Any]:
    for entry in _load_control(control_file)["subjects"]:
        if entry["kind"] == kind and entry["subject_id"] == subject_id:
            return entry
    raise RuntimeError(f"AutoData lifecycle registration for {subject_id} vanished")


def _update_registration(
    control_file: Path, *, kind: str, subject_id: str, **fields: Any
) -> dict[str, Any]:
    lock = _with_control_lock(control_file)
    try:
        control = _load_control(control_file)
        for entry in control["subjects"]:
            if entry["kind"] == kind and entry["subject_id"] == subject_id:
                entry.update(fields)
                _atomic_json(control_file, control)
                return dict(entry)
        raise RuntimeError(f"AutoData lifecycle registration for {subject_id} vanished")
    finally:
        lock.close()


def _workspace_study_and_executions(
    state: Path, workspace_id: str
) -> tuple[str, list[dict[str, Any]]]:
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        tables = _table_names(connection)
        if not {"study_members", "executions"}.issubset(tables):
            raise RuntimeError("native state lacks workspace execution lineage")
        memberships = connection.execute(
            "SELECT studyId FROM study_members "
            "WHERE subjectKind='workspace' AND subjectId=?",
            (workspace_id,),
        ).fetchall()
        if len(memberships) != 1:
            raise RuntimeError("frozen workspace has no unique native study")
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(executions)").fetchall()
        }
        if "workspaceId" not in columns:
            raise RuntimeError("native executions lack workspace linkage")
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT e.*,s.studyId AS executionStudyId FROM executions e "
                "LEFT JOIN study_members s ON s.subjectKind='execution' "
                "AND s.subjectId=e.id WHERE e.workspaceId=? "
                "ORDER BY e.createdAt,e.id",
                (workspace_id,),
            ).fetchall()
        ]
        return str(memberships[0][0]), rows


def _execution_attempts(state: Path, row: Mapping[str, Any]) -> int:
    columns = set(row.keys())
    native_count = (
        int(row["taskAttemptsUsed"] or 0) if "taskAttemptsUsed" in columns else 0
    )
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        tables = _table_names(connection)
        if "task_attempts" not in tables:
            return native_count
        columns = {
            str(value[1])
            for value in connection.execute("PRAGMA table_info(task_attempts)")
        }
        if {"scopeKind", "scopeId"}.issubset(columns):
            result = connection.execute(
                "SELECT COUNT(*) FROM task_attempts "
                "WHERE scopeKind='execution' AND scopeId=?",
                (str(row["id"]),),
            ).fetchone()
        elif "executionId" in columns:
            result = connection.execute(
                "SELECT COUNT(*) FROM task_attempts WHERE executionId=?",
                (str(row["id"]),),
            ).fetchone()
        else:
            raise RuntimeError("native task_attempts table has no execution linkage")
        row_count = int(result[0]) if result is not None else 0
        event_count = 0
        if "events" in tables:
            event_columns = {
                str(value[1])
                for value in connection.execute("PRAGMA table_info(events)")
            }
            if {"scopeKind", "scopeId", "kind"}.issubset(event_columns):
                event = connection.execute(
                    "SELECT COUNT(*) FROM events WHERE scopeKind='execution' "
                    "AND scopeId=? AND kind IN "
                    "('task_attempt.submitted','task_attempt.completed','task_attempt.failed')",
                    (str(row["id"]),),
                ).fetchone()
                event_count = int(event[0]) if event is not None else 0
    if native_count != row_count:
        raise RuntimeError(
            "native task-attempt counter and persisted attempt rows disagree"
        )
    if native_count == 0 and event_count != 0:
        raise RuntimeError(
            "native task-attempt counter is zero despite persisted attempt events"
        )
    return native_count


def _begin_workspace_reconciliation(
    control_file: Path, workspace_id: str
) -> dict[str, Any]:
    entry = _registration_entry(
        control_file, kind="workspace", subject_id=workspace_id
    )
    if entry["status"] != "registered":
        return entry
    started_at = entry.get("reconcile_started_at")
    if not isinstance(started_at, str):
        started_at = _utc_now()
    attempts = int(entry.get("reconcile_attempts") or 0)
    elapsed = (
        datetime.now(timezone.utc) - datetime.fromisoformat(started_at)
    ).total_seconds()
    if attempts >= WORKSPACE_RECONCILE_MAX_ATTEMPTS:
        raise RuntimeError("frozen workspace exceeded three reconciliation attempts")
    if elapsed >= WORKSPACE_RECONCILE_SLA_SECONDS:
        raise RuntimeError("frozen workspace exceeded the 60-second registration SLA")
    return _update_registration(
        control_file,
        kind="workspace",
        subject_id=workspace_id,
        reconcile_started_at=started_at,
        reconcile_attempts=attempts + 1,
        reconcile_last_attempt_at=_utc_now(),
    )


def reconcile_frozen_workspace(args: argparse.Namespace, workspace_id: str) -> dict[str, Any]:
    """Atomically converge a frozen workspace to one canonical meta execution."""
    workspace = _native_subject(args.state, "workspace", workspace_id)
    if workspace.get("status") != "frozen":
        raise RuntimeError(f"workspace {workspace_id} is not frozen")
    entry = _begin_workspace_reconciliation(args.control_file, workspace_id)
    study_id, linked = _workspace_study_and_executions(args.state, workspace_id)
    default_id = entry.get("default_execution_id")
    if default_id is None:
        if len(linked) != 1:
            raise RuntimeError(
                "frozen workspace default execution is ambiguous before binding"
            )
        default_id = str(linked[0]["id"])
        entry = _update_registration(
            args.control_file,
            kind="workspace",
            subject_id=workspace_id,
            default_execution_id=default_id,
        )
    defaults = [row for row in linked if str(row["id"]) == default_id]
    if len(defaults) != 1:
        raise RuntimeError("bound freeze-created default execution is missing")
    default = defaults[0]
    if default.get("executionStudyId") != study_id:
        raise RuntimeError("freeze-created default is not in the workspace study")
    default_status = str(default.get("status"))
    default_phase = str(default.get("phase"))
    attempts = _execution_attempts(args.state, default)
    if default_status == "active" and (
        default_phase not in {"created", "baseline_pending"} or attempts != 0
    ):
        raise RuntimeError(
            "freeze-created default execution progressed; refusing automatic cleanup"
        )
    if default_status not in {"active", "cancelled"}:
        raise RuntimeError(
            f"freeze-created default execution is unexpectedly {default_status}"
        )
    if default_status == "cancelled" and not entry.get("canonical_execution_id"):
        raise RuntimeError("default execution was cancelled before canonical binding")

    pipeline_root = Path(str(default.get("pipelineRoot"))).resolve(strict=True)
    source_pipeline = pipeline_root / "autodata.pipeline.json"
    try:
        settings = _trusted_execution_settings(
            campaign_policy=args.campaign_policy,
            training_data_contract=args.training_data_contract,
            resolved_config=args.resolved_config,
            resolved_config_sha256=args.resolved_config_sha256,
            campaign_policy_sha256=args.campaign_policy_sha256,
        )
    except Exception as error:
        raise _reconciliation_failure(
            error,
            error_code="workspace_trusted_settings_invalid",
            public_summary="trusted workspace execution settings are invalid",
        ) from error
    default_spec = json.loads(str(default.get("executionJson")))
    try:
        pipeline, default_spec = _materialize_canonical_meta_pipeline(
            source_pipeline=source_pipeline,
            default_manifest=default_spec,
            artifacts=args.artifacts,
            settings=settings,
        )
    except Exception as error:
        raise _reconciliation_failure(
            error,
            error_code="workspace_canonical_pipeline_invalid",
            public_summary="canonical workspace pipeline materialization failed",
        ) from error
    try:
        canonical = canonical_meta_manifest_from_default(
            default_manifest=default_spec,
            pipeline_manifest=pipeline,
            settings=settings,
        )
    except Exception as error:
        raise _reconciliation_failure(
            error,
            error_code="workspace_canonical_manifest_invalid",
            public_summary="canonical workspace execution manifest is invalid",
        ) from error
    try:
        canonical_path = _publish_canonical_execution(args.artifacts, canonical)
    except Exception as error:
        raise _reconciliation_failure(
            error,
            error_code="workspace_canonical_publish_failed",
            public_summary="canonical workspace execution manifest publication failed",
        ) from error
    try:
        contract = validate_generation_inputs(
            pipeline_manifest=pipeline,
            execution_manifest=canonical_path,
            contract_path=args.training_data_contract,
            campaign_policy_path=args.campaign_policy,
            expected_concurrency=int(settings["concurrency"]),
        )
    except Exception as error:
        raise _reconciliation_failure(
            error,
            error_code="workspace_generation_contract_invalid",
            public_summary="canonical workspace generation contract is invalid",
        ) from error
    try:
        key = execution_creation_key(
            pipeline, canonical_path, study_id=study_id, workspaces=args.workspaces
        )
    except Exception as error:
        raise _reconciliation_failure(
            error,
            error_code="workspace_creation_intent_invalid",
            public_summary="canonical workspace creation intent is invalid",
        ) from error
    existing_key = entry.get("canonical_idempotency_key")
    if existing_key is not None and existing_key != key:
        raise RuntimeError("canonical execution intent changed during recovery")
    entry = _update_registration(
        args.control_file,
        kind="workspace",
        subject_id=workspace_id,
        canonical_idempotency_key=key,
        canonical_manifest_sha256=_sha256(canonical_path),
    )
    created = _native_cli(
        args.python,
        args.state,
        args.artifacts,
        args.workspaces,
        "execution",
        "create",
        "--pipeline",
        str(pipeline),
        "--execution",
        str(canonical_path),
        "--study-id",
        study_id,
        "--idempotency-key",
        key,
    )
    execution_id = created.get("execution_id")
    if not isinstance(execution_id, str) or not execution_id:
        raise RuntimeError("native canonical creation returned no execution id")
    bound_canonical = entry.get("canonical_execution_id")
    if bound_canonical is not None and bound_canonical != execution_id:
        raise RuntimeError("canonical execution identity changed during recovery")
    _update_registration(
        args.control_file,
        kind="workspace",
        subject_id=workspace_id,
        canonical_execution_id=execution_id,
        canonical_idempotency_key=key,
    )
    if not snapshot_database(
        args.state,
        args.retained_state,
        reason=f"workspace-reconcile-created:{workspace_id}:{execution_id}",
    ):
        raise RuntimeError("cannot retain canonical execution creation")
    registration = register_subject(
        args.state, args.control_file, kind="execution", subject_id=execution_id
    )
    current_entry = _registration_entry(
        args.control_file, kind="workspace", subject_id=workspace_id
    )
    started_raw = current_entry.get("reconcile_started_at")
    if not isinstance(started_raw, str) or (
        datetime.now(timezone.utc) - datetime.fromisoformat(started_raw)
    ).total_seconds() >= WORKSPACE_RECONCILE_SLA_SECONDS:
        raise RuntimeError("frozen workspace exceeded the 60-second registration SLA")
    if default_status == "active":
        cancelled = _native_cli(
            args.python,
            args.state,
            args.artifacts,
            args.workspaces,
            "cancel",
            str(default_id),
        )
        if cancelled.get("status") != "cancelled":
            raise RuntimeError("native default execution cancellation did not complete")
    if not snapshot_database(
        args.state,
        args.retained_state,
        reason=f"workspace-reconciled:{workspace_id}:{execution_id}",
    ):
        raise RuntimeError("cannot retain reconciled workspace transition")
    _complete_registration(
        args.control_file,
        kind="workspace",
        subject_id=workspace_id,
        native_status="frozen",
    )
    return {
        "workspace_id": workspace_id,
        "study_id": study_id,
        "default_execution_id": default_id,
        "execution_id": execution_id,
        "registered": registration["registered"],
        "training_data_contract": contract["schema"],
    }


def create_or_reuse_execution(
    *,
    python: Path,
    state: Path,
    retained_state: Path,
    control_file: Path,
    artifacts: Path,
    workspaces: Path,
    pipeline: Path,
    execution: Path,
    study_id: str,
    training_data_contract: Path,
    campaign_policy: Path,
) -> dict[str, Any]:
    """Create and register exactly one semantic execution in a study."""
    settings = _trusted_execution_settings(
        campaign_policy=campaign_policy,
        training_data_contract=training_data_contract,
    )
    proposed = _json_object(execution, "proposed execution manifest")
    reserved_task_ids = (
        _study_reserved_task_ids(state, study_id)
        if proposed.get("mode") == "production"
        else []
    )
    canonical = canonical_execution_manifest(
        proposed_manifest=execution,
        pipeline_manifest=pipeline,
        settings=settings,
        reserved_task_ids=reserved_task_ids,
    )
    canonical_path = _publish_canonical_execution(artifacts, canonical)
    contract = validate_generation_inputs(
        pipeline_manifest=pipeline,
        execution_manifest=canonical_path,
        contract_path=training_data_contract,
        campaign_policy_path=campaign_policy,
        expected_concurrency=int(settings["concurrency"]),
    )
    key = execution_creation_key(
        pipeline, canonical_path, study_id=study_id, workspaces=workspaces
    )
    created = _native_cli(
        python,
        state,
        artifacts,
        workspaces,
        "execution",
        "create",
        "--pipeline",
        str(pipeline.resolve(strict=True)),
        "--execution",
        str(canonical_path),
        "--study-id",
        study_id,
        "--idempotency-key",
        key,
    )
    execution_id = created.get("execution_id")
    if not isinstance(execution_id, str) or not execution_id:
        raise RuntimeError("native AutoData creation returned no execution id")
    equivalents = _equivalent_executions(state, execution_id)
    if not equivalents:
        raise RuntimeError("created execution vanished from native AutoData state")
    canonical = equivalents[0]
    canonical_id = str(canonical["id"])
    discarded_duplicate = None
    if canonical_id != execution_id:
        duplicate = _native_subject(state, "execution", execution_id)
        if (
            duplicate.get("status") != "active"
            or int(duplicate.get("taskAttemptsUsed") or 0) != 0
            or duplicate.get("phase") not in {"created", "baseline_pending"}
        ):
            raise RuntimeError(
                "semantic duplicate execution has already begun; refusing automatic cleanup"
            )
        _native_cli(
            python,
            state,
            artifacts,
            workspaces,
            "cancel",
            execution_id,
        )
        discarded_duplicate = execution_id
        execution_id = canonical_id
    row = _native_subject(state, "execution", execution_id)
    if not snapshot_database(
        state,
        retained_state,
        reason=f"supervised-creation:execution:{execution_id}",
    ):
        raise RuntimeError("cannot retain a supervised execution without live state")
    registration = None
    if row.get("status") == "active":
        registration = register_subject(
            state, control_file, kind="execution", subject_id=execution_id
        )
    elif row.get("status") != "completed":
        raise RuntimeError(
            f"canonical execution {execution_id} is terminal as {row.get('status')}"
        )
    return {
        "execution_id": execution_id,
        "study_id": study_id,
        "status": row.get("status"),
        "registered": registration is not None,
        "idempotency_key": key,
        "deduplicated": discarded_duplicate is not None,
        "discarded_duplicate_execution_id": discarded_duplicate,
        "training_data_contract": contract["schema"],
    }


def register_subject(
    state: Path, control_file: Path, *, kind: str, subject_id: str
) -> dict[str, Any]:
    """Explicitly enroll one active native subject for supervisor stepping."""
    row = _native_subject(state, kind, subject_id)
    if row.get("status") != "active":
        raise RuntimeError(
            f"native AutoData {kind} {subject_id} is already {row.get('status')}"
        )
    lock = _with_control_lock(control_file)
    try:
        if kind == "execution":
            equivalents = _equivalent_executions(state, subject_id)
            if equivalents and equivalents[0]["id"] != subject_id:
                raise RuntimeError(
                    f"execution {subject_id} duplicates canonical execution "
                    f"{equivalents[0]['id']}; register the canonical execution"
                )
        control = _load_control(control_file)
        for entry in control["subjects"]:
            if entry["kind"] == kind and entry["subject_id"] == subject_id:
                if entry["status"] != "registered":
                    raise RuntimeError(
                        f"AutoData lifecycle registration for {subject_id} is terminal"
                    )
                return {"registered": True, "idempotent": True, **entry}
        entry = {
            "kind": kind,
            "subject_id": subject_id,
            "status": "registered",
            "registered_at": _utc_now(),
        }
        control["subjects"].append(entry)
        _atomic_json(control_file, control)
        return {"registered": True, "idempotent": False, **entry}
    finally:
        lock.close()


def _complete_registration(
    control_file: Path, *, kind: str, subject_id: str, native_status: str
) -> None:
    lock = _with_control_lock(control_file)
    try:
        control = _load_control(control_file)
        for entry in control["subjects"]:
            if entry["kind"] == kind and entry["subject_id"] == subject_id:
                if entry["status"] == "completed":
                    return
                entry.update(
                    status="completed",
                    native_status=native_status,
                    completed_at=_utc_now(),
                )
                _atomic_json(control_file, control)
                return
        raise RuntimeError(f"AutoData lifecycle registration for {subject_id} vanished")
    finally:
        lock.close()


def _frozen_registered_workspace(
    state: Path, control_file: Path
) -> str | None:
    registrations = [
        entry
        for entry in _load_control(control_file)["subjects"]
        if entry["status"] == "registered" and entry["kind"] == "workspace"
    ]
    for entry in registrations:
        row = _native_subject(state, "workspace", str(entry["subject_id"]))
        if row.get("status") == "frozen":
            return str(entry["subject_id"])
    return None


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def next_subject(
    state: Path,
    control_file: Path,
    *,
    production_timeout_seconds: int = PRODUCTION_TIMEOUT_SECONDS,
    stage_timeout_policy: str = "enforce",
) -> Subject | None:
    """Return the next explicitly registered subject ready for stepping."""
    if stage_timeout_policy not in {"enforce", "observe-only"}:
        raise ValueError("stage_timeout_policy must be enforce or observe-only")
    registrations = [
        entry
        for entry in _load_control(control_file)["subjects"]
        if entry["status"] == "registered"
    ]
    if not registrations:
        return None
    if not state.is_file():
        raise RuntimeError("registered subjects exist but live AutoData state is missing")
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        tables = _table_names(connection)
        if not {"actions", "workspaces", "executions"}.issubset(tables):
            raise RuntimeError(
                "registered subjects exist but native AutoData state is incomplete"
            )
        blocked = {
            (str(row["scopeKind"]), str(row["scopeId"]))
            for row in connection.execute(
                "SELECT scopeKind,scopeId FROM actions "
                "WHERE status IN ('pending','in_progress')"
            ).fetchall()
        }
        for registration in registrations:
            kind = str(registration["kind"])
            subject_id = str(registration["subject_id"])
            table = "workspaces" if kind == "workspace" else "executions"
            row = connection.execute(
                f"SELECT * FROM {table} WHERE id=?", (subject_id,)
            ).fetchone()
            if row is None:
                raise RuntimeError(
                    f"registered native AutoData {kind} {subject_id} is missing"
                )
            native_status = str(row["status"])
            successful_status = "frozen" if kind == "workspace" else "completed"
            if native_status == successful_status:
                if kind == "workspace":
                    raise RuntimeError(
                        f"frozen workspace {subject_id} requires canonical reconciliation"
                    )
                _complete_registration(
                    control_file,
                    kind=kind,
                    subject_id=subject_id,
                    native_status=native_status,
                )
                continue
            if native_status != "active":
                raise RuntimeError(
                    f"registered native AutoData {kind} {subject_id} terminated as "
                    f"{native_status}"
                )
            if (kind, subject_id) in blocked:
                continue
            if kind == "workspace":
                native_wall = int(row["maxWallSeconds"])
                if (
                    stage_timeout_policy == "enforce"
                    and native_wall + NATIVE_WALL_GRACE_SECONDS
                    > META_TIMEOUT_SECONDS
                ):
                    raise RuntimeError(
                        f"workspace {subject_id} native wall budget plus grace exceeds "
                        "the 2-hour controller ceiling"
                    )
                return Subject(
                    "workspace",
                    subject_id,
                    str(row["phase"]),
                    (
                        META_TIMEOUT_SECONDS
                        if stage_timeout_policy == "enforce"
                        else None
                    ),
                    META_STALL_SECONDS,
                )
            spec = json.loads(str(row["executionJson"]))
            production = spec.get("mode") == "production"
            timeout = (
                production_timeout_seconds
                if production
                else META_TIMEOUT_SECONDS
            )
            native_wall = int(row["maxWallSeconds"])
            if (
                stage_timeout_policy == "enforce"
                and native_wall + NATIVE_WALL_GRACE_SECONDS > timeout
            ):
                label = (
                    f"{timeout}-second production"
                    if production
                    else "2-hour meta"
                )
                raise RuntimeError(
                    f"execution {subject_id} native wall budget plus grace exceeds "
                    f"the {label} controller ceiling"
                )
            return Subject(
                kind,
                subject_id,
                str(row["phase"]),
                timeout if stage_timeout_policy == "enforce" else None,
                PRODUCTION_STALL_SECONDS if production else META_STALL_SECONDS,
                production,
            )
    return None


class Supervisor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stop_requested = False
        self.stop_signal: int | None = None
        self.current: subprocess.Popen[str] | None = None
        self.lock_handle: TextIO | None = None
        self.last_status_signature = ""
        self.last_status_written = 0.0
        self.status_lock = threading.RLock()
        self.failed_step_signature: tuple[Any, ...] | None = None
        self.failed_step_count = 0
        self.training_smoke_coordinator: TrainingSmokeCoordinator | None = None
        self.training_smoke_binding: tuple[Path, Path, int] | None = None

    def _failure_feedback(
        self,
        error: BaseException,
        *,
        error_code: str,
        stage: str,
        retryable: bool,
        public_summary: str,
    ) -> dict[str, Any]:
        feedback = feedback_from_exception(
            error,
            error_code=error_code,
            stage=stage,
            retryable=retryable,
            public_summary=public_summary,
        )
        # Retryability belongs to this supervisor transition, not to the lower
        # level CLI call that may have produced the nested typed failure.
        feedback["retryable"] = retryable
        return feedback

    def _write_status(self, **fields: Any) -> None:
        with self.status_lock:
            signature = json.dumps(fields, sort_keys=True, default=str)
            now = time.monotonic()
            if (
                signature == self.last_status_signature
                and now - self.last_status_written < DEFAULT_STATUS_HEARTBEAT_SECONDS
            ):
                return
            _atomic_json(
                self.args.status_file,
                {
                    "schema": "aar.autodata.lifecycle-supervisor/v1",
                    "pid": os.getpid(),
                    "updated_at": _utc_now(),
                    **fields,
                },
            )
            self.last_status_signature = signature
            self.last_status_written = now

    def _call_with_status_heartbeat(
        self,
        operation: Callable[[], _ResultT],
        **status_fields: Any,
    ) -> _ResultT:
        """Keep a durable liveness record fresh around synchronous host work."""
        self._write_status(**status_fields)
        stop = threading.Event()
        failures: list[BaseException] = []

        def refresh() -> None:
            interval = max(0.001, DEFAULT_STATUS_HEARTBEAT_SECONDS / 2)
            while not stop.wait(interval):
                if self.stop_requested:
                    return
                try:
                    self._write_status(**status_fields)
                except BaseException as error:
                    failures.append(error)
                    return

        heartbeat = threading.Thread(
            target=refresh,
            name="autodata-supervisor-heartbeat",
            daemon=True,
        )
        heartbeat.start()
        operation_error: BaseException | None = None
        try:
            result = operation()
        except BaseException as error:
            operation_error = error
            raise
        finally:
            stop.set()
            heartbeat.join()
            if failures and operation_error is None:
                raise RuntimeError(
                    "failed to refresh AutoData supervisor status during host work"
                ) from failures[0]
        return result

    def _sleep_with_status_heartbeat(
        self,
        seconds: float,
        **status_fields: Any,
    ) -> None:
        deadline = time.monotonic() + max(0.0, seconds)
        interval = max(0.001, DEFAULT_STATUS_HEARTBEAT_SECONDS / 2)
        while not self.stop_requested:
            self._write_status(**status_fields)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(interval, remaining))

    def _signal(self, signum: int, _frame: Any) -> None:
        # Signal handlers may interrupt the main thread inside _atomic_json.
        # Record intent only; re-entering the status writer here can collide
        # with its process-scoped temporary path. The serialized run path emits
        # the durable stopping/stopped states after child cleanup.
        self.stop_requested = True
        self.stop_signal = signum
        if self.current is not None and self.current.poll() is None:
            try:
                os.killpg(self.current.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def _terminate_current_process_group(self) -> int:
        """Stop the active native CLI without any unbounded wait path."""
        process = self.current
        if process is None:
            raise RuntimeError("native AutoData step process is missing")
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                return process.wait(timeout=PROCESS_TERMINATE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    return process.wait(timeout=PROCESS_KILL_GRACE_SECONDS)
                except subprocess.TimeoutExpired as error:
                    raise RuntimeError(
                        "native AutoData step did not exit after bounded TERM/KILL cleanup"
                    ) from error
        return int(process.returncode)

    def _lock(self) -> None:
        self.args.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.lock_handle = self.args.lock_file.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("another AutoData lifecycle supervisor owns this run") from error
        self.lock_handle.seek(0)
        self.lock_handle.truncate()
        self.lock_handle.write(f"{os.getpid()}\n")
        self.lock_handle.flush()

    def _snapshot(self, reason: str, *, publish_status: bool = True) -> None:
        if snapshot_database(
            self.args.state,
            self.args.retained_state,
            reason=reason,
        ) and publish_status:
            self._write_status(state="running", last_snapshot_reason=reason)

    def _reconcile_semantic_action(self) -> dict[str, Any] | None:
        """Reconcile one explicitly allowlisted native semantic action."""

        clarify_enabled = os.getenv(
            "AAR_AUTODATA_CLARIFY_COORDINATOR", ""
        ).strip().lower()
        analysis_enabled = os.getenv(
            "AAR_AUTODATA_ANALYSIS_COORDINATOR", ""
        ).strip().lower()
        pipeline_enabled = os.getenv(
            "AAR_AUTODATA_PIPELINE_COORDINATOR", ""
        ).strip().lower()
        mutation_enabled = os.getenv(
            "AAR_AUTODATA_MUTATION_COORDINATOR", ""
        ).strip().lower()
        if not any(
            (clarify_enabled, pipeline_enabled, analysis_enabled, mutation_enabled)
        ):
            return None
        for label, enabled in (
            ("clarify", clarify_enabled),
            ("pipeline", pipeline_enabled),
            ("analysis", analysis_enabled),
            ("mutation", mutation_enabled),
        ):
            if enabled and enabled not in {"1", "true", "yes", "on"}:
                raise AutoDataCoordinatorError(
                    "semantic_coordinator_flag_invalid",
                    f"{label} coordinator enablement flag is invalid",
                )
        if pipeline_enabled and (
            os.getenv("AAR_EXPERIMENT_RUN_ID") != "run13"
            or os.getenv("AAR_IDEA_UID_OVERRIDE")
            != "run13-trial7-alpha-iteration-1"
            or os.getenv("AAR_AGENT_BACKEND") != "claude"
            or os.getenv("AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE") != "1"
            or os.getenv("AAR_AUTODATA_LIFECYCLE_SUPERVISED") != "1"
        ):
            raise AutoDataCoordinatorError(
                "pipeline_coordinator_scope_invalid",
                "author_pipeline coordinator is restricted to supervised Run 13 Trial 7",
            )
        team_raw = os.getenv("TEAM_DIR", "").strip()
        if not team_raw:
            raise AutoDataCoordinatorError(
                "semantic_coordinator_team_missing",
                "clarify coordinator has no team directory",
            )
        team_dir = Path(team_raw).resolve(strict=True)
        # Workspace creation publishes native state before registration is
        # atomically added to the lifecycle control file.  That interval is an
        # expected pre-action state, not a malformed durable record.
        if not self.args.state.is_file() or not self.args.control_file.is_file():
            return None
        backend = os.getenv("AAR_AUTODATA_SEMANTIC_WORKER", "").strip().lower()
        if backend == "claude":
            worker = ClaudeWorker()
        elif backend == "kimi":
            worker = KimiWorker()
        else:
            raise AutoDataCoordinatorError(
                "semantic_worker_backend_invalid",
                "semantic coordinator names an unsupported semantic worker backend",
            )
        control = NativeAutoDataControl.from_environment(
            team_dir / "autodata" / "action-native-results"
        )
        common = {
            "control": control,
            "worker": worker,
            "team_dir": team_dir,
            "action_timeout_seconds": float(
                os.getenv("AAR_AUTODATA_CLARIFY_WORKER_SECONDS", "1800")
            ),
            "malformed_output_attempts": int(
                os.getenv("AAR_AUTODATA_CLARIFY_OUTPUT_ATTEMPTS", "3")
            ),
        }
        outcome = None
        action_kind = ""
        if clarify_enabled:
            coordinator = AutoDataActionReconciler(**common)
            outcome = asyncio.run(
                coordinator.reconcile_registered_clarify(self.args.control_file)
            )
            action_kind = "clarify_design"
        if outcome is None and pipeline_enabled:
            coordinator = WorkspacePipelineReconciler(**common)
            outcome = asyncio.run(
                coordinator.reconcile_registered_pipeline(self.args.control_file)
            )
            action_kind = "author_pipeline"
        if outcome is None and analysis_enabled:
            coordinator = ExecutionAnalysisReconciler(**common)
            outcome = asyncio.run(
                coordinator.reconcile_registered_analysis(self.args.control_file)
            )
            action_kind = "analyze_results"
        if outcome is None and mutation_enabled:
            coordinator = ExecutionMutationReconciler(**common)
            outcome = asyncio.run(
                coordinator.reconcile_registered_mutation(self.args.control_file)
            )
            action_kind = "mutate_candidate"
        if outcome is None:
            return None
        self._snapshot(
            f"semantic-action:{outcome.workspace_id}:{outcome.action_id}"
        )
        return {
            "workspace_id": outcome.workspace_id,
            "action_id": outcome.action_id,
            "action_kind": action_kind,
            "worker_backend": outcome.worker_backend,
            "receipt": str(outcome.receipt_path),
            "native_phase_observed": outcome.native_phase,
            "native_revision_observed": outcome.native_revision,
        }

    def _reconcile_approval_action(self) -> dict[str, Any] | None:
        """Complete one delegated approval through the existing shared bridge."""

        enabled = os.getenv(
            "AAR_AUTODATA_APPROVAL_COORDINATOR", ""
        ).strip().lower()
        if not enabled:
            return None
        if enabled not in {"1", "true", "yes", "on"}:
            raise AutoDataCoordinatorError(
                "approval_coordinator_flag_invalid",
                "approval coordinator enablement flag is invalid",
            )
        team_raw = os.getenv("TEAM_DIR", "").strip()
        if not team_raw:
            raise AutoDataCoordinatorError(
                "approval_coordinator_team_missing",
                "approval coordinator has no team directory",
            )
        if not self.args.state.is_file() or not self.args.control_file.is_file():
            return None
        from aar.research_loop.autodata_approval import review_and_complete_action

        control = NativeAutoDataControl.from_environment(
            Path(team_raw).resolve(strict=True)
            / "autodata"
            / "action-native-results"
        )
        outcome = WorkspaceApprovalReconciler(
            control=control,
            approval_handler=review_and_complete_action,
        ).reconcile_registered_approval(self.args.control_file)
        if outcome is None:
            return None
        self._snapshot(f"approval-action:{outcome.workspace_id}:{outcome.action_id}")
        return {
            "action_kind": outcome.action_kind,
            "workspace_id": outcome.workspace_id,
            "action_id": outcome.action_id,
            "decision": outcome.decision,
            "audit_path": str(outcome.audit_path),
            "native_phase": outcome.native_phase,
            "native_revision": outcome.native_revision,
        }

    def _reconcile_training_smoke(self) -> dict[str, Any] | None:
        """Reconcile only a verified production handoff into the terminal canary."""

        enabled = os.getenv(
            "AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR", ""
        ).strip().lower()
        if not enabled:
            return None
        if enabled not in {"1", "true", "yes", "on"}:
            raise TrainingSmokeCoordinatorError(
                "training_smoke_coordinator_flag_invalid",
                "training smoke coordinator enablement flag is invalid",
            )
        if os.getenv("AAR_AUTODATA_STOP_AFTER", "").strip() != "training_smoke":
            raise TrainingSmokeCoordinatorError(
                "training_smoke_boundary_invalid",
                "training smoke coordinator requires stop_after=training_smoke",
            )
        if os.getenv("AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE", "") != "1":
            raise TrainingSmokeCoordinatorError(
                "training_smoke_owner_invalid",
                "training smoke coordinator requires lifecycle ownership",
            )
        entries = [
            entry
            for entry in _load_control(self.args.control_file)["subjects"]
            if entry.get("kind") == "execution"
            and entry.get("status") == "completed"
            and isinstance(entry.get("parent_meta_execution_id"), str)
            and isinstance(entry.get("training_handoff_sha256"), str)
        ]
        if not entries:
            return None
        if len(entries) != 1:
            raise TrainingSmokeCoordinatorError(
                "training_smoke_lineage_ambiguous",
                "multiple production handoffs are eligible for training",
            )
        production = entries[0]
        production_id = str(production["subject_id"])
        meta_id = str(production["parent_meta_execution_id"])
        meta = _registration_entry(
            self.args.control_file, kind="execution", subject_id=meta_id
        )
        if (
            meta.get("production_execution_id") != production_id
            or meta.get("training_handoff_sha256")
            != production.get("training_handoff_sha256")
        ):
            raise TrainingSmokeCoordinatorError(
                "training_smoke_lineage_invalid",
                "training handoff lineage is inconsistent",
            )
        _, bootstrap, _run_root = _run_binding(
            self.args.state, self.args.control_file, meta_id
        )
        team_raw = os.getenv("TEAM_DIR", "").strip()
        if not team_raw:
            raise TrainingSmokeCoordinatorError(
                "training_smoke_team_missing",
                "training smoke coordinator has no team directory",
            )
        try:
            required_rows = int(os.environ["AAR_AUTODATA_PRODUCTION_ROWS"])
        except (KeyError, ValueError) as error:
            raise TrainingSmokeCoordinatorError(
                "training_smoke_rows_invalid",
                "training smoke row target is invalid",
            ) from error
        repo = Path(__file__).resolve().parents[1]
        team = Path(team_raw).resolve(strict=True)
        binding = (repo, team, required_rows)
        if self.training_smoke_binding not in {None, binding}:
            raise TrainingSmokeCoordinatorError(
                "training_smoke_binding_changed",
                "training smoke coordinator binding changed",
            )
        if self.training_smoke_coordinator is None:
            self.training_smoke_coordinator = TrainingSmokeCoordinator(
                repo=repo,
                team_dir=team,
                required_rows=required_rows,
                completion_grace_seconds=float(
                    os.getenv("AAR_TRAINING_MARKER_GRACE_SECONDS", "120")
                ),
            )
            self.training_smoke_binding = binding
        outcome = self.training_smoke_coordinator.reconcile(
            run_id=str(bootstrap["run_id"]),
            idea_name=str(bootstrap["idea_name"]),
            expected_code_hash=str(bootstrap["code_hash"]),
            meta_execution_id=meta_id,
            production_execution_id=production_id,
        )
        current_job = production.get("training_job_id")
        if current_job not in {None, outcome.job_id}:
            raise TrainingSmokeCoordinatorError(
                "training_smoke_job_changed", "training job identity changed"
            )
        fields: dict[str, Any] = {"training_job_id": outcome.job_id}
        if outcome.terminal_receipt is not None:
            fields["training_smoke_receipt_sha256"] = (
                "sha256:" + _sha256(outcome.terminal_receipt)
            )
        _update_registration(
            self.args.control_file,
            kind="execution",
            subject_id=production_id,
            **fields,
        )
        return {
            "state": outcome.state,
            "run_id": outcome.run_id,
            "job_id": outcome.job_id,
            "terminal_receipt": (
                str(outcome.terminal_receipt)
                if outcome.terminal_receipt is not None
                else None
            ),
        }

    def _progress_signature(self, subject: Subject | None = None) -> tuple[Any, ...]:
        """Return native semantic progress, never SQLite/WAL write activity."""
        if subject is None or not self.args.state.is_file():
            return ()
        table = "workspaces" if subject.kind == "workspace" else "executions"
        with sqlite3.connect(
            f"file:{self.args.state}?mode=ro", uri=True
        ) as connection:
            connection.row_factory = sqlite3.Row
            tables = _table_names(connection)
            row = connection.execute(
                f"SELECT * FROM {table} WHERE id=?", (subject.subject_id,)
            ).fetchone()
            if row is None:
                return ("missing", subject.kind, subject.subject_id)
            columns = set(row.keys())
            state = tuple(
                row[name] if name in columns else None
                for name in (
                    "status",
                    "phase",
                    "revision",
                    "iteration",
                    "taskAttemptsUsed",
                    "currentCandidateId",
                    "winnerCandidateId",
                )
            )
            attempts: tuple[Any, ...] = ()
            if "task_attempts" in tables:
                attempt_columns = {
                    str(value[1])
                    for value in connection.execute(
                        "PRAGMA table_info(task_attempts)"
                    )
                }
                if {"scopeKind", "scopeId", "state"}.issubset(attempt_columns):
                    attempts = tuple(
                        tuple(value)
                        for value in connection.execute(
                            "SELECT state,COUNT(*) FROM task_attempts "
                            "WHERE scopeKind=? AND scopeId=? GROUP BY state ORDER BY state",
                            (subject.kind, subject.subject_id),
                        ).fetchall()
                    )
            actions: tuple[Any, ...] = ()
            if "actions" in tables:
                action_columns = {
                    str(value[1])
                    for value in connection.execute("PRAGMA table_info(actions)")
                }
                selected = [
                    name
                    for name in ("id", "kind", "status", "scopeRevision", "attempt")
                    if name in action_columns
                ]
                if {"scopeKind", "scopeId"}.issubset(action_columns) and selected:
                    actions = tuple(
                        tuple(value)
                        for value in connection.execute(
                            f"SELECT {','.join(selected)} FROM actions "
                            f"WHERE scopeKind=? AND scopeId=? ORDER BY {selected[0]}",
                            (subject.kind, subject.subject_id),
                        ).fetchall()
                    )
            task_progress: tuple[Any, ...] = ()
            if "task_progress" in tables and "task_attempts" in tables:
                progress_columns = {
                    str(value[1])
                    for value in connection.execute(
                        "PRAGMA table_info(task_progress)"
                    )
                }
                if {"attemptId", "sequence", "state"}.issubset(progress_columns):
                    task_progress = tuple(
                        tuple(value)
                        for value in connection.execute(
                            "SELECT p.attemptId,p.sequence,p.state FROM task_progress p "
                            "JOIN task_attempts a ON a.id=p.attemptId "
                            "WHERE a.scopeKind=? AND a.scopeId=? GROUP BY p.attemptId "
                            "HAVING p.sequence=MAX(p.sequence) "
                            "ORDER BY p.attemptId",
                            (subject.kind, subject.subject_id),
                        ).fetchall()
                    )
        return state, attempts, actions, task_progress

    def _record_step_outcome(
        self,
        subject: Subject,
        *,
        return_code: int,
        timed_out: bool,
        stalled: bool,
        safe_diagnostic: str | None = None,
    ) -> None:
        if return_code == 0 and not timed_out and not stalled:
            self.failed_step_signature = None
            self.failed_step_count = 0
            return
        permanent_error_code = (
            _PERMANENT_NATIVE_DIAGNOSTICS.get(safe_diagnostic)
            if safe_diagnostic is not None
            else None
        )
        if permanent_error_code is None and safe_diagnostic is not None:
            budget_match = re.fullmatch(
                r"(task_attempts|iterations) budget insufficient for atomic batch: "
                r"requires [0-9]+, remaining [0-9]+",
                safe_diagnostic,
            )
            if budget_match is not None:
                permanent_error_code = (
                    "native_task_attempt_budget_insufficient"
                    if budget_match.group(1) == "task_attempts"
                    else "native_iteration_budget_insufficient"
                )
        if permanent_error_code is not None:
            raise NativeStepFailure(
                safe_diagnostic,
                error_code=permanent_error_code,
                attempts=1,
            )
        failed_signature = (
            subject.kind,
            subject.subject_id,
            subject.phase,
        )
        if failed_signature == self.failed_step_signature:
            self.failed_step_count += 1
        else:
            self.failed_step_signature = failed_signature
            self.failed_step_count = 1
        if self.failed_step_count >= 3:
            raise NativeStepFailure(safe_diagnostic)

    def _safe_step_diagnostic(self, log_offset: int) -> str | None:
        """Extract only allowlisted, content-free native contract diagnostics."""
        self.args.log_handle.flush()
        try:
            with self.args.log_file.open("rb") as handle:
                handle.seek(log_offset)
                raw = handle.read(_MAX_NATIVE_DIAGNOSTIC_BYTES + 1)
        except OSError:
            return None
        if len(raw) > _MAX_NATIVE_DIAGNOSTIC_BYTES:
            raw = raw[-_MAX_NATIVE_DIAGNOSTIC_BYTES:]
        text = raw.decode("utf-8", errors="replace")
        safe_exact = {
            "analysis action result must include a non-empty proposal",
            "analysis action has not completed",
            "mutation action has not completed",
            *_PERMANENT_NATIVE_DIAGNOSTICS,
        }
        for line in reversed(text.splitlines()):
            if not line.startswith("autodata: "):
                continue
            detail = line.removeprefix("autodata: ").strip()
            if detail in safe_exact:
                return detail
            if re.fullmatch(
                r"execution cannot step from phase '[a-z][a-z0-9_]*'", detail
            ):
                return detail
            if re.fullmatch(
                r"(?:task_attempts|iterations) budget insufficient for atomic batch: "
                r"requires [0-9]+, remaining [0-9]+",
                detail,
            ):
                return detail
        return None

    def _step(self, subject: Subject) -> None:
        if subject.production:
            _require_production_acceptance_attainability(
                self.args.state, self.args.artifacts, subject.subject_id
            )
        command = [
            str(self.args.python),
            "-m",
            "autodata.cli",
            "--state",
            str(self.args.state),
            "--artifacts",
            str(self.args.artifacts),
            "--workspaces",
            str(self.args.workspaces),
            subject.kind,
            "step",
            subject.subject_id,
        ]
        self._write_status(
            state="stepping",
            subject_kind=subject.kind,
            subject_id=subject.subject_id,
            phase=subject.phase,
            timeout_seconds=subject.timeout_seconds,
            stall_seconds=subject.stall_seconds,
        )
        self.args.log_handle.flush()
        log_offset = self.args.log_handle.tell()
        started = time.monotonic()
        self.current = subprocess.Popen(
            command,
            stdout=self.args.log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        next_snapshot = started + self.args.snapshot_interval_seconds
        timed_out = False
        stalled = False
        unattainable: NativeStepFailure | None = None
        progress_signature = self._progress_signature(subject)
        last_progress = started
        while self.current.poll() is None and not self.stop_requested:
            now = time.monotonic()
            # Native execution steps can legitimately take minutes. Refresh the
            # same durable stepping record while the child is alive so the host
            # FSM never mistakes useful work for a dead supervisor.
            self._write_status(
                state="stepping",
                subject_kind=subject.kind,
                subject_id=subject.subject_id,
                phase=subject.phase,
                timeout_seconds=subject.timeout_seconds,
                stall_seconds=subject.stall_seconds,
            )
            if (
                subject.timeout_seconds is not None
                and now - started >= subject.timeout_seconds
            ):
                timed_out = True
                self._terminate_current_process_group()
                break
            if subject.production:
                try:
                    _require_production_acceptance_attainability(
                        self.args.state, self.args.artifacts, subject.subject_id
                    )
                except NativeStepFailure as error:
                    unattainable = error
                    self._terminate_current_process_group()
                    break
                except Exception:
                    self._terminate_current_process_group()
                    self.current = None
                    raise
            current_signature = self._progress_signature(subject)
            if current_signature != progress_signature:
                progress_signature = current_signature
                last_progress = now
            elif now - last_progress >= subject.stall_seconds:
                stalled = True
                self._terminate_current_process_group()
                break
            if now >= next_snapshot:
                self._snapshot(f"in-progress:{subject.kind}:{subject.subject_id}:{subject.phase}")
                next_snapshot = now + self.args.snapshot_interval_seconds
            time.sleep(min(self.args.poll_seconds, 2.0))
        if self.stop_requested and self.current.poll() is None:
            self._terminate_current_process_group()
        return_code = self.current.poll()
        if return_code is None:
            raise RuntimeError("native AutoData step remained active after bounded cleanup")
        self.current = None
        if unattainable is not None:
            self._snapshot(
                f"step:{subject.kind}:{subject.subject_id}:unattainable"
            )
            self._write_status(
                state="running",
                last_subject_kind=subject.kind,
                last_subject_id=subject.subject_id,
                last_phase=subject.phase,
                last_outcome="unattainable",
            )
            raise unattainable
        outcome = (
            "timeout"
            if timed_out
            else "stalled"
            if stalled
            else f"exit-{return_code}"
        )
        self._snapshot(f"step:{subject.kind}:{subject.subject_id}:{outcome}")
        self._write_status(
            state="running",
            last_subject_kind=subject.kind,
            last_subject_id=subject.subject_id,
            last_phase=subject.phase,
            last_outcome=outcome,
        )
        self._record_step_outcome(
            subject,
            return_code=return_code,
            timed_out=timed_out,
            stalled=stalled,
            safe_diagnostic=self._safe_step_diagnostic(log_offset),
        )
        if return_code != 0 or timed_out or stalled:
            self._sleep_with_status_heartbeat(
                self.args.error_backoff_seconds,
                state="running",
                last_subject_kind=subject.kind,
                last_subject_id=subject.subject_id,
                last_phase=subject.phase,
                last_outcome=outcome,
            )

    def run(self) -> int:
        self._lock()
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)
        self._write_status(state="starting")
        while not self.stop_requested:
            workspace_id: str | None = None
            try:
                workspace_id = _frozen_registered_workspace(
                    self.args.state, self.args.control_file
                )
                if workspace_id is not None:
                    result = self._call_with_status_heartbeat(
                        lambda: reconcile_frozen_workspace(self.args, workspace_id),
                        state="reconciling",
                        subject_kind="workspace",
                        subject_id=workspace_id,
                    )
                    self._write_status(state="running", reconciliation=result)
                    continue
                pending_transition = _pending_completed_execution_transition(self.args)
                if pending_transition is not None:
                    transition_id, transition_mode = pending_transition
                    transition = self._call_with_status_heartbeat(
                        lambda: reconcile_completed_execution_transition(self.args),
                        state="reconciling",
                        subject_kind="execution",
                        subject_id=transition_id,
                        transition_mode=transition_mode,
                    )
                    if transition is None:
                        raise RuntimeError(
                            "completed execution transition disappeared during "
                            "reconciliation"
                        )
                    self._write_status(state="running", transition=transition)
                    continue
                training_smoke = self._call_with_status_heartbeat(
                    self._reconcile_training_smoke,
                    state="training-smoke",
                )
                if training_smoke is not None:
                    self._write_status(
                        state="training-smoke", training_smoke=training_smoke
                    )
                    self._sleep_with_status_heartbeat(
                        self.args.poll_seconds,
                        state="training-smoke",
                        training_smoke=training_smoke,
                    )
                    continue
                approval_action = self._call_with_status_heartbeat(
                    self._reconcile_approval_action,
                    state="approval-action",
                )
                if approval_action is not None:
                    self._write_status(
                        state="running", approval_action=approval_action
                    )
                    continue
                semantic_action = self._call_with_status_heartbeat(
                    self._reconcile_semantic_action,
                    state="semantic-action",
                )
                if semantic_action is not None:
                    self._write_status(
                        state="running", semantic_action=semantic_action
                    )
                    continue
                subject = next_subject(
                    self.args.state,
                    self.args.control_file,
                    production_timeout_seconds=self.args.production_timeout_seconds,
                    stage_timeout_policy=self.args.stage_timeout_policy,
                )
            except Exception as error:
                if self.stop_requested:
                    break
                if isinstance(error, AutoDataCoordinatorError):
                    feedback = self._failure_feedback(
                        error,
                        error_code=error.code,
                        stage="autodata_action",
                        retryable=error.retryable,
                        public_summary="AutoData coordinated action reconciliation failed",
                    )
                    self._snapshot("supervisor-coordinated-action-failure")
                    self._write_status(
                        state="failed",
                        error=feedback["summary"],
                        failure=feedback,
                    )
                    return 2
                if isinstance(error, TrainingSmokeCoordinatorError):
                    feedback = self._failure_feedback(
                        error,
                        error_code=error.code,
                        stage="training_smoke",
                        retryable=error.retryable,
                        public_summary="training smoke reconciliation failed",
                    )
                    if error.retryable:
                        self._write_status(
                            state="reconcile-retrying",
                            error=feedback["summary"],
                            failure=feedback,
                        )
                        self._sleep_with_status_heartbeat(
                            self.args.error_backoff_seconds,
                            state="reconcile-retrying",
                            error=feedback["summary"],
                            failure=feedback,
                        )
                        continue
                    self._write_status(
                        state="failed",
                        error=feedback["summary"],
                        failure=feedback,
                    )
                    return 2
                if workspace_id is not None:
                    entry = _registration_entry(
                        self.args.control_file,
                        kind="workspace",
                        subject_id=workspace_id,
                    )
                    attempts = int(entry.get("reconcile_attempts") or 0)
                    started_raw = entry.get("reconcile_started_at")
                    elapsed = WORKSPACE_RECONCILE_SLA_SECONDS
                    if isinstance(started_raw, str):
                        elapsed = (
                            datetime.now(timezone.utc)
                            - datetime.fromisoformat(started_raw)
                        ).total_seconds()
                    if (
                        attempts < WORKSPACE_RECONCILE_MAX_ATTEMPTS
                        and elapsed < WORKSPACE_RECONCILE_SLA_SECONDS
                    ):
                        feedback = self._failure_feedback(
                            error,
                            error_code="workspace_reconcile_failed",
                            stage="autodata_lifecycle",
                            retryable=True,
                            public_summary="workspace reconciliation failed",
                        )
                        self._write_status(
                            state="reconcile-retrying",
                            subject_kind="workspace",
                            subject_id=workspace_id,
                            attempt=attempts,
                            error=feedback["summary"],
                            failure=feedback,
                        )
                        self._sleep_with_status_heartbeat(
                            self.args.error_backoff_seconds,
                            state="reconcile-retrying",
                            subject_kind="workspace",
                            subject_id=workspace_id,
                            attempt=attempts,
                            error=feedback["summary"],
                            failure=feedback,
                        )
                        continue
                feedback = self._failure_feedback(
                    error,
                    error_code="lifecycle_configuration_failed",
                    stage="autodata_lifecycle",
                    retryable=False,
                    public_summary="AutoData lifecycle configuration failed",
                )
                self._snapshot("supervisor-configuration-failure")
                self._write_status(
                    state="failed",
                    error=feedback["summary"],
                    failure=feedback,
                )
                return 2
            if subject is None:
                self._sleep_with_status_heartbeat(
                    self.args.poll_seconds,
                    state="idle",
                )
                continue
            try:
                self._step(subject)
            except Exception as error:
                if self.stop_requested:
                    break
                error_code = "lifecycle_step_failed"
                public_summary = "native AutoData lifecycle step failed"
                if isinstance(error, NativeStepFailure):
                    error_code = error.error_code
                    public_summary = error.public_summary
                feedback = self._failure_feedback(
                    error,
                    error_code=error_code,
                    stage="autodata_lifecycle",
                    retryable=False,
                    public_summary=public_summary,
                )
                self._snapshot("supervisor-step-failure")
                self._write_status(
                    state="failed",
                    error=feedback["summary"],
                    failure=feedback,
                )
                return 2
        stop_fields: dict[str, Any] = {"state": "stopping"}
        if self.stop_signal is not None:
            stop_fields["signal"] = self.stop_signal
        self._write_status(**stop_fields)
        self._snapshot("supervisor-shutdown", publish_status=False)
        self._write_status(state="stopped", signal=self.stop_signal)
        return 0


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--state", type=_path, required=True)
    restore.add_argument("--retained-state", type=_path, required=True)
    restore.add_argument("--require-manifest", action="store_true")

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--state", type=_path, required=True)
    snapshot.add_argument("--retained-state", type=_path, required=True)
    snapshot.add_argument("--reason", required=True)

    register = subparsers.add_parser("register")
    register.add_argument("--state", type=_path, required=True)
    register.add_argument("--retained-state", type=_path, required=True)
    register.add_argument("--control-file", type=_path, required=True)
    register.add_argument(
        "--subject-kind", choices=("workspace", "execution"), required=True
    )
    register.add_argument("--subject-id", required=True)

    create_execution = subparsers.add_parser("create-execution")
    create_execution.add_argument("--python", type=_path, required=True)
    create_execution.add_argument("--state", type=_path, required=True)
    create_execution.add_argument("--retained-state", type=_path, required=True)
    create_execution.add_argument("--control-file", type=_path, required=True)
    create_execution.add_argument("--artifacts", type=_path, required=True)
    create_execution.add_argument("--workspaces", type=_path, required=True)
    create_execution.add_argument("--pipeline", type=_path, required=True)
    create_execution.add_argument("--execution", type=_path, required=True)
    create_execution.add_argument("--study-id", required=True)
    create_execution.add_argument("--training-data-contract", type=_path, required=True)
    create_execution.add_argument("--campaign-policy", type=_path, required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--python", type=_path, required=True)
    run.add_argument("--state", type=_path, required=True)
    run.add_argument("--retained-state", type=_path, required=True)
    run.add_argument("--control-file", type=_path, required=True)
    run.add_argument("--artifacts", type=_path, required=True)
    run.add_argument("--workspaces", type=_path, required=True)
    run.add_argument("--training-data-contract", type=_path, required=True)
    run.add_argument("--campaign-policy", type=_path, required=True)
    run.add_argument("--resolved-config", type=_path, required=True)
    run.add_argument("--lock-file", type=_path, required=True)
    run.add_argument("--status-file", type=_path, required=True)
    run.add_argument("--log-file", type=_path, required=True)
    run.add_argument("--poll-seconds", type=float, default=2.0)
    run.add_argument(
        "--snapshot-interval-seconds",
        type=float,
        default=DEFAULT_SNAPSHOT_INTERVAL_SECONDS,
    )
    run.add_argument("--error-backoff-seconds", type=float, default=10.0)
    run.add_argument(
        "--production-timeout-seconds",
        type=int,
        default=PRODUCTION_TIMEOUT_SECONDS,
    )
    run.add_argument(
        "--stage-timeout-policy",
        choices=("enforce", "observe-only"),
        default="enforce",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "restore":
        restored = restore_database(
            args.retained_state,
            args.state,
            require_manifest=args.require_manifest,
        )
        print(json.dumps({"restored": restored, "state": str(args.state)}))
        return 0
    if args.command == "snapshot":
        created = snapshot_database(args.state, args.retained_state, reason=args.reason)
        print(json.dumps({"snapshotted": created, "state": str(args.retained_state)}))
        return 0
    if args.command == "register":
        row = _native_subject(args.state, args.subject_kind, args.subject_id)
        if row.get("status") != "active":
            raise RuntimeError(
                f"native AutoData {args.subject_kind} {args.subject_id} is already "
                f"{row.get('status')}"
            )
        if not snapshot_database(
            args.state,
            args.retained_state,
            reason=f"registration:{args.subject_kind}:{args.subject_id}",
        ):
            raise RuntimeError("cannot register a subject without live AutoData state")
        result = register_subject(
            args.state,
            args.control_file,
            kind=args.subject_kind,
            subject_id=args.subject_id,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "create-execution":
        result = create_or_reuse_execution(
            python=args.python,
            state=args.state,
            retained_state=args.retained_state,
            control_file=args.control_file,
            artifacts=args.artifacts,
            workspaces=args.workspaces,
            pipeline=args.pipeline,
            execution=args.execution,
            study_id=args.study_id,
            training_data_contract=args.training_data_contract,
            campaign_policy=args.campaign_policy,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    if (
        args.poll_seconds <= 0
        or args.error_backoff_seconds < 0
        or args.snapshot_interval_seconds <= 0
        or args.production_timeout_seconds <= 0
    ):
        raise SystemExit(
            "poll, snapshot, and production timeout values must be positive; "
            "error backoff must be non-negative"
        )
    args.resolved_config_sha256 = _sha256(args.resolved_config)
    args.campaign_policy_sha256 = _sha256(args.campaign_policy)
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    with args.log_file.open("a", encoding="utf-8", buffering=1) as log_handle:
        args.log_handle = log_handle
        return Supervisor(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
