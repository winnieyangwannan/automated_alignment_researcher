# Literature Review Launch Guide (FAIR HPC)

This guide is for a Codex agent launching the standalone literature-review pre-phase on
`fair-cw-use2-1`. The job builds a structured, axis-level literature baseline before an
Automated Alignment Researcher (AAR) team starts iterating. It does **not** launch the AAR
research/evaluation chain.

The resulting entries are shared by all AAR teams working on the same safety axis. During an
AAR run, researchers can read this baseline through `get_literature` and can add separate,
team-specific notes to their own team literature directory.

## Source of truth

- Slurm launcher: `scripts/litreview.sh`
- Python entry point: `python -m aar.litreview.run_litreview`
- Restricted paper helper: `scripts/aar-paper-search`
- Paper-helper implementation: `aar/litreview/paper_search.py`

Read the current versions of these files before launching. This guide records the working
configuration as of 2026-09-21, but the code is authoritative if it later changes.

## What one launch does

`run_litreview.py` runs four librarian sessions sequentially so that rate limits and logs remain
manageable:

1. `general`: model-agnostic safety post-training methods.
2. `axis-specific`: papers, datasets, benchmarks, and mitigations for the selected axis.
3. `mechanism`: causes, measurements, metrics, and evaluation pitfalls.
4. `recent`: recent and adjacent work such as honesty, calibration, critique, and relevant
   tradeoffs.

Each session aims to contribute approximately nine structured entries. The requested minimum is
a **lower bound**, not a maximum. All four planned sessions run before the final count check, so a
request for 30 entries may produce roughly 36-40 entries. If the count is still below the minimum,
the program makes a limited number of top-up attempts.

The default librarian model is `claude-sonnet-4-6`. On FAIR HPC, the launcher auto-detects Meta's
authenticated Claude CLI, enables secure-internet mode, and uses the restricted arXiv search/fetch
helper. A direct `ANTHROPIC_API_KEY` is not required for this Meta path. The launcher removes
unrelated model and Hugging Face credentials from the internet-enabled child process.

## Arguments and output locations

The launcher syntax is:

```bash
sbatch scripts/litreview.sh <suite> <team_id> [minimum_entries]
```

- `<suite>` is the safety axis, for example `sycophancy`.
- `<team_id>` is a unique operational label used for this launch's workspace, for example
  `syco-lit-v2`. It does not change the default axis-level artifact directory.
- `[minimum_entries]` defaults to `30` and must be a non-negative integer.

When submitted from the HPC `uv` worktree, the default locations are:

```text
Literature JSONs: /storage/home/winnieyangwn/aar-worktrees/uv/_runs/litreview/<suite>/
Workspace:        /storage/home/winnieyangwn/aar-worktrees/uv/_runs/litreview/workspaces/<team_id>/
Slurm log:        /storage/home/winnieyangwn/aar-worktrees/uv/slurm-aar-litreview-<job_id>.out
```

The workspace can be empty after a successful run. The durable run artifacts are the JSON files
in the axis directory; do not mistake the workspace for the output directory.

These `_runs/` artifacts and Slurm logs are machine-local experiment outputs, not Git source.
Inspect them on HPC and do not commit or synchronize them through Git.

## Preflight on HPC

The devserver and HPC filesystems are separate. Run all commands that mention `/storage/...`
through SSH or from an HPC shell.

Start on the devserver:

```bash
ssh fair-cw-use2-1
cd /storage/home/winnieyangwn/aar-worktrees/uv
git branch --show-current
```

Stop if the branch is not exactly `uv`. Then initialize the worktree-local environment:

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD"
export AAR_BENCHMARK_DOCS="$PWD/benchmark_docs"
export BENCHMARK_DOCS_DIR="$PWD/benchmark_docs"
```

Check the essentials without printing secrets:

```bash
test -x .venv/bin/python
test -x scripts/aar-paper-search
test -x /usr/bin/curl
command -v claude
.venv/bin/python -c 'import anthropic, aar; print("imports ok")'
squeue -u "$USER"
```

The production launcher uses the repository-local `.venv/bin/python` directly, so activation is
mainly useful for interactive checks. It loads the worktree-local `.env` without echoing it.
Never print or commit `.env`.

This job is CPU-only from the application's perspective: it calls the hosted Claude service and
does not run local model inference. The current Slurm script uses account `ram`, partition `g3`,
QOS `g3_ram_high`, four CPUs, 8 GiB RAM, and a two-hour limit; it does not request a GPU resource.
Confirm those directives still match current cluster policy before submitting.

Before rerunning an axis, inspect its output directory:

```bash
find "_runs/litreview/sycophancy" -maxdepth 1 -type f -name '*.json' | wc -l
```

The default run writes into the existing axis-level baseline. A rerun does not mean "start from
zero" and may add more entries. Do not delete or overwrite retained results without explicit user
approval. If the goal is an isolated trial, set `LITREVIEW_OUTPUT_DIR` to a new location and make
sure any downstream reader is configured to use that location.

## Launch

For the standard sycophancy baseline:

```bash
cd /storage/home/winnieyangwn/aar-worktrees/uv
sbatch scripts/litreview.sh sycophancy syco-lit-v2 30
```

Record the job ID printed by Slurm:

```text
Submitted batch job <JOB_ID>
```

Also record the Git commit, suite, team ID, minimum, model, output directory, and job ID in the
experiment log. Do not launch a duplicate merely because the output log takes a few seconds to
appear.

## Monitor from the devserver

A command such as `tail /storage/...` fails on the devserver because that path exists only on HPC.
Always wrap monitoring commands in SSH.

Check the scheduler state:

```bash
ssh fair-cw-use2-1 \
  'sacct -j <JOB_ID> --format=JobID,State,Elapsed,Timelimit,ExitCode,NodeList'
