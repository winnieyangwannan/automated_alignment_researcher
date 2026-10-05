#!/usr/bin/env python3
"""Verify that a two-session composed AAR chain completed the full loop twice."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def verify(team_dir: Path, expected: int) -> dict:
    team_dir = team_dir.resolve(strict=True)
    if expected != 2:
        raise SystemExit("this verifier is intentionally limited to two iterations")

    logs_dir = team_dir / "logs"
    scores_dir = team_dir / "scores"
    forum_dir = team_dir / "forum"
    summary = _json(logs_dir / "run_summary.json")
    required_summary = {
        "sessions": expected,
        "successful_sessions": expected,
        "failed_sessions": 0,
        "stop_reason": "max_iterations",
    }
    for key, value in required_summary.items():
        if summary.get(key) != value:
            raise SystemExit(
                f"invalid two-iteration run summary {key}: "
                f"{summary.get(key)!r} != {value!r}"
            )

    session_logs = sorted(logs_dir.glob("session_*.log"))
    if len(session_logs) != expected:
        raise SystemExit(f"expected {expected} session logs, found {len(session_logs)}")
    for path in session_logs:
        text = path.read_text()
        if "# Result: success=True" not in text or "# ERROR:" in text:
            raise SystemExit(f"session did not complete successfully: {path}")
    session_ids = {path.stem for path in session_logs}

    score_paths = sorted(scores_dir.glob("*.json"))
    if len(score_paths) != expected:
        raise SystemExit(f"expected {expected} score artifacts, found {len(score_paths)}")
    score_ids: set[str] = set()
    for path in score_paths:
        score = _json(path)
        if score.get("suite") != "honesty_sycophancy_concealing_uncertainty":
            raise SystemExit(f"score has wrong suite: {path}")
        if not isinstance(score.get("headline_pct"), (int, float)):
            raise SystemExit(f"score is missing a headline: {path}")
        per_benchmark = score.get("per_benchmark")
        if not isinstance(per_benchmark, dict) or len(per_benchmark) != 10:
            raise SystemExit(f"research score is not the held-out-stripped 10-entry result: {path}")
        if any(
            isinstance(item, dict) and item.get("role") == "held_out"
            for item in per_benchmark.values()
        ):
            raise SystemExit(f"research score leaked a held-out entry: {path}")
        score_ids.add(path.stem)

    result_by_session: dict[str, str] = {}
    for path in sorted(forum_dir.glob("*.json")):
        finding = _json(path)
        if finding.get("finding_type") == "result" and finding.get("run_id"):
            session_id = str(finding.get("aar_session_id") or "")
            if session_id not in session_ids:
                raise SystemExit(f"result finding has no valid originating session: {path}")
            if session_id in result_by_session:
                raise SystemExit(f"session shared more than one result: {session_id}")
            result_by_session[session_id] = str(finding["run_id"])
    if set(result_by_session) != session_ids:
        raise SystemExit("each successful session must share exactly one result")
    result_ids = set(result_by_session.values())
    if score_ids != result_ids:
        raise SystemExit(
            "evaluated run ids do not exactly match shared result findings: "
            f"scores={sorted(score_ids)!r}, findings={sorted(result_ids)!r}"
        )

    return {
        "ok": True,
        "team_dir": str(team_dir),
        "iterations": expected,
        "score_run_ids": sorted(score_ids),
        "held_out_isolation": "functional-smoke-only",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-dir", type=Path, required=True)
    parser.add_argument("--expected-iterations", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.team_dir, args.expected_iterations), indent=2))


if __name__ == "__main__":
    main()
