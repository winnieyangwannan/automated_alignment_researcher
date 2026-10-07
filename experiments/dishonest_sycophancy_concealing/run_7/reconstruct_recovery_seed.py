#!/usr/bin/env python3
"""Reconstruct research-visible Run 7 history from salvaged Claude tool results.

The source leaderboard was already stripped at the evaluator boundary. This
script additionally rejects any held-out benchmark identifier before publishing
the recovered forum and per-chain memory files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


CHAINS = ("alpha", "beta", "gamma", "delta", "epsilon")
OLD_SESSIONS_STARTED = {
    "alpha": 7,
    "beta": 6,
    "gamma": 5,
    "delta": 6,
    "epsilon": 6,
}
REMAINING_SESSIONS = {
    chain: 50 - started for chain, started in OLD_SESSIONS_STARTED.items()
}
EXPECTED_COMPLETED = {
    "alpha": 2,
    "beta": 4,
    "gamma": 4,
    "delta": 3,
    "epsilon": 1,
}
PUBLIC_BENCHMARKS = {
    "mask_factual",
    "mask_continuation",
    "mask_disinformation",
    "sycophancy_eval",
    "llm_uncertainty_bench",
    "verbalized_ece",
    "abstentionbench",
    "mmlu",
    "gsm8k",
    "ifeval",
}
FORBIDDEN_HELD_OUT = {
    "deceptionbench_reward",
    "sycon_fp",
    "sciq_uncertainty",
}


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read leaderboard {path}: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        raise ValueError(f"not a leaderboard payload: {path}")
    return value


def _timestamp(path: Path) -> int:
    match = re.search(r"-(\d+)\.txt$", path.name)
    return int(match.group(1)) if match else 0


def select_leaderboard(snapshot_root: Path, expected_entries: int) -> tuple[Path, dict]:
    candidates: list[tuple[int, int, Path, dict]] = []
    pattern = "*/tool-results/mcp-server-api-tools-get_leaderboard-*.txt"
    for path in snapshot_root.glob(pattern):
        try:
            payload = _read_json(path)
        except ValueError:
            continue
        candidates.append((len(payload["entries"]), _timestamp(path), path, payload))
    if not candidates:
        raise ValueError(f"no valid salvaged leaderboard below {snapshot_root}")
    count, _, path, payload = max(candidates, key=lambda item: (item[0], item[1]))
    if count != expected_entries or payload.get("count") != expected_entries:
        raise ValueError(
            f"best salvaged leaderboard has {count} entries; expected {expected_entries}"
        )
    return path, payload


def _contains_forbidden(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_HELD_OUT or _contains_forbidden(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    if isinstance(value, str):
        return any(name in value for name in FORBIDDEN_HELD_OUT)
    return False


def _chain_and_method(run_id: str) -> tuple[str, str]:
    chain = next(
        (name for name in CHAINS if f"-explore-{name}-" in run_id), None
    )
    if chain is None or "__" not in run_id:
        raise ValueError(f"cannot recover chain/method identity from run_id={run_id!r}")
    method_with_timestamp = run_id.split("__", 1)[1]
    method = re.sub(r"-\d+$", "", method_with_timestamp)
    if not method:
        raise ValueError(f"empty recovered method in run_id={run_id!r}")
    return chain, method


def _validate_entry(entry: dict) -> tuple[str, str]:
    if _contains_forbidden(entry):
        raise ValueError("salvaged leaderboard contains an evaluator-private identifier")
    run_id = entry.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("salvaged leaderboard entry has no run_id")
    composite = entry.get("composite_scores")
    if not isinstance(composite, dict):
        raise ValueError(f"entry {run_id} has no composite_scores")
    for field in ("per_benchmark", "closed_pct", "regression_detail"):
        values = composite.get(field) or {}
        if not isinstance(values, dict) or not set(values).issubset(PUBLIC_BENCHMARKS):
            raise ValueError(f"entry {run_id} has unexpected research-visible {field}")
    if not isinstance(entry.get("headline_pct"), (int, float)):
        raise ValueError(f"entry {run_id} has no numeric headline")
    return _chain_and_method(run_id)


def _write_agent_log(
    path: Path, chain: str, entries: list[tuple[dict, str]], all_entries: list[dict]
) -> None:
    lines = [
        f"# AGENT_LOG — recovered chain explore-{chain}",
        "",
        "## RECOVERY CONTEXT",
        "",
        "This is a reconstructed continuation of Run 7 after its checkpoint NFS "
        "namespace became unresolvable. The records below come from the exact "
        "held-out-stripped leaderboard salvaged from Claude tool results. Do not "
        "treat this as a fresh first iteration, and do not infer evaluator-private "
        "benchmark identities or values.",
        "",
        f"The old chain started {OLD_SESSIONS_STARTED[chain]} sessions and completed "
        f"{len(entries)} scored findings. This continuation has a fresh loop-local "
        f"counter capped at {REMAINING_SESSIONS[chain]} additional sessions, for a "
        "combined cap of 50 started sessions.",
        "",
        "## RECOVERED COMPLETED RESULTS",
        "",
    ]
    for entry, method in sorted(entries, key=lambda item: item[0]["run_id"]):
        composite = entry["composite_scores"]
        dimensions = composite.get("dimension_scores_pct") or {}
        lines.extend(
            [
                f"- Method `{method}`; run `{entry['run_id']}`; headline "
                f"{entry['headline_pct']:.2f}; capability filter "
                f"{composite.get('passes_filter')}; regression gate "
                f"{composite.get('passes_regression')}; dimension scores "
                f"honesty={dimensions.get('honesty')}, "
                f"sycophancy={dimensions.get('sycophancy')}, "
                f"concealing_uncertainty={dimensions.get('concealing_uncertainty')}.",
                f"  Recovered conclusion: {entry.get('summary') or 'No summary retained.'}",
            ]
        )
    best = sorted(
        all_entries,
        key=lambda item: (
            bool((item.get("composite_scores") or {}).get("passes_filter")),
            float(item.get("headline_pct", 0)),
        ),
        reverse=True,
    )[:5]
    lines.extend(["", "## SHARED BEST RECOVERED RESULTS", ""])
    for entry in best:
        _, method = _chain_and_method(entry["run_id"])
        composite = entry["composite_scores"]
        lines.append(
            f"- `{method}`: headline {entry['headline_pct']:.2f}; filter "
            f"{composite.get('passes_filter')}; regression "
            f"{composite.get('passes_regression')} — {entry.get('summary') or ''}"
        )
    lines.extend(
        [
            "",
            "## CONTINUATION RULE",
            "",
            "The in-flight candidate from the interrupted old session is not counted "
            "as completed. Start a new proposal, avoid duplicating the recovered "
            "methods, and append every new result below.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def reconstruct(snapshot_root: Path, output: Path, expected_entries: int = 14) -> dict:
    snapshot_root = snapshot_root.resolve(strict=True)
    if output.exists():
        raise ValueError(f"refusing to overwrite recovery seed: {output}")
    source_path, payload = select_leaderboard(snapshot_root, expected_entries)
    grouped: dict[str, list[tuple[dict, str]]] = {chain: [] for chain in CHAINS}
    validated: list[tuple[dict, str, str]] = []
    seen_runs: set[str] = set()
    for raw in payload["entries"]:
        if not isinstance(raw, dict):
            raise ValueError("salvaged leaderboard entry is not an object")
        chain, method = _validate_entry(raw)
        run_id = raw["run_id"]
        if run_id in seen_runs:
            raise ValueError(f"duplicate recovered run_id: {run_id}")
        seen_runs.add(run_id)
        grouped[chain].append((raw, method))
        validated.append((raw, chain, method))
    actual_counts = {chain: len(entries) for chain, entries in grouped.items()}
    if actual_counts != EXPECTED_COMPLETED:
        raise ValueError(
            f"recovered per-chain result counts differ: {actual_counts}"
        )

    staging = output.with_name(f"{output.name}.incomplete.{os.getpid()}")
    staging.mkdir(parents=True)
    forum = staging / "forum"
    logs = staging / "agent_logs"
    forum.mkdir()
    logs.mkdir()
    for entry, chain, method in validated:
        recovered = dict(entry)
        digest = hashlib.sha256(entry["run_id"].encode()).hexdigest()
        recovered.update(
            {
                "id": digest,
                "post_id": digest[:12],
                "idea_name": method,
                "finding_type": "result",
                "recovered_from_run7": True,
                "recovered_chain": chain,
            }
        )
        filename = f"{digest}_{method}.json"
        (forum / filename).write_text(json.dumps(recovered, indent=2) + "\n")
    all_entries = [entry for entry, _, _ in validated]
    for chain in CHAINS:
        _write_agent_log(
            logs / f"AGENT_LOG_gemma4_31b_explore_{chain}.md",
            chain,
            grouped[chain],
            all_entries,
        )
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    metadata = {
        "source_leaderboard": str(source_path),
        "source_sha256": source_sha,
        "entry_count": len(validated),
        "per_chain_completed": actual_counts,
        "old_sessions_started": OLD_SESSIONS_STARTED,
        "remaining_sessions": REMAINING_SESSIONS,
        "heldout_identifiers_rejected": sorted(FORBIDDEN_HELD_OUT),
    }
    (staging / "recovery_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    for path in staging.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
        elif path.is_dir():
            path.chmod(0o700)
    staging.rename(output)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-entries", type=int, default=14)
    args = parser.parse_args()
    metadata = reconstruct(args.snapshot_root, args.output, args.expected_entries)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
