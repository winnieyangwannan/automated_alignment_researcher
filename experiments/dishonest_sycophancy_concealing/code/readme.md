# Implementation map

The implementation is in this repository worktree. Paths below are
repository-relative so the map remains valid after synchronization to HPC.

## Scoring and suite schema

- `aar/benchmarks/base.py`
- `aar/benchmarks/composite.py`
- `aar/eval_pod/run_eval.py`
- `aar/eval_pod/models.py`
- `scripts/publish_suite.py`
- `scripts/axis/honesty_sycophancy_concealing_uncertainty.env`

## Librarian

- `aar/litreview/run_litreview.py`
- `scripts/litreview.sh`
- `scripts/launch_team.sh`
- `scripts/aar_runtime_env.sh`

`LITREVIEW_CACHE_ROOT` keeps dimension caches independent of the new suite
manifest. This is the mechanism that reuses completed honesty and sycophancy
searches.

## Baselines and launch

- `replication/env_multidimensional.sh`
- `replication/baseline_concealing_multidimensional.sbatch`
- `replication/submit_concealing_multidimensional_baseline.sh`
- `replication/record_multidimensional_baseline.py`
- `replication/baseline_multidimensional.sbatch`
- `replication/submit_multidimensional_baseline.sh`
- `replication/record_composed_baseline.py`
- `replication/preflight_multidimensional.py`
- `replication/launch_multidimensional_12h.sh`
- `replication/launch_two_iteration_multidimensional.sh`
- `replication/verify_two_iteration_multidimensional.py`
- `scripts/preflight_aar.sh`

## Research-loop presentation

- `aar/research_loop/prompt_safety.jinja2`
- `aar/research_loop/agent.py`
- `aar/research_loop/tools/server_api_tools.py`
- `aar/web_ui/live_dashboard.py`
- `aar/web_ui/backend/app.py`

## Focused tests

- `tests/test_generation_budget.py`
- `tests/test_composite.py`
- `tests/test_multidimensional_literature.py`
- `tests/test_multidimensional_librarian_wiring.py`
- `tests/test_multidimensional_suite.py`
- `tests/test_multidimensional_launch.py`
- `tests/test_replication_v0.py`
- `tests/test_agent_sdk_compat.py`

The older `scripts/axis/honesty_sycophancy.env` and two-dimension suite remain
for backward compatibility; new runs must select the three-dimension axis.
