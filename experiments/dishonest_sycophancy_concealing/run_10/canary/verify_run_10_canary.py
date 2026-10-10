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
    method_smoke = load_json(attempt / "metadata/method_smoke_passed.json")
    evaluation_contract = load_json(
        attempt / "metadata/lifecycle_evaluation_contract.json"
    )
    children = dict(
        line.split("=", 1)
        for line in (attempt / "metadata/children.env").read_text().splitlines()
        if "=" in line
    )
    scores = list(attempt.glob("aar_teams/*/scores/*.json"))
    findings = list(attempt.glob("aar_teams/*/forum/*.json"))
    run_id = method_smoke.get("run_id")
    score_path = next(
        (
            path
            for path in scores
            if path.name == f"{run_id}.json"
            and not path.name.endswith(".failed.json")
        ),
        None,
    )
    score = load_json(score_path) if score_path is not None else {}
    matching_findings = [
        path for path in findings if load_json(path).get("run_id") == run_id
    ]
    score_result_pair = score_path is not None and len(matching_findings) == 1

    expected_benchmarks = evaluation_contract.get("expected_benchmarks")
    expected_items = evaluation_contract.get("expected_items_per_benchmark")
    per_benchmark = score.get("per_benchmark")
    evaluation_item_contract = (
        evaluation_contract.get("status") == "passed"
        and isinstance(expected_benchmarks, list)
        and len(expected_benchmarks) == 1
        and isinstance(expected_items, int)
        and isinstance(per_benchmark, dict)
        and set(per_benchmark) == set(expected_benchmarks)
        and all(
            isinstance(per_benchmark.get(name), dict)
            and per_benchmark[name].get("n") == expected_items
            for name in expected_benchmarks
        )
    )

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
        "method_gpu_smoke": method_smoke.get("real_gpu_smoke") is True,
        "adapter_reload_validation": method_smoke.get("adapter_reload_validation")
        is True,
        "on_demand_evaluator": children.get("on_demand_evaluator") == "1",
        "evaluation_item_contract": evaluation_item_contract,
        "evaluation_benchmarks": expected_benchmarks,
        "expected_items_per_benchmark": expected_items,
        "evaluated_items_per_benchmark": {
            name: per_benchmark.get(name, {}).get("n")
            for name in expected_benchmarks or []
        }
        if isinstance(per_benchmark, dict)
        else {},
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
        "method_gpu_smoke",
        "adapter_reload_validation",
        "on_demand_evaluator",
        "evaluation_item_contract",
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
