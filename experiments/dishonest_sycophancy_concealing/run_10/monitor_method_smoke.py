#!/usr/bin/env python3
"""Monitor and certify Run 10's generated-method real-GPU smoke gate."""

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
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def _job_state(job_id: str) -> str:
    result = subprocess.run(
        ["sacct", "-j", job_id, "-X", "-n", "-o", "State"],
        check=True,
        capture_output=True,
        text=True,
    )
    return next((line.strip().split()[0] for line in result.stdout.splitlines() if line.strip()), "")


def monitor(attempt: Path, timeout_seconds: int, poll_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    children_path = attempt / "metadata" / "children.env"
    while not children_path.is_file() and time.monotonic() < deadline:
        time.sleep(poll_seconds)
    children = _env_file(children_path)
    chain_ids = children.get("research_chain_jobs", "").split()
    if len(chain_ids) != 1 or children.get("evaluator_jobs", "").strip():
        raise RuntimeError("smoke must have exactly one chain and zero evaluators")

    teams = [path for path in (attempt / "aar_teams").iterdir() if path.is_dir()]
    if len(teams) != 1:
        raise RuntimeError(f"expected one team directory, found {len(teams)}")
    team = teams[0]
    receipt: Path | None = None
    while time.monotonic() < deadline:
        receipts = list((team / ".train_submissions").glob("*.env"))
        if len(receipts) == 1:
            receipt = receipts[0]
            break
        chain_state = _job_state(chain_ids[0])
        if chain_state not in {"PENDING", "RUNNING"}:
            raise RuntimeError(f"research chain ended before training receipt: {chain_state}")
        time.sleep(poll_seconds)
    if receipt is None:
        raise TimeoutError("timed out waiting for the training receipt")

    receipt_values = _env_file(receipt)
    run_id = receipt_values.get("run_id", "")
    train_job_id = receipt_values.get("job_id", "")
    passed_path = team / "method_smoke" / f"{run_id}.passed.json"
    failed_path = team / "scores" / f"{run_id}.failed.json"
    while time.monotonic() < deadline:
        if failed_path.is_file():
            raise RuntimeError(f"method smoke failed: {failed_path.read_text().strip()}")
        if passed_path.is_file() and _job_state(train_job_id) == "COMPLETED":
            break
        state = _job_state(train_job_id)
        if state and state not in {"PENDING", "RUNNING", "COMPLETING", "COMPLETED"}:
            raise RuntimeError(f"method smoke job {train_job_id} ended in {state}")
        time.sleep(poll_seconds)
    else:
        raise TimeoutError("timed out waiting for the method smoke proof")

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
    if contract.get("status") != "passed" or contract.get("source_sha256") != source_hash:
        raise RuntimeError("method contract proof is missing, failed, or stale")
    if proposal.get("code_hash") != package_hash:
        raise RuntimeError("approved proposal is not bound to the smoked method source")
    model_path = Path(smoke["model_path"])
    if team not in model_path.parents or not model_path.is_dir():
        raise RuntimeError("smoke adapter path is missing or outside the attempt")

    proof = {
        "schema_version": 1,
        "status": "passed",
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "attempt": str(attempt),
        "research_chain_job": chain_ids[0],
        "evaluator_jobs": [],
        "run_id": run_id,
        "training_job": train_job_id,
        "method": proposal["idea_name"],
        "method_source_sha256": source_hash,
        "approved_package_sha256": package_hash,
        "adapter_path": str(model_path),
        "real_gpu_smoke": True,
        "adapter_reload_validation": True,
        "research_chain_kept_for_score": True,
    }
    output = attempt / "metadata" / "method_smoke_passed.json"
    temporary = output.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    return proof


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args()
    print(
        json.dumps(
            monitor(args.attempt.resolve(), args.timeout_seconds, args.poll_seconds),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
