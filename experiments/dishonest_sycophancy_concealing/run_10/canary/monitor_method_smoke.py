#!/usr/bin/env python3
"""Monitor and certify all generated-method real-GPU lifecycle smoke jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


def _env_file(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text().splitlines() if "=" in line
    )


def _job_state(job_id: str) -> str:
    result = subprocess.run(
        ["sacct", "-j", job_id, "-X", "-n", "-o", "State"],
        check=True,
        capture_output=True,
        text=True,
    )
    return next(
        (
            line.strip().split()[0]
            for line in result.stdout.splitlines()
            if line.strip()
        ),
        "",
    )


def _method_evidence(team: Path, receipt: Path) -> dict[str, object]:
    receipt_values = _env_file(receipt)
    run_id = receipt_values.get("run_id", "")
    train_job_id = receipt_values.get("job_id", "")
    passed_path = team / "method_smoke" / f"{run_id}.passed.json"
    smoke = json.loads(passed_path.read_text())
    proposal_path = team / "scores" / ".proposals" / "runs" / f"{run_id}.json"
    proposal = json.loads(proposal_path.read_text())
    method_path = team / "methods" / proposal["idea_name"] / "run.py"
    contract_path = method_path.parent / ".aar-method-contract.json"
    contract = json.loads(contract_path.read_text())
    source_hash = hashlib.sha256(method_path.read_bytes()).hexdigest()
    package_parts = [
        f"# ===== {path.relative_to(method_path.parent)} =====\n"
        + path.read_text(errors="ignore")
        for path in sorted(method_path.parent.rglob("*.py"))
        if "__pycache__" not in str(path)
    ]
    package_hash = hashlib.sha256("\n\n".join(package_parts).encode()).hexdigest()
    if (
        contract.get("status") != "passed"
        or contract.get("source_sha256") != source_hash
    ):
        raise RuntimeError(
            f"method contract proof is missing, failed, or stale: {run_id}"
        )
    if proposal.get("code_hash") != package_hash:
        raise RuntimeError(f"approved proposal is not bound to method source: {run_id}")
    model_path = Path(smoke["model_path"])
    if team not in model_path.parents or not model_path.is_dir():
        raise RuntimeError(f"smoke adapter is missing or outside the attempt: {run_id}")
    return {
        "run_id": run_id,
        "training_job": train_job_id,
        "method": proposal["idea_name"],
        "method_source_sha256": source_hash,
        "approved_package_sha256": package_hash,
        "adapter_path": str(model_path),
        "real_gpu_smoke": True,
        "adapter_reload_validation": True,
    }


def monitor(
    attempt: Path, expected_chains: int, timeout_seconds: int, poll_seconds: int
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    children_path = attempt / "metadata" / "children.env"
    while not children_path.is_file() and time.monotonic() < deadline:
        time.sleep(poll_seconds)
    if not children_path.is_file():
        raise TimeoutError("timed out waiting for child-job metadata")
    children = _env_file(children_path)
    chain_ids = children.get("research_chain_jobs", "").split()
    if len(chain_ids) != expected_chains or children.get("evaluator_jobs", "").strip():
        raise RuntimeError(
            f"lifecycle expected {expected_chains} chains and zero initial evaluators"
        )

    teams = [path for path in (attempt / "aar_teams").iterdir() if path.is_dir()]
    if len(teams) != 1:
        raise RuntimeError(f"expected one team directory, found {len(teams)}")
    team = teams[0]
    receipts: list[Path] = []
    while time.monotonic() < deadline:
        receipts = sorted((team / ".train_submissions").glob("*.env"))
        if len(receipts) == expected_chains:
            break
        if len(receipts) > expected_chains:
            raise RuntimeError(
                f"expected {expected_chains} training receipts, found {len(receipts)}"
            )
        states = [_job_state(job_id) for job_id in chain_ids]
        if all(state and state not in {"PENDING", "RUNNING"} for state in states):
            raise RuntimeError(
                f"all research chains ended before all training receipts: {states}"
            )
        time.sleep(poll_seconds)
    else:
        raise TimeoutError("timed out waiting for all training receipts")

    pending = {receipt: _env_file(receipt) for receipt in receipts}
    while pending and time.monotonic() < deadline:
        for receipt, values in list(pending.items()):
            run_id = values.get("run_id", "")
            train_job_id = values.get("job_id", "")
            failed_path = team / "scores" / f"{run_id}.failed.json"
            passed_path = team / "method_smoke" / f"{run_id}.passed.json"
            if failed_path.is_file():
                raise RuntimeError(
                    f"method smoke failed: {failed_path.read_text().strip()}"
                )
            state = _job_state(train_job_id)
            if passed_path.is_file() and state == "COMPLETED":
                del pending[receipt]
            elif state and state not in {
                "PENDING",
                "RUNNING",
                "COMPLETING",
                "COMPLETED",
            }:
                raise RuntimeError(f"method smoke job {train_job_id} ended in {state}")
        if pending:
            time.sleep(poll_seconds)
    if pending:
        raise TimeoutError("timed out waiting for all method smoke proofs")

    runs = [_method_evidence(team, receipt) for receipt in receipts]
    proof: dict[str, object] = {
        "schema_version": 2,
        "status": "passed",
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "attempt": str(attempt),
        "research_chain_jobs": chain_ids,
        "evaluator_jobs": [],
        "expected_chains": expected_chains,
        "runs": runs,
        "real_gpu_smoke": all(run["real_gpu_smoke"] for run in runs),
        "adapter_reload_validation": all(
            run["adapter_reload_validation"] for run in runs
        ),
        "research_chains_kept_for_score": True,
    }
    if expected_chains == 1:
        proof.update(runs[0])
        proof["research_chain_job"] = chain_ids[0]
        proof["research_chain_kept_for_score"] = True
    output = attempt / "metadata" / "method_smoke_passed.json"
    temporary = output.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    return proof


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--expected-chains", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args()
    if args.expected_chains < 1:
        parser.error("--expected-chains must be positive")
    print(
        json.dumps(
            monitor(
                args.attempt.resolve(),
                args.expected_chains,
                args.timeout_seconds,
                args.poll_seconds,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
