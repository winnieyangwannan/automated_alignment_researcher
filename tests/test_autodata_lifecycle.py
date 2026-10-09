from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from aar.infrastructure.autodata_lifecycle import (
    HANDOFF_SCHEMA,
    _canonical_tree_digest,
    verify_consumption,
    verify_preflight,
)


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    return path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _grounding(ids: list[str]) -> dict[str, object]:
    return {
        "schema": "autodata.grounding/v1",
        "name": "test grounding",
        "description": "test",
        "sources": [],
        "coverage_dimensions": [],
        "dry_run_task_ids": ids[:1],
        "tasks": [
            {"id": task_id, "seed": index, "payload": {}, "source_ids": [], "facets": {}}
            for index, task_id in enumerate(ids)
        ],
    }


def _dataset(execution_id: str, source_ids: list[str]) -> dict[str, object]:
    return {
        "schema": "autodata.dataset/v1",
        "execution_id": execution_id,
        "mode": "production",
        "winner_candidate_id": "cand_prod",
        "source_task_ids": source_ids,
        "aggregate": {"task_count": len(source_ids)},
        "items": [
            {
                "id": f"row-{index:04d}",
                "prompt": "prompt",
                "response": "response",
                "metadata": {"judge_accepted": True},
            }
            for index in range(1000)
        ],
    }


