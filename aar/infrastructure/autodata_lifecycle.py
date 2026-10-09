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
from pathlib import Path
from typing import Any, Mapping


HANDOFF_SCHEMA = "aar.autodata.training-handoff/v1"
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


def _load_handoff(run_id: str) -> tuple[Path, dict[str, Any]]:
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
    if handoff.get("schema") != HANDOFF_SCHEMA or handoff.get("run_id") != run_id:
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
    if set(handoff) != expected_fields:
        raise ValueError("training handoff has unknown or missing fields")
    return run_root.resolve(strict=True), handoff


def verify_preflight(run_id: str) -> dict[str, Any]:
    """Verify completed native meta->winner->fixed-production evidence."""
    run_root, handoff = _load_handoff(run_id)
    state_raw = handoff["state_db"]
    if not isinstance(state_raw, str):
        raise ValueError("training handoff state_db must be a path")
    state = _safe_file(Path(state_raw), "native AutoData state")
    # The live controller database may be node-local.  Cross-node training
    # verifies the supervisor's atomic retained snapshot when configured.
    expected_state_raw = (
        os.getenv("AAR_AUTODATA_RETAINED_STATE", "").strip()
        or os.getenv("AAR_AUTODATA_STATE", "").strip()
    )
    if not expected_state_raw or state != _safe_file(
        Path(expected_state_raw), "trusted AAR_AUTODATA state"
    ):
        raise ValueError("training handoff state_db is not the trusted native state")

    dataset_path = _contained_file(run_root, handoff["dataset"], "production dataset")
    winner_export = _contained_directory(
        run_root, handoff["winner_export"], "winner export"
    )
    production_manifest = _contained_file(
        run_root, handoff["production_manifest"], "production manifest"
    )
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
        if len(production_ids) != REQUIRED_PRODUCTION_TASKS:
            raise ValueError("production manifest must contain exactly 1250 source tasks")
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
        if not isinstance(items, list) or len(items) < REQUIRED_TRAINING_ROWS:
            raise ValueError("production dataset retained fewer than 1000 accepted rows")
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
    finally:
        connection.close()

    return {
        "schema": "aar.autodata.lifecycle-verification/v1",
        "run_id": run_id,
        "workspace_id": workspace_id,
        "study_id": study_id,
        "meta_execution_id": meta_id,
        "production_execution_id": production_id,
        "production_manifest_sha256": _sha256(production_manifest),
        "dataset_sha256": _sha256(dataset_path),
        "source_task_count": REQUIRED_PRODUCTION_TASKS,
        "available_rows": len(items),
    }


def verify_consumption(run_id: str) -> dict[str, Any]:
    """Require proof that run_experiment consumed the verified production data."""
    verified = verify_preflight(run_id)
    run_root, handoff = _load_handoff(run_id)
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
    if value.get("required_rows") != REQUIRED_TRAINING_ROWS or value.get(
        "row_count"
    ) != REQUIRED_TRAINING_ROWS:
        raise ValueError("training consumption receipt must retain exactly 1000 rows")
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
    return {**verified, "consumption_receipt": str(receipt), "consumed_rows": 1000}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "verify-consumption"))
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    result = (
        verify_preflight(args.run_id)
        if args.command == "preflight"
        else verify_consumption(args.run_id)
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