```

Follow the live log:

```bash
ssh fair-cw-use2-1 \
  'tail -F /storage/home/winnieyangwn/aar-worktrees/uv/slurm-aar-litreview-<JOB_ID>.out'
```

Count current artifacts:

```bash
ssh fair-cw-use2-1 \
  'find /storage/home/winnieyangwn/aar-worktrees/uv/_runs/litreview/sycophancy -maxdepth 1 -type f -name "*.json" | wc -l'
```

List the newest artifacts:

```bash
ssh fair-cw-use2-1 \
  'find /storage/home/winnieyangwn/aar-worktrees/uv/_runs/litreview/sycophancy -maxdepth 1 -type f -name "*.json" -printf "%TY-%Tm-%Td %TH:%TM:%TS %f\n" | sort -r | head'
```

Expected log progression is `lit-general`, `lit-axis-specific`, `lit-mechanism`, then
`lit-recent`. Lines such as `-> mcp__server-api-tools__share_literature` indicate that an entry is
being submitted. Lines showing attempted `Bash` calls are agent/tool telemetry, not by themselves
proof that a command was permitted or succeeded; Meta secure mode is intended to allow only the
tracked paper-search helper.

Reaching the requested JSON count does **not** mean the job is done. Wait for all planned phases
and the final completion markers.

## Verify successful completion

A successful run must satisfy all of the following:

1. The parent Slurm job is `COMPLETED` with `ExitCode 0:0`.
2. The log contains `[litreview] DONE — <count> entries (target <minimum>)`.
3. The log contains `[litreview] valid unique entries: <count>` and `=== DONE ===`.
4. The final valid count is at least the requested minimum.
5. All JSON artifacts parse successfully.

Check the markers and scheduler result:

```bash
ssh fair-cw-use2-1 \
  'sacct -j <JOB_ID> --noheader --parsable2 --format=JobID,State,Elapsed,ExitCode; grep -E "\[litreview\] DONE|valid unique entries|=== DONE ===|agent error|Traceback" /storage/home/winnieyangwn/aar-worktrees/uv/slurm-aar-litreview-<JOB_ID>.out'
```

Validate the JSON files on HPC:

```bash
cd /storage/home/winnieyangwn/aar-worktrees/uv
.venv/bin/python -c 'import glob,json; p=glob.glob("_runs/litreview/sycophancy/*.json"); [json.load(open(x)) for x in p]; print(f"parsed {len(p)} JSON files")'
```

Do not report success solely from `sacct`, solely from the file count, or solely from a `DONE`
line. Use the scheduler state, application markers, minimum check, and artifact parsing together.

## Troubleshooting and interpretation

- **The log file is missing on the devserver:** it is HPC-local. Use `ssh fair-cw-use2-1` and the
  absolute HPC path. Confirm the job ID and submission directory.
- **The count exceeds the requested minimum:** expected. The minimum is a floor, and each of four
  survey sessions writes a batch of entries.
- **The count has reached the minimum but the job is still running:** expected while later survey
  phases are finishing. Do not cancel it unless the user explicitly asks.
- **The workspace is empty:** this can be normal. Check `_runs/litreview/<suite>/` for JSONs.
- **`Failed to publish enter-jail outcome counter` appears:** in the successful reference run this
  launcher-telemetry warning was non-fatal. Confirm that librarian phases continue; do not blindly
  ignore it if the process stops making progress.
- **An agent phase reports an error:** the phase wrapper may continue, but the final minimum check
  can still fail. Inspect the surrounding log, final Slurm exit code, and artifact count.
- **The job is pending:** use `squeue`/`scontrol show job <JOB_ID>` to inspect scheduler reasons. Do
  not submit duplicates as a substitute for diagnosing the pending job.
- **The job times out or fails below target:** preserve the log and artifacts, diagnose the failing
  phase, and obtain user approval before resubmitting or changing retained outputs.
- **Arbitrary shell commands appear in the transcript:** secure mode logs agent attempts, while the
  permission configuration restricts execution to `scripts/aar-paper-search`. Treat an attempt as
  evidence to review, not evidence of successful unrestricted execution.

## Successful reference run

The first production run using this path was launched on 2026-09-21 as:

```bash
cd /storage/home/winnieyangwn/aar-worktrees/uv
sbatch scripts/litreview.sh sycophancy syco-lit-v1 30
```

Results:

- Slurm job: `1516206`
- Git commit: `d26e4e11b9fe988071f69c786df5747f540e3e31`
- State and exit code: `COMPLETED`, `0:0`
- Runtime: `00:45:45`
- Model and web mode: `claude-sonnet-4-6`, `meta_secure`
- Final result: 40 valid, unique JSON entries for a target of 30
- Artifact directory:
  `/storage/home/winnieyangwn/aar-worktrees/uv/_runs/litreview/sycophancy/`
- Log:
  `/storage/home/winnieyangwn/aar-worktrees/uv/slurm-aar-litreview-1516206.out`
- Fatal errors: none

This run established three operational expectations for future agents: a normal run can take
roughly 45 minutes, the final count can substantially exceed the minimum, and the only reliable
completion signal is the combination of Slurm success, final application markers, and valid
artifacts.
