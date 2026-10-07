# Run 7 parallel launch

## Request and interpretation

On 2026-10-06, launch Run 7 based on Run 6 with five parallel research agents
for 50 iterations and continue monitoring while remaining available for
conversation. The iteration cap is interpreted per chain: five independent
chains with at most 50 started sessions each, or 250 sessions total.

## Launch contract

- Five research seeds: `alpha`, `beta`, `gamma`, `delta`, and `epsilon`.
- Fifty iterations per seed, with a 167.5-hour chain wall-clock limit.
- Up to five simultaneous one-GPU training jobs.
- Five evaluator jobs, each requesting four GPUs for seven days.
- Run 6's atomic shared candidate queue, merged-checkpoint vLLM 0.25.1
  evaluation, fail-closed markers, benchmark protocol, and retained baseline.
- The launch parent must retain five distinct evaluator IDs and five distinct
  chain IDs with `max_iterations_per_chain=50`.

## State and synchronization plan

- Devserver source: `/home/winnieyangwn/aar-worktrees/multi_dimensional`, branch
  `multi_vllm`, pre-change HEAD
  `67ff2cf9c028256986012193ac4a909532fe18b8`.
- HPC destination: `/storage/home/winnieyangwn/aar-worktrees/multi_vllm`, branch
  `multi_vllm`, pre-transfer HEAD
  `a03d43c2ecf425b9e45d3878efbc189a551873ec`.
- Both checkouts identify origin as
  `https://github.com/winnieyangwannan/automated_alignment_researcher.git`.
- Commit only the Run 7 launcher, documentation, and this decision record.
- Transfer the exact source commit directly over SSH to a unique temporary
  `refs/aar-sync/` ref, require ancestry and path-collision checks, then
  fast-forward the isolated HPC worktree. GitHub is not part of this transfer.
- Preserve all HPC-local ignored environments, credentials, caches, datasets,
  checkpoints, and run artifacts.
- Validate Bash syntax, ShellCheck, repository diff checks, HPC source state,
  launch prerequisites, distinct child job IDs, and fail-closed evaluator
  runtime markers.

Planned checks above are not completion claims; final synchronization and
runtime state are reported from live verification after submission.

## First training-submission recovery

The first approved Run 7 candidate exposed a `set -u` initialization bug in
`scripts/submit_train_job.sh`: when the per-team dependency-lane state file did
not yet exist, failed `mapfile` input left `_lanes` undefined before its length
was read. No Slurm job was submitted by that call. The Delta agent preserved
the generated method, created the missing state file, and then submitted job
`1742270` successfully.

Initialize `_lanes` to an empty array before the optional state-file read and
add a regression test that exercises the first concurrency-limited submission
with no pre-existing lane file. Validate the focused launch tests and Bash
syntax, commit on `multi_vllm`, then fast-forward the exact commit from the
devserver worktree to the isolated HPC worktree through a temporary SSH Git
ref. Preserve the active Run 7 attempt and all machine-local state.