def _fixture(tmp_path: Path) -> tuple[str, Path, Path]:
    team = tmp_path / "team"
    run_id = "chain-method-1"
    run_root = team / "autodata" / run_id
    native = team / "autodata" / "native"
    run_root.mkdir(parents=True)
    native.mkdir(parents=True)

    winner = run_root / "winner"
    _write_json(winner / "autodata.pipeline.json", {"schema": "autodata.pipeline/v1"})
    _write_json(winner / "recipe" / "config.json", {"temperature": 0.1})
    tuning_ids = [f"tune-{index:04d}" for index in range(64)]
    validation_ids = [f"validation-{index:04d}" for index in range(32)]
    test_ids = [f"test-{index:04d}" for index in range(32)]
    meta_manifest = _write_json(
        winner / "grounding" / "meta-manifest.json",
        _grounding(tuning_ids + validation_ids),
    )
    test_manifest = _write_json(
        winner / "grounding" / "test-manifest.json", _grounding(test_ids)
    )

    production_tree = run_root / "production"
    shutil.copytree(winner, production_tree)
    production_ids = [f"production-{index:04d}" for index in range(1250)]
    production_manifest = _write_json(
        production_tree / "grounding" / "production-manifest.json",
        _grounding(production_ids),
    )

    meta_id = "exe_" + "1" * 32
    production_id = "exe_" + "2" * 32
    dataset = _write_json(
        run_root / "production-dataset.json", _dataset(production_id, production_ids)
    )
    state = native / "state.db"
    with sqlite3.connect(state) as connection:
        connection.executescript(
            """
            CREATE TABLE executions (
              id TEXT PRIMARY KEY, executionJson TEXT, pipelineRoot TEXT,
              status TEXT, phase TEXT, winnerCandidateId TEXT, maxIterations INTEGER
            );
            CREATE TABLE events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, scopeKind TEXT, scopeId TEXT,
              kind TEXT, payloadJson TEXT
            );
            CREATE TABLE candidates (
              id TEXT PRIMARY KEY, executionId TEXT, workspace TEXT
            );
            CREATE TABLE study_members (
              studyId TEXT, subjectKind TEXT, subjectId TEXT
            );
            """
        )
        meta_spec = {
            "schema": "autodata.execution/v1",
            "mode": "meta_optimize",
            "grounding": {
                "manifest_path": "grounding/meta-manifest.json",
                "digest": _digest(meta_manifest),
            },
            "tuning_task_ids": tuning_ids,
            "validation_task_ids": validation_ids,
            "test_grounding": {
                "manifest_path": "grounding/test-manifest.json",
                "digest": _digest(test_manifest),
            },
            "budget": {
                "max_iterations": 3,
                "min_iterations": 3,
                "early_stop_patience": 3,
            },
        }
        production_spec = {
            "schema": "autodata.execution/v1",
            "mode": "production",
            "grounding": {
                "manifest_path": "grounding/production-manifest.json",
                "digest": _digest(production_manifest),
            },
            "budget": {"max_iterations": 0},
        }
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?,?)",
            (meta_id, json.dumps(meta_spec), str(winner), "completed", "completed", "cand_meta", 3),
        )
        connection.execute(
            "INSERT INTO candidates VALUES (?,?,?)", ("cand_meta", meta_id, str(winner))
        )
        connection.execute(
            "INSERT INTO study_members VALUES (?,?,?)", ("study_one", "execution", meta_id)
        )
        connection.execute(
            "INSERT INTO study_members VALUES (?,?,?)",
            ("study_one", "workspace", "ws_" + "3" * 32),
        )
        connection.execute(
            "INSERT INTO events(scopeKind,scopeId,kind,payloadJson) VALUES (?,?,?,?)",
            ("execution", meta_id, "execution.created", json.dumps({"mode": "meta_optimize"})),
        )
        connection.execute(
            "INSERT INTO events(scopeKind,scopeId,kind,payloadJson) VALUES (?,?,?,?)",
            (
                "execution",
                meta_id,
                "execution.finalized",
                json.dumps(
                    {
                        "winner_candidate_id": "cand_meta",
                        "winner_tree_digest": _canonical_tree_digest(winner),
                    }
                ),
            ),
        )
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?,?)",
            (
                production_id,
                json.dumps(production_spec),
                str(production_tree),
                "completed",
                "completed",
                "cand_prod",
                0,
            ),
        )
        connection.execute(
            "INSERT INTO candidates VALUES (?,?,?)",
            ("cand_prod", production_id, str(production_tree)),
        )
        connection.execute(
            "INSERT INTO study_members VALUES (?,?,?)",
            ("study_one", "execution", production_id),
        )
        connection.execute(
            "INSERT INTO events(scopeKind,scopeId,kind,payloadJson) VALUES (?,?,?,?)",
            ("execution", production_id, "execution.created", json.dumps({"mode": "production"})),
        )
        connection.execute(
            "INSERT INTO events(scopeKind,scopeId,kind,payloadJson) VALUES (?,?,?,?)",
            (
                "execution",
                production_id,
                "execution.finalized",
                json.dumps(
                    {
                        "winner_candidate_id": "cand_prod",
                        "winner_tree_digest": _canonical_tree_digest(production_tree),
                        "dataset": {"digest": _digest(dataset)},
                    }
                ),
            ),
        )

    _write_json(
        run_root / "training-handoff.json",
        {
            "schema": HANDOFF_SCHEMA,
            "run_id": run_id,
            "state_db": str(state),
            "dataset": str(dataset),
            "workspace_id": "ws_" + "3" * 32,
            "study_id": "study_one",
            "meta_execution_id": meta_id,
            "production_execution_id": production_id,
            "winner_export": str(winner),
            "production_manifest": str(production_manifest),
            "consumption_receipt": str(run_root / "training-consumption.json"),
        },
    )
    return run_id, team, state


def test_preflight_verifies_native_meta_winner_and_production(tmp_path: Path) -> None:
    run_id, team, state = _fixture(tmp_path)
    with mock.patch.dict(
        os.environ,
        {"TEAM_DIR": str(team), "AAR_AUTODATA_STATE": str(state)},
        clear=False,
    ):
        result = verify_preflight(run_id)
    assert result["source_task_count"] == 1250
    assert result["available_rows"] == 1000


def test_preflight_prefers_retained_state_for_cross_node_handoff(
    tmp_path: Path,
) -> None:
    run_id, team, state = _fixture(tmp_path)
    with mock.patch.dict(
        os.environ,
        {
            "TEAM_DIR": str(team),
            "AAR_AUTODATA_STATE": str(tmp_path / "node-local" / "state.db"),
            "AAR_AUTODATA_RETAINED_STATE": str(state),
        },
        clear=False,
    ):
        assert verify_preflight(run_id)["available_rows"] == 1000


