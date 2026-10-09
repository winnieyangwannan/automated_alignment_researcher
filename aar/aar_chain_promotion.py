"""Select the best durable adapter candidate for one AAR chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aar.autodata_campaign_policy import atomic_write_json
from aar.champion import ChampionExportError, select_champion


def select_promotion(
    team_dir: Path,
    merged_root: Path,
    current: dict[str, Any] | None,
    *,
    expected_suite: str,
) -> dict[str, Any]:
    try:
        candidate, _ = select_champion(
            team_dir,
            expected_suite=expected_suite,
            expected_inference_backend="vllm",
            required_artifact_type="adapter",
        )
    except ChampionExportError:
        if current:
            return {**current, "changed": False}
        raise
    if candidate.finding_path is None:
        raise ChampionExportError(
            f"candidate {candidate.run_id} has no durable result finding"
        )
    assert candidate.model_path is not None
    merged = (merged_root / candidate.run_id).resolve(strict=True)
    receipt = merged / ".merge-complete.json"
    if not receipt.is_file():
        raise ChampionExportError(
            f"candidate {candidate.run_id} has no retained merge receipt"
        )
    previous_run = current.get("run_id") if current else None
    previous_headline = current.get("headline_pct") if current else None
    promote = previous_run != candidate.run_id and (
        previous_headline is None or candidate.headline_pct > previous_headline
    )
    if not promote and current:
        return {**current, "changed": False}
    return {
        "schema": "aar.chain-incumbent/v1",
        "run_id": candidate.run_id,
        "headline_pct": candidate.headline_pct,
        "adapter_checkpoint": str(candidate.model_path.resolve(strict=True)),
        "merged_checkpoint": str(merged),
        "score_path": str(candidate.score_path.resolve(strict=True)),
        "finding_path": str(candidate.finding_path.resolve(strict=True)),
        "changed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-dir", required=True, type=Path)
    parser.add_argument("--merged-root", required=True, type=Path)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--expected-suite", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    current = None
    if args.current and args.current.is_file():
        current = json.loads(args.current.read_text(encoding="utf-8"))
    selected = select_promotion(
        args.team_dir.resolve(strict=True),
        args.merged_root.resolve(strict=True),
        current,
        expected_suite=args.expected_suite,
    )
    atomic_write_json(args.output, selected)
    print(json.dumps(selected, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
