from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from aar.research_loop.agent import AutonomousAgentLoop
from aar.research_loop.autodata_bootstrap import (
    BOOTSTRAP_SCHEMA,
    ensure_workspace,
)


def _environment(tmp_path: Path) -> dict[str, str]:
    team = tmp_path / "team"
    recipe = tmp_path / "recipe"
    plugin = tmp_path / "plugin"
    artifacts = team / "autodata" / "native" / "artifacts"
    workspaces = team / "autodata" / "native" / "workspaces"
    for path in (team, recipe, plugin / "scripts", artifacts, workspaces):
        path.mkdir(parents=True, exist_ok=True)
    (plugin / "scripts" / "autodata.py").write_text("# wrapper\n")
    (recipe / "autodata.workspace.json").write_text(
        json.dumps(
            {
                "schema": "autodata.workspace/v1",
                "name": "reviewed",
                "goal": "generate synthetic safety data",
                "intended_use": "SFT",
                "source_constraints": ["synthetic only"],
                "authoring_executor": {"kind": "local-bwrap"},
                "authoring_budget": {
                    "max_iterations": 3,
                    "max_task_attempts": 8,
                    "max_wall_seconds": 600,
                },
                "execution_defaults": {
                    "mode": "meta_optimize",
                    "split_seed": 7,
                    "executor": {"kind": "local-bwrap"},
                    "budget": {
                        "max_iterations": 3,
                        "max_task_attempts": 32,
                        "max_wall_seconds": 600,
                    },
                    "concurrency": 1,
                    "secret_references": [],
                },
            }
        )
    )
    for name in (
        "autodata.pipeline.json",
        "framework.lock.json",
        "objective.json",
        "comparator.json",
    ):
        (recipe / name).write_text(json.dumps({"name": name}))
    for name in ("grounding", "recipe", "schemas"):
        (recipe / name).mkdir()
    (recipe / "grounding" / "coverage.json").write_text("{}")
    (recipe / "grounding" / "build_manifest.py").write_text(
        """import argparse, json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, required=True)
parser.add_argument("--coverage")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.write_text(json.dumps({"schema": "autodata.grounding/v1", "tasks": list(range(args.count))}))
"""
    )
    (recipe / "recipe" / "task.py").write_text("# reviewed task\n")
    (recipe / "schemas" / "result.json").write_text("{}")
    contract = tmp_path / "training-contract.json"
    contract.write_text(json.dumps({"schema": "test-contract"}))
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "runner": "local-bwrap",
                "environment": "oci-runner-firecracker-large",
                "image": "docker.io/library/python@sha256:" + "a" * 64,
                "expected_image_id": "b" * 64,
                "max_cpus": 2,
                "max_memory_mb": 2048,
                "required_solve_env": {"AUTODATA_TARGET_ENABLED": "1"},
            }
        )
    )
    public = tmp_path / "public.pem"
    public.write_bytes(b"public-key")
    return {
        "TEAM_DIR": str(team),
        "AAR_AUTODATA_RECIPE_ROOT": str(recipe),
        "AAR_AUTODATA_PLUGIN_ROOT": str(plugin),
        "AAR_AUTODATA_WRAPPER_PYTHON": "/bin/python3",
        "AAR_AUTODATA_STATE": str(team / "autodata" / "native" / "live.db"),
        "AAR_AUTODATA_RETAINED_STATE": str(
            team / "autodata" / "native" / "state.db"
        ),
        "AAR_AUTODATA_ARTIFACTS": str(artifacts),
        "AAR_AUTODATA_WORKSPACES": str(workspaces),
        "AAR_AUTODATA_SUPERVISOR_CONTROL": str(
            team / "autodata" / "native" / "control.json"
        ),
        "AAR_AUTODATA_CAMPAIGN_POLICY": str(policy),
        "AAR_AUTODATA_TRAINING_DATA_CONTRACT": str(contract),
        "AAR_AUTODATA_TUNING_TASKS": "64",
        "AAR_AUTODATA_VALIDATION_TASKS": "32",
        "AAR_AUTODATA_TEST_TASKS": "32",
        "AAR_AUTODATA_BROKER_URL": "http://127.0.0.1:12345",
        "AAR_AUTODATA_CAPABILITY": "secret-value-not-written",
        "AAR_AUTODATA_CONCURRENCY": "8",
        "AAR_AUTODATA_AUTHORING_MAX_WALL_SECONDS": "1800",
        "AAR_AUTODATA_APPROVAL_PUBLIC_KEY": str(public),
        "AAR_AUTODATA_APPROVAL_PUBLIC_KEY_SHA256": (
            "sha256:" + hashlib.sha256(public.read_bytes()).hexdigest()
        ),
        "AAR_AUTODATA_APPROVAL_ACTOR": "aar-integrity-monitor",
        "AAR_AUTODATA_APPROVAL_POLICY_VERSION": "test/v1",
    }


