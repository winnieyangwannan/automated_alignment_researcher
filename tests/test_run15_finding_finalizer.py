import json
from pathlib import Path

import pytest

from experiments.dishonest_sycophancy_concealing.run_15.recovery.finalize_scored_run import (
    _select_proposal,
    _select_team,
)


def test_full_attempt_finalizer_selects_exact_seed(tmp_path: Path) -> None:
    teams = tmp_path / "aar_teams"
    alpha = teams / "run15-gemma4-31b-kimi26-alpha-100"
    gamma = teams / "run15-gemma4-31b-kimi26-gamma-100"
    alpha.mkdir(parents=True)
    gamma.mkdir()

    assert _select_team(tmp_path, "gamma") == gamma
    with pytest.raises(RuntimeError, match="expected one team directory"):
        _select_team(tmp_path, None)


def test_full_attempt_finalizer_rejects_ambiguous_seed(tmp_path: Path) -> None:
    teams = tmp_path / "aar_teams"
    (teams / "run15-alpha-one").mkdir(parents=True)
    (teams / "run15-alpha-two").mkdir()

    with pytest.raises(RuntimeError, match="found 2"):
        _select_team(tmp_path, "alpha")


def test_full_attempt_finalizer_selects_exact_run_id(tmp_path: Path) -> None:
    proposals = tmp_path / "scores" / ".proposals"
    proposals.mkdir(parents=True)
    (proposals / "first.json").write_text(json.dumps({"run_id": "run-one"}))
    (proposals / "second.json").write_text(json.dumps({"run_id": "run-two"}))

    assert _select_proposal(tmp_path, "run-two")["run_id"] == "run-two"
    with pytest.raises(RuntimeError, match="found 0"):
        _select_proposal(tmp_path, "missing")
