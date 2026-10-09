from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from aar.eval_pod.failure import (
    install_uncaught_exception_failure_hook,
    publish_failure,
    sanitize_failure_text,
)


def test_publish_failure_is_atomic_and_idempotent(tmp_path: Path) -> None:
    path = publish_failure(
        tmp_path,
        "candidate-1",
        "adapter merge failed",
        eval_job_id="42",
    )
    assert path.name == "candidate-1.failed.json"
    assert json.loads(path.read_text()) == {
        "schema_version": 2,
        "status": "failed",
        "run_id": "candidate-1",
        "stage": "evaluation",
        "error_code": "evaluator_rejected",
        "retryable": False,
        "error": "adapter merge failed",
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


def test_publish_failure_sanitizes_diagnostics_and_adds_training_context(
    tmp_path: Path,
) -> None:
    path = publish_failure(
        tmp_path,
        "candidate-2",
        "TypeError: bad argument; API_KEY=super-secret",
        stage="training",
        error_code="training_python_exception",
        exception_type="TypeError",
        exit_code=1,
        log_path="/safe/team/logs/train-12.out",
    )
    payload = json.loads(path.read_text())
    assert payload["stage"] == "training"
    assert payload["error_code"] == "training_python_exception"
    assert payload["exception_type"] == "TypeError"
    assert payload["exit_code"] == 1
    assert payload["log_path"] == "/safe/team/logs/train-12.out"
    assert "super-secret" not in payload["error"]
    assert "[REDACTED]" in payload["error"]


def test_uncaught_exception_hook_publishes_before_chaining(tmp_path: Path) -> None:
    chained: list[tuple[type[BaseException], BaseException]] = []

    def prior(exception_class, exception, _traceback) -> None:
        chained.append((exception_class, exception))

    with patch.object(sys, "excepthook", prior):
        hook = install_uncaught_exception_failure_hook(
            tmp_path,
            "candidate-3",
            stage="training",
            error_code="training_python_exception",
            log_path="/safe/train-13.out",
        )
        error = TypeError("unexpected keyword argument 'tokenizer'")
        hook(TypeError, error, None)

    payload = json.loads((tmp_path / "candidate-3.failed.json").read_text())
    assert payload["exception_type"] == "TypeError"
    assert payload["error"] == "unexpected keyword argument 'tokenizer'"
    assert chained == [(TypeError, error)]


def test_sanitize_failure_text_collapses_lines_and_redacts_bearer() -> None:
    assert sanitize_failure_text("first\nsecond Bearer abc123") == (
        "first second Bearer [REDACTED]"
    )
