from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from aar.infrastructure.autodata_coordinator.claude_worker import ClaudeWorker
from aar.infrastructure.autodata_coordinator.kimi_worker import KimiWorker
from aar.infrastructure.autodata_coordinator.coordinator import (
    ACTION_SCHEMA,
    ActionLease,
    AutoDataActionReconciler,
    AutoDataCoordinatorError,
    ExecutionAnalysisReconciler,
    ExecutionMutationReconciler,
    NativeAction,
    NativeAutoDataControl,
    NativeWorkspace,
)
from aar.infrastructure.autodata_coordinator.semantic_worker import (
    ActionContext,
    AnalysisContext,
    AnalysisOutcome,
    MalformedSemanticOutcome,
    MutationContext,
    MutationOutcome,
    SemanticOutcome,
)


WORKSPACE_ID = "ws_" + "1" * 32
ACTION_ID = "act_" + "2" * 24
TOKEN = "protected-native-action-lease-token"
EXECUTION_ID = "exe_" + "3" * 32
ANALYSIS_ACTION_ID = "act_" + "4" * 24
MUTATION_ACTION_ID = "act_" + "6" * 24


def _json_digest(value: object) -> str:
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _workspace() -> dict[str, Any]:
    return {
        "schema": "autodata.workspace/v1",
        "name": "test",
        "goal": "original goal",
        "intended_use": "test",
        "source_constraints": [],
        "authoring_executor": {"kind": "local-bwrap"},
        "authoring_budget": {
            "max_iterations": 8,
            "max_task_attempts": 8,
            "max_wall_seconds": 3600,
        },
        "execution_defaults": {"concurrency": 1, "secret_references": []},
    }


def _action(root: Path, *, status: str = "pending", result=None) -> NativeAction:
    spec = {
        "schema": ACTION_SCHEMA,
        "id": ACTION_ID,
        "scope": {"kind": "workspace", "id": WORKSPACE_ID, "revision": 0},
        "kind": "clarify_design",
        "instructions": "Confirm the already-approved design intent.",
        "artifacts": [],
        "editable_root": str(root),
        "allowed_paths": ["autodata.workspace.json"],
        "outputs": ["summary", "decisions"],
        "remaining_budget": {"revisions": 4, "task_attempts": 8, "wall_seconds": 60},
    }
    return NativeAction(ACTION_ID, "clarify_design", status, spec, result)


class FakeControl:
    def __init__(self, root: Path, *, crash_after_complete: bool = False):
        self.action = _action(root)
        self.crash_after_complete = crash_after_complete
        self.begin_calls = 0
        self.complete_calls = 0
        self.read_calls = 0
        self.lease_token: str | None = None
        self.phase = "clarify_pending"
        self.revision = 0

    def read_workspace(self, workspace_id: str) -> NativeWorkspace:
        self.read_calls += 1
        return NativeWorkspace(
            workspace_id,
            "active",
            self.phase,
            self.revision,
            (self.action,),
        )

    def begin_action(self, action_id: str) -> ActionLease:
        self.begin_calls += 1
        self.lease_token = TOKEN
        self.action = _action(
            Path(self.action.spec["editable_root"]), status="in_progress"
        )
        return ActionLease(action_id, TOKEN, self.action.spec)

    def lease_matches(self, action_id: str, token: str) -> bool:
        return action_id == ACTION_ID and token == self.lease_token

    def validate_workspace(self, candidate: dict[str, Any]) -> dict[str, Any]:
        if candidate.get("schema") != "autodata.workspace/v1":
            raise AutoDataCoordinatorError(
                "candidate_workspace_invalid", "candidate fails native schema"
            )
        return json.loads(json.dumps(candidate))

    def complete_action(
        self, action_id: str, *, lease_token: str, result: dict[str, Any]
    ) -> None:
        self.complete_calls += 1
        assert action_id == ACTION_ID and lease_token == TOKEN
        self.action = _action(
            Path(self.action.spec["editable_root"]),
            status="completed",
            result=dict(result),
        )
        self.lease_token = None
        if self.crash_after_complete:
            self.crash_after_complete = False
            raise SystemExit("simulated process crash after native completion")


class FakeWorker:
    def __init__(self, backend: str, outcomes=None):
        self.backend_name = backend
        self.outcomes = list(outcomes or [])
        self.calls = 0
        self.contexts: list[ActionContext] = []

    async def perform(self, context: ActionContext) -> SemanticOutcome:
        self.calls += 1
        self.contexts.append(context)
        if self.outcomes:
            value = self.outcomes.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        return SemanticOutcome(
            context.action_id,
            context.input_revision,
            context.input_digest,
            "confirm",
            "Design confirmed",
            ("keep scope",),
            None,
        )


def _analysis_action(*, status: str = "pending", result=None) -> NativeAction:
    spec = {
        "schema": ACTION_SCHEMA,
        "id": ANALYSIS_ACTION_ID,
        "scope": {"kind": "execution", "id": EXECUTION_ID, "revision": 0},
        "kind": "analyze_results",
        "instructions": "Propose one scoped change from visible evidence.",
        "artifacts": [
            {
                "digest": "sha256:" + "5" * 64,
                "media_type": "application/json",
                "size": 123,
                "name": "visible-evaluation.json",
            }
        ],
        "editable_root": None,
        "allowed_paths": [],
        "outputs": ["proposal", "dashboard_summary"],
        "remaining_budget": {
            "iterations": 3,
            "task_attempts": 10,
            "wall_seconds": 60,
        },
    }
    return NativeAction(ANALYSIS_ACTION_ID, "analyze_results", status, spec, result)


