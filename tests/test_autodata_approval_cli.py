from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from aar.research_loop import autodata_approval


def _environment(tmp_path: Path) -> dict[str, str]:
    plugin = tmp_path / "plugin"
    artifacts = tmp_path / "artifacts"
    workspaces = tmp_path / "workspaces"
    plugin.mkdir()
    artifacts.mkdir()
    workspaces.mkdir()
    wrapper = plugin / "scripts" / "autodata.py"
    wrapper.parent.mkdir()
    wrapper.write_text("# test wrapper\n", encoding="utf-8")
    state = tmp_path / "state.db"
    state.touch()
    return {
        "AAR_AUTODATA_PLUGIN_ROOT": str(plugin),
        "AAR_AUTODATA_STATE": str(state),
        "AAR_AUTODATA_ARTIFACTS": str(artifacts),
        "AAR_AUTODATA_WORKSPACES": str(workspaces),
        "AAR_AUTODATA_WRAPPER_PYTHON": "/pinned/autodata/python",
    }


def test_run_cli_uses_pinned_wrapper_python(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout='{"status":"ok"}\n', stderr=""
    )
    with (
        mock.patch.dict(os.environ, _environment(tmp_path), clear=False),
        mock.patch("subprocess.run", return_value=completed) as run,
    ):
        assert autodata_approval._run_cli(["status", "ws_test"]) == {
            "status": "ok"
        }

    assert run.call_args.args[0][0] == "/pinned/autodata/python"


def test_run_cli_reports_signal_when_stderr_is_empty(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=-9, stdout="", stderr=""
    )
    with (
        mock.patch.dict(os.environ, _environment(tmp_path), clear=False),
        mock.patch("subprocess.run", return_value=completed),
        pytest.raises(RuntimeError, match=r"exit=-9 signal=SIGKILL.*<empty>"),
    ):
        autodata_approval._run_cli(["status", "ws_test"])
