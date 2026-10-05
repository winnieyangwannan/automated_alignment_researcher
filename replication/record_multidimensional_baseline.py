#!/usr/bin/env python3
"""Merge three completed, profile-identical dimension baselines into one override.

Inputs must be the eval-private FULL results so all held-outs are present.
This script does not make an old-commit baseline canonical; it records a
provisional bundle used to publish and run the final-commit composed baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MODEL = "google/gemma-4-31B-it"
MODEL_REFS = {
    MODEL,
    "/checkpoint/ram/shared/models/google/gemma-4-31B-it",
}
SYC = {"sycophancy_eval", "sycon_fp", "mmlu", "gsm8k", "ifeval"}
HONESTY = {
    "mask_factual", "mask_continuation", "mask_disinformation",
    "deceptionbench_reward",
}
CONCEALING_UNCERTAINTY = {
    "llm_uncertainty_bench", "verbalized_ece", "abstentionbench",
    "sciq_uncertainty",
}
EXPECTED = SYC | HONESTY | CONCEALING_UNCERTAINTY


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_contract(manifest: dict) -> dict:
    health = manifest.get("evaluation_health") or manifest.get("health") or {}
    judge = manifest.get("judge") or {}
    return {
        "git_commit": manifest.get("git_commit") or manifest.get("commit"),
        "model": manifest.get("model_identity") or manifest.get("model"),
        "judge_backend": judge.get("backend") or manifest.get("judge_backend"),
        "judge_model": judge.get("model") or manifest.get("judge_model"),
        "thinking_enabled": manifest.get("thinking_enabled", True),
        "batch_size": health.get("batch_size") or manifest.get("batch_size"),
        "generation_ceiling": (
            health.get("freeform_generation_ceiling")
            or health.get("generation_ceiling")
            or manifest.get("freeform_generation_ceiling")
            or manifest.get("generation_ceiling")
        ),
    }


def _profile_contract(contract: dict) -> dict:
    """Return fields that must agree across reusable source baselines.

    Source runs can come from different commits: that is the point of reusing
    completed honesty and sycophancy results while adding the new dimension.
    The final composed baseline is still measured on the final code commit.
    """
    return {key: value for key, value in contract.items() if key != "git_commit"}


def _extract(result_path: Path, expected: set[str]) -> dict[str, dict]:
    result = _read(result_path)
    result_model = result.get("model")
    if result_model is not None and result_model not in MODEL_REFS:
        raise SystemExit(f"{result_path}: wrong model {result_model!r}")
    per_benchmark = result.get("per_benchmark") or {}
    if set(per_benchmark) != expected:
        raise SystemExit(
            f"{result_path}: benchmark mismatch; expected={sorted(expected)} "
            f"actual={sorted(per_benchmark)}"
        )
    extracted: dict[str, dict] = {}
    for name, raw in per_benchmark.items():
        item = {
            "mean": float(raw["mean"]),
            "ci_low": float(raw["ci_low"]),
            "ci_high": float(raw["ci_high"]),
            "n": int(raw["n"]),
        }
        if item["n"] <= 0 or not 0 <= item["ci_low"] <= item["ci_high"] <= 1:
            raise SystemExit(f"{result_path}: invalid completed score for {name}: {item}")
        extracted[name] = item
    return extracted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--syc-result", type=Path, required=True)
    parser.add_argument("--honesty-result", type=Path, required=True)
    parser.add_argument("--concealing-result", type=Path, required=True)
    parser.add_argument("--syc-manifest", type=Path, required=True)
    parser.add_argument("--honesty-manifest", type=Path, required=True)
    parser.add_argument("--concealing-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    paths = (
        args.syc_result, args.honesty_result, args.concealing_result,
        args.syc_manifest, args.honesty_manifest, args.concealing_manifest,
    )
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"required retained artifact is missing: {path}")
    syc_contract = _manifest_contract(_read(args.syc_manifest))
    honesty_contract = _manifest_contract(_read(args.honesty_manifest))
    concealing_contract = _manifest_contract(_read(args.concealing_manifest))
    required_contract = {
        "model": MODEL,
        "judge_backend": "model_api",
        "judge_model": "gpt-5-6-luna",
        "thinking_enabled": True,
        "batch_size": 2,
        "generation_ceiling": 8192,
    }
    if not (
        _profile_contract(syc_contract)
        == _profile_contract(honesty_contract)
        == _profile_contract(concealing_contract)
    ):
        raise SystemExit(
            "baseline contracts differ: "
            f"syc={syc_contract} honesty={honesty_contract} "
            f"concealing={concealing_contract}"
        )
    for key, expected in required_contract.items():
        if _profile_contract(syc_contract).get(key) != expected:
            raise SystemExit(
                f"baseline contract {key}={syc_contract.get(key)!r}; expected {expected!r}"
            )

    scores = _extract(args.syc_result, SYC)
    scores.update(_extract(args.honesty_result, HONESTY))
    scores.update(_extract(args.concealing_result, CONCEALING_UNCERTAINTY))
    if set(scores) != EXPECTED:
        raise SystemExit("internal error: merged baseline is not the exact 13-entry union")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite retained baseline: {args.output}")
    payload = {
        "axis": "honesty_sycophancy_concealing_uncertainty",
        "model": MODEL,
        "status": "provisional_until_final_commit_composed_baseline_passes",
        "evaluation_contract": _profile_contract(syc_contract),
        "source_commits": {
            "sycophancy": syc_contract["git_commit"],
            "honesty": honesty_contract["git_commit"],
            "concealing_uncertainty": concealing_contract["git_commit"],
        },
        "source_results": [
            str(args.syc_result.resolve()), str(args.honesty_result.resolve()),
            str(args.concealing_result.resolve()),
        ],
        "source_manifests": [
            str(args.syc_manifest.resolve()), str(args.honesty_manifest.resolve()),
            str(args.concealing_manifest.resolve()),
        ],
        "sha256": {str(path.resolve()): _sha256(path) for path in paths},
        "scores": {MODEL: scores},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
