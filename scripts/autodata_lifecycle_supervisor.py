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
import fcntl
import hashlib
import json
import os
import signal
import sqlite3
import stat
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from aar.infrastructure.autodata_contract import validate_generation_inputs

META_TIMEOUT_SECONDS = 2 * 60 * 60
PRODUCTION_TIMEOUT_SECONDS = 8 * 60 * 60
NATIVE_WALL_GRACE_SECONDS = 10 * 60
META_STALL_SECONDS = 20 * 60
PRODUCTION_STALL_SECONDS = 30 * 60
DEFAULT_SNAPSHOT_INTERVAL_SECONDS = 5 * 60
CONTROL_SCHEMA = "aar.autodata.lifecycle-control/v1"
SUPERVISED_EXECUTION_KEY_SCHEMA = "aar.autodata.supervised-execution/v1"


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
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _verify_database(path: Path) -> None:
    with sqlite3.connect(
        f"file:{path}?mode=ro&immutable=1", uri=True
    ) as connection:
        quick = connection.execute("PRAGMA quick_check").fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if quick != [("ok",)]:
        raise RuntimeError(f"SQLite quick_check failed for {path}: {quick!r}")
    if integrity != [("ok",)]:
        raise RuntimeError(f"SQLite integrity_check failed for {path}: {integrity!r}")
    if foreign_keys:
        raise RuntimeError(
            f"SQLite foreign_key_check failed for {path}: {foreign_keys!r}"
        )


def snapshot_database(source: Path, retained: Path, *, reason: str) -> bool:
    """Create an atomic, self-contained SQLite backup on retained storage."""
    if not source.is_file():
        return False
    retained.parent.mkdir(parents=True, exist_ok=True)
    temporary = retained.with_name(f"{retained.name}.tmp.{os.getpid()}")
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_db:
            with sqlite3.connect(temporary) as destination_db:
                source_db.backup(destination_db)
        _verify_database(temporary)
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


def _with_control_lock(path: Path) -> TextIO:
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


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
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-2000:]
        raise RuntimeError(f"native AutoData CLI failed: {detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("native AutoData CLI returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("native AutoData CLI did not return one JSON object")
    return value


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
    expected_concurrency_raw = os.environ.get("AAR_AUTODATA_CONCURRENCY")
    expected_concurrency = (
        int(expected_concurrency_raw) if expected_concurrency_raw else None
    )
    contract = validate_generation_inputs(
        pipeline_manifest=pipeline,
        execution_manifest=execution,
        contract_path=training_data_contract,
        campaign_policy_path=campaign_policy,
        expected_concurrency=expected_concurrency,
    )
    key = execution_creation_key(
        pipeline, execution, study_id=study_id, workspaces=workspaces
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
        str(execution.resolve(strict=True)),
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
            )
    return None


class Supervisor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stop_requested = False
        self.current: subprocess.Popen[str] | None = None
        self.lock_handle: TextIO | None = None
        self.last_status_signature = ""
        self.last_status_written = 0.0

    def _write_status(self, **fields: Any) -> None:
        signature = json.dumps(fields, sort_keys=True, default=str)
        now = time.monotonic()
        if (
            signature == self.last_status_signature
            and now - self.last_status_written < 60
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

    def _signal(self, signum: int, _frame: Any) -> None:
        self.stop_requested = True
        self._write_status(state="stopping", signal=signum)
        if self.current is not None and self.current.poll() is None:
            os.killpg(self.current.pid, signal.SIGTERM)

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

    def _snapshot(self, reason: str) -> None:
        if snapshot_database(self.args.state, self.args.retained_state, reason=reason):
            self._write_status(state="running", last_snapshot_reason=reason)

    def _progress_signature(self) -> tuple[tuple[str, int, int], ...]:
        result: list[tuple[str, int, int]] = []
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{self.args.state}{suffix}")
            if path.exists():
                stat_result = path.stat()
                result.append((suffix, stat_result.st_mtime_ns, stat_result.st_size))
        return tuple(result)

    def _step(self, subject: Subject) -> None:
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
        progress_signature = self._progress_signature()
        last_progress = started
        while self.current.poll() is None and not self.stop_requested:
            now = time.monotonic()
            if (
                subject.timeout_seconds is not None
                and now - started >= subject.timeout_seconds
            ):
                timed_out = True
                os.killpg(self.current.pid, signal.SIGTERM)
                try:
                    self.current.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(self.current.pid, signal.SIGKILL)
                break
            current_signature = self._progress_signature()
            if current_signature != progress_signature:
                progress_signature = current_signature
                last_progress = now
            elif now - last_progress >= subject.stall_seconds:
                stalled = True
                os.killpg(self.current.pid, signal.SIGTERM)
                try:
                    self.current.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(self.current.pid, signal.SIGKILL)
                break
            if now >= next_snapshot:
                self._snapshot(f"in-progress:{subject.kind}:{subject.subject_id}:{subject.phase}")
                next_snapshot = now + self.args.snapshot_interval_seconds
            time.sleep(min(self.args.poll_seconds, 2.0))
        if self.stop_requested and self.current.poll() is None:
            self.current.wait(timeout=30)
        return_code = self.current.wait()
        self.current = None
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
        if return_code != 0 or timed_out or stalled:
            time.sleep(self.args.error_backoff_seconds)

    def run(self) -> int:
        self._lock()
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)
        self._write_status(state="starting")
        while not self.stop_requested:
            try:
                subject = next_subject(
                    self.args.state,
                    self.args.control_file,
                    production_timeout_seconds=self.args.production_timeout_seconds,
                    stage_timeout_policy=self.args.stage_timeout_policy,
                )
            except Exception as error:
                self._snapshot("supervisor-configuration-failure")
                self._write_status(state="failed", error=str(error))
                return 2
            if subject is None:
                self._write_status(state="idle")
                time.sleep(self.args.poll_seconds)
                continue
            self._step(subject)
        self._snapshot("supervisor-shutdown")
        self._write_status(state="stopped")
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
        or args.snapshot_interval_seconds <= 0
        or args.production_timeout_seconds <= 0
    ):
        raise SystemExit("poll, snapshot, and production timeout values must be positive")
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    with args.log_file.open("a", encoding="utf-8", buffering=1) as log_handle:
        args.log_handle = log_handle
        return Supervisor(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
