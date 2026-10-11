#!/usr/bin/env python3
"""Publish the missing finding for one already-scored Run 15 iteration."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from aar.research_loop.kimi_agent import KimiAgent


def _load_object(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"expected one JSON object in {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--max-continuations", type=int, default=6)
    args = parser.parse_args()

    attempt = args.attempt.resolve(strict=True)
    workspace = Path(os.environ["AAR_REPO"]).resolve(strict=True)
    teams = [path for path in (attempt / "aar_teams").iterdir() if path.is_dir()]
    if len(teams) != 1:
        raise RuntimeError(f"expected one team directory, found {len(teams)}")
    team = teams[0]

    proposal_markers = sorted(
        path
        for path in (team / "scores" / ".proposals").glob("*.json")
        if path.is_file()
    )
    if len(proposal_markers) != 1:
        raise RuntimeError(
            f"expected one chain proposal marker, found {len(proposal_markers)}"
        )
    proposal = _load_object(proposal_markers[0])
    if proposal.get("approved") is not True:
        raise RuntimeError("proposal marker is not approved")
    run_id = proposal.get("run_id")
    idea_uid = proposal.get("idea_uid")
    idea_name = proposal.get("idea_name")
    if not all(isinstance(value, str) and value for value in (run_id, idea_uid, idea_name)):
        raise RuntimeError("proposal marker lacks run_id, idea_uid, or idea_name")

    score_path = team / "scores" / f"{run_id}.json"
    score = _load_object(score_path)
    existing = [
        path
        for path in (team / "forum").glob("*.json")
        if _load_object(path).get("run_id") == run_id
    ]
    if len(existing) == 1:
        print(existing[0])
        return
    if existing:
        raise RuntimeError(f"run_id already has {len(existing)} findings")

    environment = {
        "TEAM_DIR": str(team),
        "LOCAL_FINDINGS_DIR": str(team / "forum"),
        "SUBMISSIONS_DIR": str(team / "submissions"),
        "SCORES_DIR": str(team / "scores"),
        "AAR_IDEAS_DIR": str(team / "methods"),
        "SESSION_LOGS_DIR": str(team / "logs"),
        "LIT_FORUM_DIR": str(team / "litreview"),
        "IDEA_UID": idea_uid,
        "IDEA_NAME": idea_name,
        "AAR_RESUME_APPROVED_PROPOSAL": "1",
        "AAR_REQUIRE_SUCCESSFUL_ITERATIONS": "1",
        "AAR_AUTODATA": "0",
        "LOCAL_MODE": "true",
        "FORUM_BACKEND": "fs",
        "AAR_MODE": "true",
        "HARNESS_TRANSPORT": "fs",
    }
    os.environ.update(environment)

    public_score = json.dumps(score, sort_keys=True)
    task = (
        "Recover only the missing final finding for an experiment that is already "
        "approved, trained, and scored. Do not call literature, edit files, submit a "
        "proposal, train, or evaluate. Call the native structured MCP tool "
        "share_finding with finding_type='result', worked=false, "
        f"run_id={run_id!r}, and idea_name={idea_name!r}. Include a concise summary "
        "and a results_writeup of at least 80 characters covering the public "
        "benchmark movement, capability-filter behavior, likely mechanism, and the "
        "two-item canary limitation. The authoritative public score is: "
        f"{public_score}. Stop after share_finding succeeds."
    )
    result = asyncio.run(
        KimiAgent(
            "run15-finding-finalizer",
            workspace,
            model=None,
            cli_path=os.environ.get("KIMI_CLI_PATH"),
            include_prior_work=False,
            system_prompt=(
                "You are a finding-only recovery agent. Use the exact approved run "
                "and public score supplied by the user. Make no other experiment "
                "changes and finish with one successful share_finding call."
            ),
            completion_tool="share_finding",
            max_continuations=args.max_continuations,
            auto_approve=True,
            force_checkpoint_tools=True,
            force_completion_tool_first_turn=True,
            disallowed_tools=[
                "Write",
                "Edit",
                "Bash",
                "Glob",
                "Grep",
                "WebSearch",
                "WebFetch",
                "CreateGoal",
                "UpdateGoal",
                "SetGoalBudget",
                "TodoList",
                "WaitFor",
                "Agent",
                "AgentSwarm",
            ],
            turn_timeout_seconds=300,
        ).execute(task)
    )
    if not result.success:
        raise RuntimeError(f"finding finalizer failed: {result.error}")

    published = [
        path
        for path in (team / "forum").glob("*.json")
        if _load_object(path).get("run_id") == run_id
    ]
    if len(published) != 1:
        raise RuntimeError(
            f"expected one finding for {run_id}, found {len(published)}"
        )
    print(published[0])


if __name__ == "__main__":
    main()