def test_preflight_rejects_non_winner_production_tree(tmp_path: Path) -> None:
    run_id, team, state = _fixture(tmp_path)
    (team / "autodata" / run_id / "production" / "recipe" / "config.json").write_text(
        '{"temperature": 0.9}\n'
    )
    with mock.patch.dict(
        os.environ,
        {"TEAM_DIR": str(team), "AAR_AUTODATA_STATE": str(state)},
        clear=False,
    ):
        with pytest.raises(ValueError, match="production winner tree"):
            verify_preflight(run_id)


def test_preflight_rejects_incomplete_meta_execution(tmp_path: Path) -> None:
    run_id, team, state = _fixture(tmp_path)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "UPDATE executions SET status='active', phase='baseline_pending' "
            "WHERE id=?",
            ("exe_" + "1" * 32,),
        )
    with mock.patch.dict(
        os.environ,
        {"TEAM_DIR": str(team), "AAR_AUTODATA_STATE": str(state)},
        clear=False,
    ):
        with pytest.raises(ValueError, match="meta_optimize execution is not completed"):
            verify_preflight(run_id)


def test_preflight_rejects_production_created_before_meta_finalization(
    tmp_path: Path,
) -> None:
    run_id, team, state = _fixture(tmp_path)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "UPDATE events SET id=100 WHERE scopeId=? AND kind='execution.finalized'",
            ("exe_" + "1" * 32,),
        )
    with mock.patch.dict(
        os.environ,
        {"TEAM_DIR": str(team), "AAR_AUTODATA_STATE": str(state)},
        clear=False,
    ):
        with pytest.raises(ValueError, match="production was created before"):
            verify_preflight(run_id)


def test_preflight_rejects_overlapping_or_wrong_size_production_manifest(
    tmp_path: Path,
) -> None:
    run_id, team, state = _fixture(tmp_path)
    manifest = team / "autodata" / run_id / "production" / "grounding" / "production-manifest.json"
    _write_json(manifest, _grounding(["tune-1"]))
    with mock.patch.dict(
        os.environ,
        {"TEAM_DIR": str(team), "AAR_AUTODATA_STATE": str(state)},
        clear=False,
    ):
        with pytest.raises(ValueError):
            verify_preflight(run_id)


def test_consumption_requires_mode_0600_exact_1000_row_receipt(tmp_path: Path) -> None:
    run_id, team, state = _fixture(tmp_path)
    run_root = team / "autodata" / run_id
    dataset = run_root / "production-dataset.json"
    receipt = _write_json(
        run_root / "training-consumption.json",
        {
            "schema": "aar.autodata.native-campaign-consumption/v1",
            "execution_ids": ["exe_" + "2" * 32],
            "dataset_sha256s": [_digest(dataset)],
            "required_rows": 1000,
            "row_count": 1000,
            "consumer_pid": os.getpid(),
        },
    )
    receipt.chmod(0o600)
    with mock.patch.dict(
        os.environ,
        {"TEAM_DIR": str(team), "AAR_AUTODATA_STATE": str(state)},
        clear=False,
    ):
        assert verify_consumption(run_id)["consumed_rows"] == 1000
        receipt.chmod(0o644)
        with pytest.raises(ValueError, match="mode 0600"):
            verify_consumption(run_id)


def test_train_entrypoints_gate_before_submission_and_model_upload() -> None:
    root = Path(__file__).resolve().parents[1]
    submit = (root / "scripts" / "submit_train_job.sh").read_text()
    train = (root / "scripts" / "slurm_train_submit.sh").read_text()
    assert submit.index("autodata_lifecycle preflight") < submit.index("sbatch --parsable")
    assert train.index("autodata_lifecycle preflight") < train.index("run_experiment")
    assert train.index("verify_consumption") < train.index("transport.put_model")