class FakeAnalysisControl:
    def __init__(self) -> None:
        self.action = _analysis_action()
        self.begin_calls = 0
        self.complete_calls = 0
        self.lease_token: str | None = None
        self.phase = "awaiting_analysis"

    def read_execution(self, execution_id: str) -> NativeWorkspace:
        return NativeWorkspace(
            execution_id,
            "active",
            self.phase,
            0,
            (self.action,),
        )

    def read_json_artifact(self, _reference: dict[str, Any]) -> dict[str, Any]:
        return {"metrics": {"valid": 0.75, "challenge": 0.5}}

    def begin_action(self, action_id: str) -> ActionLease:
        self.begin_calls += 1
        self.lease_token = TOKEN
        self.action = _analysis_action(status="in_progress")
        return ActionLease(action_id, TOKEN, self.action.spec)

    def lease_matches(self, action_id: str, token: str) -> bool:
        return action_id == ANALYSIS_ACTION_ID and token == self.lease_token

    def complete_action(
        self, action_id: str, *, lease_token: str, result: dict[str, Any]
    ) -> None:
        self.complete_calls += 1
        assert action_id == ANALYSIS_ACTION_ID and lease_token == TOKEN
        self.action = _analysis_action(status="completed", result=dict(result))
        self.lease_token = None


class FakeAnalysisWorker:
    backend_name = "claude"

    def __init__(self, outcomes: list[object] | None = None) -> None:
        self.calls = 0
        self.contexts: list[AnalysisContext] = []
        self.outcomes = list(outcomes or [])

    async def perform(self, context: AnalysisContext) -> AnalysisOutcome:
        self.calls += 1
        self.contexts.append(context)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            assert isinstance(outcome, AnalysisOutcome)
            return outcome
        return AnalysisOutcome(
            action_id=context.action_id,
            input_revision=context.input_revision,
            input_digest=context.input_digest,
            proposal="Increase adversarial framing while preserving all other settings.",
            dashboard_summary={
                "headline": "Scoped framing change",
                "summary": "Visible challenge performance trails validity.",
                "next_step": "Evaluate one bounded candidate mutation.",
            },
        )


def _strategy() -> dict[str, Any]:
    return {
        "schema": "aar.autodata.generation-strategy/v2",
        "name": "baseline",
        "system_prompt": "Generate one grounded example.",
        "temperature": 0.5,
    }


def _mutation_action(
    root: Path, *, status: str = "pending", result=None
) -> NativeAction:
    spec = {
        "schema": ACTION_SCHEMA,
        "id": MUTATION_ACTION_ID,
        "scope": {"kind": "execution", "id": EXECUTION_ID, "revision": 1},
        "kind": "mutate_candidate",
        "instructions": "Strengthen the grounded generation instruction.",
        "artifacts": [],
        "editable_root": str(root),
        "allowed_paths": ["recipe/generation_strategy.json"],
        "outputs": ["summary"],
        "remaining_budget": {
            "iterations": 2,
            "task_attempts": 10,
            "wall_seconds": 60,
        },
    }
    return NativeAction(MUTATION_ACTION_ID, "mutate_candidate", status, spec, result)


class FakeMutationControl:
    def __init__(self, root: Path, *, crash_before_complete: bool = False) -> None:
        self.root = root
        self.action = _mutation_action(root)
        self.crash_before_complete = crash_before_complete
        self.begin_calls = 0
        self.complete_calls = 0
        self.lease_token: str | None = None

    def read_execution(self, execution_id: str) -> NativeWorkspace:
        return NativeWorkspace(
            execution_id,
            "active",
            "awaiting_mutation",
            1,
            (self.action,),
        )

    def begin_action(self, action_id: str) -> ActionLease:
        self.begin_calls += 1
        self.lease_token = TOKEN
        self.action = _mutation_action(self.root, status="in_progress")
        return ActionLease(action_id, TOKEN, self.action.spec)

    def lease_matches(self, action_id: str, token: str) -> bool:
        return action_id == MUTATION_ACTION_ID and token == self.lease_token

    def complete_action(
        self, action_id: str, *, lease_token: str, result: dict[str, Any]
    ) -> None:
        self.complete_calls += 1
        assert action_id == MUTATION_ACTION_ID and lease_token == TOKEN
        if self.crash_before_complete:
            self.crash_before_complete = False
            raise SystemExit("simulated crash after file replacement")
        self.action = _mutation_action(
            self.root, status="completed", result=dict(result)
        )
        self.lease_token = None


