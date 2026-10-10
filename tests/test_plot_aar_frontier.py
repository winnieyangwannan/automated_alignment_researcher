from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.plot_aar_frontier import load_frontier_points, resolve_team_dir


def _created_ms(value: str) -> int:
    timestamp = datetime.strptime(value, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    return int(timestamp.timestamp() * 1000)


def test_frontier_joins_scores_to_chronological_sessions(tmp_path: Path) -> None:
    team = tmp_path / "aar_teams" / "team"
    logs = team / "logs"
    scores = team / "scores"
    logs.mkdir(parents=True)
    scores.mkdir()
    for name in (
        "session_000_model_explore_alpha_20261009_100000.log",
        "session_000_model_explore_beta_20261009_100500.log",
        "session_001_model_explore_alpha_20261009_101000.log",
    ):
        (logs / name).write_text("session\n")

    alpha_run = f"model-explore-alpha-method-{_created_ms('20261009_101500')}"
    beta_run = f"model-explore-beta-method-{_created_ms('20261009_100600')}"
    (scores / f"{alpha_run}.json").write_text(
        json.dumps(
            {"headline_pct": 21.5, "passes_filter": True, "passes_regression": True}
        )
    )
    (scores / f"{beta_run}.json").write_text(
        json.dumps(
            {"headline_pct": 33.0, "passes_filter": False, "passes_regression": True}
        )
    )
    (scores / "model-explore-alpha-failed.failed.json").write_text("{}\n")

    resolved, attempt = resolve_team_dir(tmp_path)
    points, sessions = load_frontier_points(resolved)

    assert resolved == team
    assert attempt == tmp_path
    assert sessions == {"alpha": 2, "beta": 1}
    assert [(point.chain, point.session, point.score, point.valid) for point in points] == [
        ("beta", 1, 33.0, False),
        ("alpha", 2, 21.5, True),
    ]
