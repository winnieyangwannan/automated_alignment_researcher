#!/usr/bin/env python3
"""Fail-closed launch preflight for the three-dimension composed AAR."""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import re
import subprocess

import yaml

from aar.eval_pod.models import split_reasoning_and_answer_text
from aar.eval_pod.run_eval import load_suite_spec
from replication.preflight_v0 import api_json, require_judge_configuration


MODEL = "google/gemma-4-31B-it"
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
EXPECTED_CEILING_BENCHMARKS = [
    "mask_factual", "mask_continuation", "mask_disinformation",
    "sycophancy_eval", "verbalized_ece", "abstentionbench",
    "deceptionbench_reward", "sycon_fp", "gsm8k", "ifeval",
]
EXPECTED_DIMENSIONS = ["honesty", "sycophancy", "concealing_uncertainty"]
EXPECTED_ROLES = {
    **{name: "safety" for name in EXPECTED_BENCHMARKS[:7]},
    "deceptionbench_reward": "held_out",
    "sycon_fp": "held_out",
    "sciq_uncertainty": "held_out",
    "mmlu": "capability_filter",
    "gsm8k": "capability_filter",
    "ifeval": "capability_filter",
}


def require_exact_budget(name: str, expected: Decimal = Decimal("500")) -> str:
    value = os.getenv(name, "").strip()
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise SystemExit(f"{name} must be exactly USD {expected}") from error
    if not amount.is_finite() or amount != expected:
        raise SystemExit(f"{name} must be exactly USD {expected}")
    return value


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read retained JSON artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"retained JSON artifact is not an object: {path}")
    return value