class FakeMutationWorker:
    backend_name = "claude"

    def __init__(self, outcomes: list[object] | None = None) -> None:
        self.calls = 0
        self.contexts: list[MutationContext] = []
        self.outcomes = list(outcomes or [])

    async def perform(self, context: MutationContext) -> MutationOutcome:
        self.calls += 1
        self.contexts.append(context)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            assert isinstance(outcome, MutationOutcome)
            return outcome
        updated = dict(context.current_document)
        updated["system_prompt"] = "Generate one grounded, adversarial example."
        return MutationOutcome(
            action_id=context.action_id,
            input_revision=context.input_revision,
            input_digest=context.input_digest,
            summary="Strengthened the grounded adversarial instruction.",
            updated_document=updated,
        )


def _mutation_fixture(tmp_path: Path) -> tuple[Path, Path]:
    team = tmp_path / "team"
    root = tmp_path / "candidate"
    target = root / "recipe" / "generation_strategy.json"
    team.mkdir()
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(_strategy()), encoding="utf-8")
    return team, root


def _mutation_reconciler(
    team: Path,
    control: FakeMutationControl,
    worker: FakeMutationWorker,
) -> ExecutionMutationReconciler:
    return ExecutionMutationReconciler(
        control=control,
        worker=worker,
        team_dir=team,
        action_timeout_seconds=0.2,
        malformed_output_attempts=3,
    )


def test_execution_mutation_replaces_only_allowlisted_document(
    tmp_path: Path,
) -> None:
    team, root = _mutation_fixture(tmp_path)
    unrelated = root / "recipe" / "unchanged.txt"
    unrelated.write_text("preserve me\n", encoding="utf-8")
    control = FakeMutationControl(root)
    worker = FakeMutationWorker()

    outcome = asyncio.run(
        _mutation_reconciler(team, control, worker).coordinate_mutation(
            EXECUTION_ID, MUTATION_ACTION_ID
        )
    )

    strategy = json.loads(
        (root / "recipe" / "generation_strategy.json").read_text()
    )
    assert strategy["system_prompt"] == "Generate one grounded, adversarial example."
    assert unrelated.read_text() == "preserve me\n"
    assert control.begin_calls == control.complete_calls == worker.calls == 1
    assert worker.contexts[0].editable_path == "recipe/generation_strategy.json"
    assert not hasattr(worker.contexts[0], "lease")
    receipt = json.loads(outcome.receipt_path.read_text())
    assert receipt["action_kind"] == "mutate_candidate"
    assert receipt["editable_path"] == "recipe/generation_strategy.json"
    assert TOKEN not in outcome.receipt_path.read_text()


def test_execution_mutation_retries_stale_outcome_without_rebegin(
    tmp_path: Path,
) -> None:
    team, root = _mutation_fixture(tmp_path)
    stale = MutationOutcome(
        action_id="act_" + "9" * 24,
        input_revision=1,
        input_digest="sha256:" + "0" * 64,
        summary="Stale",
        updated_document={**_strategy(), "temperature": 0.6},
    )
    control = FakeMutationControl(root)
    worker = FakeMutationWorker([stale])

    asyncio.run(
        _mutation_reconciler(team, control, worker).coordinate_mutation(
            EXECUTION_ID, MUTATION_ACTION_ID
        )
    )

    assert control.begin_calls == control.complete_calls == 1
    assert worker.calls == 2


def test_execution_mutation_resumes_after_file_write_without_worker_reinvoke(
    tmp_path: Path,
) -> None:
    team, root = _mutation_fixture(tmp_path)
    control = FakeMutationControl(root, crash_before_complete=True)
    first_worker = FakeMutationWorker()

    with pytest.raises(SystemExit, match="simulated crash"):
        asyncio.run(
            _mutation_reconciler(team, control, first_worker).coordinate_mutation(
                EXECUTION_ID, MUTATION_ACTION_ID
            )
        )

    resumed_worker = FakeMutationWorker()
    outcome = asyncio.run(
        _mutation_reconciler(team, control, resumed_worker).coordinate_mutation(
            EXECUTION_ID, MUTATION_ACTION_ID
        )
    )

    assert control.begin_calls == 1
    assert control.complete_calls == 2
    assert first_worker.calls == 1
    assert resumed_worker.calls == 0
    assert outcome.receipt_path.is_file()


def test_execution_mutation_rejects_any_other_editable_path(tmp_path: Path) -> None:
    team, root = _mutation_fixture(tmp_path)
    control = FakeMutationControl(root)
    spec = dict(control.action.spec)
    spec["allowed_paths"] = ["recipe/generation_strategy.json", "recipe/task.py"]
    control.action = NativeAction(
        MUTATION_ACTION_ID, "mutate_candidate", "pending", spec, None
    )

    with pytest.raises(
        AutoDataCoordinatorError, match="mutate_candidate contract is inconsistent"
    ):
        asyncio.run(
            _mutation_reconciler(
                team, control, FakeMutationWorker()
            ).coordinate_mutation(EXECUTION_ID, MUTATION_ACTION_ID)
        )

    assert control.begin_calls == 0


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    team = tmp_path / "team"
    draft = tmp_path / "draft"
    team.mkdir()
    draft.mkdir()
    (draft / "autodata.workspace.json").write_text(
        json.dumps(_workspace()), encoding="utf-8"
    )
    return team, draft


