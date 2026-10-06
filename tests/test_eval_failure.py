from __future__ import annotations

import json
from pathlib import Path

import pytest

from aar.eval_pod.failure import publish_failure


def test_publish_failure_is_atomic_and_idempotent(tmp_path: Path) -> None:
    path = publish_failure(
        tmp_path,
        "candidate-1",
        "adapter merge failed",
        eval_job_id="42",
    )
    assert path.name == "candidate-1.failed.json"
    assert json.loads(path.read_text()) == {
        "status": "failed",
        "run_id": "candidate-1",
        "reason": "adapter merge failed",
        "eval_job_id": "42",
    }
    assert publish_failure(tmp_path, "candidate-1", "different") == path
    assert not list(tmp_path.glob("*.tmp"))


def test_publish_failure_never_replaces_success(tmp_path: Path) -> None:
    (tmp_path / "candidate-1.json").write_text("{}\n")
    with pytest.raises(FileExistsError, match="refusing to replace"):
        publish_failure(tmp_path, "candidate-1", "failure")


def test_publish_failure_rejects_path_run_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="path component"):
        publish_failure(tmp_path, "../candidate", "failure")