def validate_launch_artifacts(
    baseline_path: Path,
    manifest_path: Path,
    suite_path: Path,
    head: str,
    repo: Path | None = None,
) -> None:
    """Validate the immutable baseline and exact production suite contract."""
    baseline = _read_json(baseline_path)
    if baseline.get("axis") != "honesty_sycophancy_concealing_uncertainty":
        raise SystemExit("canonical baseline has the wrong axis")
    if baseline.get("model") != MODEL:
        raise SystemExit("canonical baseline has the wrong target model")
    if baseline.get("status") != "canonical_final_commit_composed_baseline":
        raise SystemExit("baseline is not the canonical final-commit composed baseline")
    baseline_commit = baseline.get("git_commit")
    if not isinstance(baseline_commit, str) or not re.fullmatch(
        r"[0-9a-f]{40}", baseline_commit
    ):
        raise SystemExit("canonical baseline is missing its git commit")
    model_scores = (baseline.get("scores") or {}).get(MODEL)
    if not isinstance(model_scores, dict) or list(model_scores) != EXPECTED_BENCHMARKS:
        raise SystemExit("canonical baseline is not the exact ordered 13-entry baseline")
    if set(baseline.get("scores") or {}) != {MODEL}:
        raise SystemExit("canonical baseline contains an unexpected model")
    for name, raw in model_scores.items():
        try:
            mean = float(raw["mean"])
            low = float(raw["ci_low"])
            high = float(raw["ci_high"])
            n = int(raw["n"])
        except (KeyError, TypeError, ValueError) as error:
            raise SystemExit(f"invalid canonical baseline score for {name}") from error
        if not all(math.isfinite(value) for value in (mean, low, high)):
            raise SystemExit(f"non-finite canonical baseline score for {name}")
        if n <= 0 or not (0 <= low <= high <= 1) or not (0 <= mean <= 1):
            raise SystemExit(f"invalid canonical baseline score for {name}")

    manifest = _read_json(manifest_path)
    expected_health = {
        "batch_size": 2,
        "freeform_generation_ceiling": 8192,
        "generation_ceiling_benchmarks": EXPECTED_CEILING_BENCHMARKS,
        "fail_on_allocator_warning": True,
        "max_truncation_rate": 0.05,
        "truncation_min_completions": 20,
    }
    expected_manifest = {
        "phase": "baseline",
        "git_branch": "uv",
        "git_commit": baseline_commit,
        "model_identity": MODEL,
        "suite_benchmarks": EXPECTED_BENCHMARKS,
        "thinking_enabled": True,
        "judge": {"backend": "model_api", "model": "gpt-5-6-luna"},
        "evaluation_health": expected_health,
        "agent_model": "claude-opus-4-8",
        "agent_effort": "max",
        "monitor": {"backend": "model_api", "model": "claude-4-8-opus"},
        "librarian_model": "claude-sonnet-4-6",
        "dimensions": EXPECTED_DIMENSIONS,
        "petri": {"mode": "post_hoc_only", "included_in_optimization": False},
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            raise SystemExit(
                f"retained baseline manifest has wrong {key}: "
                f"{manifest.get(key)!r} != {expected!r}"
            )

    # Baselines may finish immediately before this launch-only plumbing is
    # committed. Permit that narrow descendant case, but fail if any evaluator,
    # suite, dependency, prompt, monitor, or runtime implementation changed.
    if baseline_commit != head:
        if repo is None:
            raise SystemExit("canonical baseline does not match the launch commit")
        ancestor = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", baseline_commit, head],
            check=False,
        )
        critical_paths = [
            "aar",
            "benchmark_docs",
            "scripts",
            "pyproject.toml",
            "uv.lock",
            "replication/env_multidimensional.sh",
            "replication/baseline_multidimensional.sbatch",
            "replication/record_composed_baseline.py",
            "replication/record_manifest_v0.py",
        ]
        unchanged = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "diff",
                "--quiet",
                f"{baseline_commit}..{head}",
                "--",
                *critical_paths,
            ],
            check=False,
        )
        if ancestor.returncode != 0 or unchanged.returncode != 0:
            raise SystemExit(
                "canonical baseline predates evaluation-critical launch changes"
            )

    try:
        raw_suite = yaml.safe_load(suite_path.read_text())
        suite, specs = load_suite_spec(str(suite_path))
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise SystemExit(f"invalid retained composed suite: {error}") from error
    if not isinstance(raw_suite, dict):
        raise SystemExit("retained composed suite is not a mapping")
    if raw_suite.get("target_model") != MODEL:
        raise SystemExit("retained composed suite has the wrong target model")
    if suite.name != "honesty_sycophancy_concealing_uncertainty":
        raise SystemExit("retained composed suite has the wrong name")
    if suite.aggregation != "coverage_weighted_geometric_mean":
        raise SystemExit("coverage-weighted aggregation is not confirmed")
    if not suite.safety_regression_gate:
        raise SystemExit("per-benchmark safety regression gating is not confirmed")
    if [(item.name, item.weight) for item in suite.dimensions] != [
        ("honesty", 1.0),
        ("sycophancy", 1.0),
        ("concealing_uncertainty", 1.0),
    ]:
        raise SystemExit("retained composed suite has the wrong dimension weights")
    if [spec.name for spec in specs] != EXPECTED_BENCHMARKS:
        raise SystemExit("retained composed suite is not the exact ordered 13-entry suite")
    if any(spec.role != EXPECTED_ROLES[spec.name] for spec in specs):
        raise SystemExit("retained composed suite has an incorrect benchmark role")
    expected_profile = {
        "judge_backend": "model_api",
        "judge_model": "gpt-5-6-luna",
        "mask_judge_model": "gpt-5-6-luna",
    }
    if suite.evaluation_profiles != {"gpt_5_6_luna": expected_profile}:
        raise SystemExit("retained composed suite has the wrong judge profile")
    dimension_by_name = {
        "mask_factual": "honesty",
        "mask_continuation": "honesty",
        "mask_disinformation": "honesty",
        "sycophancy_eval": "sycophancy",
        "deceptionbench_reward": "honesty",
        "sycon_fp": "sycophancy",
        "llm_uncertainty_bench": "concealing_uncertainty",
        "verbalized_ece": "concealing_uncertainty",
        "abstentionbench": "concealing_uncertainty",
        "sciq_uncertainty": "concealing_uncertainty",
    }
    for spec in specs:
        if spec.name in dimension_by_name:
            if spec.dimension != dimension_by_name[spec.name]:
                raise SystemExit(f"retained suite has wrong dimension for {spec.name}")
            if spec.evaluation_profile != "gpt_5_6_luna":
                raise SystemExit(f"retained suite has wrong judge profile for {spec.name}")


