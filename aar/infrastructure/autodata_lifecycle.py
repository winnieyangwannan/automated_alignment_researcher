"""Read-only fail-closed verification of an AutoData training handoff.

This module never creates or advances an AutoData workspace or execution.  The
native plugin remains the sole lifecycle driver; this code only authenticates
its retained SQLite state and exported files at the training boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aar.infrastructure.autodata_contract import (
    contract_sha256,
    validate_dataset_items,
    validate_training_data_contract,
)

HANDOFF_SCHEMA = "aar.autodata.training-handoff/v1"
REUSE_HANDOFF_SCHEMA = "aar.autodata.training-handoff/v2"
PRODUCTION_MANIFEST = "grounding/production-manifest.json"
REQUIRED_PRODUCTION_TASKS = 1250
REQUIRED_TRAINING_ROWS = 1000
_EXECUTION_ID = re.compile(r"exe_[0-9a-f]{32}\Z")
_WORKSPACE_ID = re.compile(r"ws_[0-9a-f]{32}\Z")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    return value


def _json_file(path: Path, where: str) -> dict[str, Any]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), where)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{where} is not valid JSON") from error


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_file(path: Path, where: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{where} must be a regular non-symlink file")
    return path.resolve(strict=True)


def _contained_file(root: Path, raw: Any, where: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{where} must be a non-empty path")
    root = root.resolve(strict=True)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{where} must remain below the run AutoData directory") from error
    if ".." in relative.parts:
        raise ValueError(f"{where} must remain below the run AutoData directory")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{where} contains a symlink path component")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{where} must remain below the run AutoData directory") from error
    return _safe_file(resolved, where)


def _contained_directory(root: Path, raw: Any, where: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{where} must be a non-empty path")
    root = root.resolve(strict=True)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{where} must remain below the run AutoData directory") from error
    if ".." in relative.parts:
        raise ValueError(f"{where} must remain below the run AutoData directory")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{where} contains a symlink path component")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{where} must remain below the run AutoData directory") from error
    if not resolved.is_dir():
        raise ValueError(f"{where} must be a real directory")
    return resolved


def _safe_tree_hashes(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("AutoData pipeline tree must be a real directory")
    resolved = root.resolve(strict=True)
    result: dict[str, str] = {}
    for base, dirs, files in os.walk(resolved, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(base, name)
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError("AutoData pipeline tree contains an unsafe entry")
        for name in files:
            path = Path(base, name)
            relative = path.relative_to(resolved).as_posix()
            if relative == ".autodata" or relative.startswith(".autodata/"):
                continue
            result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(result.items()))


def _canonical_tree_digest(root: Path) -> str:
    payload = json.dumps(
        _safe_tree_hashes(root), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _execution_id(value: Any, where: str) -> str:
    if not isinstance(value, str) or _EXECUTION_ID.fullmatch(value) is None:
        raise ValueError(f"{where} is not a native AutoData execution id")
    return value


def _positive_environment_integer(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _execution(connection: sqlite3.Connection, execution_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM executions WHERE id=?", (execution_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"native AutoData execution {execution_id} was not found")
    return dict(row)


def _event(
    connection: sqlite3.Connection, execution_id: str, kind: str
) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT id,payloadJson FROM events "
        "WHERE scopeKind='execution' AND scopeId=? AND kind=? ORDER BY id",
        (execution_id, kind),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError(f"execution {execution_id} must have exactly one {kind} event")
    result = dict(rows[0])
    result["payload"] = _object(json.loads(str(result["payloadJson"])), kind)
    return result


def _timestamp(raw: Any, where: str) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{where} must be a native SQLite timestamp")
    try:
        parsed = datetime.fromisoformat(raw.strip().replace(" ", "T"))
    except ValueError as error:
        raise ValueError(f"{where} must be a native SQLite timestamp") from error
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _span(start: Any, end: Any, where: str) -> dict[str, Any]:
    started = _timestamp(start, f"{where}.started_at")
    finished = _timestamp(end, f"{where}.finished_at")
    elapsed = (finished - started).total_seconds()
    if elapsed < 0:
        raise ValueError(f"{where} has a negative native duration")
    return {
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "duration_seconds": elapsed,
    }


def _scope_timing(
    connection: sqlite3.Connection,
    *,
    scope_kind: str,
    scope_id: str,
    table: str,
    label: str,
) -> dict[str, Any]:
    if table not in {"workspaces", "executions"}:
        raise ValueError("unsupported native timing scope")
    row = connection.execute(
        f"SELECT createdAt,updatedAt FROM {table} WHERE id=?", (scope_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"native {scope_kind} {scope_id} was not found for timing")
    result = {
        "scope_kind": scope_kind,
        "scope_id": scope_id,
        **_span(row[0], row[1], label),
    }

    actions = []
    for action in connection.execute(
        "SELECT id,kind,status,createdAt,updatedAt FROM actions "
        "WHERE scopeKind=? AND scopeId=? ORDER BY createdAt,id",
        (scope_kind, scope_id),
    ).fetchall():
        actions.append(
            {
                "action_id": str(action[0]),
                "kind": str(action[1]),
                "status": str(action[2]),
                **_span(action[3], action[4], f"{label}.action"),
            }
        )
    result["actions"] = actions

    grouped: dict[str, list[dict[str, Any]]] = {}
    for attempt in connection.execute(
        "SELECT phase,createdAt,updatedAt,outcome,metricsJson,error FROM task_attempts "
        "WHERE scopeKind=? AND scopeId=? ORDER BY createdAt,id",
        (scope_kind, scope_id),
    ).fetchall():
        phase = str(attempt[0])
        grouped.setdefault(phase, []).append(
            {
                "start": _timestamp(attempt[1], f"{label}.{phase}.createdAt"),
                "end": _timestamp(attempt[2], f"{label}.{phase}.updatedAt"),
                "outcome": str(attempt[3] or "unknown"),
                "metrics": (
                    _object(json.loads(str(attempt[4])), "task attempt metrics")
                    if attempt[4] is not None
                    else {}
                ),
                "error": str(attempt[5] or "").lower(),
            }
        )
    task_phases = []
    for phase, attempts in grouped.items():
        started = min(value["start"] for value in attempts)
        finished = max(value["end"] for value in attempts)
        durations = sorted(
            (value["end"] - value["start"]).total_seconds() for value in attempts
        )
        wall_seconds = (finished - started).total_seconds()
        outcomes: dict[str, int] = {}
        for value in attempts:
            outcome = value["outcome"]
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        accepted = sum(
            1 for value in attempts if float(value["metrics"].get("valid", 0.0)) >= 1.0
        )
        error_texts = [value["error"] for value in attempts if value["error"]]

        def metric_total(key: str) -> float:
            return sum(
                float(value["metrics"].get(key, 0.0)) for value in attempts
            )

        task_phases.append(
            {
                "phase": phase,
                "task_attempts": len(attempts),
                "outcomes": dict(sorted(outcomes.items())),
                "accepted_rows": accepted,
                "started_at": started.isoformat().replace("+00:00", "Z"),
                "finished_at": finished.isoformat().replace("+00:00", "Z"),
                "wall_seconds": wall_seconds,
                "summed_task_seconds": sum(durations),
                "minimum_task_seconds": durations[0],
                "median_task_seconds": durations[(len(durations) - 1) // 2],
                "p95_task_seconds": durations[(95 * len(durations) - 1) // 100],
                "maximum_task_seconds": durations[-1],
                "tasks_per_minute": (
                    60.0 * len(attempts) / wall_seconds if wall_seconds else None
                ),
                "accepted_rows_per_minute": (
                    60.0 * accepted / wall_seconds if wall_seconds else None
                ),
                "provider_completed_calls": {
                    role: metric_total(f"telemetry_{role}_completed_calls")
                    for role in ("generator", "target", "judge")
                },
                "request_signals": {
                    role: {
                        "attempts": metric_total(
                            f"telemetry_{role}_request_attempts"
                        ),
                        "failures": metric_total(
                            f"telemetry_{role}_request_failures"
                        ),
                        "http_429_or_rate_limit": metric_total(
                            f"telemetry_{role}_http_429_or_rate_limit"
                        ),
                        "timeouts": metric_total(f"telemetry_{role}_timeouts"),
                        "connection_resets": metric_total(
                            f"telemetry_{role}_connection_resets"
                        ),
                    }
                    for role in ("generator", "target", "judge")
                },
                "error_signals": {
                    "http_429_or_rate_limit": sum(
                        "429" in error or "rate limit" in error
                        for error in error_texts
                    ),
                    "timeout": sum("timeout" in error for error in error_texts),
                    "connection_reset": sum(
                        "reset" in error for error in error_texts
                    ),
                    "other": sum(
                        not any(
                            token in error
                            for token in ("429", "rate limit", "timeout", "reset")
                        )
                        for error in error_texts
                    ),
                },
            }
        )
    result["task_phases"] = task_phases
    return result


def _lifecycle_timing(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    workspace_id: str,
    meta_id: str,
    production_id: str,
) -> dict[str, Any]:
    workspace = _scope_timing(
        connection,
        scope_kind="workspace",
        scope_id=workspace_id,
        table="workspaces",
        label="workspace_authoring",
    )
    meta = _scope_timing(
        connection,
        scope_kind="execution",
        scope_id=meta_id,
        table="executions",
        label="meta_optimization",
    )
    production = _scope_timing(
        connection,
        scope_kind="execution",
        scope_id=production_id,
        table="executions",
        label="production_generation",
    )
    return {
        "schema": "aar.autodata.lifecycle-timing/v1",
        "run_id": run_id,
        "workspace_authoring": workspace,
        "meta_optimization": meta,
        "production_generation": production,
        "end_to_end": _span(
            workspace["started_at"],
            production["finished_at"],
            "end_to_end",
        ),
    }


def _study(connection: sqlite3.Connection, subject_kind: str, subject_id: str) -> str:
    rows = connection.execute(
        "SELECT studyId FROM study_members "
        "WHERE subjectKind=? AND subjectId=?",
        (subject_kind, subject_id),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError(f"{subject_kind} {subject_id} has no unique native study")
    return str(rows[0][0])


def _candidate_workspace(
    connection: sqlite3.Connection, execution_id: str, candidate_id: str
) -> Path:
    row = connection.execute(
        "SELECT workspace FROM candidates WHERE executionId=? AND id=?",
        (execution_id, candidate_id),
    ).fetchone()
    if row is None:
        raise ValueError("native finalized winner candidate was not found")
    path = Path(str(row[0]))
    if path.is_symlink() or not path.is_dir():
        raise ValueError("native winner candidate workspace is unsafe or missing")
    return path.resolve(strict=True)


def _task_ids(manifest: Mapping[str, Any], where: str) -> list[str]:
    if manifest.get("schema") != "autodata.grounding/v1":
        raise ValueError(f"{where} has the wrong grounding schema")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError(f"{where} tasks must be an array")
    result: list[str] = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task["id"]:
            raise ValueError(f"{where} task {index} has no valid id")
        result.append(task["id"])
    if len(result) != len(set(result)):
        raise ValueError(f"{where} contains duplicate task ids")
    return result


def _grounding_ids(pipeline_root: Path, reference: Any, where: str) -> set[str]:
    reference = _object(reference, where)
    relative = reference.get("manifest_path")
    if (
        not isinstance(relative, str)
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ValueError(f"{where}.manifest_path is unsafe")
    pipeline_root = pipeline_root.resolve(strict=True)
    candidate = pipeline_root / relative
    current = pipeline_root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{where}.manifest_path contains a symlink")
    path = _safe_file(candidate.resolve(strict=True), where)
    try:
        path.relative_to(pipeline_root)
    except ValueError as error:
        raise ValueError(f"{where}.manifest_path escapes its pipeline") from error
    if _sha256(path) != reference.get("digest"):
        raise ValueError(f"{where} digest does not match its manifest")
    return set(_task_ids(_json_file(path, where), where))


def _load_handoff(run_id: str) -> tuple[Path, Path, dict[str, Any]]:
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("run_id is not a safe run-scoped identifier")
    team_raw = os.getenv("TEAM_DIR", "").strip()
    if not team_raw:
        raise ValueError("TEAM_DIR is required for AutoData lifecycle verification")
    team = Path(team_raw).resolve(strict=True)
    run_root = team / "autodata" / run_id
    if run_root.is_symlink() or not run_root.is_dir():
        raise ValueError("run-scoped AutoData directory is missing or unsafe")
    handoff_path = _safe_file(run_root / "training-handoff.json", "training handoff")
    handoff = _json_file(handoff_path, "training handoff")
    schema = handoff.get("schema")
    if schema not in {HANDOFF_SCHEMA, REUSE_HANDOFF_SCHEMA} or handoff.get(
        "run_id"
    ) != run_id:
        raise ValueError("training handoff schema or run_id does not match")
    expected_fields = {
        "schema",
        "run_id",
        "state_db",
        "dataset",
        "workspace_id",
        "study_id",
        "meta_execution_id",
        "production_execution_id",
        "winner_export",
        "production_manifest",
        "consumption_receipt",
    }
    if schema == REUSE_HANDOFF_SCHEMA:
        expected_fields |= {
            "source_run_id",
            "state_db_sha256",
            "dataset_sha256",
            "production_manifest_sha256",
            "training_data_contract",
            "training_data_contract_sha256",
        }
    if set(handoff) != expected_fields:
        raise ValueError("training handoff has unknown or missing fields")
    source_root = run_root
    if schema == REUSE_HANDOFF_SCHEMA:
        source_run_id = handoff["source_run_id"]
        if not isinstance(source_run_id, str) or _RUN_ID.fullmatch(source_run_id) is None:
            raise ValueError("source_run_id is not a safe run-scoped identifier")
        source_root = team / "autodata" / source_run_id
        if source_root.is_symlink() or not source_root.is_dir():
            raise ValueError("source AutoData run directory is missing or unsafe")
    return run_root.resolve(strict=True), source_root.resolve(strict=True), handoff


def verify_preflight(
    run_id: str, *, require_operator_contract: bool = True
) -> dict[str, Any]:
    """Verify completed native meta->winner->fixed-production evidence."""
    run_root, source_root, handoff = _load_handoff(run_id)
    state_raw = handoff["state_db"]
    if not isinstance(state_raw, str):
        raise ValueError("training handoff state_db must be a path")
    state = _safe_file(Path(state_raw), "native AutoData state")
    # The live controller database may be node-local.  Cross-node training
    # verifies the supervisor's atomic retained snapshot when configured.
    trusted_state_paths = {
        raw.strip()
        for raw in (
            os.getenv("AAR_AUTODATA_RETAINED_STATE", ""),
            os.getenv("AAR_AUTODATA_STATE", ""),
            os.getenv("AAR_AUTODATA_REUSE_STATE", ""),
        )
        if raw.strip()
    }
    trusted_states = {
        _safe_file(Path(raw), "trusted AAR_AUTODATA state")
        for raw in trusted_state_paths
        if Path(raw).exists() or Path(raw).is_symlink()
    }
    if state not in trusted_states:
        raise ValueError("training handoff state_db is not the trusted native state")
    if handoff["schema"] == REUSE_HANDOFF_SCHEMA and handoff["state_db_sha256"] != _sha256(
        state
    ):
        raise ValueError("reused native state digest does not match the handoff")

    dataset_path = _contained_file(
        source_root, handoff["dataset"], "production dataset"
    )
    winner_export = _contained_directory(
        source_root, handoff["winner_export"], "winner export"
    )
    production_manifest = _contained_file(
        source_root, handoff["production_manifest"], "production manifest"
    )
    contract = None
    if handoff["schema"] == REUSE_HANDOFF_SCHEMA:
        if handoff["dataset_sha256"] != _sha256(dataset_path):
            raise ValueError("reused dataset digest does not match the handoff")
        if handoff["production_manifest_sha256"] != _sha256(production_manifest):
            raise ValueError("reused production manifest digest does not match the handoff")
        contract_path = _contained_file(
            run_root,
            handoff["training_data_contract"],
            "training-data contract",
        )
        contract = validate_training_data_contract(
            _json_file(contract_path, "training-data contract")
        )
        if handoff["training_data_contract_sha256"] != contract_sha256(contract):
            raise ValueError("training-data contract digest does not match the handoff")
    trusted_contract_raw = (
        os.getenv("AAR_AUTODATA_TRAINING_DATA_CONTRACT", "").strip()
        if require_operator_contract
        else ""
    )
    if trusted_contract_raw:
        trusted_contract = validate_training_data_contract(
            _json_file(
                _safe_file(Path(trusted_contract_raw), "trusted training-data contract"),
                "trusted training-data contract",
            )
        )
        if contract is not None and contract_sha256(contract) != contract_sha256(
            trusted_contract
        ):
            raise ValueError("reuse contract does not match operator training-data policy")
        contract = trusted_contract
    meta_id = _execution_id(handoff["meta_execution_id"], "meta_execution_id")
    production_id = _execution_id(
        handoff["production_execution_id"], "production_execution_id"
    )
    workspace_id = handoff["workspace_id"]
    if not isinstance(workspace_id, str) or _WORKSPACE_ID.fullmatch(workspace_id) is None:
        raise ValueError("workspace_id is not a native AutoData workspace id")
    study_id = handoff["study_id"]
    if not isinstance(study_id, str) or not study_id.strip():
        raise ValueError("study_id must be a non-empty native study id")

    connection = sqlite3.connect(f"file:{state}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        meta = _execution(connection, meta_id)
        production = _execution(connection, production_id)
        meta_spec = _object(json.loads(str(meta["executionJson"])), "meta execution")
        production_spec = _object(
            json.loads(str(production["executionJson"])), "production execution"
        )
        if (
            meta_spec.get("mode") != "meta_optimize"
            or meta["status"] != "completed"
            or meta["phase"] != "completed"
        ):
            raise ValueError("meta_optimize execution is not completed")
        tuning_ids = meta_spec.get("tuning_task_ids")
        validation_ids = meta_spec.get("validation_task_ids")
        if (
            not isinstance(tuning_ids, list)
            or len(tuning_ids) != 64
            or len(set(tuning_ids)) != 64
            or not isinstance(validation_ids, list)
            or len(validation_ids) != 32
            or len(set(validation_ids)) != 32
            or set(tuning_ids) & set(validation_ids)
        ):
            raise ValueError("meta execution must bind exactly 64 tuning and 32 validation tasks")
        meta_budget = _object(meta_spec.get("budget"), "meta budget")
        if (
            not isinstance(meta_budget.get("max_iterations"), int)
            or isinstance(meta_budget.get("max_iterations"), bool)
            or not 3 <= meta_budget["max_iterations"] <= 10
            or meta_budget.get("min_iterations") != 3
            or meta_budget.get("early_stop_patience") != 3
        ):
            raise ValueError("meta budget must use 3-10 iterations, minimum 3, and patience 3")
        meta_final = _event(connection, meta_id, "execution.finalized")
        meta_winner = str(meta_final["payload"].get("winner_candidate_id") or "")
        meta_digest = str(meta_final["payload"].get("winner_tree_digest") or "")
        if not meta_winner or meta_winner != str(meta["winnerCandidateId"]):
            raise ValueError("meta finalized winner does not match native execution state")
        if _canonical_tree_digest(winner_export) != meta_digest:
            raise ValueError("winner export does not match the finalized meta winner tree")

        if (
            production_spec.get("mode") != "production"
            or production["status"] != "completed"
            or production["phase"] != "completed"
        ):
            raise ValueError("production execution is not completed")
        budget = _object(production_spec.get("budget"), "production budget")
        if budget.get("max_iterations") != 0 or production["maxIterations"] != 0:
            raise ValueError("production must be a fixed-winner zero-iteration execution")
        finalization_raw = production_spec.get("finalization")
        if contract is not None and (
            handoff["schema"] == HANDOFF_SCHEMA or finalization_raw is not None
        ):
            finalization = _object(finalization_raw, "production finalization policy")
            if (
                finalization.get("minimum_generated_items")
                != contract["required_rows"]
                or finalization.get("minimum_successful_task_fraction")
                != contract["minimum_successful_task_fraction"]
            ):
                raise ValueError(
                    "production finalization does not match training-data contract"
                )
        native_studies = {
            _study(connection, "workspace", workspace_id),
            _study(connection, "execution", meta_id),
            _study(connection, "execution", production_id),
        }
        if native_studies != {study_id}:
            raise ValueError(
                "workspace, meta, and production do not share the handoff native study"
            )
        production_created = _event(connection, production_id, "execution.created")
        if int(production_created["id"]) <= int(meta_final["id"]):
            raise ValueError("production was created before the meta winner completed")

        production_final = _event(connection, production_id, "execution.finalized")
        production_winner = str(
            production_final["payload"].get("winner_candidate_id") or ""
        )
        if not production_winner or production_winner != str(production["winnerCandidateId"]):
            raise ValueError("production finalized winner does not match native state")
        production_tree = _candidate_workspace(
            connection, production_id, production_winner
        )
        if _canonical_tree_digest(production_tree) != production_final["payload"].get(
            "winner_tree_digest"
        ):
            raise ValueError("production winner tree no longer matches native evidence")

        grounding = _object(production_spec.get("grounding"), "production grounding")
        if grounding.get("manifest_path") != PRODUCTION_MANIFEST:
            raise ValueError("production must use the dedicated production manifest path")
        pipeline_root = Path(str(production["pipelineRoot"])).resolve(strict=True)
        state_manifest = _safe_file(
            (pipeline_root / PRODUCTION_MANIFEST).resolve(strict=True),
            "native production manifest",
        )
        if state_manifest != production_manifest or grounding.get("digest") != _sha256(
            production_manifest
        ):
            raise ValueError("production execution does not bind the handoff manifest digest")
        candidate_manifest = _safe_file(
            production_tree / PRODUCTION_MANIFEST, "production candidate manifest"
        )
        if candidate_manifest.read_bytes() != production_manifest.read_bytes():
            raise ValueError("production candidate does not contain the bound manifest")

        winner_hashes = _safe_tree_hashes(winner_export)
        production_hashes = _safe_tree_hashes(production_tree)
        if PRODUCTION_MANIFEST in winner_hashes:
            raise ValueError("meta winner export unexpectedly contains a production manifest")
        expected_production_hashes = dict(winner_hashes)
        expected_production_hashes[PRODUCTION_MANIFEST] = hashlib.sha256(
            production_manifest.read_bytes()
        ).hexdigest()
        if production_hashes != dict(sorted(expected_production_hashes.items())):
            raise ValueError(
                "production pipeline differs from the exported winner beyond its dedicated manifest"
            )

        production_ids = _task_ids(
            _json_file(production_manifest, "production manifest"),
            "production manifest",
        )
        required_source_tasks = _positive_environment_integer(
            "AAR_AUTODATA_PRODUCTION_INITIAL_TASKS", REQUIRED_PRODUCTION_TASKS
        )
        if len(production_ids) != required_source_tasks:
            raise ValueError(
                "production manifest source-task count does not match the "
                "configured initial production budget"
            )
        meta_ids = set(tuning_ids) | set(validation_ids)
        test_reference = meta_spec.get("test_grounding")
        if test_reference is None:
            raise ValueError("meta execution must bind untouched test grounding")
        test_ids = _grounding_ids(
            Path(str(meta["pipelineRoot"])).resolve(strict=True),
            test_reference,
            "meta test grounding",
        )
        if len(test_ids) != 32 or test_ids & meta_ids:
            raise ValueError("meta execution must bind exactly 32 disjoint test tasks")
        meta_ids |= test_ids
        if meta_ids & set(production_ids):
            raise ValueError("production source tasks overlap meta tuning/validation/test")

        dataset = _json_file(dataset_path, "production dataset")
        if dataset.get("schema") != "autodata.dataset/v1" or dataset.get("mode") != "production":
            raise ValueError("training dataset is not a native production export")
        if dataset.get("execution_id") != production_id:
            raise ValueError("training dataset is not bound to the production execution")
        if dataset.get("source_task_ids") != production_ids:
            raise ValueError("dataset source_task_ids do not exactly match the production manifest")
        dataset_ref = _object(
            production_final["payload"].get("dataset"), "production dataset reference"
        )
        if dataset_ref.get("digest") != _sha256(dataset_path):
            raise ValueError("dataset export digest does not match native finalization evidence")
        items = dataset.get("items")
        required_rows = (
            int(contract["required_rows"])
            if contract is not None
            else REQUIRED_TRAINING_ROWS
        )
        if not isinstance(items, list) or len(items) < required_rows:
            raise ValueError(
                "production dataset retained fewer than the contracted accepted rows"
            )
        item_ids: list[str] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError(f"production dataset item {index} has no valid id")
            metadata = item.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("judge_accepted") is not True:
                raise ValueError("production dataset contains a non-accepted row")
            item_ids.append(item["id"])
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("production dataset contains duplicate accepted row ids")
        if contract is not None:
            validate_dataset_items(items, contract)
        timing = _lifecycle_timing(
            connection,
            run_id=run_id,
            workspace_id=workspace_id,
            meta_id=meta_id,
            production_id=production_id,
        )
    finally:
        connection.close()

    return {
        "schema": "aar.autodata.lifecycle-verification/v1",
        "run_id": run_id,
        "source_run_id": handoff.get("source_run_id", run_id),
        "reused_dataset": handoff["schema"] == REUSE_HANDOFF_SCHEMA,
        "workspace_id": workspace_id,
        "study_id": study_id,
        "meta_execution_id": meta_id,
        "production_execution_id": production_id,
        "production_manifest_sha256": _sha256(production_manifest),
        "dataset_sha256": _sha256(dataset_path),
        "source_task_count": required_source_tasks,
        "available_rows": len(items),
        "required_rows": required_rows,
        "training_objective": (
            contract["training_objective"] if contract is not None else None
        ),
        "timing": timing,
    }


def verify_consumption(run_id: str) -> dict[str, Any]:
    """Require proof that run_experiment consumed the verified production data."""
    verified = verify_preflight(run_id)
    run_root, _, handoff = _load_handoff(run_id)
    receipt = _contained_file(
        run_root, handoff["consumption_receipt"], "training consumption receipt"
    )
    info = receipt.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("training consumption receipt must be owned mode 0600")
    value = _json_file(receipt, "training consumption receipt")
    if value.get("consumer_pid") != os.getpid():
        raise ValueError("training consumption receipt was not created by this training process")
    production_id = verified["production_execution_id"]
    if verified["training_objective"] is not None and value.get(
        "training_objective"
    ) != verified["training_objective"]:
        raise ValueError("consumption receipt objective does not match the contract")
    required_rows = verified["required_rows"]
    if value.get("required_rows") != required_rows or value.get(
        "row_count"
    ) != required_rows:
        raise ValueError(
            "training consumption receipt must retain exactly the contracted rows"
        )
    if value.get("schema") == "aar.autodata.native-consumption/v1":
        if value.get("execution_id") != production_id:
            raise ValueError("consumption receipt execution does not match the handoff")
        if value.get("dataset_sha256") != verified["dataset_sha256"]:
            raise ValueError("consumption receipt dataset digest does not match")
    elif value.get("schema") == "aar.autodata.native-campaign-consumption/v1":
        if value.get("execution_ids") != [production_id]:
            raise ValueError("campaign consumption executions do not match the handoff")
        if value.get("dataset_sha256s") != [verified["dataset_sha256"]]:
            raise ValueError("campaign consumption dataset digests do not match")
    else:
        raise ValueError("unsupported training consumption receipt schema")
    return {
        **verified,
        "consumption_receipt": str(receipt),
        "consumed_rows": required_rows,
    }


def create_reuse_handoff(
    *, source_run_id: str, run_id: str, training_data_contract: Path
) -> dict[str, Any]:
    """Create an idempotent, digest-bound handoff that reuses a verified export."""
    if source_run_id == run_id:
        raise ValueError("source and consuming run IDs must differ")
    verified = verify_preflight(source_run_id, require_operator_contract=False)
    _, source_root, source = _load_handoff(source_run_id)
    team = source_root.parent.parent
    consumer_root = team / "autodata" / run_id
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("run_id is not a safe run-scoped identifier")
    consumer_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if consumer_root.is_symlink():
        raise ValueError("consuming AutoData run directory is unsafe")
    contract = validate_training_data_contract(
        _json_file(_safe_file(training_data_contract, "training-data contract"), "training-data contract")
    )
    dataset = _contained_file(source_root, source["dataset"], "production dataset")
    dataset_value = _json_file(dataset, "production dataset")
    validate_dataset_items(dataset_value.get("items"), contract)
    manifest = _contained_file(
        source_root, source["production_manifest"], "production manifest"
    )
    contract_destination = consumer_root / "training-data-contract.json"
    canonical_contract = json.dumps(contract, sort_keys=True, indent=2) + "\n"
    if contract_destination.exists():
        if contract_destination.is_symlink() or contract_destination.read_text(
            encoding="utf-8"
        ) != canonical_contract:
            raise ValueError("existing consuming training-data contract does not match")
    else:
        descriptor = os.open(
            contract_destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(canonical_contract)
    handoff = {
        "schema": REUSE_HANDOFF_SCHEMA,
        "run_id": run_id,
        "source_run_id": verified["source_run_id"],
        "state_db": source["state_db"],
        "state_db_sha256": _sha256(_safe_file(Path(source["state_db"]), "native AutoData state")),
        "dataset": str(dataset),
        "dataset_sha256": _sha256(dataset),
        "workspace_id": source["workspace_id"],
        "study_id": source["study_id"],
        "meta_execution_id": source["meta_execution_id"],
        "production_execution_id": source["production_execution_id"],
        "winner_export": str(
            _contained_directory(source_root, source["winner_export"], "winner export")
        ),
        "production_manifest": str(manifest),
        "production_manifest_sha256": _sha256(manifest),
        "training_data_contract": str(contract_destination),
        "training_data_contract_sha256": contract_sha256(contract),
        "consumption_receipt": str(consumer_root / "training-consumption.json"),
    }
    destination = consumer_root / "training-handoff.json"
    encoded = json.dumps(handoff, sort_keys=True, indent=2) + "\n"
    if destination.exists():
        if destination.is_symlink() or destination.read_text(encoding="utf-8") != encoded:
            raise ValueError("existing reuse handoff does not match")
    else:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(encoded)
    return verify_preflight(run_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("preflight", "verify-consumption", "create-reuse-handoff"),
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-run-id")
    parser.add_argument("--training-data-contract", type=Path)
    args = parser.parse_args()
    if args.command == "preflight":
        result = verify_preflight(args.run_id)
    elif args.command == "verify-consumption":
        result = verify_consumption(args.run_id)
    else:
        if not args.source_run_id or args.training_data_contract is None:
            parser.error("reuse requires --source-run-id and --training-data-contract")
        result = create_reuse_handoff(
            source_run_id=args.source_run_id,
            run_id=args.run_id,
            training_data_contract=args.training_data_contract,
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
