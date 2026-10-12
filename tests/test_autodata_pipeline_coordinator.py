from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from aar.infrastructure.autodata_coordinator.coordinator import (
    ACTION_SCHEMA,
    ActionLease,
    AutoDataCoordinatorError,
    NativeAction,
    NativeWorkspace,
    WorkspacePipelineReconciler,
)
from aar.infrastructure.autodata_coordinator.semantic_worker import (
    PipelineContext,
    SemanticOutcome,
)

WORKSPACE_ID = "ws_" + "1" * 32
ACTION_ID = "act_" + "2" * 24
TOKEN = "protected-native-action-lease-token"


def _action(root: Path, status: str = "pending", result=None) -> NativeAction:
    spec = {
        "schema": ACTION_SCHEMA,
        "id": ACTION_ID,
        "scope": {"kind": "workspace", "id": WORKSPACE_ID, "revision": 3},
        "kind": "author_pipeline",
        "instructions": "Review the staged pipeline against approved grounding.",
        "artifacts": [],
        "editable_root": str(root),
        "allowed_paths": ["**"],
        "outputs": ["summary", "decisions"],
    }
    return NativeAction(ACTION_ID, "author_pipeline", status, spec, result)


class Control:
    def __init__(self, root: Path, *, crash_after_complete: bool = False) -> None:
        self.action = _action(root)
        self.lease: str | None = None
        self.begin_calls = self.complete_calls = 0
        self.crash_after_complete = crash_after_complete

    def read_workspace(self, workspace_id: str) -> NativeWorkspace:
        return NativeWorkspace(
            workspace_id, "active", "pipeline_pending", 3, (self.action,)
        )

    def begin_action(self, action_id: str) -> ActionLease:
        self.begin_calls += 1
        self.lease = TOKEN
        self.action = _action(Path(self.action.spec["editable_root"]), "in_progress")
        return ActionLease(action_id, TOKEN, self.action.spec)

    def lease_matches(self, action_id: str, token: str) -> bool:
        return action_id == ACTION_ID and token == self.lease

    def complete_action(
        self, action_id: str, *, lease_token: str, result: dict[str, Any]
    ) -> None:
        self.complete_calls += 1
        assert action_id == ACTION_ID and lease_token == TOKEN
        self.action = _action(
            Path(self.action.spec["editable_root"]), "completed", dict(result)
        )
        self.lease = None
        if self.crash_after_complete:
            self.crash_after_complete = False
            raise SystemExit("simulated crash after native completion")