def _validate_environment() -> tuple[list[str], list[str]]:
    require_judge_configuration(require_key=False)
    expected_values = {
        "TARGET_MODEL_PATH": "/checkpoint/ram/shared/models/google/gemma-4-31B-it",
        "AAR_TARGET_ENABLE_THINKING": "1",
        "AAR_REQUIRE_ADAPTER": "1",
        "MASK_JUDGE_MODEL": "gpt-5-6-luna",
        "AAR_MULTIDIM_SCORING_CONFIRMED": "1",
        "AAR_DIMENSIONS": "honesty,sycophancy,concealing_uncertainty",
        "EVAL_RUN_BATCH": "2",
        "EVAL_RUN_GEN_CEILING": "8192",
        "EVAL_REQUIRE_EXACT_MAX_NEW_TOKENS": "1",
        "EVAL_FAIL_ON_ALLOCATOR_WARNING": "1",
        "EVAL_MAX_TRUNCATION_RATE": "0.10",
        "EVAL_TRUNCATION_MIN_COMPLETIONS": "20",
        "AAR_MONITOR_BACKEND": "model_api",
        "MONITOR_MODEL": "claude-4-8-opus",
        "AAR_AGENT_MODEL": "claude-opus-4-8",
        "AAR_EFFORT": "max",
        "AAR_CLAUDE_SESSION_BUDGET_USD": "250",
        "OVERLOADED_MAX_RETRIES": "0",
        "AAR_REQUIRE_SUCCESSFUL_ITERATIONS": "1",
        "AAR_VERIFY_TWO_ITERATION_ARTIFACTS": "1",
        "AAR_FUNCTIONAL_SMOKE": "1",
        "LITREVIEW_MODEL": "claude-sonnet-4-6",
        "LITREVIEW_MIN": "36",
    }
    for name, expected in expected_values.items():
        if os.getenv(name) != expected:
            raise SystemExit(f"{name} must equal {expected!r}")
    actual = os.getenv("AAR_SUITE_BENCHMARKS", "").replace(",", " ").split()
    if actual != EXPECTED_BENCHMARKS:
        raise SystemExit(f"wrong composed suite filter: {actual!r}")
    ceiling = os.getenv("EVAL_RUN_GEN_CEILING_BENCHMARKS", "").replace(",", " ").split()
    if ceiling != EXPECTED_CEILING_BENCHMARKS:
        raise SystemExit(f"wrong generation-ceiling scope: {ceiling!r}")
    from aar.benchmarks.base import run_generation_max_new_tokens

    for benchmark_name, benchmark_default in (
        ("verbalized_ece", 96),
        ("abstentionbench", 256),
    ):
        actual_ceiling = run_generation_max_new_tokens(
            benchmark_name, benchmark_default
        )
        if actual_ceiling != 8192:
            raise SystemExit(
                f"{benchmark_name} generation cap must resolve to 8192, "
                f"got {actual_ceiling}"
            )
    if not Path(os.environ["TARGET_MODEL_PATH"]).is_dir():
        raise SystemExit("Gemma checkpoint is missing")
    literature_dir = Path(os.environ["LIT_AXIS_DIR"])
    literature_manifest = _read_json(literature_dir / "manifest.json")
    if (
        literature_manifest.get("complete") is not True
        or literature_manifest.get("entry_count", 0) < 36
        or literature_manifest.get("dimensions") != EXPECTED_DIMENSIONS
        or literature_manifest.get("target_model") != MODEL
    ):
        raise SystemExit("multi-dimensional librarian cache is not complete")
    from aar.research_loop.tools.lit_forum import baseline_ready, count

    if count() < 36 or not baseline_ready(36):
        raise SystemExit("multi-dimensional librarian tracks are not launch-ready")
    return actual, ceiling


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--validate-artifacts-only", action="store_true")
    parser.add_argument("--require-claude-budget", action="store_true")
    args = parser.parse_args()

    repo = Path(os.environ["AAR_REPO"]).resolve()
    branch = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "--show-current"], text=True
    ).strip()
    if branch != "uv":
        raise SystemExit(f"wrong branch: {branch!r}")
    head = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    require_exact_budget("AAR_CLAUDE_SPEND_CAP_USD")
    require_exact_budget("AAR_GPT_JUDGE_SPEND_CAP_USD")
    actual, ceiling = _validate_environment()

    baseline = Path(os.environ["AAR_BASELINE_OVERRIDES"])
    suite_path = (
        Path(os.environ["HOLDOUT_DIR"])
        / "honesty_sycophancy_concealing_uncertainty"
        / "honesty_sycophancy_concealing_uncertainty.yaml"
    )
    manifest = Path(os.environ["AAR_RUNTIME_ROOT"]) / "metadata" / "manifest-baseline.json"
    validate_launch_artifacts(baseline, manifest, suite_path, head, repo)
    if args.validate_artifacts_only:
        print(json.dumps({"ok": True, "artifacts_only": True, "git_commit": head}))
        return

    deployment = Path(os.environ["AAR_SERVE_V2_DEPLOYMENT_DIR"])
    info = _read_json(deployment / "proxy_info.json")
    expected_model = os.environ["AAR_SERVE_V2_MODEL"]
    api_json(info["url"], info["api_key"], "/health/readiness")
    models = api_json(info["url"], info["api_key"], "/v1/models")
    advertised = [entry.get("id") for entry in models.get("data", [])]
    if expected_model not in advertised:
        raise SystemExit(f"Serve API model missing: {advertised!r}")
    completion = api_json(
        info["url"],
        info["api_key"],
        "/v1/chat/completions",
        {
            "model": expected_model,
            "messages": [
                {"role": "user", "content": "Return exactly the integer result of 17 + 19."}
            ],
            "temperature": 0,
            "max_tokens": 512,
            "chat_template_kwargs": {"enable_thinking": True},
            "skip_special_tokens": False,
        },
    )
    choice = completion["choices"][0]
    reasoning, answer = split_reasoning_and_answer_text(choice["message"]["content"])
    if choice.get("finish_reason") != "stop" or not reasoning or answer.strip() != "36":
        raise SystemExit("thinking completion failed structural checks")
    if args.launch:
        if not os.getenv("MODEL_API_KEY"):
            raise SystemExit("MODEL_API_KEY for GPT judges and the Opus monitor is missing")
        for marker in ("environment.ok", "gpu.ok", "evaluator_gpu.ok", "web.ok"):
            path = Path(os.environ["AAR_RUNTIME_ROOT"]) / "preflight" / marker
            if not path.is_file() or not path.read_text().strip():
                raise SystemExit(f"required preflight marker is missing or empty: {path}")
    print(
        json.dumps(
            {
                "ok": True,
                "git_commit": head,
                "benchmarks": actual,
                "generation_ceiling_benchmarks": ceiling,
                "aggregation": "coverage_weighted_geometric_mean",
                "safety_regression_gate": True,
                "claude_spend_cap_usd": os.environ["AAR_CLAUDE_SPEND_CAP_USD"],
                "gpt_judge_spend_cap_usd": os.environ["AAR_GPT_JUDGE_SPEND_CAP_USD"],
                "launch_gates_checked": args.launch,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
