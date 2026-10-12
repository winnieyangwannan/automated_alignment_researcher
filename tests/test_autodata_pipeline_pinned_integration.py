from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

from aar.infrastructure.autodata_coordinator.coordinator import (
    ActionLease,
    NativeAction,
    NativeWorkspace,
    WorkspaceGroundingReconciler,
    WorkspacePipelineReconciler,
)
from aar.infrastructure.autodata_coordinator.semantic_worker import (
    ActionContext,
    SemanticOutcome,
)

PIN = "51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1"
CHECKOUT = os.getenv("AAR_AUTODATA_PINNED_CHECKOUT", "").strip()

pytestmark = pytest.mark.skipif(
    not CHECKOUT,
    reason="set AAR_AUTODATA_PINNED_CHECKOUT to an exact detached AutoData pin",
)


class ConfirmWorker:
    backend_name = "claude"

    async def perform(self, context: ActionContext) -> SemanticOutcome:
        return SemanticOutcome(
            context.action_id,
            context.input_revision,
            context.input_digest,
            "confirm",
            "The staged toy pipeline is complete.",
            ("Keep every pipeline file byte-identical.",),
            None,
        )


class StoreControl:
    def __init__(self, store: Any) -> None:
        self.store = store

    def read_workspace(self, workspace_id: str) -> NativeWorkspace:
        row = self.store.get_workspace(workspace_id)
        actions = []
        for summary in self.store.list_actions("workspace", workspace_id):
            action = self.store.get_action(summary["id"])
            actions.append(
                NativeAction(
                    id=str(action["id"]),
                    kind=str(action["kind"]),
                    status=str(action["status"]),
                    spec=json.loads(str(action["specJson"])),
                    result=(
                        None
                        if action["resultJson"] is None
                        else json.loads(str(action["resultJson"]))
                    ),
                )
            )
        return NativeWorkspace(
            id=str(row["id"]),
            status=str(row["status"]),
            phase=str(row["phase"]),
            revision=int(row["revision"]),
            actions=tuple(actions),
        )

    def begin_action(self, action_id: str) -> ActionLease:
        action = self.store.get_action(action_id)
        begun = self.store.begin_action(
            action_id, expected_revision=int(action["scopeRevision"])
        )
        return ActionLease(
            action_id,
            str(begun["leaseToken"]),
            json.loads(str(action["specJson"])),
        )

    def lease_matches(self, action_id: str, token: str) -> bool:
        action = self.store.get_action(action_id)
        return action["leaseTokenHash"] == hashlib.sha256(token.encode()).hexdigest()

    def validate_workspace(self, candidate: Mapping[str, Any]) -> Mapping[str, Any]:
        return candidate

    def complete_action(
        self, action_id: str, *, lease_token: str, result: Mapping[str, Any]
    ) -> None:
        self.store.complete_action(
            action_id, lease_token=lease_token, result=result
        )


def _complete(store: Any, action: Any, result: Mapping[str, Any]) -> None:
    begun = store.begin_action(action.id, expected_revision=action.scope.revision)
    store.complete_action(
        action.id, lease_token=begun["leaseToken"], result=result
    )


def test_confirm_pipeline_with_exact_pinned_native_engine(tmp_path: Path) -> None:
    checkout = Path(CHECKOUT).resolve(strict=True)
    head = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head == PIN
    assert subprocess.run(
        ["git", "-C", str(checkout), "symbolic-ref", "-q", "HEAD"],
        check=False,
        capture_output=True,
    ).returncode != 0
    assert not subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert not any(name == "autodata" or name.startswith("autodata.") for name in sys.modules)

    sys.path.insert(0, str(checkout / "src"))
    support_name = "_pinned_autodata_test_support"
    try:
        from autodata.artifacts import FileArtifactStore
        from autodata.models import load_workspace
        from autodata.sqlite_store import SQLiteStateStore
        from autodata.workspace import WorkspaceEngine

        spec = importlib.util.spec_from_file_location(
            support_name, checkout / "tests" / "support.py"
        )
        assert spec is not None and spec.loader is not None
        support = importlib.util.module_from_spec(spec)
        sys.modules[support_name] = support
        spec.loader.exec_module(support)

        team = tmp_path / "team"
        draft = team / "autodata" / "pinned-integration" / "draft"
        shutil.copytree(checkout / "recipes" / "toy", draft)
        store = SQLiteStateStore(tmp_path / "state.db")
        engine = WorkspaceEngine.create(
            store,
            FileArtifactStore(tmp_path / "artifacts"),
            support.DirectTestExecutor(),
            support.DirectTestExecutor(),
            load_workspace(draft / "autodata.workspace.json"),
            root=draft,
            internal_root=tmp_path / "internal",
            idempotency_key="aar-pinned-author-pipeline",
        )
        clarify = engine.step()
        assert clarify.kind == "clarify_design"
        _complete(store, clarify, {"summary": "confirmed", "decisions": []})
        grounding = engine.step()
        assert grounding.kind == "author_grounding"
        grounding_before = {
            path.relative_to(draft).as_posix(): path.read_bytes()
            for path in draft.rglob("*")
            if path.is_file() and ".autodata" not in path.parts
        }
        grounding_outcome = asyncio.run(
            WorkspaceGroundingReconciler(
                control=StoreControl(store),
                worker=ConfirmWorker(),
                team_dir=team,
                action_timeout_seconds=5,
                malformed_output_attempts=1,
            ).coordinate_grounding(engine.workspace_id)
        )
        assert grounding_outcome.action_id == grounding.id
        assert (
            json.loads(grounding_outcome.receipt_path.read_text())["changed_paths"]
            == []
        )
        assert grounding_before == {
            path.relative_to(draft).as_posix(): path.read_bytes()
            for path in draft.rglob("*")
            if path.is_file() and ".autodata" not in path.parts
        }
        approval = engine.step()
        assert approval.kind == "approve_grounding"
        _complete(
            store,
            approval,
            {"decision": "approve", "user_acknowledged": True},
        )
        pipeline = engine.step()
        assert pipeline.kind == "author_pipeline"
        before = {
            path.relative_to(draft).as_posix(): path.read_bytes()
            for path in draft.rglob("*")
            if path.is_file() and ".autodata" not in path.parts
        }

        outcome = asyncio.run(
            WorkspacePipelineReconciler(
                control=StoreControl(store),
                worker=ConfirmWorker(),
                team_dir=team,
                action_timeout_seconds=5,
                malformed_output_attempts=1,
            ).coordinate_pipeline(engine.workspace_id)
        )
        assert outcome.action_id == pipeline.id
        assert json.loads(outcome.receipt_path.read_text())["changed_paths"] == []
        assert before == {
            path.relative_to(draft).as_posix(): path.read_bytes()
            for path in draft.rglob("*")
            if path.is_file() and ".autodata" not in path.parts
        }

        approval = engine.step()
        workspace = store.get_workspace(engine.workspace_id)
        assert approval.kind == "approve_baseline"
        assert workspace["phase"] == "baseline_review"
        assert int(workspace["revision"]) > pipeline.scope.revision
    finally:
        sys.path.remove(str(checkout / "src"))
        sys.modules.pop(support_name, None)
        for name in list(sys.modules):
            if name == "autodata" or name.startswith("autodata."):
                sys.modules.pop(name, None)
