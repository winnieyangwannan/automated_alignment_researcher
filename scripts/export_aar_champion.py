#!/usr/bin/env python3
"""Select and package the highest-scoring valid result from one AAR team run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aar.champion import ChampionExportError, export_champion  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--team-dir",
        type=Path,
        help="team directory containing scores/, submissions/, methods/, and forum/",
    )
    source.add_argument(
        "--attempt-dir",
        type=Path,
        help="run attempt containing exactly one aar_teams/<team>/ directory",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="new submission directory to create atomically",
    )
    parser.add_argument("--suite", help="reject scores from any other suite")
    parser.add_argument(
        "--inference-backend",
        help="reject scores produced by any other inference backend",
    )
    parser.add_argument(
        "--require-artifact-type",
        choices=("either", "adapter", "full_model"),
        default="either",
    )
    parser.add_argument(
        "--base-model",
        help="portable base-model identifier to record instead of the adapter's local path",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output directory",
    )
    return parser.parse_args()


def resolve_team_dir(args: argparse.Namespace) -> Path:
    if args.team_dir:
        return args.team_dir
    teams_root = args.attempt_dir / "aar_teams"
    if not teams_root.is_dir():
        raise ChampionExportError(f"teams directory does not exist: {teams_root}")
    teams = sorted(path for path in teams_root.iterdir() if path.is_dir())
    if len(teams) != 1:
        raise ChampionExportError(
            f"expected exactly one team under {teams_root}, found {len(teams)}"
        )
    return teams[0]


def main() -> int:
    args = parse_args()
    try:
        team_dir = resolve_team_dir(args)
        manifest = export_champion(
            team_dir,
            args.output_dir,
            expected_suite=args.suite,
            expected_inference_backend=args.inference_backend,
            required_artifact_type=args.require_artifact_type,
            base_model=args.base_model,
            force=args.force,
        )
    except ChampionExportError as error:
        print(f"ERROR: {error}")
        return 1
    selected = manifest["selected"]
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.absolute()),
                "run_id": selected["run_id"],
                "idea_name": selected["idea_name"],
                "headline_pct": selected["headline_pct"],
                "artifact_type": selected["artifact_type"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