class Worker:
    backend_name = "claude"

    def __init__(self, outcomes: list[SemanticOutcome] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls = 0
        self.contexts: list[PipelineContext] = []

    async def perform(self, context: PipelineContext) -> SemanticOutcome:
        self.calls += 1
        self.contexts.append(context)
        if self.outcomes:
            return self.outcomes.pop(0)
        return SemanticOutcome(
            context.action_id,
            context.input_revision,
            context.input_digest,
            "confirm",
            "The reviewed pipeline is complete.",
            ("Keep the staged files byte-identical.",),
            None,
        )


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    team = tmp_path / "team"
    root = team / "autodata" / "test-run" / "draft"
    team.mkdir(parents=True)
    (root / "grounding").mkdir(parents=True)
    (root / "recipe").mkdir()
    (root / "autodata.workspace.json").write_text(
        json.dumps({"schema": "autodata.workspace/v1", "goal": "test"})
    )
    (root / "grounding/manifest.json").write_text(
        json.dumps({"schema": "autodata.grounding/v1", "tasks": []})
    )
    (root / "autodata.pipeline.json").write_text(
        json.dumps({"schema": "autodata.pipeline/v1", "name": "test"})
    )
    (root / "recipe/task.py").write_text("print('reviewed')\n")
    return team, root


def _digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _reconciler(team: Path, control: Control, worker: Worker):
    return WorkspacePipelineReconciler(
        control=control,
        worker=worker,
        team_dir=team,
        action_timeout_seconds=0.2,
        malformed_output_attempts=3,
    )


def test_pipeline_confirm_is_bound_tool_free_and_byte_identical(tmp_path: Path) -> None:
    team, root = _fixture(tmp_path)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    control, worker = Control(root), Worker()

    outcome = asyncio.run(_reconciler(team, control, worker).coordinate_pipeline(WORKSPACE_ID))

    assert control.begin_calls == control.complete_calls == worker.calls == 1
    assert not hasattr(worker.contexts[0], "lease")
    assert before == {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    receipt = json.loads(outcome.receipt_path.read_text())
    assert receipt["action_kind"] == "author_pipeline"
    assert receipt["changed_paths"] == []
    assert TOKEN not in outcome.receipt_path.read_text()


def test_pipeline_retries_stale_typed_output_without_rebegin(tmp_path: Path) -> None:
    team, root = _fixture(tmp_path)
    stale = SemanticOutcome(
        ACTION_ID, 2, "sha256:" + "0" * 64, "confirm", "stale", (), None
    )
    control, worker = Control(root), Worker([stale])

    asyncio.run(_reconciler(team, control, worker).coordinate_pipeline(WORKSPACE_ID))

    assert worker.calls == 2
    assert control.begin_calls == control.complete_calls == 1


def test_pipeline_rejects_worker_file_update_without_rebegin(tmp_path: Path) -> None:
    team, root = _fixture(tmp_path)
    proposed = SemanticOutcome(
        ACTION_ID,
        3,
        "placeholder",
        "update",
        "change files",
        (),
        {"unexpected": "candidate"},
    )
    control, worker = Control(root), Worker([proposed])

    async def retry(context: PipelineContext) -> SemanticOutcome:
        if worker.outcomes:
            stale = worker.outcomes.pop()
            return SemanticOutcome(
                stale.action_id,
                stale.input_revision,
                context.input_digest,
                stale.decision,
                stale.summary,
                stale.decisions,
                stale.updated_workspace,
            )
        return await Worker.perform(worker, context)

    worker.perform = retry  # type: ignore[method-assign]
    asyncio.run(_reconciler(team, control, worker).coordinate_pipeline(WORKSPACE_ID))

    assert control.begin_calls == control.complete_calls == 1
    assert json.loads((root / "autodata.pipeline.json").read_text())["name"] == "test"


def test_pipeline_change_during_review_fails_before_native_completion(
    tmp_path: Path,
) -> None:
    team, root = _fixture(tmp_path)
    control, worker = Control(root), Worker()

    async def change(context: PipelineContext) -> SemanticOutcome:
        (root / "recipe/task.py").write_text("print('changed elsewhere')\n")
        return SemanticOutcome(
            context.action_id,
            context.input_revision,
            context.input_digest,
            "confirm",
            "Looks complete.",
            (),
            None,
        )

    worker.perform = change  # type: ignore[method-assign]
    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(_reconciler(team, control, worker).coordinate_pipeline(WORKSPACE_ID))

    assert raised.value.code == "pipeline_changed_during_action"
    assert control.complete_calls == 0


@pytest.mark.parametrize("durable", [True, False])
def test_pipeline_in_progress_requires_matching_durable_lease(
    tmp_path: Path, durable: bool
) -> None:
    team, root = _fixture(tmp_path)
    control, worker = Control(root), Worker()
    control.action, control.lease = _action(root, "in_progress"), TOKEN
    if durable:
        path = team / f"autodata/action-leases/{ACTION_ID}.token"
        path.parent.mkdir(parents=True)
        path.write_text(TOKEN + "\n")
        path.chmod(0o600)

    if durable:
        asyncio.run(_reconciler(team, control, worker).coordinate_pipeline(WORKSPACE_ID))
        assert control.begin_calls == 0 and worker.calls == 1
    else:
        with pytest.raises(AutoDataCoordinatorError) as raised:
            asyncio.run(
                _reconciler(team, control, worker).coordinate_pipeline(WORKSPACE_ID)
            )
        assert raised.value.code == "action_lease_missing" and worker.calls == 0


def test_pipeline_completed_action_recovers_without_worker_reinvoke(tmp_path: Path) -> None:
    team, root = _fixture(tmp_path)
    control, first = Control(root, crash_after_complete=True), Worker()
    with pytest.raises(SystemExit):
        asyncio.run(_reconciler(team, control, first).coordinate_pipeline(WORKSPACE_ID))

    second = Worker()
    outcome = asyncio.run(
        _reconciler(team, control, second).coordinate_pipeline(WORKSPACE_ID)
    )
    third = Worker()
    repeated = asyncio.run(
        _reconciler(team, control, third).coordinate_pipeline(WORKSPACE_ID)
    )

    assert first.calls == control.begin_calls == control.complete_calls == 1
    assert second.calls == third.calls == 0
    assert repeated.receipt_path == outcome.receipt_path


def test_pipeline_completed_without_stage_fails_closed(tmp_path: Path) -> None:
    team, root = _fixture(tmp_path)
    control, worker = Control(root), Worker()
    control.action = _action(root, "completed", {"summary": "legacy"})

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(_reconciler(team, control, worker).coordinate_pipeline(WORKSPACE_ID))

    assert raised.value.code == "semantic_stage_missing"
    assert worker.calls == 0


def test_pipeline_receipt_rebinds_native_result(tmp_path: Path) -> None:
    team, root = _fixture(tmp_path)
    control, worker = Control(root), Worker()
    asyncio.run(_reconciler(team, control, worker).coordinate_pipeline(WORKSPACE_ID))
    control.action = _action(root, "completed", {"summary": "tampered"})

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(_reconciler(team, control, Worker()).coordinate_pipeline(WORKSPACE_ID))

    assert raised.value.code == "pipeline_receipt_invalid"


@pytest.mark.parametrize(
    ("field", "value"),
    [("native_phase_observed", 7), ("native_revision_observed", 99)],
)
def test_pipeline_receipt_rejects_invalid_native_state(
    tmp_path: Path, field: str, value: object
) -> None:
    team, root = _fixture(tmp_path)
    control = Control(root)
    outcome = asyncio.run(
        _reconciler(team, control, Worker()).coordinate_pipeline(WORKSPACE_ID)
    )
    receipt = json.loads(outcome.receipt_path.read_text())
    receipt[field] = value
    unsigned = dict(receipt)
    unsigned.pop("receipt_digest")
    receipt["receipt_digest"] = _digest(unsigned)
    outcome.receipt_path.write_text(json.dumps(receipt))
    outcome.receipt_path.chmod(0o600)

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(_reconciler(team, control, Worker()).coordinate_pipeline(WORKSPACE_ID))

    assert raised.value.code == "pipeline_receipt_invalid"


def test_pipeline_root_must_be_run_draft_under_team(tmp_path: Path) -> None:
    team = tmp_path / "team"
    team.mkdir()
    _, escaped = _fixture(tmp_path / "other")
    control = Control(escaped)

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(_reconciler(team, control, Worker()).coordinate_pipeline(WORKSPACE_ID))

    assert raised.value.code == "editable_root_invalid"
    assert control.begin_calls == 0


def test_pipeline_root_symlink_fails_closed(tmp_path: Path) -> None:
    team = tmp_path / "team"
    outside = tmp_path / "outside"
    outside.mkdir()
    root = team / "autodata" / "test-run" / "draft"
    root.parent.mkdir(parents=True)
    root.symlink_to(outside, target_is_directory=True)
    control = Control(root)

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(_reconciler(team, control, Worker()).coordinate_pipeline(WORKSPACE_ID))

    assert raised.value.code == "editable_root_invalid"
    assert control.begin_calls == 0


def test_pipeline_reconciler_leaves_unknown_action_unchanged(tmp_path: Path) -> None:
    team, root = _fixture(tmp_path)
    control, worker = Control(root), Worker()
    control.action = NativeAction(
        ACTION_ID,
        "approve_baseline",
        "pending",
        {**control.action.spec, "kind": "approve_baseline"},
    )
    control_file = tmp_path / "control.json"
    control_file.write_text(
        json.dumps(
            {
                "subjects": [
                    {
                        "kind": "workspace",
                        "subject_id": WORKSPACE_ID,
                        "status": "registered",
                    }
                ]
            }
        )
    )

    result = asyncio.run(
        _reconciler(team, control, worker).reconcile_registered_pipeline(control_file)
    )

    assert result is None and worker.calls == control.begin_calls == 0