def _reconciler(
    team: Path, control: FakeControl, worker: FakeWorker, *, attempts: int = 3
) -> AutoDataActionReconciler:
    return AutoDataActionReconciler(
        control=control,
        worker=worker,
        team_dir=team,
        action_timeout_seconds=0.2,
        malformed_output_attempts=attempts,
    )


def _analysis_reconciler(
    team: Path,
    control: FakeAnalysisControl,
    worker: FakeAnalysisWorker,
    *,
    attempts: int = 3,
) -> ExecutionAnalysisReconciler:
    return ExecutionAnalysisReconciler(
        control=control,
        worker=worker,
        team_dir=team,
        action_timeout_seconds=0.2,
        malformed_output_attempts=attempts,
    )


def test_execution_analysis_is_leased_once_and_completed_by_host(
    tmp_path: Path,
) -> None:
    team = tmp_path / "team"
    team.mkdir()
    control = FakeAnalysisControl()
    worker = FakeAnalysisWorker()

    outcome = asyncio.run(
        _analysis_reconciler(team, control, worker).coordinate_analysis(
            EXECUTION_ID, ANALYSIS_ACTION_ID
        )
    )

    assert control.begin_calls == control.complete_calls == worker.calls == 1
    assert outcome.native_phase == "awaiting_analysis"
    assert worker.contexts[0].evidence == (
        {"metrics": {"valid": 0.75, "challenge": 0.5}},
    )
    assert not hasattr(worker.contexts[0], "lease")
    receipt = json.loads(outcome.receipt_path.read_text(encoding="utf-8"))
    assert receipt["subject_kind"] == "execution"
    assert receipt["execution_id"] == EXECUTION_ID
    assert receipt["action_kind"] == "analyze_results"
    assert TOKEN not in outcome.receipt_path.read_text(encoding="utf-8")


def test_execution_analysis_retries_malformed_output_without_rebegin(
    tmp_path: Path,
) -> None:
    team = tmp_path / "team"
    team.mkdir()
    control = FakeAnalysisControl()
    wrong = AnalysisOutcome(
        action_id="act_" + "9" * 24,
        input_revision=0,
        input_digest="sha256:" + "0" * 64,
        proposal="Stale proposal",
        dashboard_summary={
            "headline": "Stale",
            "summary": "Stale",
            "next_step": "Stop",
        },
    )
    worker = FakeAnalysisWorker([wrong])

    asyncio.run(
        _analysis_reconciler(team, control, worker).coordinate_analysis(
            EXECUTION_ID, ANALYSIS_ACTION_ID
        )
    )

    assert control.begin_calls == 1
    assert control.complete_calls == 1
    assert worker.calls == 2


def test_execution_analysis_resumes_in_progress_with_protected_lease(
    tmp_path: Path,
) -> None:
    team = tmp_path / "team"
    team.mkdir()
    control = FakeAnalysisControl()
    control.action = _analysis_action(status="in_progress")
    control.lease_token = TOKEN
    worker = FakeAnalysisWorker()
    lease = team / "autodata" / "action-leases" / f"{ANALYSIS_ACTION_ID}.token"
    lease.parent.mkdir(parents=True)
    lease.write_text(TOKEN + "\n", encoding="utf-8")
    lease.chmod(0o600)

    asyncio.run(
        _analysis_reconciler(team, control, worker).coordinate_analysis(
            EXECUTION_ID, ANALYSIS_ACTION_ID
        )
    )

    assert control.begin_calls == 0
    assert control.complete_calls == worker.calls == 1


def test_execution_analysis_fails_closed_without_durable_lease(
    tmp_path: Path,
) -> None:
    team = tmp_path / "team"
    team.mkdir()
    control = FakeAnalysisControl()
    control.action = _analysis_action(status="in_progress")
    control.lease_token = TOKEN
    worker = FakeAnalysisWorker()

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(
            _analysis_reconciler(team, control, worker).coordinate_analysis(
                EXECUTION_ID, ANALYSIS_ACTION_ID
            )
        )

    assert raised.value.code == "action_lease_missing"
    assert worker.calls == 0


