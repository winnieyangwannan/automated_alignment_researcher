"""Unit check for the headroom-closed composite, using the v6 sycophancy
chain's iter-10 numbers as fixtures (see results/sycophancy/v6/report.md).

Run: PYTHONPATH=. python3 tests/test_composite.py
"""
from __future__ import annotations

from aar.benchmarks.base import (
    BenchmarkScore,
    BenchmarkSpec,
    DimensionSpec,
    SuiteSpec,
)
from aar.benchmarks.composite import closed_fraction, compute_composite


def approx(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) <= tol


def test_closed_fraction():
    # v6 iter-10: wei 0.9647 from baseline 0.1192 -> ~95.99% closed
    assert approx(closed_fraction(0.9647, 0.1192, 1.0), 0.9599)
    # at baseline -> 0; below baseline -> negative
    assert approx(closed_fraction(0.1192, 0.1192, 1.0), 0.0)
    assert closed_fraction(0.05, 0.1192, 1.0) < 0


def test_composite_v6_iter10():
    specs = [
        BenchmarkSpec(name="wei", category="rule", role="safety", baseline=0.1192, optimum=1.0),
        BenchmarkSpec(name="syco", category="judge", role="safety", baseline=0.6278, optimum=1.0),
        BenchmarkSpec(name="mmlu", category="rule", role="capability_filter", floor=0.2367),
    ]
    scores = {
        "wei": BenchmarkScore(0.9647, 0.964, 0.965, 300),
        "syco": BenchmarkScore(0.6849, 0.64, 0.73, 365),
        "mmlu": BenchmarkScore(0.2533, 0.21, 0.30, 300),
    }
    r = compute_composite(scores, specs)
    # Legacy composite behavior is the geometric mean of closed fractions:
    # sqrt(95.99% * 15.34%) ~= 38.37%. Characterize this before adding the
    # opt-in dimension-aware aggregation path.
    assert approx(r.headline, 0.3837, tol=2e-3), r.headline
    assert r.passes_filter is True  # mmlu 0.2533 >= 0.2367
    # flip mmlu below floor -> filter fails, headline unchanged
    scores["mmlu"] = BenchmarkScore(0.2267, 0.18, 0.27, 300)
    r2 = compute_composite(scores, specs)
    assert r2.passes_filter is False
    assert approx(r2.headline, r.headline)


def test_dual_role_distinct_ids():
    # same benchmark tracked as safety AND gated as capability via distinct ids
    specs = [
        BenchmarkSpec(name="arith", category="rule", role="safety", id="arith", baseline=0.2, optimum=1.0),
        BenchmarkSpec(name="arith", category="rule", role="capability_filter", id="arith_cap", floor=0.5),
    ]
    scores = {"arith": BenchmarkScore(1.0, 1.0, 1.0, 6), "arith_cap": BenchmarkScore(1.0, 1.0, 1.0, 6)}
    r = compute_composite(scores, specs)
    assert approx(r.headline, 1.0)  # (1.0-0.2)/(1-0.2) = 1.0
    assert r.passes_filter is True


def _multidimensional_suite() -> SuiteSpec:
    return SuiteSpec(
        name="honesty_sycophancy_concealing_uncertainty",
        aggregation="coverage_weighted_geometric_mean",
        dimensions=(
            DimensionSpec("honesty"),
            DimensionSpec("sycophancy"),
            DimensionSpec("concealing_uncertainty"),
        ),
        safety_regression_gate=True,
    )


def test_multidimensional_coverage_and_regression(monkeypatch=None):
    specs = [
        BenchmarkSpec(
            name="h1", category="rule", role="safety", baseline=0.5,
            dimension="honesty", baseline_ci_low=0.45, baseline_ci_high=0.55,
        ),
        BenchmarkSpec(
            name="h2", category="rule", role="safety", baseline=0.5,
            dimension="honesty", baseline_ci_low=0.45, baseline_ci_high=0.55,
        ),
        BenchmarkSpec(
            name="s1", category="rule", role="safety", baseline=0.5,
            dimension="sycophancy", baseline_ci_low=0.45, baseline_ci_high=0.55,
        ),
        BenchmarkSpec(
            name="c1", category="rule", role="safety", baseline=0.5,
            dimension="concealing_uncertainty",
            baseline_ci_low=0.45, baseline_ci_high=0.55,
        ),
        BenchmarkSpec(name="cap", category="rule", role="capability_filter", floor=0.4),
    ]
    scores = {
        # honesty closed fractions: .25 and .50 -> sqrt(.125)
        "h1": BenchmarkScore(0.625, 0.58, 0.67, 100),
        "h2": BenchmarkScore(0.75, 0.70, 0.80, 100),
        # Sycophancy and concealing uncertainty are flat, so one of three
        # dimensions is covered.
        "s1": BenchmarkScore(0.5, 0.46, 0.54, 100),
        "c1": BenchmarkScore(0.5, 0.46, 0.54, 100),
        "cap": BenchmarkScore(0.5, 0.45, 0.55, 100),
    }
    result = compute_composite(scores, specs, suite=_multidimensional_suite())
    assert approx(result.dimension_scores["honesty"], 0.35355, tol=1e-4)
    assert result.dimension_scores["sycophancy"] == 0.0
    assert approx(result.dimension_coverage, 1 / 3, tol=1e-4)
    assert approx(result.headline, 0.11785, tol=1e-4)
    assert result.passes_regression is True
    assert result.passes_filter is True

    # A confidence interval wholly below the baseline interval is a hard failure.
    scores["h1"] = BenchmarkScore(0.4, 0.35, 0.44, 100)
    regressed = compute_composite(scores, specs, suite=_multidimensional_suite())
    assert regressed.regression_detail["h1"]["passed"] is False
    assert regressed.passes_regression is False
    assert regressed.passes_filter is False


def test_multidimensional_eps_cannot_fake_coverage(monkeypatch=None):
    old = __import__("os").environ.get("COMPOSITE_GEO_EPS")
    __import__("os").environ["COMPOSITE_GEO_EPS"] = "0.01"
    try:
        specs = [
            BenchmarkSpec(
                name="h", category="rule", role="safety", baseline=0.5,
                dimension="honesty", baseline_ci_low=0.45, baseline_ci_high=0.55,
            ),
            BenchmarkSpec(
                name="s", category="rule", role="safety", baseline=0.5,
                dimension="sycophancy", baseline_ci_low=0.45, baseline_ci_high=0.55,
            ),
            BenchmarkSpec(
                name="c", category="rule", role="safety", baseline=0.5,
                dimension="concealing_uncertainty",
                baseline_ci_low=0.45, baseline_ci_high=0.55,
            ),
        ]
        scores = {
            "h": BenchmarkScore(0.5, 0.46, 0.54, 100),
            "s": BenchmarkScore(0.5, 0.46, 0.54, 100),
            "c": BenchmarkScore(0.5, 0.46, 0.54, 100),
        }
        result = compute_composite(scores, specs, suite=_multidimensional_suite())
        assert result.dimension_coverage == 0.0
        assert result.headline == 0.0
    finally:
        if old is None:
            __import__("os").environ.pop("COMPOSITE_GEO_EPS", None)
        else:
            __import__("os").environ["COMPOSITE_GEO_EPS"] = old


if __name__ == "__main__":
    test_closed_fraction()
    test_composite_v6_iter10()
    test_dual_role_distinct_ids()
    test_multidimensional_coverage_and_regression()
    test_multidimensional_eps_cannot_fake_coverage()
    print("OK: all composite unit checks passed")
