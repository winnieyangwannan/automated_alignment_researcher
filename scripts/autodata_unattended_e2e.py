#!/usr/bin/env python3
"""Run the native AutoData workspace -> meta -> production lifecycle locally.

This is a deterministic orchestration test.  It imports the canonical AutoData
implementation from an explicit checkout, executes its bundled toy recipe, and
uses two named actors:

* ``aar-research-agent`` fulfills authoring, analysis, and mutation actions;
* ``aar-integrity-monitor`` fulfills the two approval actions under delegated,
  pre-authorized test policy.

No model or provider call is made.  The purpose is to prove that an AAR-owned
caller can initiate a workspace and drive both native execution modes without a
human pausing the state machine.  Live Kimi/Luna/SandoQ validation is a separate
provider canary after this contract test succeeds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


RESEARCH_AGENT = "aar-research-agent"
INTEGRITY_MONITOR = "aar-integrity-monitor"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _install_autodata_import(root: Path) -> None:
    source = root / "src"
    if not (source / "autodata" / "engine.py").is_file():
        raise SystemExit(f"not an AutoData checkout: {root}")
    sys.path.insert(0, str(source))


@dataclass
class _Result:
    request: Any
    status: Any
    stdout: bytes
    stderr: bytes


class DeterministicDirectExecutor:
    """Local test executor implementing AutoData's Executor protocol."""

    backend = "aar-deterministic-direct-test"

    def __init__(self) -> None:
        self.results: dict[str, _Result] = {}
        self._lock = threading.Lock()

    def submit(self, request: Any) -> Any:
        from autodata.protocols import TaskAttemptHandle, TaskAttemptStatus

        prefix = str(request.workspace.resolve()) + "/"
        argv = tuple(arg.replace("/workspace/", prefix) for arg in request.argv)
        completed = subprocess.run(
            argv,
            cwd=request.workspace,
            input=request.stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **request.env},
            timeout=request.timeout_seconds,
            check=False,
        )
        attempt_id = "aar_e2e_" + uuid.uuid4().hex
        result = _Result(
            request=request,
            status=TaskAttemptStatus(
                "succeeded" if completed.returncode == 0 else "failed",
                completed.returncode,
                completed.stderr.decode("utf-8", "replace") or None,
            ),
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        with self._lock:
            self.results[attempt_id] = result
        return TaskAttemptHandle(attempt_id, self.backend)

    def poll(self, handle: Any) -> Any:
        with self._lock:
            return self.results[handle.id].status

    def cancel(self, handle: Any) -> None:
        from autodata.protocols import TaskAttemptStatus

        with self._lock:
            self.results[handle.id].status = TaskAttemptStatus("cancelled")

    def collect(self, handle: Any, artifacts: Any) -> dict[str, Any]:
        with self._lock:
            result = self.results[handle.id]
        refs = {
            "stdout": artifacts.put_bytes(
                result.stdout, media_type="text/plain", name="stdout.txt"
            ),
            "stderr": artifacts.put_bytes(
                result.stderr, media_type="text/plain", name="stderr.txt"
            ),
        }
        for relative in result.request.result_paths:
            path = result.request.workspace / relative
            if path.exists():
                refs[relative] = artifacts.collect_path(
                    result.request.workspace, relative
                )
        return refs

    def cleanup(self, handle: Any) -> None:
        with self._lock:
            self.results.pop(handle.id, None)

    def progress(self, handle: Any) -> tuple[Any, ...]:
        from autodata.progress import parse_progress_lines

        with self._lock:
            stdout = self.results[handle.id].stdout
        return tuple(parse_progress_lines(stdout.decode("utf-8", "replace").splitlines()))


def _complete(store: Any, action: Any, result: dict[str, Any]) -> None:
    begun = store.begin_action(action.id, expected_revision=action.scope.revision)
    store.complete_action(action.id, lease_token=begun["leaseToken"], result=result)


def _record_action(
    audit: list[dict[str, Any]], action: Any, actor: str, result: dict[str, Any]
) -> None:
    audit.append(
        {
            "action_id": action.id,
            "scope_kind": action.scope.kind,
            "scope_id": action.scope.id,
            "scope_revision": action.scope.revision,
            "kind": action.kind,
            "actor": actor,
            "result_sha256": hashlib.sha256(
                _canonical_json(result).encode("utf-8")
            ).hexdigest(),
        }
    )


def _drive_workspace(engine: Any, store: Any, audit: list[dict[str, Any]]) -> dict[str, Any]:
    expected = (
        "clarify_design",
        "author_grounding",
        "approve_grounding",
        "author_pipeline",
        "approve_baseline",
    )
    for kind in expected:
        action = engine.step()
        if not hasattr(action, "kind") or action.kind != kind:
            raise RuntimeError(f"expected workspace action {kind}, got {action!r}")
        if kind in {"approve_grounding", "approve_baseline"}:
            actor = INTEGRITY_MONITOR
            target = "grounding" if kind == "approve_grounding" else "pipeline"
            result = {
                "decision": "approve",
                "feedback": "Approved by pre-authorized deterministic integrity policy.",
                "target": target,
                # AutoData main's v1 compatibility field.  The audit fields below
                # identify the actual delegated principal; no human is implied.
                "user_acknowledged": True,
                "approval_principal": INTEGRITY_MONITOR,
                "delegated_authority": "aar-unattended-e2e/v1",
            }
        else:
            actor = RESEARCH_AGENT
            result = {
                "summary": f"{RESEARCH_AGENT} completed {kind} from the pinned recipe.",
                "decisions": ["Use the checked-in deterministic recipe unchanged."],
            }
        _complete(store, action, result)
        _record_action(audit, action, actor, result)
    frozen = engine.step()
    if frozen.get("status") != "frozen":
        raise RuntimeError(f"workspace did not freeze: {frozen!r}")
    return dict(frozen)


def _drive_execution(
    engine: Any,
    store: Any,
    audit: list[dict[str, Any]],
    *,
    factor_text: str,
) -> dict[str, Any]:
    analysis = engine.step()
    if not hasattr(analysis, "kind") or analysis.kind != "analyze_results":
        raise RuntimeError(f"expected analyze_results, got {analysis!r}")
    analysis_result = {
        "proposal": "Set recipe/config.json factor to the exact doubling value 2.",
        "dashboard_summary": {
            "headline": "Deterministic baseline inspected",
            "summary": "The visible evidence supports changing the factor to two.",
            "next_step": "Apply the single allowlisted configuration change.",
        },
    }
    _complete(store, analysis, analysis_result)
    _record_action(audit, analysis, RESEARCH_AGENT, analysis_result)

    mutation = engine.step()
    if not hasattr(mutation, "kind") or mutation.kind != "mutate_candidate":
        raise RuntimeError(f"expected mutate_candidate, got {mutation!r}")
    config = Path(mutation.editable_root) / "recipe" / "config.json"
    config.write_text(f'{{"factor": {factor_text}}}\n', encoding="utf-8")
    mutation_result = {"summary": f"Set the allowlisted factor to {factor_text}."}
    _complete(store, mutation, mutation_result)
    _record_action(audit, mutation, RESEARCH_AGENT, mutation_result)

    completed = engine.step()
    if completed.get("status") != "completed":
        raise RuntimeError(f"execution did not complete: {completed!r}")
    return dict(completed)


def _final_dataset(store: Any, artifacts: Any, execution_id: str) -> dict[str, Any]:
    from autodata.models import ArtifactRef

    final = None
    for event in store.list_events("execution", execution_id):
        if event["kind"] == "execution.finalized":
            final = json.loads(str(event["payloadJson"]))
    if final is None:
        raise RuntimeError(f"execution {execution_id} has no final dataset event")
    ref = ArtifactRef.from_dict(final["dataset"])
    return json.loads(artifacts.get_bytes(ref))


def run(args: argparse.Namespace) -> dict[str, Any]:
    from autodata.artifacts import FileArtifactStore
    from autodata.engine import ExecutionEngine
    from autodata.models import load_pipeline, load_workspace
    from autodata.sqlite_store import SQLiteStateStore
    from autodata.workspace import WorkspaceEngine

    autodata_root = args.autodata_root.resolve()
    source_recipe = autodata_root / "recipes" / "toy"
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError(f"output root must be absent or empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    draft = output_root / "draft"
    shutil.copytree(source_recipe, draft)

    state = SQLiteStateStore(output_root / "state.db")
    artifacts = FileArtifactStore(output_root / "artifacts")
    executor = DeterministicDirectExecutor()
    audit: list[dict[str, Any]] = []

    workspace = WorkspaceEngine.create(
        state,
        artifacts,
        executor,
        executor,
        load_workspace(draft / "autodata.workspace.json"),
        root=draft,
        internal_root=output_root / "workspaces" / "authoring",
        idempotency_key=f"{args.run_id}:workspace",
    )
    workspace_created = {
        "event": "workspace.created",
        "actor": RESEARCH_AGENT,
        "workspace_id": workspace.workspace_id,
    }
    frozen = _drive_workspace(workspace, state, audit)

    meta = ExecutionEngine(state, artifacts, executor, frozen["execution_id"])
    meta_completed = _drive_execution(meta, state, audit, factor_text="2")
    meta_dataset = _final_dataset(state, artifacts, meta.execution_id)
    meta_attempts = state.list_task_attempts("execution", meta.execution_id)
    meta_winner = state.get_candidate(meta_completed["winner_candidate_id"])
    winner_root = Path(str(meta_winner["workspace"]))

    production_spec = replace(
        meta.execution,
        mode="production",
        tuning_task_ids=(),
        validation_task_ids=(),
        budget=replace(meta.execution.budget, max_task_attempts=50),
    )
    production = ExecutionEngine.create(
        state,
        artifacts,
        executor,
        load_pipeline(winner_root / "autodata.pipeline.json"),
        production_spec,
        pipeline_root=winner_root,
        workspace_root=output_root / "workspaces" / "executions",
        idempotency_key=f"{args.run_id}:production",
        study_id=state.study_for_subject("workspace", workspace.workspace_id),
    )
    production_completed = _drive_execution(
        production, state, audit, factor_text="2.0"
    )
    production_dataset = _final_dataset(state, artifacts, production.execution_id)
    production_attempts = state.list_task_attempts(
        "execution", production.execution_id
    )

    rows = production_dataset["items"]
    rows_payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    pipeline_sha = _git_head(autodata_root)
    manifest = {
        "schema": "aar.autodata.dataset/v1",
        "run_id": args.run_id,
        "pipeline_sha": pipeline_sha,
        "row_count": len(rows),
        "dataset_sha256": hashlib.sha256(rows_payload.encode("utf-8")).hexdigest(),
        "native_autodata_schema": production_dataset["schema"],
        "native_autodata_execution_id": production.execution_id,
        "workspace_id": workspace.workspace_id,
        "meta_optimize_execution_id": meta.execution_id,
        "modes_completed_in_order": ["meta_optimize", "production"],
        "approval_mode": "delegated-preauthorized-test-policy",
        "approval_principal": INTEGRITY_MONITOR,
        "initiator": RESEARCH_AGENT,
        "provider": "deterministic-local-test",
        "model_calls": 0,
        "cost_usd": 0.0,
        "integration_smoke_only": True,
    }
    (output_root / "autodata_rows.jsonl").write_text(rows_payload, encoding="utf-8")
    (output_root / "autodata_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = {
        "schema": "aar.autodata.unattended-e2e-report/v1",
        "success": True,
        "run_id": args.run_id,
        "autodata_root": str(autodata_root),
        "autodata_sha": pipeline_sha,
        "recipe": str(source_recipe),
        "workspace_created": workspace_created,
        "workspace_frozen": frozen,
        "meta_optimize": {
            "execution_id": meta.execution_id,
            "status": meta_completed["status"],
            "fitness": meta_dataset["aggregate"]["fitness"],
            "source_task_count": len(meta_dataset["source_task_ids"]),
            "task_attempt_count": len(meta_attempts),
            "hidden_task_attempt_count": sum(
                1 for attempt in meta_attempts if attempt["hidden"]
            ),
        },
        "production": {
            "execution_id": production.execution_id,
            "status": production_completed["status"],
            "fitness": production_dataset["aggregate"]["fitness"],
            "source_task_count": len(production_dataset["source_task_ids"]),
            "retained_rows": len(rows),
            "task_attempt_count": len(production_attempts),
            "hidden_task_attempt_count": sum(
                1 for attempt in production_attempts if attempt["hidden"]
            ),
        },
        "action_audit": audit,
        "manifest": manifest,
    }
    (output_root / "e2e_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--autodata-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", default="run-8-unattended-e2e")
    args = parser.parse_args()
    _install_autodata_import(args.autodata_root.resolve())
    report = run(args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
