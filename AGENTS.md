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

### Devserver and FAIR HPC workflow

- Work on branch `uv` in both environments. The authoritative editing and source-control worktree is
  `/home/winnieyangwn/aar-worktrees/uv` on the devserver. The execution worktree is
  `/storage/home/winnieyangwn/aar-worktrees/uv` on FAIR HPC.
- Use `fair-cw-use2-1` as the default HPC cluster for this project unless the user specifies another cluster.
- Before editing or running, verify the checkout path and confirm `git branch --show-current` prints `uv`. Do not
  edit, stage, or commit repository work in the `main` worktree unless the user explicitly requests it; it may contain
  unrelated work in progress.
- Make focused changes and commits in the devserver `uv` worktree, then synchronize the exact commit to the HPC `uv`
  worktree through direct Git-over-SSH using the `git-sync-from-dev-to-hpc` skill. Require a fast-forward and preserve
  all HPC-local ignored state. Do not assume the filesystems are shared, copy working-tree files directly, or push to
  GitHub unless the user explicitly requests it.
- Record experiment decisions and conversation notes under `experiments/<YYYYMMDD>/` in the devserver `uv` worktree,
  commit them on `uv`, and synchronize them to the HPC `uv` worktree. Do not maintain the canonical log on `main`.
- Maintain a separate Python environment on each cluster architecture. Do not copy environments between the
  x86_64 devserver and ARM64 GB300 clusters.
- When a project's environment includes GPU or CUDA dependencies, first obtain a Slurm allocation on the intended
  GPU partition/node, verify the host architecture and CUDA/toolkit compatibility, and create or sync the environment
  on that compute node—not on a login node or by copying an environment across architectures. Before treating the
  installation as complete, verify that PyTorch is CUDA-enabled, `torch.cuda.is_available()` is true, and the intended
  GPU is visible. This does not apply to CPU-only environments.
- Use cluster login nodes for lightweight orchestration only. Submit compute-heavy work through `sbatch` or `srun`.
- Keep source code and environments under `~/`. Put write-heavy checkpoints and experiment artifacts under the
  appropriate `/checkpoint/<project>` directory.
- Commit reproducible environment definitions and job scripts. Do not commit installed environments, generated
  datasets, ephemeral endpoint hostnames, credentials, secrets, or run outputs.
- Keep small smoke-test outputs in the repository's ignored `**/run/` directories on the cluster. Put substantial,
  write-heavy, or long-lived results under the appropriate `/checkpoint/<project>` directory or approved artifact
  store; do not use Git as an artifact store.
- Preserve reproducibility metadata with every retained run: the Git commit, configuration, seed, dataset/source
  revisions and hashes, model identity, and relevant environment or dependency lock.
- Regenerate reproducible public data from its preparation script instead of synchronizing generated copies. Inspect
  cluster results in place when practical; move results across environments only with approved FAIR transfer tools
  appropriate to the data classification.
- Do not delete or overwrite retained datasets, checkpoints, logs, or run results without explicit user approval.

### HPC `uv` execution worktree

- The HPC branch is `uv`, checked out at `/storage/home/winnieyangwn/aar-worktrees/uv` on `fair-cw-use2-1`.
- Before working there, run `git branch --show-current` and confirm it prints `uv`, then run
  `source .venv/bin/activate` and export `PYTHONPATH="$PWD"`, `AAR_BENCHMARK_DOCS="$PWD/benchmark_docs"`, and
  `BENCHMARK_DOCS_DIR="$PWD/benchmark_docs"`.
- The ARM64 `uv` executable is `/storage/home/winnieyangwn/envs/aar-uv-bootstrap/bin/uv`. Run locked environment
  updates from the worktree with that executable and `uv sync --frozen`.
- Known ARM64 packaging issue: `nvidia-cusparselt-cu13==0.8.1` contains an ARM64 library but declares the internal
  wheel tag `manylinux2014_sbsa`, so `uv pip check` and `uv sync --check` report it as incompatible. Pending an
  upstream or reproducibly repacked wheel, tolerate only this exact warning and require successful imports, CUDA
  computation, and representative target-model generation before a full evaluation. Stop on any additional error.
- Keep the HPC `.venv` and `.env` local to the HPC worktree. Sync source files and documentation through Git; never
  copy an installed environment between the devserver and HPC.
