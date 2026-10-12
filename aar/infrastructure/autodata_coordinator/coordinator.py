"""Reconcile one action exposed by AutoData's authoritative state machine.

This module does not map phases or choose transitions. It reads the native
action, owns its lease, asks a tool-free semantic worker for a bound proposal,
submits the validated result through the native action API, and re-reads native
state. AutoData alone decides what action exists and how the workspace advances.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol
from zoneinfo import ZoneInfo

from .semantic_worker import (
    ActionContext,
    AnalysisContext,
    AnalysisOutcome,
    MalformedSemanticOutcome,
    SemanticOutcome,
    SemanticWorker,
)

ACTION_SCHEMA = "autodata.action/v1"
STAGE_SCHEMA = "aar.autodata.bound-semantic-outcome/v1"
RECEIPT_SCHEMA = "aar.autodata.coordinator-receipt/v1"
_ACTION_ID = re.compile(r"^act_[0-9a-f]{24}$")
_WORKSPACE_ID = re.compile(r"^ws_[0-9a-f]{32}$")
_EXECUTION_ID = re.compile(r"^exe_[0-9a-f]{32}$")


class AutoDataCoordinatorError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class NativeAction:
    id: str
    kind: str
    status: str
    spec: Mapping[str, Any]
    result: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class NativeWorkspace:
    id: str
    status: str
    phase: str
    revision: int
    actions: tuple[NativeAction, ...]


@dataclass(frozen=True, slots=True)
class ActionLease:
    action_id: str
    token: str
    spec: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CoordinatorOutcome:
    workspace_id: str
    action_id: str
    receipt_path: Path
    worker_backend: str
    native_phase: str
    native_revision: int


class AutoDataControl(Protocol):
    def read_workspace(self, workspace_id: str) -> NativeWorkspace: ...

    def read_execution(self, execution_id: str) -> NativeWorkspace: ...

    def read_json_artifact(self, reference: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def begin_action(self, action_id: str) -> ActionLease: ...

    def lease_matches(self, action_id: str, token: str) -> bool: ...

    def validate_workspace(self, candidate: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def complete_action(
        self, action_id: str, *, lease_token: str, result: Mapping[str, Any]
    ) -> None: ...


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise MalformedSemanticOutcome("value is not canonical JSON") from error


def _deep_json(value: object) -> Any:
    return json.loads(_canonical(value))


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _pt_now() -> str:
    return datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(timespec="seconds")


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise AutoDataCoordinatorError(
            "durable_record_invalid", f"{label} is unavailable"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AutoDataCoordinatorError(
            "durable_record_invalid", f"{label} is invalid"
        ) from error
    if not isinstance(value, dict):
        raise AutoDataCoordinatorError(
            "durable_record_invalid", f"{label} is not an object"
        )
    return value


def _atomic_private_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(dict(value), sort_keys=True, indent=2).encode())
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_private_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class NativeAutoDataControl:
    """Exact native CLI adapter plus read-only lease/schema verification."""

    _VALIDATE_CODE = """
import json
import sys
from autodata.errors import AutoDataError
from autodata.models import load_workspace
try:
    value = load_workspace(sys.argv[1]).to_dict()
except (AutoDataError, OSError, UnicodeError, json.JSONDecodeError):
    raise SystemExit(2)
