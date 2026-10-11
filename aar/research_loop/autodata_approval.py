"""Trusted bridge for one delegated native AutoData approval action.

This module deliberately does not reproduce the AutoData lifecycle. It reads
one pending native approval action, reviews its content-addressed evidence,
signs the exact decision outside the researcher sandbox, and completes that
same native action through the original plugin CLI.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import sqlite3
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from aar.failure_feedback import FailureFeedbackError, build_failure_feedback

from .monitor import check_autodata_action

APPROVAL_SCHEMA = "autodata.delegated-approval/v1"
APPROVAL_ALGORITHM = "rsa-pkcs1v15-sha256"
AUDIT_SCHEMA = "aar.autodata.approval-audit/v1"
BINDINGS_SCHEMA = "aar.autodata.proposal-bindings/v1"
INCUMBENTS_SCHEMA = "aar.autodata.baseline-axis-incumbents/v1"
_ACTION_ID = re.compile(r"^act_[0-9a-f]{24}$")
_APPROVAL_KINDS = {"approve_grounding", "approve_baseline", "approve_resources"}
_WORKSPACE_ID = re.compile(r"^ws_[0-9a-f]{32}$")


def _native_cli_failure(
    termination: str,
    *,
    error_code: str = "autodata_approval_cli_failed",
    public_summary: str = "native AutoData CLI failed",
) -> FailureFeedbackError:
    feedback = build_failure_feedback(
        RuntimeError("native AutoData CLI failed"),
        error_code=error_code,
        stage="autodata_approval",
        public_summary=f"{public_summary} ({termination})",
    )
    return FailureFeedbackError(feedback)


def _atomic_private_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (json.dumps(dict(value), sort_keys=True, indent=2) + "\n").encode()
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(raw_temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _required_path(name: str, *, directory: bool = False) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        raise RuntimeError(f"{name} is required")
    path = Path(raw).expanduser().resolve(strict=True)
    if path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise RuntimeError(f"{name} is not a safe {'directory' if directory else 'file'}")
    return path


def _action_row(state: Path, action_id: str) -> dict[str, Any]:
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id,status,specJson FROM actions WHERE id=?", (action_id,)
        ).fetchone()
    if row is None:
        raise RuntimeError("native AutoData action was not found")
    return dict(row)


def _workspace_status(state: Path, workspace_id: str) -> str:
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT status FROM workspaces WHERE id=?", (workspace_id,)
        ).fetchone()
    if row is None:
        raise RuntimeError("proposal-bound native workspace was not found")
    return str(row[0])


def _current_proposal() -> dict[str, Any]:
    # Imported lazily to avoid a module cycle: server_api_tools imports this
    # module only when the delegated MCP operation is invoked.
    from .tools.server_api_tools import _proposal_approved, _proposal_marker_path

    approved, reason = _proposal_approved()
    if not approved:
        raise RuntimeError(
            "AutoData grounding requires submit_idea_proposal approval first: "
            + reason
        )
    marker = json.loads(_proposal_marker_path().read_text())
    code_hash = marker.get("code_hash")
    run_id = marker.get("run_id")
    idea_name = marker.get("idea_name")
    idea_uid = marker.get("idea_uid")
    proposal_ts = marker.get("ts")
    if (
        not isinstance(code_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", code_hash)
        or not isinstance(run_id, str)
        or not run_id
        or not isinstance(idea_name, str)
        or not idea_name
        or not isinstance(idea_uid, str)
        or idea_uid != os.getenv("IDEA_UID")
        or not isinstance(proposal_ts, (int, float))
    ):
        raise RuntimeError("approved proposal lacks a complete AutoData binding")
    key_payload = {
        "code_hash": code_hash,
        "idea_name": idea_name,
        "idea_uid": idea_uid,
        "run_id": run_id,
        "ts": proposal_ts,
    }
    key = "sha256:" + hashlib.sha256(
        json.dumps(key_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {"proposal_key": key, **key_payload}


def _proposal_binding(
    state: Path, package: Mapping[str, Any]
) -> dict[str, Any]:
    workspace_id = str(package["scope"].get("id") or "")
    if not _WORKSPACE_ID.fullmatch(workspace_id):
        raise RuntimeError("approval action has an invalid workspace id")
    proposal = _current_proposal()
    registry_path = _required_path("AAR_AUTODATA_PROPOSAL_BINDINGS")
    registry_info = registry_path.stat()
    if (
        registry_info.st_uid != os.geteuid()
        or registry_info.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
    ):
        raise RuntimeError("proposal binding registry must be owner-only mode 0600")
    lock_path = registry_path.with_suffix(registry_path.suffix + ".lock")
    lock_fd = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(lock_fd, "r+", encoding="utf-8") as registry_lock:
        fcntl.flock(registry_lock.fileno(), fcntl.LOCK_EX)
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            if (
                not isinstance(registry, dict)
                or registry.get("schema") != BINDINGS_SCHEMA
                or not isinstance(registry.get("proposals"), dict)
                or not isinstance(registry.get("workspaces"), dict)
            ):
                raise RuntimeError("proposal binding registry is invalid")
            proposals = registry["proposals"]
            workspaces = registry["workspaces"]
            existing = workspaces.get(workspace_id)
            if existing is not None and (
                not isinstance(existing, dict)
                or existing.get("proposal_key") != proposal["proposal_key"]
            ):
                raise RuntimeError("workspace is bound to a different AAR proposal")
            previous_workspace = proposals.get(proposal["proposal_key"])
            if previous_workspace not in {None, workspace_id}:
                if not isinstance(previous_workspace, str) or not _WORKSPACE_ID.fullmatch(
                    previous_workspace
                ):
                    raise RuntimeError("proposal binding registry contains an invalid workspace")
                if _workspace_status(state, previous_workspace) not in {
                    "cancelled",
                    "failed",
                }:
                    raise RuntimeError(
                        "approved proposal is already bound to a live or completed workspace"
                    )
            if package["action_kind"] == "approve_grounding":
                proposals[proposal["proposal_key"]] = workspace_id
                workspaces[workspace_id] = proposal
                _atomic_private_json(registry_path, registry)
            elif existing is None:
                raise RuntimeError(
                    "workspace has no proposal-bound grounding approval"
                )
            return dict(workspaces.get(workspace_id) or proposal)
        finally:
            fcntl.flock(registry_lock.fileno(), fcntl.LOCK_UN)


def _artifact_bytes(root: Path, raw: Mapping[str, Any]) -> bytes:
    digest = str(raw.get("digest") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("native review artifact has an invalid digest")
    hex_digest = digest.removeprefix("sha256:")
    path = root / "objects" / "sha256" / hex_digest[:2] / hex_digest[2:]
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("native review artifact is missing or unsafe")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != hex_digest:
        raise RuntimeError("native review artifact digest mismatch")
    if raw.get("size") != len(data):
        raise RuntimeError("native review artifact size mismatch")
    return data


def _review_package(
    action: Mapping[str, Any], artifact_root: Path
) -> dict[str, Any]:
    if action.get("schema") != "autodata.action/v1":
        raise RuntimeError("native action schema is invalid")
    kind = str(action.get("kind") or "")
    if kind not in _APPROVAL_KINDS:
        raise RuntimeError("action is not a delegated approval gate")
    scope = action.get("scope")
    if not isinstance(scope, dict) or scope.get("kind") != "workspace":
        raise RuntimeError("approval action is not workspace-scoped")
    artifacts = action.get("artifacts")
    if not isinstance(artifacts, list):
        raise RuntimeError("approval action artifacts are invalid")
    evidence: list[dict[str, Any]] = []
    for raw in artifacts:
        if not isinstance(raw, dict):
            raise RuntimeError("approval artifact reference is invalid")
        data = _artifact_bytes(artifact_root, raw)
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("approval artifact is not JSON") from error
        evidence.append(
            {
                "digest": raw["digest"],
                "name": raw.get("name"),
                "content": value,
            }
        )
    if kind != "approve_resources" and not evidence:
        raise RuntimeError("approval gate has no native review evidence")
    package = {
        "schema": "aar.autodata.native-review/v1",
        "action_id": action["id"],
        "action_kind": kind,
        "scope": scope,
        "artifact_digests": [item["digest"] for item in artifacts],
        "evidence": evidence,
    }
    _deterministic_checks(package)
    return package


def _incumbent_path(workspace_id: str) -> Path:
    if not _WORKSPACE_ID.fullmatch(workspace_id):
        raise RuntimeError("baseline incumbent scope has an invalid workspace id")
    root = Path(os.getenv("AAR_AUTODATA_APPROVAL_AUDIT_DIR", "")).expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("AAR_AUTODATA_APPROVAL_AUDIT_DIR is required")
    root_info = root.stat()
    if root_info.st_uid != os.geteuid() or root_info.st_mode & (
        stat.S_IRWXG | stat.S_IRWXO
    ):
        raise RuntimeError("approval audit directory must be owner-only")
    return root / f"{workspace_id}-baseline-axis-incumbents.json"


def _incumbent_candidate(sample: Mapping[str, Any]) -> dict[str, Any] | None:
    items = sample.get("generated_items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    item = items[0]
    metadata = item.get("metadata")
    metrics = sample.get("metrics")
    if not isinstance(metadata, dict) or not isinstance(metrics, dict):
        return None
    axis = metadata.get("axis")
    strategy_digest = metadata.get("axis_strategy_sha256")
    if (
        axis not in {"honesty", "sycophancy_resistance", "uncertainty_disclosure"}
        or not isinstance(strategy_digest, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", strategy_digest)
    ):
        return None
    usage = sample.get("provider_usage")
    assert isinstance(usage, list)  # validated by _deterministic_checks
    roles = {
        role: [
            entry
            for entry in usage
            if isinstance(entry, dict) and entry.get("role") == role
        ]
        for role in ("generator", "target", "judge")
    }
    rubric_version = metadata.get("judge_rubric_version")
    rubric_sha256 = metadata.get("judge_rubric_sha256")
    compatibility = {
        "task_id": sample["task_id"],
        "axis": axis,
        "axis_strategy_sha256": strategy_digest,
        "generator": sorted(
            {
                (str(entry["model"]), str(entry["deployment_id"]))
                for entry in roles["generator"]
            }
        ),
        "target": sorted(
            {
                (
                    str(entry["model"]),
                    str(entry["deployment_id"]),
                    str(entry["checkpoint_hash"]),
                )
                for entry in roles["target"]
            }
        ),
        "judge_models": sorted({str(entry["model"]) for entry in roles["judge"]}),
        "judge_rubric_version": rubric_version,
        "judge_rubric_sha256": rubric_sha256,
    }
    compatibility_sha256 = "sha256:" + hashlib.sha256(
        json.dumps(compatibility, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    provenance = [
        {
            key: entry.get(key)
            for key in (
                "role",
                "request_id",
                "model",
                "deployment_id",
                "checkpoint_hash",
            )
            if entry.get(key) is not None
        }
        for entry in usage
        if isinstance(entry, dict)
    ]
    result_payload = json.dumps(sample, sort_keys=True, separators=(",", ":")).encode()
    return {
        "axis": axis,
        "task_id": sample["task_id"],
        "axis_strategy_sha256": strategy_digest,
        "compatibility_sha256": compatibility_sha256,
        "accepted": (
            metrics.get("valid") == 1
            and metadata.get("judge_accepted") is True
            and metadata.get("teacher_accepted") is True
            and metadata.get("target_challenging") is True
            and isinstance(metrics.get("challenge"), (int, float))
            and not isinstance(metrics.get("challenge"), bool)
            and float(metrics["challenge"]) > 0
            and isinstance(metadata.get("primary_teacher_dimension"), str)
            and bool(metadata["primary_teacher_dimension"].strip())
            and isinstance(metadata.get("judge_rubric_version"), str)
            and bool(metadata["judge_rubric_version"].strip())
            and bool(
                re.fullmatch(
                    r"sha256:[0-9a-f]{64}",
                    str(metadata.get("judge_rubric_sha256") or ""),
                )
            )
        ),
        "result_sha256": "sha256:" + hashlib.sha256(result_payload).hexdigest(),
        "provider_provenance_sha256": "sha256:"
        + hashlib.sha256(
            json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _global_incumbent_binding(package: Mapping[str, Any]) -> str:
    """Bind every retained axis to the campaign-wide model and rubric identity."""
    identities: set[str] = set()
    for sample in package["evidence"][0]["content"]["sample_results"]:
        item = sample["generated_items"][0]
        metadata = item["metadata"]
        usage = sample["provider_usage"]
        binding = {
            "generator": sorted(
                {
                    (entry["model"], entry["deployment_id"])
                    for entry in usage
                    if entry["role"] == "generator"
                }
            ),
            "target": sorted(
                {
                    (
                        entry["model"],
                        entry["deployment_id"],
                        entry["checkpoint_hash"],
                    )
                    for entry in usage
                    if entry["role"] == "target"
                }
            ),
            "judge_models": sorted(
                {entry["model"] for entry in usage if entry["role"] == "judge"}
            ),
            "judge_rubric_version": metadata["judge_rubric_version"],
            "judge_rubric_sha256": metadata["judge_rubric_sha256"],
        }
        identities.add(
            "sha256:"
            + hashlib.sha256(
                json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
    if len(identities) != 1:
        raise RuntimeError("baseline samples disagree on global provider/rubric binding")
    return identities.pop()


def _validate_incumbent_state(
    state: Any, *, workspace_id: str
) -> dict[str, Any]:
    allowed_axes = {"honesty", "sycophancy_resistance", "uncertainty_disclosure"}
    if (
        not isinstance(state, dict)
        or set(state)
        != {
            "schema",
            "workspace_id",
            "global_binding_sha256",
            "axes",
            "applied_actions",
        }
        or state.get("schema") != INCUMBENTS_SCHEMA
        or state.get("workspace_id") != workspace_id
        or not isinstance(state.get("axes"), dict)
        or not isinstance(state.get("applied_actions"), dict)
    ):
        raise RuntimeError("baseline incumbent state is invalid")
    global_binding = state["global_binding_sha256"]
    if global_binding is not None and not re.fullmatch(
        r"sha256:[0-9a-f]{64}", str(global_binding)
    ):
        raise RuntimeError("baseline incumbent global binding is invalid")
    if global_binding is None and (state["axes"] or state["applied_actions"]):
        raise RuntimeError("baseline incumbent global binding is missing")
    record_keys = {
        "axis",
        "task_id",
        "axis_strategy_sha256",
        "compatibility_sha256",
        "result_sha256",
        "provider_provenance_sha256",
        "artifact_digest",
        "action_id",
    }
    for axis, record in state["axes"].items():
        if (
            axis not in allowed_axes
            or not isinstance(record, dict)
            or set(record) != record_keys
            or record.get("axis") != axis
            or not isinstance(record.get("task_id"), str)
            or not record["task_id"]
            or not _ACTION_ID.fullmatch(str(record.get("action_id") or ""))
            or any(
                not re.fullmatch(r"sha256:[0-9a-f]{64}", str(record.get(key) or ""))
                for key in (
                    "axis_strategy_sha256",
                    "compatibility_sha256",
                    "result_sha256",
                    "provider_provenance_sha256",
                    "artifact_digest",
                )
            )
        ):
            raise RuntimeError("baseline incumbent axis record is invalid")
    for action_id, journal in state["applied_actions"].items():
        transition = journal.get("transition") if isinstance(journal, dict) else None
        if (
            not _ACTION_ID.fullmatch(str(action_id))
            or not isinstance(journal, dict)
            or set(journal) != {"package_sha256", "transition"}
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(journal.get("package_sha256") or "")
            )
            or not isinstance(transition, dict)
            or set(transition)
            != {
                "schema",
                "active_axes",
                "updated_axes",
                "retained_axes",
                "invalidated_axes",
            }
            or transition.get("schema") != INCUMBENTS_SCHEMA
            or any(
                not isinstance(transition.get(key), list)
                or len(transition[key]) != len(set(transition[key]))
                or not set(transition[key]).issubset(allowed_axes)
                for key in (
                    "active_axes",
                    "updated_axes",
                    "retained_axes",
                    "invalidated_axes",
                )
            )
        ):
            raise RuntimeError("baseline incumbent action journal is invalid")
    return state


def _read_incumbent_state(path: Path, *, workspace_id: str) -> dict[str, Any]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return {
            "schema": INCUMBENTS_SCHEMA,
            "workspace_id": workspace_id,
            "global_binding_sha256": None,
            "axes": {},
            "applied_actions": {},
        }
    with os.fdopen(descriptor, "r", encoding="utf-8") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
        ):
            raise RuntimeError("baseline incumbent state is unsafe")
        try:
            state = json.load(source)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("baseline incumbent state is invalid") from error
    return _validate_incumbent_state(state, workspace_id=workspace_id)


def _update_axis_incumbents(
    package: Mapping[str, Any], *, action_id: str
) -> dict[str, Any]:
    """Persist accepted axis evidence outside the researcher-editable workspace.

    Unchanged axis digests retain their accepted incumbent when a later visible
    diagnostic regresses. A digest change invalidates only that axis. This
    state is review evidence; native production acceptance remains independent.
    """
    scope = package.get("scope")
    workspace_id = scope.get("id") if isinstance(scope, dict) else None
    if not isinstance(workspace_id, str):
        raise RuntimeError("baseline review has no workspace identity")
    if not _ACTION_ID.fullmatch(action_id):
        raise RuntimeError("baseline incumbent action id is invalid")
    path = _incumbent_path(workspace_id)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_fd = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(lock_fd, "r+") as lock:
        lock_info = os.fstat(lock.fileno())
        if (
            not stat.S_ISREG(lock_info.st_mode)
            or lock_info.st_uid != os.geteuid()
            or lock_info.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
        ):
            raise RuntimeError("baseline incumbent lock is unsafe")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = _read_incumbent_state(path, workspace_id=workspace_id)
        package_sha256 = "sha256:" + hashlib.sha256(
            json.dumps(package, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        applied = state["applied_actions"].get(action_id)
        if applied is not None:
            if applied["package_sha256"] != package_sha256:
                raise RuntimeError(
                    "baseline incumbent action replay changed its review package"
                )
            return dict(applied["transition"])
        axes = state["axes"]
        invalidated: list[str] = []
        retained: list[str] = []
        updated: list[str] = []
        content = package["evidence"][0]["content"]
        artifact_digest = package["artifact_digests"][0]
        global_binding = _global_incumbent_binding(package)
        if state["global_binding_sha256"] not in {None, global_binding}:
            invalidated.extend(axes)
            axes.clear()
        state["global_binding_sha256"] = global_binding
        for sample in content["sample_results"]:
            candidate = _incumbent_candidate(sample)
            if candidate is None:
                continue
            axis = candidate["axis"]
            existing = axes.get(axis)
            if isinstance(existing, dict) and existing.get(
                "compatibility_sha256"
            ) != candidate["compatibility_sha256"]:
                axes.pop(axis, None)
                existing = None
                invalidated.append(axis)
            if candidate.pop("accepted"):
                axes[axis] = {
                    **candidate,
                    "artifact_digest": artifact_digest,
                    "action_id": action_id,
                }
                updated.append(axis)
            elif existing is not None:
                retained.append(axis)
        transition = {
            "schema": INCUMBENTS_SCHEMA,
            "active_axes": sorted(axes),
            "updated_axes": sorted(set(updated)),
            "retained_axes": sorted(set(retained)),
            "invalidated_axes": sorted(set(invalidated)),
        }
        state["applied_actions"][action_id] = {
            "package_sha256": package_sha256,
            "transition": transition,
        }
        _validate_incumbent_state(state, workspace_id=workspace_id)
        encoded = (json.dumps(state, sort_keys=True, indent=2) + "\n").encode()
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            directory = os.open(
                path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return transition


def _expected_provider_identities() -> dict[str, tuple[str, ...]]:
    raw = os.getenv("AAR_AUTODATA_CAMPAIGN_POLICY", "").strip()
    if not raw:
        raise RuntimeError(
            "baseline approval requires a trusted campaign policy identity"
        )
    path = Path(raw).expanduser()
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise RuntimeError("trusted campaign policy is unavailable") from error
    with os.fdopen(descriptor, "r", encoding="utf-8") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
        ):
            raise RuntimeError("trusted campaign policy is unsafe")
        try:
            policy = json.load(source)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("trusted campaign policy is invalid") from error
    environment = policy.get("required_solve_env") if isinstance(policy, dict) else None
    required = (
        "AUTODATA_GENERATOR_MODEL",
        "AUTODATA_GENERATOR_DEPLOYMENT_ID",
        "AUTODATA_TARGET_MODEL",
        "AUTODATA_TARGET_DEPLOYMENT_ID",
        "AUTODATA_TARGET_CHECKPOINT_HASH",
        "AUTODATA_JUDGE_MODEL",
    )
    if not isinstance(environment, dict) or any(
        not isinstance(environment.get(key), str) or not environment[key].strip()
        for key in required
    ):
        raise RuntimeError("trusted campaign policy lacks provider identity")
    checkpoint = environment["AUTODATA_TARGET_CHECKPOINT_HASH"].lower()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", checkpoint):
        raise RuntimeError("trusted campaign policy has an invalid target checkpoint")
    return {
        "generator": (
            environment["AUTODATA_GENERATOR_MODEL"],
            environment["AUTODATA_GENERATOR_DEPLOYMENT_ID"],
        ),
        "target": (
            environment["AUTODATA_TARGET_MODEL"],
            environment["AUTODATA_TARGET_DEPLOYMENT_ID"],
            checkpoint,
        ),
        "judge": (environment["AUTODATA_JUDGE_MODEL"],),
    }


def _deterministic_checks(package: Mapping[str, Any]) -> None:
    kind = package["action_kind"]
    evidence = package["evidence"]
    if kind == "approve_grounding":
        content = evidence[0]["content"]
        if (
            not isinstance(content, dict)
            or content.get("schema") != "autodata.grounding-review/v1"
        ):
            raise RuntimeError("grounding approval lacks native grounding-review evidence")
        if not isinstance(content.get("task_count"), int) or content["task_count"] < 1:
            raise RuntimeError("grounding review contains no tasks")
        if not content.get("coverage_dimensions") or not content.get("facet_counts"):
            raise RuntimeError("grounding review lacks coverage evidence")
    elif kind == "approve_baseline":
        expected_identities = _expected_provider_identities()
        if len(evidence) != 1 or len(package.get("artifact_digests", [])) != 1:
            raise RuntimeError("baseline review requires exactly one evidence artifact")
        content = evidence[0]["content"]
        if (
            not isinstance(content, dict)
            or content.get("schema") != "autodata.baseline-review/v1"
        ):
            raise RuntimeError("baseline approval lacks native baseline-review evidence")
        samples = content.get("sample_results")
        if not isinstance(samples, list) or not samples:
            raise RuntimeError("baseline review contains no dry-run samples")
        if any(
            not isinstance(item, dict) or item.get("outcome") != "succeeded"
            for item in samples
        ):
            raise RuntimeError("baseline dry run did not succeed for every sample")
        sample_ids = content.get("sample_task_ids")
        if (
            not isinstance(sample_ids, list)
            or not sample_ids
            or len(samples) != len(sample_ids)
            or len(sample_ids) != len(set(sample_ids))
            or any(not isinstance(value, str) or not value for value in sample_ids)
            or {item.get("task_id") for item in samples} != set(sample_ids)
        ):
            raise RuntimeError("baseline review task identities are inconsistent")
        rubric_identities: set[tuple[str, str]] = set()
        for sample in samples:
            if sample.get("schema") != "autodata.task-result/v1":
                raise RuntimeError("baseline sample task-result schema is invalid")
            metrics = sample.get("metrics")
            if (
                not isinstance(metrics, dict)
                or not {
                    "quality",
                    "valid",
                    "challenge",
                    "quality_challenge_utility",
                }.issubset(metrics)
                or any(
                    isinstance(metrics[key], bool)
                    or not isinstance(metrics[key], (int, float))
                    or not math.isfinite(float(metrics[key]))
                    or not 0.0 <= float(metrics[key]) <= 1.0
                    for key in (
                        "quality",
                        "valid",
                        "challenge",
                        "quality_challenge_utility",
                    )
                )
            ):
                raise RuntimeError(
                    "baseline sample lacks bounded finite diagnostic metrics"
                )
            usage = sample.get("provider_usage")
            if not isinstance(usage, list) or not usage:
                raise RuntimeError("baseline sample lacks provider provenance")
            roles: dict[str, list[Mapping[str, Any]]] = {
                role: [
                    entry
                    for entry in usage
                    if isinstance(entry, dict) and entry.get("role") == role
                ]
                for role in ("generator", "target", "judge")
            }
            if any(not entries for entries in roles.values()):
                raise RuntimeError(
                    "baseline sample must record generator, target, and judge roles"
                )
            if any(
                not isinstance(entry.get("request_id"), str)
                or not entry["request_id"].strip()
                or not isinstance(entry.get("model"), str)
                or not entry["model"].strip()
                for entries in roles.values()
                for entry in entries
            ):
                raise RuntimeError("baseline sample provider identity is incomplete")
            request_ids = [
                entry["request_id"] for entries in roles.values() for entry in entries
            ]
            if len(request_ids) != len(set(request_ids)):
                raise RuntimeError("baseline provider request ids are not unique")
            if any(
                not isinstance(entry.get("deployment_id"), str)
                or not entry["deployment_id"].strip()
                for role in ("generator", "target")
                for entry in roles[role]
            ):
                raise RuntimeError("baseline sample deployment provenance is incomplete")
            if any(
                not isinstance(entry.get("checkpoint_hash"), str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", entry["checkpoint_hash"])
                for entry in roles["target"]
            ):
                raise RuntimeError("baseline target checkpoint provenance is incomplete")
            role_models = {
                role: {entry["model"] for entry in entries}
                for role, entries in roles.items()
            }
            if any(
                role_models[left] & role_models[right]
                for left, right in (
                    ("generator", "target"),
                    ("generator", "judge"),
                    ("target", "judge"),
                )
            ):
                raise RuntimeError("baseline provider roles reuse a spoofed identity")
            generator_identities = {
                (entry["model"], entry["deployment_id"])
                for entry in roles["generator"]
            }
            target_identities = {
                (
                    entry["model"],
                    entry["deployment_id"],
                    entry["checkpoint_hash"],
                )
                for entry in roles["target"]
            }
            judge_identities = {(entry["model"],) for entry in roles["judge"]}
            if (
                generator_identities != {expected_identities["generator"]}
                or target_identities != {expected_identities["target"]}
                or judge_identities != {expected_identities["judge"]}
            ):
                raise RuntimeError(
                    "baseline provider identity does not match trusted runtime"
                )
            items = sample.get("generated_items")
            if not isinstance(items, list) or len(items) != 1:
                raise RuntimeError(
                    "baseline sample requires exactly one diagnostic item"
                )
            item = items[0]
            metadata = item.get("metadata") if isinstance(item, dict) else None
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("prompt"), str)
                or not item["prompt"].strip()
                or not isinstance(item.get("response"), str)
                or not item["response"].strip()
                or not isinstance(metadata, dict)
                or metadata.get("axis")
                not in {
                    "honesty",
                    "sycophancy_resistance",
                    "uncertainty_disclosure",
                }
                or not re.fullmatch(
                    r"sha256:[0-9a-f]{64}",
                    str(metadata.get("axis_strategy_sha256") or ""),
                )
                or not isinstance(metadata.get("judge_rubric_version"), str)
                or not metadata["judge_rubric_version"].strip()
                or not re.fullmatch(
                    r"sha256:[0-9a-f]{64}",
                    str(metadata.get("judge_rubric_sha256") or ""),
                )
                or not isinstance(metadata.get("primary_teacher_dimension"), str)
                or not metadata["primary_teacher_dimension"].strip()
                or isinstance(metadata.get("judge_score"), bool)
                or not isinstance(metadata.get("judge_score"), (int, float))
                or not math.isfinite(float(metadata["judge_score"]))
                or not 0.0 <= float(metadata["judge_score"]) <= 1.0
                or not isinstance(metadata.get("judge_reason"), str)
                or not metadata["judge_reason"].strip()
                or not isinstance(metadata.get("judge_accepted"), bool)
                or not isinstance(metadata.get("teacher_accepted"), bool)
                or not isinstance(metadata.get("target_challenging"), bool)
            ):
                raise RuntimeError("baseline sample item schema is invalid")
            target_identities = {
                (
                    entry["model"],
                    entry["deployment_id"],
                    entry["checkpoint_hash"],
                )
                for entry in roles["target"]
            }
            if target_identities != {
                (
                    metadata.get("target_model"),
                    metadata.get("target_deployment_id"),
                    metadata.get("target_checkpoint_hash"),
                )
            }:
                raise RuntimeError(
                    "baseline target metadata does not match provider provenance"
                )
            rubric_identities.add(
                (
                    metadata["judge_rubric_version"],
                    metadata["judge_rubric_sha256"],
                )
            )
            valid = float(metrics["valid"])
            quality = float(metrics["quality"])
            challenge = float(metrics["challenge"])
            if valid not in {0.0, 1.0} or not 0.0 <= challenge <= 1.0:
                raise RuntimeError("baseline acceptance metrics are out of range")
            expected_dimension = {
                "honesty": "factual_honesty",
                "sycophancy_resistance": "sycophancy_resistance",
                "uncertainty_disclosure": "uncertainty_disclosure",
            }[metadata["axis"]]
            if (
                float(metadata["judge_score"]) != quality
                or metadata["primary_teacher_dimension"] != expected_dimension
            ):
                raise RuntimeError("baseline teacher evidence is contradictory")
            if (valid == 1.0) != metadata["judge_accepted"]:
                raise RuntimeError("baseline acceptance evidence is contradictory")
            if (challenge > 0.0) != metadata["target_challenging"]:
                raise RuntimeError("baseline challenge evidence is contradictory")
            if valid == 1.0 and challenge <= 0.0:
                raise RuntimeError("accepted baseline item has no target challenge")
            if valid == 1.0 and not metadata["teacher_accepted"]:
                raise RuntimeError("accepted baseline item has a rejected teacher")
            if (
                valid == 0.0
                and metadata["teacher_accepted"]
                and metadata["target_challenging"]
            ):
                raise RuntimeError("baseline rejection evidence is contradictory")
            expected_utility = (
                0.0
                if valid == 0.0 or quality <= 0.0 or challenge <= 0.0
                else 2.0 * quality * challenge / (quality + challenge)
            )
            if not math.isclose(
                float(metrics["quality_challenge_utility"]),
                expected_utility,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise RuntimeError("baseline utility evidence is contradictory")
            reason_code = sample.get("reason_code")
            expected_reason = (
                None
                if valid == 1.0
                else "judge_rejected"
                if metadata["teacher_accepted"] is False
                else "target_not_challenging"
            )
            if reason_code != expected_reason:
                raise RuntimeError("baseline reason code contradicts item metadata")
        if len(rubric_identities) != 1:
            raise RuntimeError("baseline samples disagree on judge rubric identity")
        mutable = content.get("mutable_paths")
        if mutable != ["recipe/generation_strategy.json"]:
            raise RuntimeError("baseline review mutation surface is not narrowly bounded")
        protected = content.get("protected_paths")
        required_protected = {
            "autodata.pipeline.json",
            "autodata.workspace.json",
            "grounding/**",
            "framework.lock.json",
            "objective.json",
            "comparator.json",
            "schemas/**",
            "recipe/judge_rubric.json",
            "recipe/task.py",
            "recipe/check.py",
            "recipe/request.json",
            "training-data-contract.json",
        }
        if not isinstance(protected, list) or set(protected) != required_protected:
            raise RuntimeError("baseline review does not protect scientific controls")
    elif os.getenv("AAR_AUTODATA_RESOURCES_READY", "0") != "1":
        raise RuntimeError("operator resource profile has not declared resources ready")


def _baseline_operational_verdict(package: Mapping[str, Any]) -> dict[str, Any]:
    """Approve a deterministically valid dry run without judging row quality."""
    samples = package["evidence"][0]["content"]["sample_results"]
    valid = sum(sample["metrics"]["valid"] == 1 for sample in samples)
    challenging = sum(sample["metrics"]["challenge"] > 0 for sample in samples)
    total = len(samples)
    return {
        "approved": True,
        "target": "pipeline",
        "feedback": (
            "Operational baseline passed; proceed to native meta-optimization. "
            f"Diagnostic acceptance was {valid}/{total} and positive target "
            f"challenge was {challenging}/{total}; these are optimization signals, "
            "not authoring gates."
        ),
        "reasoning": (
            "Every dry-run task completed with valid schema, finite metrics, "
            "pinned generator/target/judge provenance, and bounded mutation controls."
        ),
        "monitor_model": "deterministic-operational-policy",
        "monitor_backend": "local",
    }


def approval_payload(
    action: Mapping[str, Any],
    *,
    decision: str,
    feedback: str,
    target: str,
    actor: str,
    policy_version: str,
) -> bytes:
    value = {
        "schema": APPROVAL_SCHEMA,
        "action_id": action["id"],
        "action_kind": action["kind"],
        "scope": action["scope"],
        "artifact_digests": [item["digest"] for item in action.get("artifacts", [])],
        "decision": decision,
        "feedback": feedback,
        "target": target,
        "actor": actor,
        "policy_version": policy_version,
    }
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sign(private_key: Path, payload: bytes) -> str:
    mode = private_key.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise RuntimeError("delegated approval private key must have mode 0600")
    with tempfile.TemporaryDirectory(prefix="aar-autodata-sign-") as temporary:
        signature = Path(temporary) / "signature.bin"
        subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-sign",
                str(private_key),
                "-out",
                str(signature),
            ],
            input=payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=True,
        )
        return base64.b64encode(signature.read_bytes()).decode("ascii")


def _run_cli(arguments: list[str]) -> dict[str, Any]:
    plugin = _required_path("AAR_AUTODATA_PLUGIN_ROOT", directory=True)
    wrapper = plugin / "scripts" / "autodata.py"
    state = _required_path("AAR_AUTODATA_STATE")
    artifacts = _required_path("AAR_AUTODATA_ARTIFACTS", directory=True)
    workspaces = Path(os.getenv("AAR_AUTODATA_WORKSPACES", "")).expanduser().resolve()
    if not workspaces.is_dir():
        raise RuntimeError("AAR_AUTODATA_WORKSPACES is required")
    completed = subprocess.run(
        [
            os.environ.get("AAR_AUTODATA_WRAPPER_PYTHON", "python3"),
            str(wrapper),
            "--state",
            str(state),
            "--artifacts",
            str(artifacts),
            "--workspaces",
            str(workspaces),
            *arguments,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        termination = f"exit={completed.returncode}"
        if completed.returncode < 0:
            try:
                termination += f" signal={signal.Signals(-completed.returncode).name}"
            except ValueError:
                termination += f" signal={-completed.returncode}"
        raise _native_cli_failure(termination)
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise _native_cli_failure(
            "exit=0",
            error_code="autodata_approval_invalid_json",
            public_summary="native AutoData CLI returned invalid JSON",
        ) from error
    if not isinstance(value, dict):
        raise RuntimeError("native AutoData CLI returned invalid JSON")
    return value


def _write_audit(action_id: str, value: Mapping[str, Any]) -> Path:
    root = Path(os.getenv("AAR_AUTODATA_APPROVAL_AUDIT_DIR", "")).expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("AAR_AUTODATA_APPROVAL_AUDIT_DIR is required")
    path = root / f"{action_id}.json"
    encoded = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        existing = json.loads(path.read_text())
        if existing != dict(value):
            raise RuntimeError("existing approval audit does not match decision")
        return path
    with os.fdopen(descriptor, "wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return path


def _approval_completion_intent_path(action_id: str) -> Path:
    root = Path(os.getenv("AAR_AUTODATA_APPROVAL_AUDIT_DIR", "")).expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("AAR_AUTODATA_APPROVAL_AUDIT_DIR is required")
    return root / f".{action_id}.completion-intent.json"


def _read_approval_completion_intent(action_id: str) -> dict[str, Any]:
    path = _approval_completion_intent_path(action_id)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(
            "native approval action is in_progress but its durable completion "
            "intent is missing"
        )
    info = path.stat()
    if info.st_uid != os.geteuid() or info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise RuntimeError("native approval completion intent is unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("native approval completion intent is invalid") from error
    if (
        not isinstance(value, dict)
        or value.get("action_id") != action_id
        or not isinstance(value.get("lease_token"), str)
        or not isinstance(value.get("result"), dict)
        or not isinstance(value.get("completed_at_unix"), (int, float))
    ):
        raise RuntimeError("native approval completion intent is incomplete")
    return value


def review_and_complete_action(action_id: str) -> dict[str, Any]:
    if not _ACTION_ID.fullmatch(action_id):
        raise ValueError("action_id is invalid")
    state = _required_path("AAR_AUTODATA_STATE")
    artifacts = _required_path("AAR_AUTODATA_ARTIFACTS", directory=True)
    row = _action_row(state, action_id)
    if row["status"] not in {"pending", "in_progress", "completed"}:
        raise RuntimeError("native approval action is not pending or resumable")
    action = json.loads(row["specJson"])
    package = _review_package(action, artifacts)
    kind = action["kind"]
    intent_path = _approval_completion_intent_path(action_id)
    if row["status"] in {"in_progress", "completed"}:
        intent = _read_approval_completion_intent(action_id)
        lease = intent["lease_token"]
        result = intent["result"]
        verdict = intent["verdict"]
        proposal_binding = intent["proposal_binding"]
        decision = str(result["decision"])
        target = str(result["target"])
        feedback = str(result["feedback"])
        actor = str(result["delegated_approval"]["actor"])
        policy_version = str(result["delegated_approval"]["policy_version"])
        completed_at_unix = float(intent["completed_at_unix"])
        payload = approval_payload(
            action,
            decision=decision,
            feedback=feedback,
            target=target,
            actor=actor,
            policy_version=policy_version,
        )
    else:
        proposal_binding = _proposal_binding(state, package)
        if kind == "approve_resources":
            verdict = {
                "approved": True,
                "target": "pipeline",
                "feedback": "Pinned operator resources are ready.",
                "reasoning": "Deterministic operator-profile check passed.",
                "monitor_model": "deterministic-policy",
                "monitor_backend": "local",
            }
            decision = "retry"
        elif kind == "approve_baseline":
            verdict = _baseline_operational_verdict(package)
            decision = "approve"
        else:
            verdict = check_autodata_action(package)
            decision = "approve" if verdict.get("approved") is True else "revise"
        target = str(
            verdict.get("target")
            or ("grounding" if kind == "approve_grounding" else "pipeline")
        )
        feedback = str(
            verdict.get("feedback") or verdict.get("reasoning") or "Revision required"
        )[:4000]
        actor = os.getenv("AAR_AUTODATA_APPROVAL_ACTOR", "aar-integrity-monitor")
        policy_version = os.getenv(
            "AAR_AUTODATA_APPROVAL_POLICY_VERSION", "aar-autodata/v1"
        )
        payload = approval_payload(
            action,
            decision=decision,
            feedback=feedback,
            target=target,
            actor=actor,
            policy_version=policy_version,
        )
        signature = _sign(_required_path("AAR_AUTODATA_APPROVAL_PRIVATE_KEY"), payload)
        result = {
            "decision": decision,
            "feedback": feedback,
            "target": target,
            "delegated_approval": {
                "schema": APPROVAL_SCHEMA,
                "algorithm": APPROVAL_ALGORITHM,
                "actor": actor,
                "policy_version": policy_version,
                "signature": signature,
            },
        }
        completed_at_unix = time.time()
        begun = _run_cli(["action", "begin", action_id])
        lease = begun.get("lease_token")
        if not isinstance(lease, str) or not lease:
            raise RuntimeError("native action lease was not returned")
        _atomic_private_json(
            intent_path,
            {
                "action_id": action_id,
                "lease_token": lease,
                "result": result,
                "verdict": verdict,
                "proposal_binding": proposal_binding,
                "completed_at_unix": completed_at_unix,
            },
        )
    if row["status"] != "completed":
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="aar-autodata-result-", suffix=".json"
        ) as handle:
            json.dump(result, handle, sort_keys=True)
            handle.flush()
            _run_cli(
                [
                    "action",
                    "complete",
                    action_id,
                    "--lease-token",
                    lease,
                    "--result",
                    handle.name,
                ]
            )
    incumbent_transition = None
    if kind == "approve_baseline":
        incumbent_transition = _update_axis_incumbents(
            package, action_id=action_id
        )
    audit = {
        "schema": AUDIT_SCHEMA,
        "action_id": action_id,
        "action_kind": kind,
        "scope": action["scope"],
        "artifact_digests": package["artifact_digests"],
        "decision": decision,
        "target": target,
        "feedback": feedback,
        "actor": actor,
        "proposal_binding": proposal_binding,
        "policy_version": policy_version,
        "payload_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "monitor_model": verdict.get("monitor_model"),
        "monitor_backend": verdict.get("monitor_backend"),
        "monitor_reasoning": verdict.get("reasoning"),
        "axis_incumbents": incumbent_transition,
        "completed_at_unix": completed_at_unix,
    }
    audit_path = _write_audit(action_id, audit)
    intent_path.unlink(missing_ok=True)
    directory = os.open(
        intent_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {**audit, "audit_path": str(audit_path)}
