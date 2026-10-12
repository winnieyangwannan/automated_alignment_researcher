from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aar.infrastructure.autodata_coordinator.coordinator import (
    ACTION_SCHEMA,
    AutoDataCoordinatorError,
    NativeAction,
    NativeWorkspace,
    WorkspaceApprovalReconciler,
)

WORKSPACE_ID = "ws_" + "1" * 32
ACTION_ID = "act_" + "2" * 24
ARTIFACT_DIGEST = "sha256:" + "3" * 64


def _action(kind: str, *, status: str = "pending") -> NativeAction:
    spec = {
        "schema": ACTION_SCHEMA,
        "id": ACTION_ID,
        "scope": {"kind": "workspace", "id": WORKSPACE_ID, "revision": 3},
        "kind": kind,
        "instructions": "Review the immutable native evidence.",
        "artifacts": [{"digest": ARTIFACT_DIGEST}],
        "editable_root": "/not/model-visible",
        "allowed_paths": [],
        "outputs": ["decision", "feedback"],
    }
    result = (
        {
            "decision": "approve",
            "feedback": "Approved from native evidence.",
            "target": "pipeline",
            "delegated_approval": {
                "actor": "aar-integrity-monitor",
                "policy_version": "aar-autodata/v1",
            },
        }
        if status == "completed"
        else None
    )
    return NativeAction(ACTION_ID, kind, status, spec, result)


class Control:
    def __init__(self, kind: str) -> None:
        self.action = _action(kind)

    def read_workspace(self, workspace_id: str) -> NativeWorkspace:
        phase = "pipeline_pending" if self.action.status == "completed" else "review"
        revision = 4 if self.action.status == "completed" else 3
        return NativeWorkspace(
            workspace_id, "active", phase, revision, (self.action,)
        )


def _control_file(tmp_path: Path) -> Path:
    path = tmp_path / "control.json"
    path.write_text(
        json.dumps(
            {
                "schema": "aar.autodata.lifecycle-control/v1",
                "subjects": [
                    {
                        "kind": "workspace",
                        "subject_id": WORKSPACE_ID,
                        "status": "registered",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("kind", ["approve_grounding", "approve_baseline"])
def test_shared_approval_route_completes_exact_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    control = Control(kind)
    calls: list[str] = []
    monkeypatch.setenv("AAR_AUTODATA_APPROVAL_AUDIT_DIR", str(tmp_path))

    def approve(action_id: str) -> dict[str, Any]:
        calls.append(action_id)
        control.action = _action(kind, status="completed")
        audit = {
            "schema": "aar.autodata.approval-audit/v1",
            "action_id": action_id,
            "action_kind": kind,
            "scope": control.action.spec["scope"],
            "artifact_digests": [ARTIFACT_DIGEST],
            "decision": "approve",
            "feedback": "Approved from native evidence.",
            "target": "pipeline",
            "actor": "aar-integrity-monitor",
            "policy_version": "aar-autodata/v1",
        }
        path = tmp_path / f"{action_id}.json"
        path.write_text(json.dumps(audit), encoding="utf-8")
        path.chmod(0o600)
        return {**audit, "audit_path": str(path)}

    outcome = WorkspaceApprovalReconciler(
        control=control, approval_handler=approve
    ).reconcile_registered_approval(_control_file(tmp_path))

    assert outcome is not None
    assert calls == [ACTION_ID]
    assert outcome.action_id == ACTION_ID
    assert outcome.action_kind == kind
    assert outcome.native_phase == "pipeline_pending"
    assert outcome.native_revision == 4


def test_shared_approval_route_ignores_unrelated_action(tmp_path: Path) -> None:
    control = Control("author_grounding")

    outcome = WorkspaceApprovalReconciler(
        control=control,
        approval_handler=lambda _action_id: pytest.fail("handler must not run"),
    ).reconcile_registered_approval(_control_file(tmp_path))

    assert outcome is None


def test_shared_approval_route_wraps_bridge_failure(tmp_path: Path) -> None:
    control = Control("approve_grounding")

    def fail(_action_id: str) -> dict[str, Any]:
        raise RuntimeError("monitor unavailable")

    with pytest.raises(AutoDataCoordinatorError) as raised:
        WorkspaceApprovalReconciler(
            control=control, approval_handler=fail
        ).reconcile_registered_approval(_control_file(tmp_path))

    assert raised.value.code == "delegated_approval_failed"
    assert raised.value.retryable is False


def test_shared_approval_route_rejects_stale_revision(tmp_path: Path) -> None:
    control = Control("approve_grounding")
    stale = dict(control.action.spec)
    stale["scope"] = {**stale["scope"], "revision": 2}
    control.action = NativeAction(
        ACTION_ID, "approve_grounding", "pending", stale, None
    )

    with pytest.raises(AutoDataCoordinatorError) as raised:
        WorkspaceApprovalReconciler(
            control=control,
            approval_handler=lambda _action_id: pytest.fail("handler must not run"),
        ).reconcile_registered_approval(_control_file(tmp_path))

    assert raised.value.code == "approval_action_contract_invalid"


def test_shared_approval_route_rejects_native_result_audit_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = Control("approve_grounding")
    monkeypatch.setenv("AAR_AUTODATA_APPROVAL_AUDIT_DIR", str(tmp_path))

    def approve(action_id: str) -> dict[str, Any]:
        control.action = _action("approve_grounding", status="completed")
        audit = {
            "schema": "aar.autodata.approval-audit/v1",
            "action_id": action_id,
            "action_kind": "approve_grounding",
            "scope": control.action.spec["scope"],
            "artifact_digests": [ARTIFACT_DIGEST],
            "decision": "revise",
            "feedback": "Approved from native evidence.",
            "target": "pipeline",
            "actor": "aar-integrity-monitor",
            "policy_version": "aar-autodata/v1",
        }
        path = tmp_path / f"{action_id}.json"
        path.write_text(json.dumps(audit), encoding="utf-8")
        path.chmod(0o600)
        return {**audit, "audit_path": str(path)}

    with pytest.raises(AutoDataCoordinatorError) as raised:
        WorkspaceApprovalReconciler(
            control=control, approval_handler=approve
        ).reconcile_registered_approval(_control_file(tmp_path))

    assert raised.value.code == "approval_completion_invalid"


def test_approval_coordinator_flag_survives_sanitized_chain_launch() -> None:
    root = Path(__file__).resolve().parents[1]
    runtime = (root / "scripts" / "aar_runtime_env.sh").read_text(encoding="utf-8")
    preserve = runtime.split("_AAR_PRESERVE=(", 1)[1].split("\n)", 1)[0]

    assert "AAR_AUTODATA_APPROVAL_COORDINATOR" in preserve.split()
