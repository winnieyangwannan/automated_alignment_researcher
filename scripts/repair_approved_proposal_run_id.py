#!/usr/bin/env python3
"""Repair a missing run ID on one already-approved decoupled proposal."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-dir", type=Path, required=True)
    parser.add_argument("--idea-uid", required=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--allow-method-drift", action="store_true")
    args = parser.parse_args()

    team = args.team_dir.resolve(strict=True)
    if not args.idea_uid or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for char in args.idea_uid
    ):
        parser.error("unsafe idea UID")
    os.environ.update(
        {
            "TEAM_DIR": str(team),
            "SCORES_DIR": str(team / "scores"),
            "AAR_IDEAS_DIR": str(team / "methods"),
            "IDEA_UID": args.idea_uid,
            "IDEA_NAME": args.idea_uid,
            "AAR_NO_LOCAL_GPU": "true",
        }
    )

    from aar.research_loop.tools.server_api_tools import (
        _approved_proposal_run_id_candidate,
        _ensure_approved_proposal_run_id,
    )

    if args.plan_only:
        print(
            _approved_proposal_run_id_candidate(
                allow_method_drift=args.allow_method_drift
            )
        )
    else:
        if args.allow_method_drift:
            parser.error("--allow-method-drift requires --plan-only")
        print(_ensure_approved_proposal_run_id())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
