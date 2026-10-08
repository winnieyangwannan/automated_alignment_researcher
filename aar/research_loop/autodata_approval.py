"""Trusted bridge for one delegated native AutoData approval action.

This module deliberately does not reproduce the AutoData lifecycle. It reads
one pending native approval action, reviews its content-addressed evidence,
signs the exact decision outside the researcher sandbox, and completes that
same native action through the original plugin CLI.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from .monitor import check_autodata_action

APPROVAL_SCHEMA = "autodata.delegated-approval/v1"
APPROVAL_ALGORITHM = "rsa-pkcs1v15-sha256"
AUDIT_SCHEMA = "aar.autodata.approval-audit/v1"
_ACTION_ID = re.compile(r"^act_[0-9a-f]{24}$")
_APPROVAL_KINDS = {"approve_grounding", "approve_baseline", "approve_resources"}


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
        mutable = content.get("mutable_paths")
        if not isinstance(mutable, list) or not mutable:
            raise RuntimeError("baseline review has no bounded mutation surface")
    elif os.getenv("AAR_AUTODATA_RESOURCES_READY", "0") != "1":
        raise RuntimeError("operator resource profile has not declared resources ready")


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
        raise RuntimeError("native AutoData CLI failed: " + completed.stderr[-1000:])
    value = json.loads(completed.stdout)
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
    return path


def review_and_complete_action(action_id: str) -> dict[str, Any]:
    if not _ACTION_ID.fullmatch(action_id):
        raise ValueError("action_id is invalid")
    state = _required_path("AAR_AUTODATA_STATE")
    artifacts = _required_path("AAR_AUTODATA_ARTIFACTS", directory=True)
    row = _action_row(state, action_id)
    if row["status"] != "pending":
        raise RuntimeError("native approval action is not pending")
    action = json.loads(row["specJson"])
    package = _review_package(action, artifacts)
    kind = action["kind"]
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
    begun = _run_cli(["action", "begin", action_id])
    lease = begun.get("lease_token")
    if not isinstance(lease, str) or not lease:
        raise RuntimeError("native action lease was not returned")
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
        "policy_version": policy_version,
        "payload_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "monitor_model": verdict.get("monitor_model"),
        "monitor_backend": verdict.get("monitor_backend"),
        "monitor_reasoning": verdict.get("reasoning"),
        "completed_at_unix": time.time(),
    }
    audit_path = _write_audit(action_id, audit)
    return {**audit, "audit_path": str(audit_path)}
