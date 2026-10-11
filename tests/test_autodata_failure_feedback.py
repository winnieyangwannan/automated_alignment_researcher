from __future__ import annotations

import importlib.util
import urllib.error
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RECIPES = (
    ROOT
    / "aar"
    / "autodata_recipes"
    / "dishonest_sycophancy_concealing"
    / "recipe"
    / "task.py",
    ROOT
    / "aar"
    / "autodata_recipes"
    / "dishonest_sycophancy_concealing_v1"
    / "recipe"
    / "task.py",
)


def _load(path: Path, index: int):
    spec = importlib.util.spec_from_file_location(
        f"autodata_failure_feedback_{index}", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", RECIPES)
def test_recipe_failure_detail_retains_cause_but_redacts_secrets(
    path: Path,
) -> None:
    task = _load(path, RECIPES.index(path))
    try:
        raise ValueError(
            "HTTP 409 token=top-secret "
            "https://user:pass@provider.test/v1?api_key=also-secret"
        )
    except ValueError as cause:
        error = RuntimeError("model request exhausted bounded attempts")
        error.__cause__ = cause

    detail = task._safe_failure_detail(error)

    assert "RuntimeError: model request exhausted bounded attempts" in detail
    assert "caused by ValueError: HTTP 409" in detail
    assert "top-secret" not in detail
    assert "also-secret" not in detail
    assert "user:pass" not in detail
    assert "[REDACTED]" in detail
    assert len(detail) <= 800


@pytest.mark.parametrize("path", RECIPES)
def test_recipe_emits_non_content_broker_error_codes(path: Path) -> None:
    task = _load(path, RECIPES.index(path) + 10)
    http_error = urllib.error.HTTPError(
        "https://provider.test/v1", 409, "Conflict", {}, None
    )
    wrapped = RuntimeError("model request failed after bounded attempts")
    wrapped.__cause__ = http_error

    assert task._failure_reason_code(wrapped) == "provider_http_409"
    assert task._failure_reason_code(TimeoutError("timed out")) == "provider_timeout"
    assert (
        task._failure_reason_code(urllib.error.URLError("connection reset"))
        == "provider_connection_failure"
    )
    assert (
        task._failure_reason_code(
            task.MeteredCallError("generator content was unusable", {})
        )
        == "generator_invalid_content"
    )