def test_bootstrap_creates_registers_and_resumes_one_workspace(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    workspace_id = "ws_" + "1" * 32

    def run(command: list[str], **_: object) -> dict[str, object]:
        if "workspace" in command and "create" in command:
            return {
                "workspace_id": workspace_id,
                "study_id": "study_test",
                "status": "active",
            }
        if "register" in command:
            return {"registered": True, "subject_id": workspace_id}
        if "status" in command:
            return {"status": "active", "workspace_id": workspace_id}
        raise AssertionError(command)

    with (
        patch.dict(os.environ, environment, clear=False),
        patch("aar.research_loop.autodata_bootstrap._run_json", side_effect=run) as call,
        patch(
            "aar.research_loop.autodata_bootstrap._workspace_status",
            return_value="active",
        ),
    ):
        first = ensure_workspace(
            run_id="chain-iteration-1-method-123",
            idea_name="chain__method",
            code_hash="a" * 64,
        )
        second = ensure_workspace(
            run_id="chain-iteration-1-method-123",
            idea_name="chain__method",
            code_hash="a" * 64,
        )

    assert first["schema"] == BOOTSTRAP_SCHEMA
    assert first["workspace_id"] == workspace_id
    assert first["idempotent"] is False
    assert second["workspace_id"] == workspace_id
    assert second["idempotent"] is True
    assert call.call_count == 3  # create+register, then idempotent re-registration

    root = (
        Path(environment["TEAM_DIR"])
        / "autodata"
        / "chain-iteration-1-method-123"
    )
    brief = json.loads((root / "input" / "autodata.workspace.json").read_text())
    executor = brief["authoring_executor"]
    assert executor["kind"] == "sandoq-firecracker"
    assert executor["non_secret_env"] == {"AUTODATA_TARGET_ENABLED": "1"}
    assert executor["broker_auth_secret_ref"] == "AAR_AUTODATA_CAPABILITY"
    assert "secret-value-not-written" not in json.dumps(brief)
    assert brief["execution_defaults"]["concurrency"] == 8
    assert brief["authoring_budget"]["max_wall_seconds"] == 1800
    draft = root / "draft"
    assert (draft / "autodata.pipeline.json").is_file()
    assert (draft / "recipe" / "task.py").is_file()
    assert (draft / "training-data-contract.json").is_file()
    grounding = json.loads((draft / "grounding" / "manifest.json").read_text())
    assert len(grounding["tasks"]) == 128


@pytest.mark.parametrize("backend", ["kimi", "claude"])
def test_session_bootstrap_is_research_backend_independent(
    tmp_path: Path, backend: str
) -> None:
    marker = tmp_path / "proposal.json"
    marker.write_text(
        json.dumps(
            {
                "approved": True,
                "run_id": "run-one",
                "idea_name": "method_one",
                "code_hash": "a" * 64,
            }
        )
    )
    loop = object.__new__(AutonomousAgentLoop)
    loop.backend = backend
    with (
        patch.dict(os.environ, {"AAR_AUTODATA": "1"}, clear=False),
        patch(
            "aar.research_loop.tools.server_api_tools._proposal_approved",
            return_value=(True, "approved"),
        ),
        patch(
            "aar.research_loop.tools.server_api_tools._proposal_marker_path",
            return_value=marker,
        ),
        patch(
            "aar.research_loop.autodata_bootstrap.ensure_workspace",
            return_value={"workspace_id": "ws_" + "1" * 32, "idempotent": True},
        ) as ensure,
    ):
        loop._ensure_approved_autodata_workspace()

    ensure.assert_called_once_with(
        run_id="run-one", idea_name="method_one", code_hash="a" * 64
    )


def test_bootstrap_rejects_changed_proposal_identity(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    run_id = "chain-iteration-1-method-123"
    root = Path(environment["TEAM_DIR"]) / "autodata" / run_id
    root.mkdir(parents=True)
    (root / "workspace-bootstrap.json").write_text(
        json.dumps(
            {
                "schema": BOOTSTRAP_SCHEMA,
                "run_id": run_id,
                "idea_name": "other_method",
                "code_hash": "b" * 64,
                "workspace_id": "ws_" + "2" * 32,
            }
        )
    )
    with patch.dict(os.environ, environment, clear=False):
        with pytest.raises(RuntimeError, match="binds another proposal"):
            ensure_workspace(
                run_id=run_id,
                idea_name="chain__method",
                code_hash="a" * 64,
            )