def test_backend_neutral_worker_contract_confirms(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    worker = FakeWorker("claude")

    outcome = asyncio.run(
        _reconciler(team, control, worker).coordinate_clarify_design(WORKSPACE_ID)
    )

    assert control.begin_calls == control.complete_calls == worker.calls == 1
    assert outcome.native_phase == "clarify_pending"
    assert outcome.native_revision == 0
    receipt = outcome.receipt_path.read_text()
    assert "claude" in receipt
    assert TOKEN not in receipt
    assert worker.contexts[0].workspace == _workspace()
    assert not hasattr(worker.contexts[0], "lease")


def test_update_candidate_is_host_validated_and_applied(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)

    async def update(context: ActionContext) -> SemanticOutcome:
        candidate = json.loads(json.dumps(context.workspace))
        candidate["goal"] = "clarified goal"
        return SemanticOutcome(
            context.action_id,
            context.input_revision,
            context.input_digest,
            "update",
            "Goal clarified",
            ("use clarified goal",),
            candidate,
        )

    worker = FakeWorker("claude")
    worker.perform = update  # type: ignore[method-assign]
    asyncio.run(
        _reconciler(team, control, worker).coordinate_clarify_design(WORKSPACE_ID)
    )

    assert (
        json.loads((draft / "autodata.workspace.json").read_text())["goal"]
        == "clarified goal"
    )
    stage = json.loads((team / f"autodata/action-results/{ACTION_ID}.json").read_text())
    assert stage["action_id"] == ACTION_ID
    assert stage["input_revision"] == 0
    assert stage["candidate_digest"].startswith("sha256:")


def test_worker_workspace_mutation_cannot_change_trusted_input(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    worker = FakeWorker("claude")

    async def mutate_received(context: ActionContext) -> SemanticOutcome:
        assert isinstance(context.workspace, dict)
        context.workspace["goal"] = "untrusted mutation"
        return SemanticOutcome(
            context.action_id,
            context.input_revision,
            context.input_digest,
            "confirm",
            "Confirmed without update",
            (),
            None,
        )

    worker.perform = mutate_received  # type: ignore[method-assign]
    asyncio.run(
        _reconciler(team, control, worker).coordinate_clarify_design(WORKSPACE_ID)
    )

    assert (
        json.loads((draft / "autodata.workspace.json").read_text())["goal"]
        == "original goal"
    )


def test_tampered_receipt_fails_closed_without_worker(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    worker = FakeWorker("claude")
    reconciler = _reconciler(team, control, worker)
    first = asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))
    stale = json.loads(first.receipt_path.read_text())
    stale["native_phase_observed"] = "tampered"
    first.receipt_path.write_text(json.dumps(stale))

    tampered_bytes = first.receipt_path.read_bytes()
    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))

    assert raised.value.code == "clarify_receipt_invalid"
    assert first.receipt_path.read_bytes() == tampered_bytes
    assert worker.calls == 1


def test_later_native_state_preserves_immutable_clarify_receipt(
    tmp_path: Path,
) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    worker = FakeWorker("claude")
    reconciler = _reconciler(team, control, worker)
    outcome = asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))
    original = outcome.receipt_path.read_bytes()
    unrelated = outcome.receipt_path.with_name("act_" + "f" * 24 + ".json")
    unrelated.write_text(
        json.dumps(
            {
                "schema": "aar.autodata.coordinator-receipt/v1",
                "workspace_id": WORKSPACE_ID,
                "action_id": "act_" + "f" * 24,
                "action_kind": "author_pipeline",
            }
        )
    )
    unrelated.chmod(0o600)
    control.phase = "grounding_pending"
    control.revision = 1
    control_file = tmp_path / "control.json"
    control_file.write_text(
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
        )
    )

    progress = asyncio.run(reconciler.reconcile_registered_clarify(control_file))

    assert progress is None
    assert outcome.receipt_path.read_bytes() == original
    assert worker.calls == 1


def test_tampered_workspace_rejects_existing_receipt(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    worker = FakeWorker("claude")
    reconciler = _reconciler(team, control, worker)
    asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))
    workspace = json.loads((draft / "autodata.workspace.json").read_text())
    workspace["goal"] = "tampered at same revision"
    (draft / "autodata.workspace.json").write_text(json.dumps(workspace))

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))

    assert raised.value.code == "completed_workspace_mismatch"
    assert worker.calls == 1


def test_tampered_staged_confirmation_candidate_fails_closed(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    worker = FakeWorker("claude")
    reconciler = _reconciler(team, control, worker)
    asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))
    stage_path = team / f"autodata/action-results/{ACTION_ID}.json"
    stage = json.loads(stage_path.read_text())
    stage["updated_workspace"] = _workspace()
    stage["candidate_digest"] = _json_digest(stage["updated_workspace"])
    stage_path.write_text(json.dumps(stage))

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))

    assert raised.value.code == "semantic_stage_invalid"
    assert worker.calls == 1


def test_tampered_staged_update_is_revalidated_by_native_schema(
    tmp_path: Path,
) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    worker = FakeWorker("claude")

    async def update(context: ActionContext) -> SemanticOutcome:
        candidate = json.loads(json.dumps(context.workspace))
        candidate["goal"] = "clarified goal"
        return SemanticOutcome(
            context.action_id,
            context.input_revision,
            context.input_digest,
            "update",
            "Goal clarified",
            (),
            candidate,
        )

    worker.perform = update  # type: ignore[method-assign]
    reconciler = _reconciler(team, control, worker)
    asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))
    stage_path = team / f"autodata/action-results/{ACTION_ID}.json"
    stage = json.loads(stage_path.read_text())
    stage["updated_workspace"]["schema"] = "tampered.workspace/v1"
    stage["candidate_digest"] = _json_digest(stage["updated_workspace"])
    stage_path.write_text(json.dumps(stage))

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))

    assert raised.value.code == "semantic_stage_invalid"


