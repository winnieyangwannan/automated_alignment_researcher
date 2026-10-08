#!/usr/bin/env python3
"""Create the fail-closed proof required before the Run 10 full launch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object in {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()
    attempt = args.attempt.resolve(strict=True)
    submission_lines = (attempt / "metadata/submission.txt").read_text().splitlines()
    submission = dict(
        line.split("=", 1) for line in submission_lines if "=" in line
    )
    preflight = load_json(attempt / "metadata/kimi_mcp_preflight.json")
    scores = list(attempt.glob("aar_teams/*/scores/*.json"))
    findings = list(attempt.glob("aar_teams/*/forum/*.json"))
    score_uids = {load_json(path).get("idea_uid") for path in scores}
    finding_uids = {load_json(path).get("idea_uid") for path in findings}
    score_result_pair = bool((score_uids & finding_uids) - {None})

    eval_logs = list(attempt.glob("aar_teams/*/_eval_private/eval_worker_*.out"))
    log_text = "\n".join(path.read_text(errors="replace") for path in eval_logs)
    fail_closed_markers = all(
        marker in log_text
        for marker in (
            "backend=vllm image=docker.io/vllm/vllm-openai:v0.25.1 lora_strategy=merged_checkpoint",
            "runtime backend=vllm version=0.25.1 language_model_only=True",
        )
    )
    merge_manifest_retained = bool(
        list(attempt.glob("aar_teams/*/_eval_private/merge_manifests/*.json"))
    )
    ephemeral_merge_removed = "removed ephemeral merged checkpoint" in log_text
    ephemeral_root_absent = not (attempt / "merged_candidates").exists()
    proof = {
        "status": "passed",
        "canary_git_commit": submission.get("git_commit"),
        "attempt_dir": str(attempt),
        "score_result_pair": score_result_pair,
        "fail_closed_markers": fail_closed_markers,
        "merge_manifest_retained": merge_manifest_retained,
        "ephemeral_merge_removed": ephemeral_merge_removed and ephemeral_root_absent,
        "kimi_mcp_tool_roundtrip": preflight.get("mcp_tool_roundtrip") is True,
        "score_files": len(scores),
        "finding_files": len(findings),
    }
    required = (
        "canary_git_commit",
        "score_result_pair",
        "fail_closed_markers",
        "merge_manifest_retained",
        "ephemeral_merge_removed",
        "kimi_mcp_tool_roundtrip",
    )
    failed = [field for field in required if not proof.get(field)]
    if failed:
        proof["status"] = "failed"
    output = attempt / "metadata/canary_passed.json"
    output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    if failed:
        raise SystemExit(f"canary proof failed: {', '.join(failed)}")
    print(output)


if __name__ == "__main__":
    main()
