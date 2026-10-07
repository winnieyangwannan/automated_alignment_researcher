"""Eval-pod entrypoint: score a submitted model against a secret benchmark suite.

    python -m aar.eval_pod.run_eval --suite configs/toy.yaml --model stub:perfect

Reads the suite YAML, loads the model once, runs every benchmark in the suite
(rule / judge / trajectory) via the registry, computes the composite headline +
capability filter, prints a table, and writes scores.json. Only aggregate
scores are emitted — never individual items. In production this runs on the
ephemeral eval pod; locally it runs as a plain process with a stub model.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
from typing import Any

import yaml

# Parallelism. WITHIN each benchmark the expensive work already fans out (judge
# calls via JUDGE_CONCURRENCY; generation BATCHED via generate_batch). ACROSS
# benchmarks we parallelize when EVAL_GPUS>1: one model replica per GPU, with
# workers pulling the next benchmark from a shared queue so uneven benchmark
# runtimes do not leave GPUs idle. On a single GPU (EVAL_GPUS=1, default) we
# stay sequential — benchmark-level threads there
# just starve the cheap benchmarks behind the slow ones. Set EVAL_GPUS to the
# job's --gres gpu count (eval_worker.sh / baseline_*.sh do this).

from aar.benchmarks import registry
from aar.benchmarks.base import BenchmarkSpec, DimensionSpec, SuiteSpec
from aar.benchmarks.composite import compute_composite
from aar.eval_pod.models import load_model, resolve_inference_backend
from aar.phase_timing import phase


def load_suite(path: str) -> tuple[str, list[BenchmarkSpec]]:
    """Compatibility wrapper for callers that only need the legacy tuple."""
    suite, specs = load_suite_spec(path)
    return suite.name, specs


def load_suite_spec(path: str) -> tuple[SuiteSpec, list[BenchmarkSpec]]:
    data = yaml.safe_load(Path(path).read_text())
    dimensions = tuple(
        DimensionSpec(
            name=(item if isinstance(item, str) else item["name"]),
            weight=(1.0 if isinstance(item, str) else float(item.get("weight", 1.0))),
        )
        for item in (data.get("dimensions") or [])
    )
    profiles = data.get("evaluation_profiles") or {}
    suite = SuiteSpec(
        name=data.get("suite", "unnamed"),
        aggregation=data.get("aggregation", "legacy_geometric_mean"),
        dimensions=dimensions,
        safety_regression_gate=bool(data.get("safety_regression_gate", False)),
        evaluation_profiles=profiles,
    )
    allowed_aggregations = {"legacy_geometric_mean", "coverage_weighted_geometric_mean"}
    if suite.aggregation not in allowed_aggregations:
        raise ValueError(f"unsupported suite aggregation {suite.aggregation!r}")
    if len({dimension.name for dimension in dimensions}) != len(dimensions):
        raise ValueError("suite contains duplicate dimension names")
    if any(dimension.weight <= 0 for dimension in dimensions):
        raise ValueError("dimension weights must be positive")
    gemma_composed_suites = {
        "honesty_sycophancy",
        "honesty_sycophancy_concealing_uncertainty",
    }
    if (
        suite.name in gemma_composed_suites
        and data.get("target_model") != "google/gemma-4-31B-it"
    ):
        raise ValueError(
            f"{suite.name} requires target_model google/gemma-4-31B-it"
        )
    if suite.aggregation == "coverage_weighted_geometric_mean" and not dimensions:
        raise ValueError("dimension aggregation requires at least one dimension")
    dimension_names = {dimension.name for dimension in dimensions}
    specs = []
    for b in data["benchmarks"]:
        dimension = b.get("dimension")
        if dimension and dimension_names and dimension not in dimension_names:
            raise ValueError(f"benchmark {b['name']!r} has unknown dimension {dimension!r}")
        profile_name = b.get("evaluation_profile")
        if profile_name and profile_name not in profiles:
            raise ValueError(
                f"benchmark {b['name']!r} requires missing evaluation profile {profile_name!r}"
            )
        extra = dict(b.get("extra", {}) or {})
        if profile_name:
            extra["_evaluation_profile"] = dict(profiles[profile_name])
        specs.append(BenchmarkSpec(
            name=b["name"],
            category=b["category"],
            role=b.get("role", "safety"),
            id=b.get("id", ""),
            baseline=float(b.get("baseline", 0.0)),
            optimum=float(b.get("optimum", 1.0)),
            floor=(float(b["floor"]) if "floor" in b else None),
            subset_size=b.get("subset_size"),
            dimension=dimension,
            baseline_group=b.get("baseline_group"),
            evaluation_profile=profile_name,
            baseline_ci_low=(
                float(b["baseline_ci_low"]) if b.get("baseline_ci_low") is not None else None
            ),
            baseline_ci_high=(
                float(b["baseline_ci_high"]) if b.get("baseline_ci_high") is not None else None
            ),
            extra=extra,
        ))
    if len({spec.id for spec in specs}) != len(specs):
        raise ValueError("suite contains duplicate benchmark ids")
    if dimensions:
        missing = [
            spec.id for spec in specs
            if spec.role in ("safety", "held_out") and not spec.dimension
        ]
        if missing:
            raise ValueError(f"dimension-aware suite has unassigned safety entries: {missing}")
        empty = [
            dimension.name for dimension in dimensions
            if not any(
                spec.role == "safety" and spec.dimension == dimension.name
                for spec in specs
            )
        ]
        if empty:
            raise ValueError(f"dimensions have no optimized safety benchmarks: {empty}")
    if suite.safety_regression_gate:
        missing_intervals = [
            spec.id for spec in specs
            if spec.role == "safety"
            and (spec.baseline_ci_low is None or spec.baseline_ci_high is None)
        ]
        if missing_intervals:
            raise ValueError(
                "safety regression gate requires baseline confidence intervals: "
                f"{missing_intervals}"
            )
    return suite, specs


def build_benchmark(spec: BenchmarkSpec, secret_dir: str, real_judge_fn=None):
    """Instantiate a benchmark plugin, wiring a judge_fn into any benchmark
    whose constructor accepts one (judge benchmarks + judge-graded trajectory
    benchmarks like syc_eval)."""
    import inspect
    cls = registry.get(spec.name)
    if "judge_fn" in inspect.signature(cls.__init__).parameters:
        # Each judge benchmark declares its historical/default `judge_model` (e.g.
        # sycophancy_eval/feedback -> "gpt-4"; sycon_fp -> "gpt-4o"). The resolver
        # retains that per-benchmark default unless JUDGE_MODEL explicitly overrides it.
        jm = getattr(cls, "judge_model", None)
        profile = spec.extra.get("_evaluation_profile")
        judge_fn = _resolve_judge_fn(jm, profile=profile)
        if profile and judge_fn is None:
            raise RuntimeError(
                f"{spec.id}: configured evaluation profile {spec.evaluation_profile!r} "
                "could not initialize its judge"
            )
        judge_fn = judge_fn or real_judge_fn or getattr(cls, "default_judge_fn", None)
        return cls(spec, secret_dir, judge_fn=judge_fn)
    return cls(spec, secret_dir)


@contextmanager
def _evaluation_profile(spec: BenchmarkSpec):
    """Apply the benchmark's explicit judge profile inside its evaluator process.

    This is also required by plugins such as MASK that resolve their specialized
    judge directly from environment variables rather than ``judge_fn``.
    """
    profile = spec.extra.get("_evaluation_profile") or {}
    env_names = {
        "judge_backend": "JUDGE_BACKEND",
        "judge_model": "JUDGE_MODEL",
        "mask_judge_model": "MASK_JUDGE_MODEL",
        "judge_concurrency": "JUDGE_CONCURRENCY",
    }
    previous = {env_name: os.environ.get(env_name) for env_name in env_names.values()}
    try:
        for key, env_name in env_names.items():
            if profile.get(key) is not None:
                os.environ[env_name] = str(profile[key])
        yield
    finally:
        for env_name, value in previous.items():
            if value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = value


def _resolve_judge_fn(model: str | None = None, profile: dict | None = None):
    """Pick the judge backend for judge-category benchmarks.

    `model` = the benchmark's declared historical/default `judge_model`.
    JUDGE_BACKEND = "local" -> on-GPU HF judge (grid default; bounds cost — but NOT
    paper-faithful, so not used for the published baselines). "openai"/unset uses an
    explicitly configured JUDGE_MODEL first, then the per-benchmark model, then gpt-4o,
    if a key is present; otherwise returns None.
    """
    import os
    profile = profile or {}
    backend = str(profile.get("judge_backend") or os.getenv("JUDGE_BACKEND", "openai")).lower()
    configured_model = profile.get("judge_model") or os.getenv("JUDGE_MODEL")
    if backend == "local":
        from aar.eval_pod.judges import make_local_judge
        return make_local_judge(os.getenv("JUDGE_MODEL_LOCAL") or None)
    if backend == "anthropic":
        from aar.eval_pod.judges import make_anthropic_judge
        from aar.benchmarks._judge_http import _anthropic_key
        if _anthropic_key():
            return make_anthropic_judge(model=(configured_model or "claude-haiku-4-5"))
        return None
    if backend == "model_api":
        from aar.eval_pod.judges import make_model_api_judge
        from aar.benchmarks._judge_http import _model_api_key
        if _model_api_key():
            return make_model_api_judge(
                model=(configured_model or "claude-4-8-opus")
            )
        return None
    if os.getenv("OAI_API") or os.getenv("OPENAI_API_KEY") or os.getenv("MODEL_API_KEY"):
        from aar.eval_pod.judges import make_openai_judge
        return make_openai_judge(model=(configured_model or model or "gpt-4o"))
    return None


# Benchmarks whose baseline is the SHARED capability basket (benchmark_docs/capability/),
# not the safety axis. They must be scored at the capability config on EVERY axis.
_CAP_BENCHES = {"mmlu", "gsm8k", "ifeval"}
_DECODING_CACHE: dict[str, dict] = {}

# FREE-FORM GENERATION benchmarks: long, open-ended completions where a degenerate model can
# fall into a no-EOS repetition loop. These get the optional run-time no_repeat_ngram guard.
# EXCLUDED on purpose:
#   - ifeval: instructions REQUIRE legit repetition / verbatim echoing / keyword-frequency — an
#     ngram guard makes compliance impossible and tanks the score.
#   - gsm8k: math CoT with an EXACT final-answer format. A tight ceiling truncates verbose chains
#     before the "#### answer" (Qwen 0.76 -> 0.055) and no_repeat_ngram disrupts the arithmetic
#     (math naturally repeats number/operator n-grams; Llama 0.665 -> 0.40). It is a reasoning
#     task, NOT free-form text — keep ngram 0. Its ceiling can still be raised uniformly.
#   - logprob/MCQ benches (mmlu, truthfulqa_mc2, news_factor, expert_factor): no generation -> no-op.
#   - structured prompt-injection extraction benches: short exact-string outputs ngram could corrupt.
# CAUTION for later: ragtruth measures source-FAITHFULNESS; an ngram guard could force the model to
# diverge from the source it should quote -> revisit/validate before trusting task-3 ragtruth.
_FREEFORM_GEN = {
    # JUDGE-scored, short-response free-form benches only (the judge is robust to the ngram
    # guard). EXCLUDED after the hard way: rule-scored pattern-keyed benches (gsm8k arithmetic,
    # ifeval echoing, elephant_aita affirmation-phrases — ngram inflates them), trajectory/long
    # benches (sycon_fp needs its own long-rollout profile), and detector-scored
    # faithfulness (ragtruth — ngram could force divergence from the quoted source).
    "sycophancy_eval", "sycophancy_feedback",
    "truthfulqa_gen",
    "mask_generative", "mask_factual", "mask_continuation", "mask_disinformation",
    "deceptionbench_pressure", "deceptionbench_reward",
    "harmbench", "jbb", "jbb_artifacts", "strongreject",
    # NB: sycon_fp (trajectory held-out) was TEMPORARILY added here for its dedicated temp-1 re-run
    # (array 1669675, 2026-06-08) so EVAL_RUN_NGRAM/CEILING could bound its degeneration runaways;
    # that run is DONE and it is now removed — it must NOT carry the ngram/ceiling treatment normally.
}

# Generated target responses that share the run-wide thinking-plus-answer
# ceiling. Rule/logprob benchmarks are intentionally absent.
_GENERATION_CEILING_OVERRIDE = _FREEFORM_GEN | {
    "sycon_fp", "gsm8k", "ifeval", "verbalized_ece", "abstentionbench",
}


def _run_override(spec: BenchmarkSpec, d: dict) -> dict:
    """Report-only re-measurement overrides (see rerun config), env-gated so the live AAR's
    golden configs are untouched when these envs are unset:
      EVAL_RUN_BATCH       -> force batch_size for ALL benches (uniform throughput)
      EVAL_RUN_NGRAM       -> no_repeat_ngram for FREE-FORM GEN benches only (kills runaways)
      EVAL_RUN_GEN_CEILING -> auto_ceiling for every generated combined-suite response
    Temperature is carried by the model (EVAL_TEMPERATURE) and is not touched here."""
    bs = os.getenv("EVAL_RUN_BATCH")
    if bs:
        d["batch_size"] = int(bs)
    if spec.name in _FREEFORM_GEN:
        ng = os.getenv("EVAL_RUN_NGRAM")
        if ng:
            d["no_repeat_ngram"] = int(ng)
    if spec.name in _GENERATION_CEILING_OVERRIDE:
        cg = os.getenv("EVAL_RUN_GEN_CEILING")
        if cg:
            d["auto_ceiling"] = int(cg)
            # A source profile may carry a smaller fixed maximum. The explicit
            # run-wide budget replaces it for this newly baselined experiment.
            d["max_new_tokens"] = None
    return d


def _health_snapshot(model) -> dict[str, int]:
    if not hasattr(model, "evaluation_health"):
        return {}
    return dict(model.evaluation_health())


def _validate_evaluation_health(model, before: dict[str, int], benchmark_id: str) -> None:
    """Reject unhealthy generation before a benchmark score can be accepted."""
    after = _health_snapshot(model)
    if not after:
        return
    delta = {
        name: int(after.get(name, 0)) - int(before.get(name, 0))
        for name in ("generated", "truncated", "allocator_warnings", "ooms")
    }
    if delta["ooms"]:
        raise RuntimeError(f"{benchmark_id}: CUDA OOM detected during evaluation")
    if (
        os.getenv("EVAL_FAIL_ON_ALLOCATOR_WARNING", "0").lower()
        in ("1", "true", "yes")
        and delta["allocator_warnings"]
    ):
        raise RuntimeError(
            f"{benchmark_id}: {delta['allocator_warnings']} CUDA allocator warning(s) detected"
        )

    minimum = int(os.getenv("EVAL_TRUNCATION_MIN_COMPLETIONS", "20"))
    maximum = os.getenv("EVAL_MAX_TRUNCATION_RATE", "").strip()
    rate = (
        delta["truncated"] / delta["generated"] if delta["generated"] else 0.0
    )
    print(
        f"  [health] {benchmark_id}: generated={delta['generated']} "
        f"truncated={delta['truncated']} rate={rate:.2%} "
        f"allocator_warnings={delta['allocator_warnings']}",
        flush=True,
    )
    if maximum and delta["generated"] >= minimum and rate > float(maximum):
        raise RuntimeError(
            f"{benchmark_id}: truncation rate {rate:.2%} exceeds {float(maximum):.2%} "
            f"after {delta['generated']} completions"
        )


def _fingerprint_loaded_model(model) -> str | None:
    """Fingerprint an already-loaded model without making scoring depend on it."""
    try:
        from aar.eval_pod.model_fingerprint import compute_fingerprint

        return compute_fingerprint(model)
    except Exception as error:  # noqa: BLE001 - fingerprinting is additive
        print(f"  [fingerprint] skipped ({error})", flush=True)
        return None


def _golden_decoding(spec: BenchmarkSpec, suite_name: str) -> dict:
    """The benchmark's GOLDEN decoding, read live from benchmark_docs/<group>/baseline.json
    — the SAME config its baseline was measured at. The shared capability basket maps to
    'capability' (fixed across all axes); every other benchmark maps to the suite's axis.
    Returns {} when unavailable, so we keep the current/global decoding as a safe fallback."""
    import json as _json
    from aar import config as _cfg
    group = spec.baseline_group or ("capability" if spec.name in _CAP_BENCHES else suite_name)
    if group not in _DECODING_CACHE:
        d: dict = {}
        try:
            p = Path(_cfg.BENCHMARK_DOCS_DIR) / group / "baseline.json"
            dec = (_json.loads(p.read_text()).get("decoding") or {})
            d = {"batch_size": dec.get("batch", dec.get("batch_size")),
                 "auto_ceiling": dec.get("auto_ceiling"),
                 "no_repeat_ngram": dec.get("no_repeat_ngram", 0),
                 "max_new_tokens": dec.get("max_new_tokens"),
                 # decoding STRATEGY from the docs (the config the baseline was measured at):
                 # temp-1 sampling (temperature/top_p) + a fixed seed for reproducibility.
                 "temperature": dec.get("temperature"),
                 "top_p": dec.get("top_p"),
                 "seed": dec.get("seed"),
                 # free-form judge-scored gen benches get the doc's freeform_treatment override
                 # (tighter ngram/ceiling) — applied per-benchmark below, not baked into the cache.
                 "_freeform": dec.get("freeform_treatment") or {}}
        except Exception as e:
            print(f"  [decoding] WARN: no benchmark_docs decoding for group '{group}' "
                  f"({e}); keeping global decoding", flush=True)
        _DECODING_CACHE[group] = d
    d = dict(_DECODING_CACHE[group])
    ff = d.pop("_freeform", {}) or {}
    if spec.name in _FREEFORM_GEN:
        if ff.get("no_repeat_ngram") is not None:
            d["no_repeat_ngram"] = ff["no_repeat_ngram"]
        if ff.get("auto_ceiling") is not None:
            d["auto_ceiling"] = ff["auto_ceiling"]
    return d


def _apply_golden(model, spec: BenchmarkSpec, suite_name: str) -> None:
    """Pin the model's decoding to THIS benchmark's golden config before scoring it, so
    per-iteration eval == baseline measurement for every benchmark (the capability basket
    at batch8/ceiling4096/ngram0 on every axis; safety/held-out at the axis's config)."""
    if not hasattr(model, "apply_decoding"):
        return  # toy/stub model: no real decoding to set
    d = _golden_decoding(spec, suite_name)
    if not d:
        return
    d = _run_override(spec, d)   # report-only run overrides (env-gated; no-op for the live AAR)
    kw: dict = {}
    if d.get("batch_size") is not None:
        kw["batch_size"] = d["batch_size"]
    if d.get("no_repeat_ngram") is not None:
        kw["no_repeat_ngram"] = d["no_repeat_ngram"]
    if d.get("auto_ceiling") is not None:
        kw["auto_ceiling"] = d["auto_ceiling"]
    if d.get("temperature") is not None:
        kw["temperature"] = d["temperature"]
    if d.get("top_p") is not None:
        kw["top_p"] = d["top_p"]
    if d.get("seed") is not None:
        kw["seed"] = d["seed"]
    # Explicit max_new_tokens (scalar, or a per-benchmark map e.g. prompt_injection) overrides
    # AUTO; otherwise use AUTO bounded by the group ceiling (resetting any prior explicit value).
    mnt = d.get("max_new_tokens")
    if isinstance(mnt, dict):
        mnt = mnt.get(spec.id) or mnt.get(spec.name)
    if mnt is not None:
        kw["max_new_tokens"] = mnt
    elif d.get("auto_ceiling") is not None:
        kw["max_new_tokens"] = None
    if kw:
        model.apply_decoding(**kw)
        grp = spec.baseline_group or ("capability" if spec.name in _CAP_BENCHES else suite_name)
        print(f"  [decoding] {spec.id} ({grp}): batch={model.batch_size} "
              f"ceiling={model._auto_ceiling} ngram={model._no_repeat_ngram} "
              f"max_new={model.max_new_tokens} temp={model._temperature} "
              f"top_p={model._top_p} seed={model._seed}", flush=True)


def _benchmark_timing_metadata(
    spec: BenchmarkSpec,
    *,
    worker: str | None = None,
) -> dict[str, str]:
    is_held_out = spec.role == "held_out"
    metadata = {
        "benchmark": "held_out" if is_held_out else spec.id,
        "category": "held_out" if is_held_out else spec.category,
        "role": spec.role,
    }
    if worker is not None:
        metadata["worker"] = worker
    return metadata


def _score_sequential(specs, model_ref, secret_dir, suite_name=""):
    with phase("eval.model_loading", metadata={"worker": "sequential"}):
        model = load_model(model_ref)
    try:
        judge_fn = _resolve_judge_fn()
        scores = {}
        for spec in specs:
            with phase(
                "eval.benchmark",
                metadata=_benchmark_timing_metadata(spec),
            ):
                with _evaluation_profile(spec):
                    _apply_golden(model, spec, suite_name)   # golden per-benchmark decoding (== baseline)
                    health_before = _health_snapshot(model)
                    sc = build_benchmark(spec, secret_dir, real_judge_fn=judge_fn).score(model)
                    _validate_evaluation_health(model, health_before, spec.id)
            scores[spec.id] = sc
            if spec.role == "held_out":
                # Never print the held-out score to stdout — eval logs can land in
                # research-readable paths; the only place its score is allowed is the
                # eval-private HELDOUT_SCORES_DIR.
                print("  [a held_out benchmark — name, score, n all hidden from logs]", flush=True)
            else:
                print(f"  {spec.id:16s} [{spec.category:10s} {spec.role:18s}] "
                      f"mean={sc.mean:.4f} ci=[{sc.ci_low:.4f},{sc.ci_high:.4f}] n={sc.n}", flush=True)
        fingerprint = None
        if not str(model_ref).startswith("stub:"):
            with phase("eval.model_fingerprint"):
                fingerprint = _fingerprint_loaded_model(model)
        return scores, fingerprint
    finally:
        close = getattr(model, "close", None)
        if callable(close):
            close()


def _gpu_worker(
    gpu: str,
    tasks,
    model_ref: str,
    secret_dir: str,
    q,
    suite_name="",
    fingerprint: bool = False,
) -> None:
    """Load one GPU replica and pull benchmarks from the shared task queue."""
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    model = None
    try:
        from aar.benchmarks import registry as _reg
        _reg.discover()
        judge_fn = _resolve_judge_fn()
        with phase("eval.model_loading", metadata={"worker": str(gpu)}):
            model = load_model(model_ref)
        while True:
            spec = tasks.get()
            if spec is None:
                break
            try:
                with phase(
                    "eval.benchmark",
                    metadata=_benchmark_timing_metadata(spec, worker=str(gpu)),
                ):
                    with _evaluation_profile(spec):
                        _apply_golden(model, spec, suite_name)   # golden per-benchmark decoding (== baseline)
                        health_before = _health_snapshot(model)
                        sc = build_benchmark(spec, secret_dir, real_judge_fn=judge_fn).score(model)
                        _validate_evaluation_health(model, health_before, spec.id)
                q.put(("score", spec.id, sc, None))
            except Exception as e:  # one benchmark failing shouldn't sink the rest
                q.put(("score", spec.id, None, repr(e)))
        if fingerprint:
            with phase("eval.model_fingerprint", metadata={"worker": str(gpu)}):
                q.put(("fingerprint", None, _fingerprint_loaded_model(model), None))
    except Exception as e:  # worker-level failure (model load, etc.)
        q.put(("worker_error", str(gpu), None, repr(e)))
    finally:
        try:
            close = getattr(model, "close", None)
            if callable(close):
                close()
        finally:
            q.put(("done", str(gpu), None, None))


def _score_parallel(specs, model_ref, secret_dir, ngpu, suite_name=""):
    """Dynamically schedule benchmarks across one model replica per GPU."""
    import multiprocessing as mp
    # The GPUs SLURM allocated us (CUDA_VISIBLE_DEVICES may be physical ids like
    # "2,5"); index into it so each worker gets a distinct allocated GPU.
    alloc = [x for x in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if x.strip()]
    nworkers = min(ngpu, len(specs))
    print(
        f"  scoring {len(specs)} benchmarks across {nworkers} GPUs "
        "(dynamic queue)",
        flush=True,
    )
    ctx = mp.get_context("spawn")   # spawn: required for CUDA in subprocesses
    tasks = ctx.Queue()
    q = ctx.Queue()
    for spec in specs:
        tasks.put(spec)
    for _ in range(nworkers):
        tasks.put(None)
    procs = []
    for g in range(nworkers):
        gpu = alloc[g] if g < len(alloc) else str(g)
        p = ctx.Process(
            target=_gpu_worker,
            args=(gpu, tasks, model_ref, secret_dir, q, suite_name, g == 0),
        )
        p.start()
        procs.append(p)
    _role = {s.id: s.role for s in specs}
    scores, errors, fingerprint = {}, [], None
    workers_done = 0
    while workers_done < nworkers:
        kind, sid, sc, err = q.get()
        if kind == "done":
            workers_done += 1
        elif kind == "fingerprint":
            fingerprint = sc
        elif kind == "worker_error":
            errors.append((f"gpu:{sid}", err))
            print(f"  gpu:{sid} FAILED: {err}", flush=True)
        elif err:
            errors.append((sid, err))
            print(f"  {sid:16s} FAILED: {err}", flush=True)
        else:
            scores[sid] = sc
            if _role.get(sid) == "held_out":      # never print held-out score to stdout
                print("  [a held_out benchmark — name, score, n all hidden from logs]", flush=True)
            else:
                print(f"  {sid:16s} mean={sc.mean:.4f} ci=[{sc.ci_low:.4f},{sc.ci_high:.4f}] n={sc.n}", flush=True)
    for p in procs:
        p.join()
    if errors:
        raise RuntimeError(f"{len(errors)} benchmark(s) failed: {errors}")
    missing = sorted(_role.keys() - scores.keys())
    if missing:
        raise RuntimeError(f"workers exited without scoring benchmarks: {missing}")
    return scores, fingerprint


def _resolve_ngpu() -> int:
    """GPUs to parallelize benchmarks over. EVAL_GPUS=<n> forces it; otherwise
    auto = however many GPUs the job was allocated (CUDA_VISIBLE_DEVICES). We then
    cap to the benchmark count in run(), so the allocation drives parallelism and
    nothing is hardcoded — a 5-benchmark suite uses 5, a 6-benchmark suite 6."""
    env = os.getenv("EVAL_GPUS", "").strip().lower()
    if env.isdigit():
        return int(env)
    cvd = [x for x in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if x.strip()]
    return len(cvd) if cvd else 1


def run(suite_path: str, model_ref: str, secret_dir: str = "", out: str = "scores.json",
        heldout_dir: str = "") -> dict[str, Any]:
    with phase("eval.suite_loading"):
        registry.discover()
        suite, specs = load_suite_spec(suite_path)
    suite_name = suite.name

    if not str(model_ref).startswith("stub:"):
        for name, profile in suite.evaluation_profiles.items():
            backend = str(profile.get("judge_backend", "")).lower()
            if backend == "model_api" and not os.getenv("MODEL_API_KEY"):
                raise RuntimeError(
                    f"evaluation profile {name!r} requires MODEL_API_KEY"
                )

    ngpu = _resolve_ngpu()
    if ngpu > 1 and len(specs) > 1 and not str(model_ref).startswith("stub:"):
        scores, model_fingerprint = _score_parallel(
            specs, model_ref, secret_dir, ngpu, suite_name
        )   # capped to len(specs) inside
    else:
        scores, model_fingerprint = _score_sequential(
            specs, model_ref, secret_dir, suite_name
        )

    with phase("eval.composite_calculation"):
        composite = compute_composite(scores, specs, suite=suite)
    result = {
        "suite": suite_name,
        "model": model_ref,
        "inference_backend": resolve_inference_backend(model_ref),
        **composite.to_dict(),
    }
    # Behavioral fingerprint (deterministic greedy probe of the model). Lets share_finding DEDUP
    # behaviorally-identical submissions — a no-op intervention (e.g. a zero-valued ITI bias) or a
    # shared trained core that the eval correctly scores identically, but that were otherwise posted
    # as DISTINCT findings (polluting the forum + the idea-forecasting data). Additive + fail-safe:
    # a fingerprint error NEVER breaks scoring; old evals simply lack the field (dedup then no-ops).
    if model_fingerprint:
        result["model_fingerprint"] = model_fingerprint
        print(f"  model_fingerprint = {model_fingerprint}")
    # HELD-OUT ISOLATION (the boundary that actually enforces invisibility):
    # `--out` is the RESEARCH-readable handoff (the AAR side reads it, and could even
    # `cat` it). So we write the STRIPPED composite there — the held-out's score never
    # enters research-readable storage, and everything downstream (forum/leaderboard/
    # evaluate_model) inherits a held-out-free view. The FULL composite (incl the
    # held-out) is written ONLY to the eval-private held-out dir (the eval worker runs
    # as the secret eval user; we chmod 700 so the research user can't read it). The
    # human reads the generalization score from there, with eval credentials.
    from aar.benchmarks.composite import contains_held_out, strip_held_out
    if contains_held_out(result):
        Path(out).write_text(json.dumps(strip_held_out(result), indent=2))
        hdir = heldout_dir or os.getenv("HELDOUT_SCORES_DIR", "")
        if hdir:
            Path(hdir).mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(hdir, 0o700)
            except OSError:
                pass
            private_path = Path(hdir) / Path(out).name
            private_path.write_text(json.dumps(result, indent=2))
            try:
                os.chmod(private_path, 0o600)
            except OSError:
                pass
            print(f"  wrote FULL incl held-out -> {private_path} (eval-private, mode-700)")
        else:
            print("  WARN: held-out present but no --heldout-dir / HELDOUT_SCORES_DIR — full "
                  "held-out NOT persisted (research handoff IS stripped, so the AAR stays safe)",
                  flush=True)
        print(f"  wrote STRIPPED (no held-out) -> {out}")
    else:
        Path(out).write_text(json.dumps(result, indent=2))
    print("=" * 60)
    print(f"  HEADLINE {composite.headline * 100:+.2f}%   passes_filter={composite.passes_filter}")
    for name, score in composite.dimension_scores.items():
        print(f"    dimension[{name}] = {score * 100:+.2f}%")
    if composite.dimension_coverage is not None:
        print(f"    dimension_coverage = {composite.dimension_coverage:.2%}")
    for name, frac in composite.closed.items():
        print(f"    closed[{name}] = {frac * 100:+.2f}%")
    for name, d in composite.filter_detail.items():
        thr = d.get("floor", d.get("baseline_ci_low"))
        gate = d.get("gate", "floor")
        print(f"    filter[{name}] = {d['mean']:.4f} ({gate} {thr}) -> {'PASS' if d['passed'] else 'FAIL'}")
    print(f"  wrote {out}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True, help="path to suite YAML")
    ap.add_argument("--model", required=True, help="model ref (stub:perfect | stub:sycophantic | stub:weak | <path>)")
    ap.add_argument("--secret-dir", default="", help="dir holding benchmarks' secret data (toy benchmarks inline theirs)")
    ap.add_argument("--out", default="scores.json", help="RESEARCH-readable handoff (held-out STRIPPED)")
    ap.add_argument("--heldout-dir", default="",
                    help="EVAL-PRIVATE dir (mode-700) for the FULL scores incl held-out; "
                         "the human reads the generalization score here with eval credentials")
    args = ap.parse_args()
    run(args.suite, args.model, args.secret_dir, args.out, args.heldout_dir)


if __name__ == "__main__":
    main()