def test_malformed_output_retries_with_one_native_begin(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    wrong = SemanticOutcome(
        "act_" + "9" * 24,
        0,
        "sha256:" + "0" * 64,
        "confirm",
        "Wrong binding",
        (),
        None,
    )
    worker = FakeWorker("claude", [wrong])

    asyncio.run(
        _reconciler(team, control, worker).coordinate_clarify_design(WORKSPACE_ID)
    )

    assert worker.calls == 2
    assert control.begin_calls == 1


def test_in_progress_matching_protected_lease_resumes_without_begin(
    tmp_path: Path,
) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    control.action = _action(draft, status="in_progress")
    control.lease_token = TOKEN
    lease = team / f"autodata/action-leases/{ACTION_ID}.token"
    lease.parent.mkdir(parents=True)
    lease.write_text(TOKEN + "\n")
    lease.chmod(0o600)
    worker = FakeWorker("claude")

    asyncio.run(
        _reconciler(team, control, worker).coordinate_clarify_design(WORKSPACE_ID)
    )

    assert control.begin_calls == 0
    assert worker.calls == 1


@pytest.mark.parametrize("token", [None, "wrong-protected-action-lease-token"])
def test_in_progress_missing_or_mismatched_lease_fails_without_worker(
    tmp_path: Path, token: str | None
) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    control.action = _action(draft, status="in_progress")
    control.lease_token = TOKEN
    if token is not None:
        lease = team / f"autodata/action-leases/{ACTION_ID}.token"
        lease.parent.mkdir(parents=True)
        lease.write_text(token + "\n")
        lease.chmod(0o600)
    worker = FakeWorker("claude")

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(
            _reconciler(team, control, worker).coordinate_clarify_design(WORKSPACE_ID)
        )

    assert raised.value.code in {"action_lease_missing", "action_lease_mismatch"}
    assert worker.calls == 0


def test_crash_after_native_completion_recovers_without_worker_reinvoke(
    tmp_path: Path,
) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft, crash_after_complete=True)
    worker = FakeWorker("claude")
    reconciler = _reconciler(team, control, worker)

    with pytest.raises(SystemExit):
        asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))
    outcome = asyncio.run(reconciler.coordinate_clarify_design(WORKSPACE_ID))

    assert outcome.action_id == ACTION_ID
    assert worker.calls == 1
    assert control.begin_calls == control.complete_calls == 1


