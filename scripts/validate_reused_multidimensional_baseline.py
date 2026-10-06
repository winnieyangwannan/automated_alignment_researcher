#!/usr/bin/env python3
"""Validate and record the exact retained Gemma baseline reused by run 5."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

MODEL = "google/gemma-4-31B-it"
MODEL_PATH = "/checkpoint/ram/shared/models/google/gemma-4-31B-it"
BASELINE_SHA256 = "f8825e08954d3798d622e551a1bf326e752400f0ca7e26945037c8d698af13db"
EXPECTED_BENCHMARKS = [
    "mask_factual",
    "mask_continuation",
    "mask_disinformation",
    "sycophancy_eval",
    "llm_uncertainty_bench",
    "verbalized_ece",
    "abstentionbench",
    "deceptionbench_reward",
    "sycon_fp",
    "sciq_uncertainty",
    "mmlu",
    "gsm8k",
    "ifeval",
]


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read retained JSON artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"retained JSON artifact is not an object: {path}")
    return value


def validate(path: Path) -> dict:
    actual_sha = _digest(path)
    if actual_sha != BASELINE_SHA256:
        raise SystemExit(
            f"unexpected retained baseline sha256: {actual_sha} != {BASELINE_SHA256}"
        )
    baseline = _read(path)
    if baseline.get("axis") != "honesty_sycophancy_concealing_uncertainty":
        raise SystemExit("retained baseline has the wrong axis")
    if baseline.get("model") != MODEL:
        raise SystemExit("retained baseline has the wrong model identity")
    if baseline.get("status") != "canonical_reused_compatible_source_baselines":
        raise SystemExit("retained baseline has an unexpected status")

    contract = baseline.get("evaluation_contract")
    expected_contract = {
        "model": MODEL,
        "judge_backend": "model_api",
        "judge_model": "gpt-5-6-luna",
        "thinking_enabled": True,
        "batch_size": 2,
        "generation_ceiling": 8192,
        "batch_size_overrides": {
            "mask_factual": 4,
            "mask_continuation": 4,
            "mask_disinformation": 4,
        },
    }
    if contract != expected_contract:
        raise SystemExit("retained baseline evaluation contract does not match run 5")

    scores = (baseline.get("scores") or {}).get(MODEL)
    if not isinstance(scores, dict) or list(scores) != EXPECTED_BENCHMARKS:
        raise SystemExit("retained baseline is not the exact ordered 13-score baseline")
    for name, score in scores.items():
        try:
            values = [float(score[key]) for key in ("mean", "ci_low", "ci_high")]
            sample_count = int(score["n"])
        except (KeyError, TypeError, ValueError) as error:
            raise SystemExit(f"invalid retained score for {name}") from error
        if not all(math.isfinite(value) for value in values) or sample_count <= 0:
            raise SystemExit(f"invalid retained score for {name}")
        if not (0 <= values[1] <= values[2] <= 1 and 0 <= values[0] <= 1):
            raise SystemExit(f"out-of-range retained score for {name}")

    recorded_hashes = baseline.get("sha256") or {}
    result_paths = [Path(value) for value in baseline.get("source_results") or []]
    manifest_paths = [Path(value) for value in baseline.get("source_manifests") or []]
    if len(result_paths) != 3 or len(manifest_paths) != 3:
        raise SystemExit("retained baseline does not name exactly three source evaluations")

    source_scores = {}
    source_suites = set()
    for source_path in result_paths:
        expected_sha = recorded_hashes.get(str(source_path))
        if not expected_sha or _digest(source_path) != expected_sha:
            raise SystemExit(f"source result hash mismatch: {source_path}")
        source = _read(source_path)
        if source.get("error"):
            raise SystemExit(f"source evaluation recorded an error: {source_path}")
        if source.get("model") != MODEL_PATH:
            raise SystemExit(f"source evaluation used a different model: {source_path}")
        source_suites.add(source.get("suite"))
        per_benchmark = source.get("per_benchmark")
        if not isinstance(per_benchmark, dict):
            raise SystemExit(f"source result has no benchmark scores: {source_path}")
        overlap = set(source_scores).intersection(per_benchmark)
        if overlap:
            raise SystemExit(f"duplicate source benchmark scores: {sorted(overlap)}")
        source_scores.update(per_benchmark)
    if source_suites != {"honesty", "sycophancy", "concealing_uncertainty"}:
        raise SystemExit(f"unexpected source evaluation suites: {source_suites}")
    if set(source_scores) != set(EXPECTED_BENCHMARKS):
        raise SystemExit("source evaluations do not cover the exact 13 benchmarks")
    for name, expected in scores.items():
        actual = source_scores[name]
        for key in ("mean", "ci_low", "ci_high", "n"):
            if actual.get(key) != expected.get(key):
                raise SystemExit(f"source score mismatch for {name}.{key}")

    source_commits = set((baseline.get("source_commits") or {}).values())
    manifest_commits = set()
    manifest_benchmarks = set()
    for manifest_path in manifest_paths:
        expected_sha = recorded_hashes.get(str(manifest_path))
        if not expected_sha or _digest(manifest_path) != expected_sha:
            raise SystemExit(f"source manifest hash mismatch: {manifest_path}")
        manifest = _read(manifest_path)
        if manifest.get("model_identity") != MODEL:
            raise SystemExit(f"source manifest used a different model: {manifest_path}")
        if manifest.get("judge") != {"backend": "model_api", "model": "gpt-5-6-luna"}:
            raise SystemExit(f"source manifest used a different judge: {manifest_path}")
        if manifest.get("thinking_enabled") is not True:
            raise SystemExit(f"source manifest disabled thinking: {manifest_path}")
        health = manifest.get("evaluation_health") or {}
        if health.get("batch_size") != 2 or health.get("freeform_generation_ceiling") != 8192:
            raise SystemExit(f"source manifest used a different generation profile: {manifest_path}")
        manifest_commits.add(manifest.get("git_commit"))
        manifest_benchmarks.update(manifest.get("suite_benchmarks") or [])
    if manifest_commits != source_commits:
        raise SystemExit("source manifest commits do not match the composed baseline")
    if manifest_benchmarks != set(EXPECTED_BENCHMARKS):
        raise SystemExit("source manifests do not cover the exact 13 benchmarks")
    return baseline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("--provenance-output", type=Path)
    args = parser.parse_args()
    baseline_path = args.baseline.resolve(strict=True)
    baseline = validate(baseline_path)
    provenance = {
        "validated_utc": datetime.now(timezone.utc).isoformat(),
        "launch_git_commit": os.environ.get("AAR_BASELINE_GIT_COMMIT"),
        "retained_baseline_path": str(baseline_path),
        "retained_baseline_sha256": BASELINE_SHA256,
        "model_identity": MODEL,
        "score_count": len(EXPECTED_BENCHMARKS),
        "scores": baseline["scores"][MODEL],
        "reuse_authorization": (
            "User explicitly authorized reusing the retained Gemma baseline on 2026-10-06; "
            "a fresh vLLM baseline must not be run because the inference backend is not "
            "expected to change the base-model benchmark result."
        ),
        "cross_backend_policy": (
            "Baseline source protocol is retained exactly; candidate evaluations remain "
            "fail-closed on vLLM 0.25.1 with merged checkpoints."
        ),
        "candidate_inference_backend": "vllm",
        "candidate_vllm_image": "docker.io/vllm/vllm-openai:v0.25.1",
    }
    if args.provenance_output:
        args.provenance_output.parent.mkdir(parents=True, exist_ok=True)
        with args.provenance_output.open("x") as handle:
            json.dump(provenance, handle, indent=2)
            handle.write("\n")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