print(json.dumps(value, sort_keys=True, separators=(\",\", \":\")))
""".strip()

    def __init__(
        self,
        *,
        python: Path,
        wrapper: Path,
        state: Path,
        artifacts: Path,
        workspaces: Path,
        temporary_root: Path,
        timeout_seconds: float = 60,
    ):
        self.python = python
        self.wrapper = wrapper
        self.state = state
        self.artifacts = artifacts
        self.workspaces = workspaces
        self.temporary_root = temporary_root
        self.timeout_seconds = timeout_seconds
        self._schema_python: Path | None = None

    @classmethod
    def from_environment(cls, temporary_root: Path) -> NativeAutoDataControl:
        plugin = Path(os.environ["AAR_AUTODATA_PLUGIN_ROOT"]).resolve(strict=True)
        return cls(
            python=Path(os.environ["AAR_AUTODATA_WRAPPER_PYTHON"]).resolve(strict=True),
            wrapper=(plugin / "scripts" / "autodata.py").resolve(strict=True),
            state=Path(os.environ["AAR_AUTODATA_STATE"]).resolve(strict=True),
            artifacts=Path(os.environ["AAR_AUTODATA_ARTIFACTS"]).resolve(strict=True),
            workspaces=Path(os.environ["AAR_AUTODATA_WORKSPACES"]).resolve(strict=True),
            temporary_root=temporary_root,
        )

    def _run(self, *arguments: str) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                [
                    str(self.python),
                    str(self.wrapper),
                    "--state",
                    str(self.state),
                    "--artifacts",
                    str(self.artifacts),
                    "--workspaces",
                    str(self.workspaces),
                    *arguments,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise AutoDataCoordinatorError(
                "native_cli_timeout",
                "native AutoData control timed out",
                retryable=True,
            ) from error
        if completed.returncode != 0:
            raise AutoDataCoordinatorError(
                "native_cli_failed",
                f"native AutoData control failed with exit {completed.returncode}",
            )
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise AutoDataCoordinatorError(
                "native_cli_invalid_json", "native AutoData returned invalid JSON"
            ) from error
        if not isinstance(value, dict):
            raise AutoDataCoordinatorError(
                "native_cli_invalid_json", "native result is not an object"
            )
        return value

    @staticmethod
    def _mapping(raw: object) -> Mapping[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as error:
                raise AutoDataCoordinatorError(
                    "native_state_invalid", "native action payload is invalid"
                ) from error
            if isinstance(value, dict):
                return value
        raise AutoDataCoordinatorError(
            "native_state_invalid", "native action payload is invalid"
        )

    def _action_detail(self, action_id: str) -> tuple[object, object, object] | None:
        try:
            with sqlite3.connect(f"file:{self.state}?mode=ro", uri=True) as connection:
                return connection.execute(
                    "SELECT specJson,resultJson,leaseTokenHash FROM actions WHERE id=?",
                    (action_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise AutoDataCoordinatorError(
                "native_state_invalid", "native action detail is unreadable"
            ) from error

    def _read_subject(self, subject_id: str, *, payload_key: str) -> NativeWorkspace:
        payload = self._run("status", subject_id)
        workspace = payload.get(payload_key)
        actions = payload.get("actions")
        if not isinstance(workspace, dict) or not isinstance(actions, list):
            raise AutoDataCoordinatorError(
                "native_state_invalid", "native status is incomplete"
            )
        parsed: list[NativeAction] = []
        for raw in actions:
            if not isinstance(raw, dict):
                raise AutoDataCoordinatorError(
                    "native_state_invalid", "native action row is invalid"
                )
            action_id = str(raw.get("id") or "")
            spec_raw = raw.get("specJson", raw.get("spec"))
            result_raw = raw.get("resultJson", raw.get("result"))
            if spec_raw is None:
                detail = self._action_detail(action_id)
                if detail is None:
                    raise AutoDataCoordinatorError(
                        "native_state_invalid", "native action is missing"
                    )
                spec_raw, result_raw, _ = detail
            spec = self._mapping(spec_raw)
            parsed.append(
                NativeAction(
                    id=action_id or str(spec.get("id") or ""),
                    kind=str(raw.get("kind") or spec.get("kind") or ""),
                    status=str(raw.get("status") or ""),
                    spec=spec,
                    result=None if result_raw is None else self._mapping(result_raw),
                )
            )
        try:
            revision = int(workspace["revision"])
        except (KeyError, TypeError, ValueError) as error:
            raise AutoDataCoordinatorError(
                "native_state_invalid", "native revision is invalid"
            ) from error
        return NativeWorkspace(
            id=str(workspace.get("id") or ""),
            status=str(workspace.get("status") or ""),
            phase=str(workspace.get("phase") or ""),
            revision=revision,
            actions=tuple(parsed),
        )

    def read_workspace(self, workspace_id: str) -> NativeWorkspace:
        return self._read_subject(workspace_id, payload_key="workspace")

    def read_execution(self, execution_id: str) -> NativeWorkspace:
        payload = self._run("status", execution_id)
        if payload.get("execution_id") != execution_id:
            raise AutoDataCoordinatorError(
                "native_state_invalid", "native status returned another execution"
            )
        try:
            revision = int(payload["revision"])
        except (KeyError, TypeError, ValueError) as error:
            raise AutoDataCoordinatorError(
                "native_state_invalid", "native execution revision is invalid"
            ) from error
        try:
            with sqlite3.connect(f"file:{self.state}?mode=ro", uri=True) as connection:
                rows = connection.execute(
                    "SELECT id,kind,status,specJson,resultJson FROM actions "
                    "WHERE scopeKind='execution' AND scopeId=? "
                    "ORDER BY createdAt,id",
                    (execution_id,),
                ).fetchall()
        except sqlite3.Error as error:
            raise AutoDataCoordinatorError(
                "native_state_invalid", "native execution actions are unreadable"
            ) from error
        actions: list[NativeAction] = []
        for action_id, kind, status, spec_raw, result_raw in rows:
            actions.append(
                NativeAction(
                    id=str(action_id),
                    kind=str(kind),
                    status=str(status),
                    spec=self._mapping(spec_raw),
                    result=None if result_raw is None else self._mapping(result_raw),
                )
            )
        return NativeWorkspace(
            id=execution_id,
            status=str(payload.get("status") or ""),
            phase=str(payload.get("phase") or ""),
            revision=revision,
            actions=tuple(actions),
        )

    def read_json_artifact(self, reference: Mapping[str, Any]) -> Mapping[str, Any]:
        digest = reference.get("digest")
        size = reference.get("size")
        media_type = reference.get("media_type")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or size > 2 * 1024 * 1024
            or media_type != "application/json"
        ):
            raise AutoDataCoordinatorError(
                "native_artifact_invalid",
                "native analysis artifact reference is invalid",
            )
        hexadecimal = digest.removeprefix("sha256:")
        root = self.artifacts.resolve(strict=True)
        path = root / "objects" / "sha256" / hexadecimal[:2] / hexadecimal[2:]
        if path.is_symlink() or not path.is_file():
            raise AutoDataCoordinatorError(
                "native_artifact_missing", "native analysis artifact is unavailable"
            )
        payload = path.read_bytes()
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != hexadecimal:
            raise AutoDataCoordinatorError(
                "native_artifact_mismatch",
                "native analysis artifact failed integrity validation",
            )
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AutoDataCoordinatorError(
                "native_artifact_invalid", "native analysis artifact is not valid JSON"
            ) from error
        if not isinstance(value, dict):
            raise AutoDataCoordinatorError(
                "native_artifact_invalid", "native analysis artifact is not an object"
            )
        return value

    def begin_action(self, action_id: str) -> ActionLease:
        payload = self._run("action", "begin", action_id)
        token = payload.get("lease_token")
        spec = payload.get("action")
        if not isinstance(token, str) or len(token) < 20 or not isinstance(spec, dict):
            raise AutoDataCoordinatorError(
                "native_lease_invalid", "native begin returned an invalid lease"
            )
        return ActionLease(str(spec.get("id") or ""), token, spec)

    def lease_matches(self, action_id: str, token: str) -> bool:
        detail = self._action_detail(action_id)
        if detail is None or not isinstance(detail[2], str):
            return False
        return hashlib.sha256(token.encode()).hexdigest() == detail[2]

    def _plugin_python(self) -> Path:
        if self._schema_python is not None:
            return self._schema_python
        bootstrap = self.wrapper.parent / "bootstrap.py"
        try:
            completed = subprocess.run(
                [str(self.python), str(bootstrap)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise AutoDataCoordinatorError(
                "native_schema_timeout", "native plugin bootstrap timed out"
            ) from error
        if completed.returncode != 0:
            raise AutoDataCoordinatorError(
                "native_schema_failed", "native plugin bootstrap failed"
            )
        candidate = Path(completed.stdout.strip())
        if candidate.is_symlink() or not candidate.is_file():
            raise AutoDataCoordinatorError(
                "native_schema_failed", "native plugin Python is unavailable"
            )
        self._schema_python = candidate.resolve(strict=True)
        return self._schema_python

    def validate_workspace(self, candidate: Mapping[str, Any]) -> Mapping[str, Any]:
        self.temporary_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, raw = tempfile.mkstemp(suffix=".json", dir=self.temporary_root)
        path = Path(raw)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_canonical(candidate) + b"\n")
            completed = subprocess.run(
                [str(self._plugin_python()), "-c", self._VALIDATE_CODE, str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise AutoDataCoordinatorError(
                "native_schema_timeout", "native schema validation timed out"
            ) from error
        finally:
            path.unlink(missing_ok=True)
        if completed.returncode == 2:
            raise AutoDataCoordinatorError(
                "candidate_workspace_invalid", "candidate fails native schema"
            )
        if completed.returncode != 0:
            raise AutoDataCoordinatorError(
                "native_schema_failed", "native schema validator failed"
            )
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise AutoDataCoordinatorError(
                "native_schema_failed", "native schema validator returned invalid JSON"
            ) from error
        if not isinstance(value, dict):
            raise AutoDataCoordinatorError(
                "native_schema_failed", "native schema validator returned non-object"
            )
        return value

    def complete_action(
        self, action_id: str, *, lease_token: str, result: Mapping[str, Any]
    ) -> None:
        self.temporary_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, raw = tempfile.mkstemp(suffix=".json", dir=self.temporary_root)
        path = Path(raw)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_canonical(result) + b"\n")
            self._run(
                "action",
                "complete",
                action_id,
                f"--lease-token={lease_token}",
                "--result",
                str(path),
            )
        finally:
            path.unlink(missing_ok=True)


class AutoDataActionReconciler:
    """Reconcile native ``clarify_design``; later actions remain legacy-owned."""

    def __init__(
        self,
        *,
        control: AutoDataControl,
        worker: SemanticWorker,
        team_dir: Path,
        action_timeout_seconds: float = 1800,
        malformed_output_attempts: int = 3,
    ):
        if action_timeout_seconds <= 0 or malformed_output_attempts < 1:
            raise ValueError("coordinator bounds must be positive")
        self.control = control
        self.worker = worker
        self.team_dir = team_dir.resolve(strict=True)
        self.action_timeout_seconds = action_timeout_seconds
        self.malformed_output_attempts = malformed_output_attempts

    def _lease_path(self, action_id: str) -> Path:
        return self.team_dir / "autodata" / "action-leases" / f"{action_id}.token"

    def _stage_path(self, action_id: str) -> Path:
        return self.team_dir / "autodata" / "action-results" / f"{action_id}.json"

    def _receipt_path(self, action_id: str) -> Path:
        return self.team_dir / "autodata" / "action-receipts" / f"{action_id}.json"

    @staticmethod
    def _completed(snapshot: NativeWorkspace) -> NativeAction | None:
        matches = [
            action
            for action in snapshot.actions
            if action.kind == "clarify_design" and action.status == "completed"
        ]
        if len(matches) > 1:
            raise AutoDataCoordinatorError(
                "multiple_clarify_actions", "multiple completed clarify actions exist"
            )
        return matches[0] if matches else None

    @staticmethod
    def _live(snapshot: NativeWorkspace) -> NativeAction | None:
        live = [
            action
            for action in snapshot.actions
            if action.status in {"pending", "in_progress"}
        ]
        if len(live) > 1:
            raise AutoDataCoordinatorError(
                "multiple_pending_actions", "multiple native actions are live"
            )
        if live and live[0].kind != "clarify_design":
            raise AutoDataCoordinatorError(
                "unexpected_pending_action",
                "first coordinated action is not clarify_design",
            )
        return live[0] if live else None

    @staticmethod
    def _context(
        snapshot: NativeWorkspace,
        action: NativeAction,
        *,
        completed_input_digest: str | None = None,
    ) -> tuple[ActionContext, Path]:
        spec = action.spec
        scope = spec.get("scope")
        if (
            spec.get("schema") != ACTION_SCHEMA
            or spec.get("id") != action.id
            or spec.get("kind") != "clarify_design"
            or not isinstance(scope, dict)
            or scope.get("kind") != "workspace"
            or scope.get("id") != snapshot.id
            or not isinstance(scope.get("revision"), int)
            or (
                completed_input_digest is None
                and scope.get("revision") != snapshot.revision
            )
            or (
                completed_input_digest is not None
                and scope.get("revision") > snapshot.revision
            )
            or snapshot.status != "active"
            or spec.get("allowed_paths") != ["autodata.workspace.json"]
            or spec.get("outputs") != ["summary", "decisions"]
            or not isinstance(spec.get("instructions"), str)
            or not spec["instructions"].strip()
            or not isinstance(spec.get("editable_root"), str)
        ):
            raise AutoDataCoordinatorError(
                "clarify_action_contract_invalid",
                "native clarify contract is inconsistent",
            )
        root = Path(spec["editable_root"])
        if root.is_symlink() or not root.is_absolute():
            raise AutoDataCoordinatorError(
                "editable_root_invalid", "native editable root is unsafe"
            )
        root = root.resolve(strict=True)
        workspace_file = root / "autodata.workspace.json"
        workspace = _read_object(workspace_file, "workspace input")
        frozen = _deep_json(workspace)
        return (
            ActionContext(
                action_id=action.id,
                workspace_id=snapshot.id,
                input_revision=scope["revision"],
                input_digest=(
                    completed_input_digest
                    if completed_input_digest is not None
                    else _digest(frozen)
                ),
                instructions=spec["instructions"],
                allowed_paths=("autodata.workspace.json",),
                required_outputs=("summary", "decisions"),
                workspace=frozen,
            ),
            workspace_file,
        )

    def _write_lease(self, action_id: str, token: str) -> None:
        path = self._lease_path(action_id)
        if path.exists() or path.is_symlink():
            raise AutoDataCoordinatorError(
                "stale_action_lease", "pending action has a stale protected lease"
            )
        _atomic_private_text(path, token)

    def _read_matching_lease(self, action_id: str) -> str:
        path = self._lease_path(action_id)
        if path.is_symlink() or not path.is_file():
            raise AutoDataCoordinatorError(
                "action_lease_missing", "active action has no protected lease"
            )
        mode = path.stat()
        if mode.st_uid != os.geteuid() or stat.S_IMODE(mode.st_mode) != 0o600:
            raise AutoDataCoordinatorError(
                "action_lease_unprotected", "active action lease is not protected"
            )
        token = path.read_text(encoding="utf-8").strip()
        if len(token) < 20 or not self.control.lease_matches(action_id, token):
            raise AutoDataCoordinatorError(
                "action_lease_mismatch", "protected lease does not match native state"
            )
        return token

    def _validate_outcome(
        self, context: ActionContext, outcome: SemanticOutcome
    ) -> dict[str, Any]:
        if (
            outcome.action_id != context.action_id
            or outcome.input_revision != context.input_revision
            or outcome.input_digest != context.input_digest
            or not isinstance(outcome.summary, str)
            or not outcome.summary.strip()
        ):
            raise MalformedSemanticOutcome("semantic outcome binding is invalid")
        decisions = _deep_json(list(outcome.decisions))
        candidate: dict[str, Any] | None
        if outcome.decision == "confirm":
            if outcome.updated_workspace is not None:
                raise MalformedSemanticOutcome("confirm outcome includes a candidate")
            candidate = None
        elif outcome.decision == "update":
            if not isinstance(outcome.updated_workspace, Mapping):
                raise MalformedSemanticOutcome("update outcome has no full candidate")
            candidate = _deep_json(outcome.updated_workspace)
            try:
                normalized = self.control.validate_workspace(candidate)
            except AutoDataCoordinatorError as error:
                if error.code == "candidate_workspace_invalid":
                    raise MalformedSemanticOutcome(
                        "candidate fails native schema"
                    ) from error
                raise
            if _canonical(normalized) != _canonical(candidate):
                raise MalformedSemanticOutcome(
                    "candidate is not a full native workspace"
                )
            if candidate.get("approval_policy") != context.workspace.get(
                "approval_policy"
            ):
                raise MalformedSemanticOutcome(
                    "candidate changes protected approval policy"
                )
            if _digest(candidate) == context.input_digest:
                raise MalformedSemanticOutcome(
                    "update candidate does not change the workspace"
                )
        else:
            raise MalformedSemanticOutcome("semantic decision is unsupported")
        native_result = {"summary": outcome.summary.strip(), "decisions": decisions}
        return {
            "schema": STAGE_SCHEMA,
            "recorded_at_pt": _pt_now(),
            "action_id": context.action_id,
            "workspace_id": context.workspace_id,
            "input_revision": context.input_revision,
            "input_digest": context.input_digest,
            "worker_backend": self.worker.backend_name,
            "decision": outcome.decision,
            "updated_workspace": candidate,
            "candidate_digest": None if candidate is None else _digest(candidate),
            "native_result": native_result,
            "native_result_digest": _digest(native_result),
        }

    async def _produce_stage(self, context: ActionContext) -> dict[str, Any]:
        last_error: BaseException | None = None
        for _ in range(self.malformed_output_attempts):
            try:
                worker_context = replace(
                    context, workspace=_deep_json(context.workspace)
                )
                outcome = await asyncio.wait_for(
                    self.worker.perform(worker_context),
                    timeout=self.action_timeout_seconds,
                )
                return self._validate_outcome(context, outcome)
            except asyncio.TimeoutError as error:
                raise AutoDataCoordinatorError(
                    "semantic_worker_timeout",
                    "semantic worker timed out",
                    retryable=True,
                ) from error
            except MalformedSemanticOutcome as error:
                last_error = error
                continue
            except AutoDataCoordinatorError:
                raise
            except Exception as error:
                raise AutoDataCoordinatorError(
                    "semantic_worker_failed", "semantic worker failed"
                ) from error
        raise AutoDataCoordinatorError(
            "semantic_worker_output_invalid",
            "semantic worker exhausted malformed-output attempts",
        ) from last_error

    def _stage_context(self, stage: Mapping[str, Any], context: ActionContext) -> None:
        native_result = stage.get("native_result")
        if (
            stage.get("schema") != STAGE_SCHEMA
            or stage.get("action_id") != context.action_id
            or stage.get("workspace_id") != context.workspace_id
            or stage.get("input_revision") != context.input_revision
            or stage.get("input_digest") != context.input_digest
            or stage.get("decision") not in {"confirm", "update"}
            or not isinstance(stage.get("worker_backend"), str)
            or not stage["worker_backend"]
            or not isinstance(native_result, dict)
            or set(native_result) != {"summary", "decisions"}
            or not isinstance(native_result.get("summary"), str)
            or not native_result["summary"].strip()
            or not isinstance(native_result.get("decisions"), list)
            or stage.get("native_result_digest") != _digest(native_result)
        ):
            raise AutoDataCoordinatorError(
                "semantic_stage_mismatch", "staged outcome is not bound to this action"
            )
        candidate = stage.get("updated_workspace")
        candidate_digest = stage.get("candidate_digest")
        if stage.get("decision") == "confirm":
            if candidate is not None or candidate_digest is not None:
                raise AutoDataCoordinatorError(
                    "semantic_stage_invalid", "staged confirmation contains a candidate"
                )
            return
        if not isinstance(candidate, dict) or candidate_digest != _digest(candidate):
            raise AutoDataCoordinatorError(
                "semantic_stage_invalid", "staged update candidate digest is invalid"
            )
        try:
            normalized = self.control.validate_workspace(candidate)
        except AutoDataCoordinatorError as error:
            if error.code == "candidate_workspace_invalid":
                raise AutoDataCoordinatorError(
                    "semantic_stage_invalid",
                    "staged update fails native workspace schema",
                ) from error
            raise
        if _canonical(normalized) != _canonical(candidate):
            raise AutoDataCoordinatorError(
                "semantic_stage_invalid", "staged update is not a full native workspace"
            )
        if candidate.get("approval_policy") != context.workspace.get("approval_policy"):
            raise AutoDataCoordinatorError(
                "semantic_stage_invalid",
                "staged update changes protected approval policy",
            )
        if candidate_digest == context.input_digest:
            raise AutoDataCoordinatorError(
                "semantic_stage_invalid", "staged update does not change the workspace"
            )

    @staticmethod
    def _apply_stage(
        stage: Mapping[str, Any], context: ActionContext, workspace_file: Path
    ) -> str:
        current = _read_object(workspace_file, "workspace input")
        current_digest = _digest(current)
        candidate = stage.get("updated_workspace")
        if stage.get("decision") == "confirm":
            if candidate is not None or current_digest != context.input_digest:
                raise AutoDataCoordinatorError(
                    "workspace_changed_during_action",
                    "workspace changed during confirmation",
                )
            return current_digest
        if not isinstance(candidate, dict) or stage.get("candidate_digest") != _digest(
            candidate
        ):
            raise AutoDataCoordinatorError(
                "semantic_stage_invalid", "staged candidate is invalid"
            )
        candidate_digest = str(stage["candidate_digest"])
        if current_digest == candidate_digest:
            return candidate_digest
        if current_digest != context.input_digest:
            raise AutoDataCoordinatorError(
                "workspace_changed_during_action",
                "workspace changed outside coordinator",
            )
        _atomic_private_json(workspace_file, candidate)
        return candidate_digest

    def _finalize(
        self,
        snapshot: NativeWorkspace,
        action: NativeAction,
        context: ActionContext,
        stage: Mapping[str, Any],
    ) -> CoordinatorOutcome:
        if snapshot.revision < context.input_revision:
            raise AutoDataCoordinatorError(
                "native_revision_mismatch", "native revision precedes action input"
            )
        if not isinstance(action.result, Mapping) or _digest(
            action.result
        ) != stage.get("native_result_digest"):
            raise AutoDataCoordinatorError(
                "native_result_mismatch", "completed native result differs from stage"
            )
        if any(
            item.id == action.id and item.status in {"pending", "in_progress"}
            for item in snapshot.actions
        ):
            raise AutoDataCoordinatorError(
                "native_action_still_required",
                "native action remains live after completion",
            )
        workspace_file = (
            Path(str(action.spec["editable_root"])) / "autodata.workspace.json"
        )
        current_workspace = _read_object(workspace_file, "completed workspace")
        self.control.validate_workspace(current_workspace)
        actual_digest = _digest(current_workspace)
        clarify_digest = stage.get("candidate_digest") or context.input_digest
        if (
            snapshot.revision == context.input_revision
            and actual_digest != clarify_digest
        ):
            raise AutoDataCoordinatorError(
                "completed_workspace_mismatch",
                "completed workspace differs from outcome",
            )
        receipt_path = self._receipt_path(action.id)
        if receipt_path.exists() or receipt_path.is_symlink():
            raise AutoDataCoordinatorError(
                "clarify_receipt_conflict", "clarify receipt already exists"
            )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "recorded_at_pt": _pt_now(),
            "workspace_id": snapshot.id,
            "action_id": action.id,
            "action_kind": "clarify_design",
            "input_revision": context.input_revision,
            "input_digest": context.input_digest,
            "worker_backend": stage.get("worker_backend"),
            "decision": stage.get("decision"),
            "result_digest": stage.get("native_result_digest"),
            "clarify_workspace_digest": clarify_digest,
            "workspace_digest_observed": actual_digest,
            "native_status": action.status,
            "native_phase_observed": snapshot.phase,
            "native_revision_observed": snapshot.revision,
        }
        receipt["receipt_digest"] = _digest(receipt)
        _atomic_private_json(receipt_path, receipt)
        self._lease_path(action.id).unlink(missing_ok=True)
        return CoordinatorOutcome(
            workspace_id=snapshot.id,
            action_id=action.id,
            receipt_path=receipt_path,
            worker_backend=str(stage.get("worker_backend") or "unknown"),
            native_phase=snapshot.phase,
            native_revision=snapshot.revision,
        )

    def _existing_receipt(
        self,
        snapshot: NativeWorkspace,
        action: NativeAction,
        context: ActionContext,
        stage: Mapping[str, Any],
    ) -> CoordinatorOutcome | None:
        root = self.team_dir / "autodata" / "action-receipts"
        if not root.is_dir() or root.is_symlink():
            return None
        matches: list[tuple[Path, dict[str, Any]]] = []
        for path in root.glob("act_*.json"):
            value = _read_object(path, "coordinator receipt")
            if value.get("workspace_id") == snapshot.id:
                matches.append((path, value))
        if len(matches) > 1:
            raise AutoDataCoordinatorError(
                "multiple_clarify_receipts", "workspace has multiple clarify receipts"
            )
        if not matches:
            return None
        path, value = matches[0]
        current_workspace = _read_object(
            Path(str(action.spec["editable_root"])) / "autodata.workspace.json",
            "current workspace",
        )
        current_digest = _digest(current_workspace)
        receipt_digest = value.get("receipt_digest")
        digest_payload = dict(value)
        digest_payload.pop("receipt_digest", None)
        path_stat = path.stat()
        clarify_digest = stage.get("candidate_digest") or context.input_digest
        if (
            value.get("schema") != RECEIPT_SCHEMA
            or value.get("workspace_id") != snapshot.id
            or value.get("action_id") != action.id
            or value.get("action_kind") != "clarify_design"
            or value.get("native_status") != "completed"
            or value.get("input_revision") != context.input_revision
            or value.get("input_digest") != context.input_digest
            or value.get("result_digest") != stage.get("native_result_digest")
            or not isinstance(action.result, Mapping)
            or _digest(action.result) != stage.get("native_result_digest")
            or value.get("clarify_workspace_digest") != clarify_digest
            or value.get("worker_backend") != stage.get("worker_backend")
            or value.get("decision") != stage.get("decision")
            or not isinstance(value.get("workspace_digest_observed"), str)
            or not isinstance(value.get("native_phase_observed"), str)
            or not value["native_phase_observed"]
            or not isinstance(value.get("native_revision_observed"), int)
            or value["native_revision_observed"] < context.input_revision
            or snapshot.revision < value["native_revision_observed"]
            or not isinstance(receipt_digest, str)
            or receipt_digest != _digest(digest_payload)
            or path_stat.st_uid != os.geteuid()
            or stat.S_IMODE(path_stat.st_mode) != 0o600
        ):
            raise AutoDataCoordinatorError(
                "clarify_receipt_invalid", "clarify receipt does not match native state"
            )
        if (
            snapshot.revision == context.input_revision
            and current_digest != clarify_digest
        ):
            raise AutoDataCoordinatorError(
                "completed_workspace_mismatch",
                "workspace differs from clarify output at the same revision",
            )
        return CoordinatorOutcome(
            workspace_id=snapshot.id,
            action_id=action.id,
            receipt_path=path,
            worker_backend=str(value.get("worker_backend") or "unknown"),
            native_phase=str(value["native_phase_observed"]),
            native_revision=int(value["native_revision_observed"]),
        )

    def _completed_material(
        self, snapshot: NativeWorkspace, action: NativeAction
    ) -> tuple[ActionContext, dict[str, Any]]:
        stage_path = self._stage_path(action.id)
        if not stage_path.is_file():
            raise AutoDataCoordinatorError(
                "semantic_stage_missing", "completed action has no bound stage"
            )
        stage = _read_object(stage_path, "bound semantic outcome")
        input_digest = stage.get("input_digest")
        if not isinstance(input_digest, str):
            raise AutoDataCoordinatorError(
                "semantic_stage_mismatch", "bound stage has no input digest"
            )
        context, _ = self._context(
            snapshot, action, completed_input_digest=input_digest
        )
        self._stage_context(stage, context)
        return context, stage

    async def reconcile_registered_clarify(
        self, control_file: Path
    ) -> CoordinatorOutcome | None:
        control = _read_object(control_file, "lifecycle control")
        subjects = control.get("subjects")
        if not isinstance(subjects, list):
            raise AutoDataCoordinatorError(
                "lifecycle_control_invalid", "control has no subjects"
            )
        candidates: list[str] = []
        for entry in subjects:
            if (
                not isinstance(entry, dict)
                or entry.get("kind") != "workspace"
                or entry.get("status") != "registered"
            ):
                continue
            workspace_id = entry.get("subject_id")
            if not isinstance(workspace_id, str):
                raise AutoDataCoordinatorError(
                    "lifecycle_control_invalid", "workspace registration is invalid"
                )
            snapshot = self.control.read_workspace(workspace_id)
            completed = self._completed(snapshot)
            live = [
                item
                for item in snapshot.actions
                if item.status in {"pending", "in_progress"}
            ]
            if len(live) > 1:
                raise AutoDataCoordinatorError(
                    "multiple_pending_actions", "multiple native actions are live"
                )
            if completed is not None:
                context, stage = self._completed_material(snapshot, completed)
                if self._existing_receipt(snapshot, completed, context, stage) is None:
                    candidates.append(workspace_id)
                continue
            if live:
                if live[0].kind == "clarify_design":
                    candidates.append(workspace_id)
                else:
                    raise AutoDataCoordinatorError(
                        "unexpected_pending_action",
                        "first coordinated action is not clarify_design",
                    )
        if not candidates:
            return None
        if len(candidates) != 1:
            raise AutoDataCoordinatorError(
                "multiple_pending_actions", "multiple workspaces need clarification"
            )
        return await self.coordinate_clarify_design(candidates[0])

    async def coordinate_clarify_design(self, workspace_id: str) -> CoordinatorOutcome:
        if not _WORKSPACE_ID.fullmatch(workspace_id):
            raise AutoDataCoordinatorError(
                "workspace_identity_invalid", "workspace ID is invalid"
            )
        snapshot = self.control.read_workspace(workspace_id)
        if snapshot.id != workspace_id:
            raise AutoDataCoordinatorError(
                "workspace_identity_mismatch",
                "native status returned another workspace",
            )
        completed = self._completed(snapshot)
        action = completed or self._live(snapshot)
        if action is None:
            raise AutoDataCoordinatorError(
                "clarify_action_missing", "native clarify action is not exposed"
            )
        if not _ACTION_ID.fullmatch(action.id):
            raise AutoDataCoordinatorError(
                "clarify_action_identity_mismatch", "native action ID is invalid"
            )
        stage_path = self._stage_path(action.id)
        if completed is not None:
            context, stage = self._completed_material(snapshot, action)
            receipt = self._existing_receipt(snapshot, action, context, stage)
            if receipt is not None:
                return receipt
            return self._finalize(snapshot, action, context, stage)

        context, workspace_file = self._context(snapshot, action)

        if action.status == "pending":
            if self._lease_path(action.id).exists():
                raise AutoDataCoordinatorError(
                    "stale_action_lease", "pending action has a stale protected lease"
                )
            lease = self.control.begin_action(action.id)
            if lease.action_id != action.id or _canonical(lease.spec) != _canonical(
                action.spec
            ):
                raise AutoDataCoordinatorError(
                    "action_lease_mismatch", "native begin returned another action"
                )
            self._write_lease(action.id, lease.token)
            snapshot = self.control.read_workspace(workspace_id)
            active = [item for item in snapshot.actions if item.id == action.id]
            if len(active) != 1 or active[0].status != "in_progress":
                raise AutoDataCoordinatorError(
                    "action_lease_not_durable", "native action did not become active"
                )
            action = active[0]
        try:
            token = self._read_matching_lease(action.id)
        except AutoDataCoordinatorError:
            recovered = self.control.read_workspace(workspace_id)
            recovered_action = self._completed(recovered)
            if (
                recovered_action is not None
                and recovered_action.id == action.id
                and stage_path.is_file()
            ):
                stage = _read_object(stage_path, "bound semantic outcome")
                self._stage_context(stage, context)
                return self._finalize(recovered, recovered_action, context, stage)
            raise

        if stage_path.is_file():
            stage = _read_object(stage_path, "bound semantic outcome")
            self._stage_context(stage, context)
        else:
            stage = await self._produce_stage(context)
            _atomic_private_json(stage_path, stage)
        self._apply_stage(stage, context, workspace_file)
        native_result = stage["native_result"]
        try:
            self.control.complete_action(
                action.id, lease_token=token, result=native_result
            )
        except Exception as error:
            current = self.control.read_workspace(workspace_id)
            done = self._completed(current)
            if done is not None and done.id == action.id:
                return self._finalize(current, done, context, stage)
            if isinstance(error, AutoDataCoordinatorError):
                raise
            raise AutoDataCoordinatorError(
                "action_completion_failed", "native completion failed"
            ) from error
        current = self.control.read_workspace(workspace_id)
        done = self._completed(current)
        if done is None or done.id != action.id:
            raise AutoDataCoordinatorError(
                "action_completion_unconfirmed", "native completion is not durable"
            )
        return self._finalize(current, done, context, stage)


class ExecutionAnalysisReconciler(AutoDataActionReconciler):
    """Reconcile only native ``analyze_results`` execution actions."""

    @staticmethod
    def _analysis_context(
        snapshot: NativeWorkspace,
        action: NativeAction,
    ) -> AnalysisContext:
        spec = action.spec
        scope = spec.get("scope")
        artifacts = spec.get("artifacts")
        if (
            spec.get("schema") != ACTION_SCHEMA
            or spec.get("id") != action.id
            or spec.get("kind") != "analyze_results"
            or not isinstance(scope, dict)
            or scope.get("kind") != "execution"
            or scope.get("id") != snapshot.id
            or not isinstance(scope.get("revision"), int)
            or scope.get("revision") > snapshot.revision
            or snapshot.status != "active"
            or spec.get("editable_root") is not None
            or spec.get("allowed_paths") != []
            or spec.get("outputs") != ["proposal", "dashboard_summary"]
            or not isinstance(spec.get("instructions"), str)
            or not spec["instructions"].strip()
            or not isinstance(artifacts, list)
            or not artifacts
            or any(not isinstance(reference, dict) for reference in artifacts)
        ):
            raise AutoDataCoordinatorError(
                "analysis_action_contract_invalid",
                "native analyze_results contract is inconsistent",
            )
        return AnalysisContext(
            action_id=action.id,
            execution_id=snapshot.id,
            input_revision=int(scope["revision"]),
            input_digest="",
            instructions=str(spec["instructions"]),
            required_outputs=("proposal", "dashboard_summary"),
            evidence=(),
        )

    def _materialize_analysis_context(
        self,
        snapshot: NativeWorkspace,
        action: NativeAction,
    ) -> AnalysisContext:
        context = self._analysis_context(snapshot, action)
        evidence = tuple(
            _deep_json(self.control.read_json_artifact(reference))
            for reference in action.spec["artifacts"]
        )
        digest = _digest(
            {
                "action": _deep_json(action.spec),
                "evidence": evidence,
            }
        )
        return replace(context, input_digest=digest, evidence=evidence)

    def _validate_analysis_outcome(
        self,
        context: AnalysisContext,
        outcome: object,
    ) -> dict[str, Any]:
        if not isinstance(outcome, AnalysisOutcome):
            raise MalformedSemanticOutcome(
                "semantic worker returned the wrong outcome type"
            )
        dashboard = _deep_json(outcome.dashboard_summary)
        if (
            outcome.action_id != context.action_id
            or outcome.input_revision != context.input_revision
            or outcome.input_digest != context.input_digest
            or not isinstance(outcome.proposal, str)
            or not outcome.proposal.strip()
            or not isinstance(dashboard, dict)
            or set(dashboard) != {"headline", "summary", "next_step"}
            or any(
                not isinstance(value, str) or not value.strip()
                for value in dashboard.values()
            )
        ):
            raise MalformedSemanticOutcome("analysis outcome binding is invalid")
        native_result = {
            "proposal": outcome.proposal.strip(),
            "dashboard_summary": dashboard,
        }
        return {
            "schema": STAGE_SCHEMA,
            "recorded_at_pt": _pt_now(),
            "action_id": context.action_id,
            "action_kind": "analyze_results",
            "execution_id": context.execution_id,
            "input_revision": context.input_revision,
            "input_digest": context.input_digest,
            "worker_backend": self.worker.backend_name,
            "native_result": native_result,
            "native_result_digest": _digest(native_result),
        }

    async def _produce_analysis_stage(self, context: AnalysisContext) -> dict[str, Any]:
        last_error: BaseException | None = None
        for _ in range(self.malformed_output_attempts):
            try:
                worker_context = replace(
                    context,
                    evidence=tuple(_deep_json(item) for item in context.evidence),
                )
                outcome = await asyncio.wait_for(
                    self.worker.perform(worker_context),
                    timeout=self.action_timeout_seconds,
                )
                return self._validate_analysis_outcome(context, outcome)
            except asyncio.TimeoutError as error:
                raise AutoDataCoordinatorError(
                    "semantic_worker_timeout",
                    "semantic worker timed out",
                    retryable=True,
                ) from error
            except MalformedSemanticOutcome as error:
                last_error = error
                continue
            except AutoDataCoordinatorError:
                raise
            except Exception as error:
                raise AutoDataCoordinatorError(
                    "semantic_worker_failed", "semantic worker failed"
                ) from error
        raise AutoDataCoordinatorError(
            "semantic_worker_output_invalid",
            "semantic worker exhausted malformed-output attempts",
        ) from last_error

    @staticmethod
    def _validate_analysis_stage(
        stage: Mapping[str, Any], context: AnalysisContext
    ) -> None:
        native_result = stage.get("native_result")
        dashboard = (
            native_result.get("dashboard_summary")
            if isinstance(native_result, dict)
            else None
        )
        if (
            stage.get("schema") != STAGE_SCHEMA
            or stage.get("action_id") != context.action_id
            or stage.get("action_kind") != "analyze_results"
            or stage.get("execution_id") != context.execution_id
            or stage.get("input_revision") != context.input_revision
            or stage.get("input_digest") != context.input_digest
            or not isinstance(stage.get("worker_backend"), str)
            or not stage["worker_backend"]
            or not isinstance(native_result, dict)
            or set(native_result) != {"proposal", "dashboard_summary"}
            or not isinstance(native_result.get("proposal"), str)
            or not native_result["proposal"].strip()
            or not isinstance(dashboard, dict)
            or set(dashboard) != {"headline", "summary", "next_step"}
            or any(
                not isinstance(value, str) or not value.strip()
                for value in dashboard.values()
            )
            or stage.get("native_result_digest") != _digest(native_result)
        ):
            raise AutoDataCoordinatorError(
                "semantic_stage_mismatch",
                "staged analysis is not bound to this action",
            )

    def _analysis_receipt(
        self,
        snapshot: NativeWorkspace,
        action: NativeAction,
        context: AnalysisContext,
        stage: Mapping[str, Any],
    ) -> CoordinatorOutcome:
        if snapshot.revision < context.input_revision:
            raise AutoDataCoordinatorError(
                "native_revision_mismatch", "native revision precedes action input"
            )
        if not isinstance(action.result, Mapping) or _digest(
            action.result
        ) != stage.get("native_result_digest"):
            raise AutoDataCoordinatorError(
                "native_result_mismatch", "completed native result differs from stage"
            )
        receipt_path = self._receipt_path(action.id)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "recorded_at_pt": _pt_now(),
            "subject_kind": "execution",
            "execution_id": snapshot.id,
            "action_id": action.id,
            "action_kind": "analyze_results",
            "input_revision": context.input_revision,
            "input_digest": context.input_digest,
            "worker_backend": stage.get("worker_backend"),
            "result_digest": stage.get("native_result_digest"),
            "native_status": action.status,
            "native_phase_observed": snapshot.phase,
            "native_revision_observed": snapshot.revision,
        }
        receipt["receipt_digest"] = _digest(receipt)
        if receipt_path.exists() or receipt_path.is_symlink():
            existing = _read_object(receipt_path, "analysis coordinator receipt")
            existing_digest = existing.get("receipt_digest")
            existing_payload = dict(existing)
            existing_payload.pop("receipt_digest", None)
            mode = receipt_path.stat()
            if (
                existing.get("schema") != RECEIPT_SCHEMA
                or existing.get("subject_kind") != "execution"
                or existing.get("execution_id") != snapshot.id
                or existing.get("action_id") != action.id
                or existing.get("action_kind") != "analyze_results"
                or existing.get("input_revision") != context.input_revision
                or existing.get("input_digest") != context.input_digest
                or existing.get("worker_backend") != stage.get("worker_backend")
                or existing.get("result_digest") != stage.get("native_result_digest")
                or existing.get("native_status") != "completed"
                or not isinstance(existing.get("native_phase_observed"), str)
                or not existing["native_phase_observed"]
                or not isinstance(existing.get("native_revision_observed"), int)
                or existing["native_revision_observed"] < context.input_revision
                or snapshot.revision < existing["native_revision_observed"]
                or not isinstance(existing_digest, str)
                or existing_digest != _digest(existing_payload)
                or mode.st_uid != os.geteuid()
                or stat.S_IMODE(mode.st_mode) != 0o600
            ):
                raise AutoDataCoordinatorError(
                    "analysis_receipt_invalid",
                    "analysis receipt does not match native state",
                )
        else:
            _atomic_private_json(receipt_path, receipt)
        self._lease_path(action.id).unlink(missing_ok=True)
        return CoordinatorOutcome(
            workspace_id=snapshot.id,
            action_id=action.id,
            receipt_path=receipt_path,
            worker_backend=str(stage.get("worker_backend") or "unknown"),
            native_phase=snapshot.phase,
            native_revision=snapshot.revision,
        )

    async def reconcile_registered_analysis(
        self, control_file: Path
    ) -> CoordinatorOutcome | None:
        control = _read_object(control_file, "lifecycle control")
        subjects = control.get("subjects")
        if not isinstance(subjects, list):
            raise AutoDataCoordinatorError(
                "lifecycle_control_invalid", "control has no subjects"
            )
        candidates: list[tuple[str, str]] = []
        for entry in subjects:
            if (
                not isinstance(entry, dict)
                or entry.get("kind") != "execution"
                or entry.get("status") != "registered"
            ):
                continue
            execution_id = entry.get("subject_id")
            if not isinstance(execution_id, str):
                raise AutoDataCoordinatorError(
                    "lifecycle_control_invalid",
                    "execution registration is invalid",
                )
            snapshot = self.control.read_execution(execution_id)
            live = [
                action
                for action in snapshot.actions
                if action.status in {"pending", "in_progress"}
            ]
            if len(live) > 1:
                raise AutoDataCoordinatorError(
                    "multiple_pending_actions", "multiple native actions are live"
                )
            if live and live[0].kind == "analyze_results":
                candidates.append((execution_id, live[0].id))
                continue
            for action in snapshot.actions:
                if (
                    action.kind == "analyze_results"
                    and action.status == "completed"
                    and self._stage_path(action.id).is_file()
                    and not self._receipt_path(action.id).is_file()
                ):
                    candidates.append((execution_id, action.id))
        if not candidates:
            return None
        if len(candidates) != 1:
            raise AutoDataCoordinatorError(
                "multiple_pending_actions",
                "multiple executions need semantic analysis",
            )
        return await self.coordinate_analysis(*candidates[0])

    async def coordinate_analysis(
        self, execution_id: str, action_id: str
    ) -> CoordinatorOutcome:
        if not _EXECUTION_ID.fullmatch(execution_id):
            raise AutoDataCoordinatorError(
                "execution_identity_invalid", "execution ID is invalid"
            )
        if not _ACTION_ID.fullmatch(action_id):
            raise AutoDataCoordinatorError(
                "analysis_action_identity_mismatch", "action ID is invalid"
            )
        snapshot = self.control.read_execution(execution_id)
        if snapshot.id != execution_id:
            raise AutoDataCoordinatorError(
                "execution_identity_mismatch",
                "native status returned another execution",
            )
        matches = [action for action in snapshot.actions if action.id == action_id]
        if len(matches) != 1 or matches[0].kind != "analyze_results":
            raise AutoDataCoordinatorError(
                "analysis_action_missing",
                "native analyze_results action is unavailable",
            )
        action = matches[0]
        if action.status not in {"pending", "in_progress", "completed"}:
            raise AutoDataCoordinatorError(
                "analysis_action_terminal",
                "native analyze_results action is not resumable",
            )
        context = self._materialize_analysis_context(snapshot, action)
        stage_path = self._stage_path(action.id)
        if action.status == "completed":
            if not stage_path.is_file():
                raise AutoDataCoordinatorError(
                    "semantic_stage_missing", "completed action has no bound stage"
                )
            stage = _read_object(stage_path, "bound analysis outcome")
            self._validate_analysis_stage(stage, context)
            return self._analysis_receipt(snapshot, action, context, stage)

        if action.status == "pending":
            if self._lease_path(action.id).exists():
                raise AutoDataCoordinatorError(
                    "stale_action_lease", "pending action has a stale protected lease"
                )
            lease = self.control.begin_action(action.id)
            if lease.action_id != action.id or _canonical(lease.spec) != _canonical(
                action.spec
            ):
                raise AutoDataCoordinatorError(
                    "action_lease_mismatch", "native begin returned another action"
                )
            self._write_lease(action.id, lease.token)
            snapshot = self.control.read_execution(execution_id)
            active = [item for item in snapshot.actions if item.id == action.id]
            if len(active) != 1 or active[0].status != "in_progress":
                raise AutoDataCoordinatorError(
                    "action_lease_not_durable", "native action did not become active"
                )
            action = active[0]
        token = self._read_matching_lease(action.id)
        if stage_path.is_file():
            stage = _read_object(stage_path, "bound analysis outcome")
            self._validate_analysis_stage(stage, context)
        else:
            stage = await self._produce_analysis_stage(context)
            _atomic_private_json(stage_path, stage)
        try:
            self.control.complete_action(
                action.id,
                lease_token=token,
                result=stage["native_result"],
            )
        except Exception as error:
            current = self.control.read_execution(execution_id)
            completed = [item for item in current.actions if item.id == action.id]
            if len(completed) == 1 and completed[0].status == "completed":
                return self._analysis_receipt(current, completed[0], context, stage)
            if isinstance(error, AutoDataCoordinatorError):
                raise
            raise AutoDataCoordinatorError(
                "action_completion_failed", "native completion failed"
            ) from error
        current = self.control.read_execution(execution_id)
        completed = [item for item in current.actions if item.id == action.id]
        if len(completed) != 1 or completed[0].status != "completed":
            raise AutoDataCoordinatorError(
                "action_completion_unconfirmed", "native completion is not durable"
            )
        return self._analysis_receipt(current, completed[0], context, stage)
