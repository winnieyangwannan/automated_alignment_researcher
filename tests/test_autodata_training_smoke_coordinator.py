from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from aar.infrastructure.autodata_coordinator.training_smoke import (
    TrainingSmokeCoordinator,
    TrainingSmokeCoordinatorError,
    training_job_id,
)


RUN_ID = "run13-trial5-alpha-method-1"
IDEA_NAME = "alpha__method"
CODE_HASH = "a" * 64
META_ID = "exe_" + "1" * 32
PRODUCTION_ID = "exe_" + "2" * 32


def _verification() -> dict[str, object]:
    return {
        "schema": "aar.autodata.lifecycle-verification/v1",
        "run_id": RUN_ID,
        "available_rows": 1000,
        "required_rows": 1000,
        "dataset_sha256": "sha256:" + "3" * 64,
        "meta_execution_id": META_ID,
        "production_execution_id": PRODUCTION_ID,
        "timing": {
            "schema": "aar.autodata.lifecycle-timing/v1",
            "run_id": RUN_ID,
        },
    }


def _coordinator(
    tmp_path: Path,
    *,
    runner=None,
    method_hash: str | None = CODE_HASH,
    scheduler_state: str | None = "PENDING",
    completion_grace_seconds: float = 120,
) -> tuple[TrainingSmokeCoordinator, Path, Path]:
    repo = tmp_path / "repo"
    team = tmp_path / "team"
    repo.mkdir()
    team.mkdir()

    def submit(command, **_kwargs):
        receipt = team / ".train_submissions" / f"{RUN_ID}.env"
        receipt.parent.mkdir()
        receipt.write_text(f"run_id={RUN_ID}\njob_id=12345\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "12345\n", "")

    return (
        TrainingSmokeCoordinator(
            repo=repo,
            team_dir=team,
            required_rows=1000,
            completion_grace_seconds=completion_grace_seconds,
            preflight_verifier=lambda _run_id: _verification(),
            method_hasher=lambda _idea_name: method_hash,
            protected_verifier=lambda _repo: None,
            command_runner=runner or submit,
            scheduler_reader=lambda _job_id: scheduler_state,
        ),
        repo,
        team,
    )


def _reconcile(coordinator: TrainingSmokeCoordinator):
    return coordinator.reconcile(
        run_id=RUN_ID,
        idea_name=IDEA_NAME,
        expected_code_hash=CODE_HASH,
        meta_execution_id=META_ID,
        production_execution_id=PRODUCTION_ID,
    )


def test_training_smoke_submission_is_receipt_idempotent(tmp_path: Path) -> None:
    calls = 0
    team = tmp_path / "team"

    def submit(command, **_kwargs):
        nonlocal calls
        calls += 1
        receipt = team / ".train_submissions" / f"{RUN_ID}.env"
        receipt.parent.mkdir()
        receipt.write_text(f"run_id={RUN_ID}\njob_id=12345\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "12345\n", "")

    coordinator, _repo, actual_team = _coordinator(tmp_path, runner=submit)
    assert actual_team == team

    submitted = _reconcile(coordinator)
    waiting = _reconcile(coordinator)

    assert submitted.state == "submitted"
    assert waiting.state == "waiting"
    assert submitted.job_id == waiting.job_id == "12345"
    assert calls == 1


def test_training_smoke_publishes_verified_terminal_receipt(tmp_path: Path) -> None:
    coordinator, _repo, team = _coordinator(tmp_path)
    assert _reconcile(coordinator).state == "submitted"
    model = team / "_train" / "model"
    model.mkdir(parents=True)
    weight = model / "adapter_model.safetensors"
    weight.write_bytes(b"adapter")
    consumption = team / "autodata" / RUN_ID / "training-consumption.json"
    consumption.parent.mkdir(parents=True)
    consumption.write_text("{}\n", encoding="utf-8")
    timings = team / "phase-timings.json"
    timings.write_text("{}\n", encoding="utf-8")
    smoke = team / "method_smoke" / f"{RUN_ID}.passed.json"
    smoke.parent.mkdir()
    smoke.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "passed",
                "run_id": RUN_ID,
                "model_path": str(model),
                "adapter_weight_file": weight.name,
                "smoke_run": True,
                "optimizer_steps": 1,
                "slurm_job_id": "12345",
                "phase_timings": str(timings),
                "autodata_consumption": {
                    **_verification(),
                    "consumed_rows": 1000,
                    "consumption_receipt": str(consumption),
                },
            }
        ),
        encoding="utf-8",
    )

    outcome = _reconcile(coordinator)

    assert outcome.state == "complete"
    assert outcome.terminal_receipt is not None
    payload = json.loads(outcome.terminal_receipt.read_text())
    assert payload["training"]["optimizer_steps"] == 1
    assert payload["training"]["consumed_rows"] == 1000
    assert payload["training"]["adapter_weight_sha256"]
    assert stat_mode(outcome.terminal_receipt) == 0o600


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_training_smoke_rejects_method_drift_before_submission(
    tmp_path: Path,
) -> None:
    calls = 0

    def submit(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("submission must not run")

    coordinator, _repo, _team = _coordinator(
        tmp_path, runner=submit, method_hash="b" * 64
    )

    with pytest.raises(
        TrainingSmokeCoordinatorError, match="method changed"
    ) as raised:
        _reconcile(coordinator)

    assert raised.value.code == "training_method_hash_mismatch"
    assert calls == 0


def test_training_smoke_fails_on_terminal_job_without_marker(tmp_path: Path) -> None:
    coordinator, _repo, _team = _coordinator(
        tmp_path, scheduler_state="FAILED"
    )
    assert _reconcile(coordinator).state == "submitted"

    with pytest.raises(TrainingSmokeCoordinatorError, match="ended in FAILED"):
        _reconcile(coordinator)


def test_training_smoke_bounds_completed_job_marker_grace(tmp_path: Path) -> None:
    coordinator, _repo, _team = _coordinator(
        tmp_path,
        scheduler_state="COMPLETED",
        completion_grace_seconds=0,
    )
    assert _reconcile(coordinator).state == "submitted"

    with pytest.raises(
        TrainingSmokeCoordinatorError, match="without its one-step result marker"
    ):
        _reconcile(coordinator)


def test_training_receipt_parser_rejects_extra_shell_fields(tmp_path: Path) -> None:
    team = tmp_path / "team"
    receipt = team / ".train_submissions" / f"{RUN_ID}.env"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        f"run_id={RUN_ID}\njob_id=12345\nextra=unsafe\n", encoding="utf-8"
    )

    with pytest.raises(TrainingSmokeCoordinatorError, match="does not match"):
        training_job_id(team, RUN_ID)
