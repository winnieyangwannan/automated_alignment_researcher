"""Tests for held-out-safe Run 7 continuation reconstruction."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "experiments"
    / "dishonest_sycophancy_concealing"
    / "run_7"
    / "reconstruct_recovery_seed.py"
)
SPEC = importlib.util.spec_from_file_location("run7_reconstruct", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _entries() -> list[dict]:
    entries = []
    index = 0
    for chain, count in MODULE.EXPECTED_COMPLETED.items():
        for chain_index in range(count):
            index += 1
            run_id = (
                f"gemma4_31b-explore-{chain}-old-"
                f"gemma4_31b_explore_{chain}__method_{chain_index}-{index}"
            )
            entries.append(
                {
                    "run_id": run_id,
                    "headline_pct": float(index),
                    "summary": f"Public conclusion {index}",
                    "composite_scores": {
                        "passes_filter": True,
                        "passes_regression": True,
                        "per_benchmark": {"mmlu": {"mean": 0.4}},
                        "closed_pct": {"mask_factual": 1.0},
                        "regression_detail": {},
                        "dimension_scores_pct": {
                            "honesty": 1.0,
                            "sycophancy": 1.0,
                            "concealing_uncertainty": 0.0,
                        },
                    },
                }
            )
    return entries


def _snapshot(tmp_path: Path, entries: list[dict]) -> Path:
    root = tmp_path / "snapshot"
    results = root / "session" / "tool-results"
    results.mkdir(parents=True)
    payload = {"success": True, "entries": entries, "count": len(entries)}
    (results / "mcp-server-api-tools-get_leaderboard-123.txt").write_text(
        json.dumps(payload)
    )
    return root


def test_reconstructs_exact_forum_and_five_chain_logs(tmp_path: Path) -> None:
    output = tmp_path / "seed"
    metadata = MODULE.reconstruct(_snapshot(tmp_path, _entries()), output)

    assert metadata["entry_count"] == 14
    assert len(list((output / "forum").glob("*.json"))) == 14
    assert len(list((output / "agent_logs").glob("AGENT_LOG_*.md"))) == 5
    assert metadata["remaining_sessions"] == {
        "alpha": 43,
        "beta": 44,
        "gamma": 45,
        "delta": 44,
        "epsilon": 44,
    }
    alpha = (output / "agent_logs" / "AGENT_LOG_gemma4_31b_explore_alpha.md")
    assert "not a fresh first iteration" in alpha.read_text()


def test_rejects_any_heldout_identifier(tmp_path: Path) -> None:
    entries = _entries()
    entries[0]["composite_scores"]["per_benchmark"]["sycon_fp"] = {
        "mean": 0.5
    }

    with pytest.raises(ValueError, match="evaluator-private"):
        MODULE.reconstruct(_snapshot(tmp_path, entries), tmp_path / "seed")
