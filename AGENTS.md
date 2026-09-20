# Repository Guidelines

## Project Structure & Module Organization

`aar/` contains the main Python package. Benchmark implementations live in `aar/benchmarks/`, evaluation code in `aar/eval_pod/`, orchestration in `aar/research_loop/`, and infrastructure adapters in `aar/infrastructure/`. The Flask/React dashboard is under `aar/web_ui/`, with frontend code in `aar/web_ui/frontend/src/`. Use `generic_aar/` as the task-agnostic example and template. Tests belong in `tests/`; benchmark baselines and explanations belong in `benchmark_docs/`; reusable operational utilities belong in `scripts/`. Keep generated suites, scores, and checkpoints in the ignored `_holdout/`, `_runs/`, or `results/` directories.

## Build, Test, and Development Commands

- `uv venv && uv sync && source .venv/bin/activate`: create the Python 3.12 environment from `uv.lock`.
- `python -m aar.eval_pod.run_eval --suite configs/toy.yaml --model stub:perfect`: run the no-GPU smoke evaluation.
- `python -m aar.benchmarks.registry list`: verify benchmark discovery.
- `pytest`: run the Python test suite; target one file with `pytest tests/test_composite.py`.
- `ruff check .`: lint Python sources.
- `cd aar/web_ui/frontend && npm install && npm start`: launch the React development server; use `npm run build` for a production bundle.
- `python run.py server`: start the local orchestrator and dashboard backend.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for Python functions/modules, `PascalCase` for classes and React components, and uppercase names for environment variables. Add type hints to public Python interfaces and keep benchmark-specific logic within its benchmark package. Follow Ruff defaults and existing import ordering. Prefer repository-relative paths and configuration through `aar/config.py` or environment variables rather than machine-specific constants.

## Testing Guidelines

Pytest is the primary test framework. Name files `test_*.py` and tests `test_*`; keep unit fixtures deterministic. Changes to scoring or benchmark registration should include focused unit coverage plus the stub smoke test. GPU- or API-backed evaluation is not required for ordinary unit changes; document it when performed.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries, optionally scoped (`README: add arXiv paper link`). Keep each commit focused. Pull requests should explain the behavior change, list validation commands, note configuration or benchmark-baseline effects, and link relevant issues. Include screenshots for dashboard changes.

## Security & Evaluation Isolation

Copy `.env.example` to `.env`; never commit credentials. Preserve the research/evaluator boundary described in `ISOLATION.md`: held-out items and full held-out scores must remain evaluator-only and must not leak into research-readable outputs.
