#!/usr/bin/env python3
"""Create a fail-closed proof for a Run 16 native-generation lifecycle gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import yaml


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object in {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method_runs(method_smoke: dict) -> list[dict]:
    runs = method_smoke.get("runs")
    if isinstance(runs, list) and runs and all(isinstance(run, dict) for run in runs):
        return runs
    if method_smoke.get("run_id"):
        return [method_smoke]
    return []


def _key_values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text().splitlines() if "=" in line
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()
    attempt = args.attempt.resolve(strict=True)

    submission = _key_values(attempt / "metadata/submission.txt")
    children = _key_values(attempt / "metadata/children.env")
    preflight = load_json(attempt / "metadata/claude_research_preflight.json")
    method_runs = _method_runs(
        load_json(attempt / "metadata/method_smoke_passed.json")
    )
    evaluation_contract = load_json(
        attempt / "metadata/lifecycle_evaluation_contract.json"
    )
    config = yaml.safe_load((attempt / "metadata/run.yaml").read_text())
    if not isinstance(config, dict):
        raise RuntimeError("retained run config must be a mapping")

    chain_count = len(method_runs)
    configured_seeds = config.get("research", {}).get("seeds", [])
    configured_workers = config.get("evaluation", {}).get("workers")
    autodata_disabled = (
        config.get("data_generation", {}).get("backend") == "native"
        and submission.get("data_generation_backend") == "native"
        and submission.get("autodata") == "0"
    )

    scores = list(attempt.glob("aar_teams/*/scores/*.json"))
    findings = list(attempt.glob("aar_teams/*/forum/*.json"))
    successful_scores = {
        path.stem: path
        for path in scores
        if not path.name.endswith(".failed.json")
    }
    findings_by_run: dict[str, list[Path]] = {}
    for path in findings:
        run_id = load_json(path).get("run_id")
        if isinstance(run_id, str):
            findings_by_run.setdefault(run_id, []).append(path)

    expected_benchmarks = evaluation_contract.get("expected_benchmarks")
    expected_items = evaluation_contract.get("expected_items_per_benchmark")
    score_contracts: list[bool] = []
    paired_runs: list[str] = []
    evaluated_items: dict[str, dict[str, int | None]] = {}
    for method_run in method_runs:
        run_id = method_run.get("run_id")
        score_path = successful_scores.get(run_id)
        score = load_json(score_path) if score_path is not None else {}
        per_benchmark = score.get("per_benchmark")
        contract_passed = (
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
        score_contracts.append(contract_passed)
        if score_path is not None and len(findings_by_run.get(run_id, [])) == 1:
            paired_runs.append(run_id)
        evaluated_items[run_id] = (
            {
                name: per_benchmark.get(name, {}).get("n")
                for name in expected_benchmarks or []
            }
            if isinstance(per_benchmark, dict)
            else {}
        )

    evaluator_ids = children.get("evaluator_jobs", "").split()
    expected_evaluator_jobs = int(
        children.get("expected_evaluator_jobs", str(configured_workers or 0))
    )
    eval_logs = list(attempt.glob("aar_teams/*/_eval_private/eval_worker_*.out"))
    required_markers = (
        "backend=vllm image=docker.io/vllm/vllm-openai:v0.25.1 "
        "lora_strategy=merged_checkpoint",
        "runtime backend=vllm version=0.25.1 language_model_only=True",
    )
    log_texts = [path.read_text(errors="replace") for path in eval_logs]
    fail_closed_markers = (
        len(evaluator_ids) == expected_evaluator_jobs > 0
        and len(eval_logs) >= expected_evaluator_jobs
        and all(all(marker in text for marker in required_markers) for text in log_texts)
    )
    manifests = list(
        attempt.glob("aar_teams/*/_eval_private/merge_manifests/*.json")
    )
    ephemeral_root_absent = not (attempt / "merged_candidates").exists()
    prerequisite = attempt / "metadata/prerequisite_lifecycle_passed.json"
    prerequisite_hash = _sha256(prerequisite) if prerequisite.is_file() else None

    proof = {
        "schema_version": 1,
        "status": "passed",
        "canary_git_commit": submission.get("git_commit"),
        "attempt_dir": str(attempt),
        "lifecycle_name": submission.get("lifecycle_name"),
        "lifecycle_chain_count": chain_count,
        "successful_lifecycle_runs": len(paired_runs),
        "run_ids": [run.get("run_id") for run in method_runs],
        "score_result_pair": chain_count > 0 and len(paired_runs) == chain_count,
        "fail_closed_markers": fail_closed_markers,
        "merge_manifest_retained": len(manifests) >= chain_count > 0,
        "ephemeral_merge_removed": (
            sum(
                text.count("removed ephemeral merged checkpoint")
                for text in log_texts
            )
            >= chain_count
            and ephemeral_root_absent
        ),
        "claude_research_preflight": (
            preflight.get("status") == "passed"
            and preflight.get("research_backend") == "claude"
            and preflight.get("research_model") == "claude-opus-4-8"
            and preflight.get("research_effort") == "max"
            and preflight.get("claude_cli_executable") is True
            and preflight.get("secure_internet_mode") is True
            and preflight.get("bounded_paper_search") is True
        ),
        "method_gpu_smoke": chain_count > 0
        and all(run.get("real_gpu_smoke") is True for run in method_runs),
        "adapter_reload_validation": chain_count > 0
        and all(
            run.get("adapter_reload_validation") is True for run in method_runs
        ),
        "on_demand_evaluator": children.get("on_demand_evaluator") == "1"
        and len(evaluator_ids) == expected_evaluator_jobs > 0,
        "evaluation_item_contract": chain_count > 0 and all(score_contracts),
        "autodata_disabled": autodata_disabled,
        "evaluation_benchmarks": expected_benchmarks,
        "expected_items_per_benchmark": expected_items,
        "evaluated_items_per_run": evaluated_items,
        "score_files": len(scores),
        "finding_files": len(findings),
        "prerequisite_proof_sha256": prerequisite_hash,
    }
    if chain_count == 1:
        proof["evaluated_items_per_benchmark"] = next(
            iter(evaluated_items.values()), {}
        )

    required = (
        "canary_git_commit",
        "score_result_pair",
        "fail_closed_markers",
        "merge_manifest_retained",
        "ephemeral_merge_removed",
        "claude_research_preflight",
        "method_gpu_smoke",
        "adapter_reload_validation",
        "on_demand_evaluator",
        "evaluation_item_contract",
        "autodata_disabled",
    )
    failed = [field for field in required if not proof.get(field)]
    if chain_count not in {1, 5} or len(configured_seeds) != chain_count:
        failed.append("lifecycle_chain_count")
    if chain_count == 5 and prerequisite_hash is None:
        failed.append("prerequisite_proof_sha256")
    if failed:
        proof["status"] = "failed"

    output = attempt / "metadata/canary_passed.json"
    temporary = output.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    if failed:
        raise SystemExit(f"lifecycle proof failed: {', '.join(failed)}")
    print(output)


if __name__ == "__main__":
    main()
