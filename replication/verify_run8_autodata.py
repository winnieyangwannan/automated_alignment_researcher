#!/usr/bin/env python3
"""Fail-closed completion proof for the two-iteration production Run 8 chain."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from replication.verify_two_iteration_multidimensional import verify as verify_base


SUITE = "honesty_sycophancy_concealing_uncertainty"
GENERATOR = "Kimi-K2.6"
GENERATOR_DEPLOYMENT = "winnieyangwn-kimi26"
JUDGE = "gpt-5-6-luna"
DATASET_SCHEMA = "aar.autodata.dataset/v1"
CONSUMPTION_SCHEMA = "aar.autodata.consumption/v1"
TRAINING_LINK_SCHEMA = "aar.autodata.training-link/v1"
SUBMISSION_SCHEMA = "aar.model-submission/v1"
DIGEST = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_POLICY_SHA256 = hashlib.sha256(
    b"aar-run8-unattended-production/v1:synthetic-only:no-benchmark-mimicry"
).hexdigest()


def _fail(message: str) -> None:
    raise SystemExit(message)


def _json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        _fail(f"completion artifact must not be a symlink: {path}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        _fail(f"cannot read JSON artifact {path}: {error}")
    if not isinstance(value, dict):
        _fail(f"JSON artifact is not an object: {path}")
    return value


def _digest(value: Any, label: str) -> str:
    result = str(value or "").lower().removeprefix("sha256:")
    if not DIGEST.fullmatch(result):
        _fail(f"{label} is not a SHA-256 digest")
    return result


def _canonical_rows(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    if path.is_symlink():
        _fail(f"dataset rows must not be a symlink: {path}")
    try:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as error:
        _fail(f"cannot read dataset rows {path}: {error}")
    if not rows or not all(isinstance(row, dict) for row in rows):
        _fail(f"dataset rows are empty or malformed: {path}")
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
    if path.read_bytes() != payload:
        _fail(f"dataset rows are not immutable canonical JSONL: {path}")
    return rows, payload


def _result_findings(team_dir: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((team_dir / "forum").glob("*.json")):
        finding = _json(path)
        if finding.get("finding_type") != "result":
            continue
        run_id = str(finding.get("run_id") or "")
        if not run_id:
            _fail(f"result finding has no run_id: {path}")
        if run_id in result:
            _fail(f"more than one result finding is bound to run {run_id}")
        result[run_id] = finding
    return result


def _proposal_path(team_dir: Path, run_id: str) -> Path:
    safe = "".join(
        character if character.isalnum() or character in "_.:-" else "_"
        for character in run_id
    )
    return team_dir / "scores" / ".proposals" / "runs" / f"{safe}.json"


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        _fail(f"{label} mismatch: {actual!r} != {expected!r}")


def _verify_run(
    team_dir: Path,
    run_id: str,
    finding: dict[str, Any],
    *,
    minimum_rows: int,
) -> dict[str, Any]:
    root = team_dir / "autodata" / run_id
    if not root.is_dir() or root.is_symlink():
        _fail(f"verified AutoData artifact directory is missing for {run_id}")
    manifest = _json(root / "autodata_manifest.json")
    rows, payload = _canonical_rows(root / "autodata_rows.jsonl")
    receipt = _json(root / "autodata_consumption.json")
    training_link = _json(root / "autodata_training_link.json")
    score = _json(team_dir / "scores" / f"{run_id}.json")
    proposal = _json(_proposal_path(team_dir, run_id))

    _require_equal(manifest.get("schema"), DATASET_SCHEMA, f"{run_id} manifest schema")
    _require_equal(manifest.get("run_id"), run_id, f"{run_id} manifest run_id")
    _require_equal(manifest.get("training_view"), "sft", f"{run_id} training view")
    row_count = manifest.get("row_count")
    if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < minimum_rows:
        _fail(f"{run_id} retained fewer than {minimum_rows} SFT rows")
    _require_equal(row_count, len(rows), f"{run_id} row count")
    _require_equal(
        manifest.get("required_retained_rows"),
        minimum_rows,
        f"{run_id} retained-row contract",
    )
    counts = manifest.get("counts")
    if not isinstance(counts, dict) or counts.get("retained") != row_count:
        _fail(f"{run_id} retained count is inconsistent")
    for index, row in enumerate(rows):
        if not all(
            isinstance(row.get(key), str) and row[key].strip()
            for key in ("prompt", "response")
        ):
            _fail(f"{run_id} row {index} is not an SFT record")

    dataset_digest = hashlib.sha256(payload).hexdigest()
    _require_equal(
        _digest(manifest.get("dataset_sha256"), f"{run_id} dataset digest"),
        dataset_digest,
        f"{run_id} dataset content digest",
    )
    pipeline_sha = str(manifest.get("pipeline_sha") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", pipeline_sha):
        _fail(f"{run_id} AutoData commit is not a Git/SHA-256 identity")
    for field in (
        "method_code_sha256",
        "autodata_spec_sha256",
        "resource_profile_sha256",
        "recipe_digest",
        "pipeline_digest",
    ):
        _digest(manifest.get(field), f"{run_id} manifest {field}")

    _require_equal(
        manifest.get("modes_completed_in_order"),
        ["meta_optimize", "production"],
        f"{run_id} AutoData lifecycle order",
    )
    meta_id = str(manifest.get("meta_optimize_execution_id") or "")
    production_id = str(manifest.get("production_execution_id") or "")
    workspace_id = str(manifest.get("workspace_id") or "")
    study_id = str(manifest.get("study_id") or "")
    if not workspace_id or not study_id:
        _fail(f"{run_id} does not prove autonomous workspace/study creation")
    if not meta_id or not production_id or meta_id == production_id:
        _fail(f"{run_id} does not identify distinct meta-optimize and production executions")
    _require_equal(manifest.get("execution_id"), production_id, f"{run_id} final execution")
    _require_equal(manifest.get("meta_optimize_tuning_task_count"), 64, f"{run_id} tuning split")
    _require_equal(
        manifest.get("meta_optimize_validation_task_count"),
        32,
        f"{run_id} validation split",
    )
    for field in ("meta_optimize_source_task_count", "production_source_task_count"):
        value = manifest.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum_rows:
            _fail(f"{run_id} {field} does not prove a production-scale native execution")
    _require_equal(
        manifest.get("sandoq_executor"),
        "SandoQFirecrackerExecutor",
        f"{run_id} executor",
    )
    _require_equal(manifest.get("unattended"), True, f"{run_id} unattended lifecycle")
    _require_equal(
        manifest.get("approval_principal"),
        "aar-integrity-monitor",
        f"{run_id} autonomous approval principal",
    )
    _require_equal(
        manifest.get("action_provider"),
        "aar-visible-agent-and-integrity-monitor",
        f"{run_id} autonomous action provider",
    )
    _require_equal(
        manifest.get("approval_policy_sha256"),
        APPROVAL_POLICY_SHA256,
        f"{run_id} autonomous approval policy",
    )
    audit = manifest.get("action_audit")
    required_actions = [
        ("clarify_design", "aar-research-agent"),
        ("author_grounding", "aar-research-agent"),
        ("approve_grounding", "aar-integrity-monitor"),
        ("author_pipeline", "aar-research-agent"),
        ("approve_baseline", "aar-integrity-monitor"),
    ]
    if not isinstance(audit, list) or [
        (item.get("kind"), item.get("actor"))
        for item in audit[: len(required_actions)]
        if isinstance(item, dict)
    ] != required_actions:
        _fail(f"{run_id} action audit does not prove autonomous workspace advancement")
    if any(
        not isinstance(item, dict)
        or not DIGEST.fullmatch(str(item.get("result_sha256") or ""))
        for item in audit
    ):
        _fail(f"{run_id} action audit has malformed result attestations")

    models = manifest.get("models")
    if not isinstance(models, dict):
        _fail(f"{run_id} model provenance is missing")
    generator = models.get("generator")
    judge = models.get("judge")
    if not isinstance(generator, dict) or not isinstance(judge, dict):
        _fail(f"{run_id} generator/judge provenance is malformed")
    _require_equal(generator.get("identity"), GENERATOR, f"{run_id} generator")
    _require_equal(
        generator.get("deployment_id"),
        GENERATOR_DEPLOYMENT,
        f"{run_id} generator deployment",
    )
    _require_equal(judge.get("identity"), JUDGE, f"{run_id} judge")
    budget = manifest.get("budget")
    if (
        not isinstance(budget, dict)
        or not isinstance(budget.get("model_calls"), int)
        or budget["model_calls"] < 2
    ):
        _fail(f"{run_id} has no metered Kimi/Luna model calls")

    # The approval-time proposal stamp independently binds the method, spec,
    # operator profile, budget scope, and row contract to this run id.
    _require_equal(proposal.get("run_id"), run_id, f"{run_id} proposal run_id")
    _require_equal(proposal.get("idea_name"), manifest.get("idea_name"), f"{run_id} approved idea")
    if not isinstance(proposal.get("paper"), dict) or not proposal["paper"]:
        _fail(f"{run_id} has no approval-time frozen proposal paper")
    if not isinstance(proposal.get("proposal_ts"), (int, float)):
        _fail(f"{run_id} has no approval-time proposal timestamp")
    for proposal_field, manifest_field in (
        ("code_hash", "method_code_sha256"),
        ("autodata_spec_sha256", "autodata_spec_sha256"),
        ("autodata_resource_profile", "resource_profile"),
        ("autodata_resource_profile_sha256", "resource_profile_sha256"),
        ("autodata_budget_scope_id", "budget_scope_id"),
        ("autodata_required_retained_rows", "required_retained_rows"),
    ):
        approved = proposal.get(proposal_field)
        produced = manifest.get(manifest_field)
        if proposal_field == "autodata_required_retained_rows":
            try:
                approved = int(approved)
            except (TypeError, ValueError):
                _fail(f"{run_id} approved retained-row contract is invalid")
        _require_equal(approved, produced, f"{run_id} approved {proposal_field}")

    expected_link = {
        "schema": TRAINING_LINK_SCHEMA,
        "run_id": run_id,
        "dataset_sha256": dataset_digest,
        "row_count": row_count,
        "training_view": "sft",
        "consumption_receipt_schema": CONSUMPTION_SCHEMA,
    }
    _require_equal(receipt.get("schema"), CONSUMPTION_SCHEMA, f"{run_id} consumption schema")
    for key in ("run_id", "dataset_sha256", "row_count"):
        _require_equal(receipt.get(key), expected_link[key], f"{run_id} consumption {key}")
    for key, value in expected_link.items():
        _require_equal(training_link.get(key), value, f"{run_id} training link {key}")
    if not training_link.get("model_submission_ref"):
        _fail(f"{run_id} training link has no submitted model reference")

    _require_equal(score.get("suite"), SUITE, f"{run_id} score suite")
    submission = score.get("model_submission")
    if not isinstance(submission, dict):
        _fail(f"{run_id} score has no model-submission provenance")
    _require_equal(submission.get("schema"), SUBMISSION_SCHEMA, f"{run_id} submission schema")
    _require_equal(submission.get("run_id"), run_id, f"{run_id} submitted model run_id")
    _require_equal(
        submission.get("training_data"),
        expected_link,
        f"{run_id} submitted model dataset",
    )

    composite = finding.get("composite_scores")
    if not isinstance(composite, dict):
        _fail(f"{run_id} result finding has no authoritative composite")
    _require_equal(composite.get("model_submission"), submission, f"{run_id} result/model linkage")
    _require_equal(
        finding.get("autodata_dataset_sha256"),
        dataset_digest,
        f"{run_id} result dataset digest",
    )
    _require_equal(composite.get("run_id"), run_id, f"{run_id} authoritative result run_id")
    _require_equal(composite.get("_authoritative"), True, f"{run_id} authoritative score marker")
    return {
        "run_id": run_id,
        "dataset_sha256": dataset_digest,
        "row_count": row_count,
        "workspace_id": workspace_id,
        "meta_optimize_execution_id": meta_id,
        "production_execution_id": production_id,
        "model_calls": budget["model_calls"],
    }


def verify(team_dir: Path, expected: int = 2, minimum_rows: int = 64) -> dict[str, Any]:
    base = verify_base(team_dir, expected)
    team_dir = team_dir.resolve(strict=True)
    session_logs = sorted((team_dir / "logs").glob("session_*.log"))
    expected_prefixes = [f"session_{index:03d}_" for index in range(expected)]
    for path, prefix in zip(session_logs, expected_prefixes, strict=True):
        if not path.stem.startswith(prefix):
            _fail(f"sessions are not the expected sequential chain: {path.name}")

    findings = _result_findings(team_dir)
    score_run_ids = set(base["score_run_ids"])
    if set(findings) != score_run_ids:
        _fail("result findings do not exactly match the two scored Run 8 ids")
    run_ids: list[str] = []
    for session_path in session_logs:
        matches = [
            run_id
            for run_id, finding in findings.items()
            if finding.get("aar_session_id") == session_path.stem
        ]
        if len(matches) != 1:
            _fail(f"session {session_path.stem} does not map to exactly one scored result")
        run_ids.append(matches[0])
    if len(set(run_ids)) != expected:
        _fail("the sequential sessions do not identify two distinct runs")
    runs = [
        _verify_run(team_dir, run_id, findings[run_id], minimum_rows=minimum_rows)
        for run_id in run_ids
    ]
    budget_scopes = {
        _json(team_dir / "autodata" / run_id / "autodata_manifest.json").get("budget_scope_id")
        for run_id in run_ids
    }
    if len(budget_scopes) != 1 or None in budget_scopes:
        _fail("the two AutoData iterations do not share one operator budget scope")
    return {
        **base,
        "verification_schema": "aar.run8.completion/v1",
        "autodata": {
            "generator": GENERATOR,
            "judge": JUDGE,
            "executor": "SandoQFirecrackerExecutor",
            "budget_scope_id": next(iter(budget_scopes)),
            "runs": runs,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-dir", type=Path, required=True)
    parser.add_argument("--expected-iterations", type=int, default=2)
    parser.add_argument("--minimum-rows", type=int, default=64)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.team_dir, args.expected_iterations, args.minimum_rows)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(payload)
        os.replace(temporary, args.output)
    print(payload, end="")


if __name__ == "__main__":
    main()