def test_missing_action_reads_once_without_model_busy_wait(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    control.action = NativeAction(
        ACTION_ID, "clarify_design", "cancelled", control.action.spec
    )
    worker = FakeWorker("claude")

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(
            _reconciler(team, control, worker).coordinate_clarify_design(WORKSPACE_ID)
        )

    assert raised.value.code == "clarify_action_missing"
    assert control.read_calls == 1
    assert worker.calls == 0


def test_multiple_live_actions_fail_closed(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    original = control.read_workspace

    def multiple(workspace_id: str) -> NativeWorkspace:
        value = original(workspace_id)
        other = NativeAction(
            "act_" + "3" * 24,
            "author_grounding",
            "pending",
            {
                **control.action.spec,
                "id": "act_" + "3" * 24,
                "kind": "author_grounding",
            },
        )
        return NativeWorkspace(
            value.id, value.status, value.phase, value.revision, (control.action, other)
        )

    control.read_workspace = multiple  # type: ignore[method-assign]
    with pytest.raises(AutoDataCoordinatorError, match="multiple"):
        asyncio.run(
            _reconciler(team, control, FakeWorker("claude")).coordinate_clarify_design(
                WORKSPACE_ID
            )
        )


def test_non_clarify_action_is_not_dispatched_to_worker(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    control.action = NativeAction(
        ACTION_ID,
        "author_grounding",
        "pending",
        {**control.action.spec, "kind": "author_grounding"},
    )
    worker = FakeWorker("claude")

    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(
            _reconciler(team, control, worker).coordinate_clarify_design(WORKSPACE_ID)
        )

    assert raised.value.code == "unexpected_pending_action"
    assert worker.calls == 0


def test_worker_timeout_is_typed(tmp_path: Path) -> None:
    team, draft = _fixture(tmp_path)
    control = FakeControl(draft)
    worker = FakeWorker("claude")

    async def slow(_context: ActionContext) -> SemanticOutcome:
        await asyncio.sleep(1)
        raise AssertionError

    worker.perform = slow  # type: ignore[method-assign]
    with pytest.raises(AutoDataCoordinatorError) as raised:
        asyncio.run(
            _reconciler(team, control, worker).coordinate_clarify_design(WORKSPACE_ID)
        )
    assert raised.value.code == "semantic_worker_timeout"
    assert raised.value.retryable is True


def test_native_mapping_json_failure_is_typed() -> None:
    with pytest.raises(AutoDataCoordinatorError) as raised:
        NativeAutoDataControl._mapping("{not-json")
    assert raised.value.code == "native_state_invalid"


def test_native_execution_status_joins_flat_cli_state_with_action_rows(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state.db"
    spec = _analysis_action().spec
    with sqlite3.connect(state) as connection:
        connection.execute(
            "CREATE TABLE actions("
            "id TEXT,kind TEXT,status TEXT,specJson TEXT,resultJson TEXT,"
            "scopeKind TEXT,scopeId TEXT,createdAt TEXT)"
        )
        connection.execute(
            "INSERT INTO actions VALUES(?,?,?,?,?,?,?,?)",
            (
                ANALYSIS_ACTION_ID,
                "analyze_results",
                "pending",
                json.dumps(spec),
                None,
                "execution",
                EXECUTION_ID,
                "2026-10-12T00:00:00Z",
            ),
        )
    artifacts = tmp_path / "artifacts"
    workspaces = tmp_path / "workspaces"
    temporary = tmp_path / "temporary"
    for path in (artifacts, workspaces, temporary):
        path.mkdir()
    control = NativeAutoDataControl(
        python=Path(sys.executable),
        wrapper=tmp_path / "autodata.py",
        state=state,
        artifacts=artifacts,
        workspaces=workspaces,
        temporary_root=temporary,
    )
    control._run = lambda *_args: {  # type: ignore[method-assign]
        "execution_id": EXECUTION_ID,
        "status": "active",
        "phase": "awaiting_analysis",
        "revision": 0,
        "pending_action": {
            "id": ANALYSIS_ACTION_ID,
            "kind": "analyze_results",
            "status": "pending",
            "revision": 0,
        },
    }

    snapshot = control.read_execution(EXECUTION_ID)

    assert snapshot.id == EXECUTION_ID
    assert snapshot.phase == "awaiting_analysis"
    assert snapshot.actions == (_analysis_action(),)


def test_claude_worker_is_tool_free_and_hides_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, Any] = {}

    class Agent:
        async def execute(self, task: str):
            observed["task"] = task
            observed["capability"] = os.getenv("AAR_AUTODATA_CAPABILITY")
            payload = json.loads(task.split("ACTION:\n", 1)[1])
            return type(
                "Response",
                (),
                {
                    "success": True,
                    "output": {
                        "text_outputs": [
                            json.dumps(
                                {
                                    "action_id": payload["action_id"],
                                    "input_revision": payload["input_revision"],
                                    "input_digest": payload["input_digest"],
                                    "decision": "confirm",
                                    "summary": "Confirmed",
                                    "decisions": [],
                                    "updated_workspace": None,
                                }
                            )
                        ]
                    },
                },
            )()

    context = ActionContext(
        ACTION_ID,
        WORKSPACE_ID,
        0,
        "sha256:" + "a" * 64,
        "Confirm",
        ("autodata.workspace.json",),
        ("summary", "decisions"),
        _workspace(),
    )
    monkeypatch.setenv("AAR_AUTODATA_CAPABILITY", "secret")
    outcome = asyncio.run(
        ClaudeWorker(agent_factory=lambda _: Agent()).perform(context)
    )

    assert outcome.decision == "confirm"
    assert observed["capability"] is None
    assert "lease" not in str(observed["task"]).lower()
    assert os.environ["AAR_AUTODATA_CAPABILITY"] == "secret"


def test_claude_worker_returns_typed_mutation_outcome() -> None:
    class Agent:
        async def execute(self, task: str):
            payload = json.loads(task.split("ACTION:\n", 1)[1])
            updated = dict(payload["current_document"])
            updated["temperature"] = 0.4
            return type(
                "Response",
                (),
                {
                    "success": True,
                    "output": {
                        "text_outputs": [
                            json.dumps(
                                {
                                    "action_id": payload["action_id"],
                                    "input_revision": payload["input_revision"],
                                    "input_digest": payload["input_digest"],
                                    "summary": "Reduced sampling temperature.",
                                    "updated_document": updated,
                                }
                            )
                        ]
                    },
                },
            )()

    context = MutationContext(
        MUTATION_ACTION_ID,
        EXECUTION_ID,
        1,
        "sha256:" + "a" * 64,
        "Make one scoped change.",
        "recipe/generation_strategy.json",
        _strategy(),
    )

    outcome = asyncio.run(
        ClaudeWorker(agent_factory=lambda _: Agent()).perform(context)
    )

    assert isinstance(outcome, MutationOutcome)
    assert outcome.updated_document["temperature"] == 0.4
    assert "lease" not in ClaudeWorker._task(context).lower()


def test_kimi_worker_is_one_turn_tool_free_and_hides_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = tmp_path / "capture.json"
    cli = tmp_path / "kimi"
    cli.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "prompt = args[args.index('--prompt') + 1]\n"
        "payload = json.loads(prompt.split('ACTION:\\n', 1)[1])\n"
        "home = Path(os.environ['KIMI_CODE_HOME'])\n"
        f"Path({str(capture)!r}).write_text(json.dumps({{\n"
        "  'args': args,\n"
        "  'cwd': os.getcwd(),\n"
        "  'mcp': json.loads((home / 'mcp.json').read_text()),\n"
        "  'profile': Path(args[args.index('--agent-file') + 1]).read_text(),\n"
        "  'capability': os.environ.get('AAR_AUTODATA_CAPABILITY'),\n"
        "  'autodata': os.environ.get('AAR_AUTODATA'),\n"
        "  'resume': os.environ.get('AAR_RESUME_APPROVED_PROPOSAL'),\n"
        "}))\n"
        "print(json.dumps({'role': 'assistant', 'content': json.dumps({\n"
        "  'action_id': payload['action_id'],\n"
        "  'input_revision': payload['input_revision'],\n"
        "  'input_digest': payload['input_digest'],\n"
        "  'decision': 'confirm',\n"
        "  'summary': 'Confirmed',\n"
        "  'decisions': [],\n"
        "  'updated_workspace': None,\n"
        "})}))\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    context = ActionContext(
        ACTION_ID,
        WORKSPACE_ID,
        0,
        "sha256:" + "a" * 64,
        "Confirm",
        ("autodata.workspace.json",),
        ("summary", "decisions"),
        _workspace(),
    )
    monkeypatch.setenv("AAR_AUTODATA_CAPABILITY", "secret")
    monkeypatch.setenv("AAR_AUTODATA", "1")
    monkeypatch.setenv("AAR_RESUME_APPROVED_PROPOSAL", "1")
    monkeypatch.delenv("AAR_KIMI_SERVE_DEPLOYMENT", raising=False)

    outcome = asyncio.run(KimiWorker(cli_path=str(cli)).perform(context))

    observed = json.loads(capture.read_text())
    assert outcome.decision == "confirm"
    assert observed["mcp"] == {"mcpServers": {}}
    assert observed["cwd"] == str(Path(observed["args"][1]).parent)
    assert "--continue" not in observed["args"]
    assert "--skills-dir" not in observed["args"]
    assert "disallowedTools:" in observed["profile"]
    assert observed["capability"] is None
    assert observed["autodata"] is None
    assert observed["resume"] is None
    assert os.environ["AAR_AUTODATA_CAPABILITY"] == "secret"


def test_kimi_worker_preserves_only_explicit_deployment_registry_locators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, str] = {}
    monkeypatch.setenv("SLURM_CLUSTER_NAME", "fair-cw-use2-1")
    monkeypatch.setenv("V2_DEPLOYMENTS_ROOT", "/checkpoint/ram/shared/vllm_deployments_v2")
    monkeypatch.setenv("AAR_AUTODATA_CAPABILITY", "secret")
    monkeypatch.setattr(
        "aar.infrastructure.autodata_coordinator.kimi_worker.KimiAgent.configure_serve_api_provider",
        lambda env: observed.update(env),
    )

    environment = KimiWorker._environment(tmp_path)

    assert observed["SLURM_CLUSTER_NAME"] == "fair-cw-use2-1"
    assert observed["V2_DEPLOYMENTS_ROOT"] == "/checkpoint/ram/shared/vllm_deployments_v2"
    assert environment["KIMI_CODE_HOME"] == str(tmp_path)
    assert "AAR_AUTODATA_CAPABILITY" not in environment


def test_kimi_worker_rejects_any_tool_call() -> None:
    class ToolCallingWorker(KimiWorker):
        async def _execute(self, _task: str) -> dict[str, Any]:
            return {"tool_uses": [{"function": {"name": "Read"}}]}

    context = ActionContext(
        ACTION_ID,
        WORKSPACE_ID,
        0,
        "sha256:" + "a" * 64,
        "Confirm",
        ("autodata.workspace.json",),
        ("summary", "decisions"),
        _workspace(),
    )

    with pytest.raises(MalformedSemanticOutcome, match="forbidden tool"):
        asyncio.run(ToolCallingWorker().perform(context))


def test_real_native_workspace_confirm_and_receipt(tmp_path: Path) -> None:
    root_raw = os.getenv("AAR_TEST_AUTODATA_ROOT", "").strip()
    if not root_raw:
        pytest.skip("set AAR_TEST_AUTODATA_ROOT to the reviewed native checkout")
    root = Path(root_raw).resolve(strict=True)
    wrapper = root / "plugin/autodata/scripts/autodata.py"
    draft = tmp_path / "draft"
    shutil.copytree(root / "recipes/toy", draft)
    state = tmp_path / "state.db"
    artifacts = tmp_path / "artifacts"
    workspaces = tmp_path / "workspaces"
    command = [
        sys.executable,
        str(wrapper),
        "--state",
        str(state),
        "--artifacts",
        str(artifacts),
        "--workspaces",
        str(workspaces),
    ]
    created = subprocess.run(
        [
            *command,
            "workspace",
            "create",
            "--brief",
            str(draft / "autodata.workspace.json"),
            "--root",
            str(draft),
            "--idempotency-key",
            "coordinator-claude",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    workspace_id = json.loads(created.stdout)["workspace_id"]
    subprocess.run(
        [*command, "workspace", "step", workspace_id],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    control = NativeAutoDataControl(
        python=Path(sys.executable),
        wrapper=wrapper,
        state=state,
        artifacts=artifacts,
        workspaces=workspaces,
        temporary_root=tmp_path / "native-results",
    )
    team = tmp_path / "team"
    team.mkdir()
    outcome = asyncio.run(
        AutoDataActionReconciler(
            control=control,
            worker=FakeWorker("claude"),
            team_dir=team,
        ).coordinate_clarify_design(workspace_id)
    )

    after = control.read_workspace(workspace_id)
    assert outcome.native_phase == after.phase == "clarify_pending"
    assert any(action.status == "completed" for action in after.actions)
    receipt = json.loads(outcome.receipt_path.read_text())
    assert receipt["native_phase_observed"] == "clarify_pending"
    assert receipt["native_revision_observed"] == 0
    assert TOKEN not in outcome.receipt_path.read_text()
