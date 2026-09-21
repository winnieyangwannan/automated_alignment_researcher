# Literature Review Launch Guide

This standalone job creates the shared literature baseline for one safety axis before the AAR
research loop begins. It does **not** launch the AAR loop. The launcher is
`scripts/litreview.sh`, which runs `aar.litreview.run_litreview`.

The librarian surveys four areas sequentially: general methods, axis-specific work, mechanisms
and measurement, and recent related work. The requested entry count is a minimum, not a cap.

## Preflight and launch

Run on `fair-cw-use2-1`, from the HPC `uv` worktree:

```bash
ssh fair-cw-use2-1
cd /storage/home/winnieyangwn/aar-worktrees/uv
git branch --show-current  # must print: uv

source .venv/bin/activate
export PYTHONPATH="$PWD"
export AAR_BENCHMARK_DOCS="$PWD/benchmark_docs"
export BENCHMARK_DOCS_DIR="$PWD/benchmark_docs"

test -x .venv/bin/python
test -x scripts/aar-paper-search
command -v claude
```

Check whether this axis already has entries:

```bash
find _runs/litreview/sycophancy -maxdepth 1 -type f -name '*.json' | wc -l
```

The default output is shared by all teams on that axis. Rerunning the job adds to the existing
directory; do not delete or overwrite retained results without user approval.

Launch:

```bash
sbatch scripts/litreview.sh sycophancy syco-lit-v2 30
```

Arguments are `<suite> <team_id> [minimum_entries]`. Record the returned job ID. The job uses
Claude Sonnet 4.6 by default through Meta's authenticated Claude CLI and secure-internet mode; it
does not require a direct Anthropic key or a local GPU.

## Monitor from the devserver

The `/storage/...` paths exist only on HPC, so use SSH:

```bash
ssh fair-cw-use2-1 \
  'sacct -j <JOB_ID> --format=JobID,State,Elapsed,Timelimit,ExitCode,NodeList'

ssh fair-cw-use2-1 \
  'tail -F /storage/home/winnieyangwn/aar-worktrees/uv/slurm-aar-litreview-<JOB_ID>.out'

ssh fair-cw-use2-1 \
  'find /storage/home/winnieyangwn/aar-worktrees/uv/_runs/litreview/sycophancy -maxdepth 1 -type f -name "*.json" | wc -l'
```

Artifacts are written to:

```text
/storage/home/winnieyangwn/aar-worktrees/uv/_runs/litreview/<suite>/
```

The Slurm log is written to the worktree root as
`slurm-aar-litreview-<JOB_ID>.out`.

## Confirm completion

Do not treat reaching the minimum count as completion. The job finishes all four survey phases.
A successful run has:

- Slurm state `COMPLETED` and exit code `0:0`.
- `[litreview] DONE — ...` in the log.
- `[litreview] valid unique entries: ...` and `=== DONE ===` in the log.
- At least the requested number of valid JSON files.

Check the final markers:

```bash
ssh fair-cw-use2-1 \
  'grep -E "\[litreview\] DONE|valid unique entries|=== DONE ===|agent error|Traceback" /storage/home/winnieyangwn/aar-worktrees/uv/slurm-aar-litreview-<JOB_ID>.out'
```

Validate the JSON files on HPC:

```bash
cd /storage/home/winnieyangwn/aar-worktrees/uv
.venv/bin/python -c 'import glob,json; p=glob.glob("_runs/litreview/sycophancy/*.json"); [json.load(open(x)) for x in p]; print(f"parsed {len(p)} JSON files")'
```

## Lessons from the first production run

Job `1516206` completed successfully in 45:45 and produced 40 valid entries for a minimum of 30.
The important operational lessons were:

- A count at or above the minimum does not mean the job has finished; wait for the final markers.
- An empty `_runs/litreview/workspaces/<team_id>/` directory is normal; the JSONs are in the
  axis-level directory.
- `Failed to publish enter-jail outcome counter` was harmless launcher telemetry in this run as
  long as the librarian continued making progress.
- `_runs/` contents and Slurm logs are HPC-local artifacts and should not be committed to Git.
