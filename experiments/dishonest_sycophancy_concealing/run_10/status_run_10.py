#!/usr/bin/env python3
"""Summarize one durable Run 10 attempt without reading evaluator holdout data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()
    attempt = args.attempt.resolve(strict=True)
    teams = list((attempt / "aar_teams").glob("*")) if (attempt / "aar_teams").exists() else []
    payload = {
        "attempt": str(attempt),
        "teams": len(teams),
        "submissions": sum(len(list(team.glob("submissions/*.json"))) for team in teams),
        "scores": sum(len(list(team.glob("scores/*.json"))) for team in teams),
        "findings": sum(len(list(team.glob("forum/*.json"))) for team in teams),
        "session_logs": sum(len(list(team.glob("logs/session_*.log"))) for team in teams),
        "children_recorded": (attempt / "metadata/children.env").exists(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
