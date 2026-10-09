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

## Evaluator worker-snapshot recovery

At 01:40 UTC, the first two valid adapters merged successfully but failed
closed before vLLM startup because the configured shared deployment snapshot
`aar-gemma-4-31b-it` had been removed externally at approximately 01:35 UTC.
The Alpha and Epsilon failure JSON files and their completed merged checkpoints
remain retained. Cancel only the five evaluator jobs so later submissions wait
instead of receiving the same infrastructure failure; leave all five research
chains running.

Use the surviving `eval-gemma-4-31b-it` snapshot only after verifying its full
worker directory is readable and its `worker_vllm.sh` SHA-256 is
`913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361`, identical
to the other retained Gemma snapshots. Add a hash-pinned evaluator-only Run 7
recovery launcher that reuses the existing team queue, starts five new
four-GPU evaluators, and never removes or overwrites terminal candidate
artifacts. Fresh research iterations, not evaluator mutation, supply new run
IDs after the infrastructure failure.

## Second evaluator worker-snapshot recovery

At 06:13 UTC, Alpha's `bdpa_v1` adapter completed training and an evaluator
atomically merged it into a 13-shard, 62,546,336,448-byte checkpoint. Before
the benchmark suite started, the evaluator failed closed because the configured
`eval-gemma-4-31b-it` worker snapshot was unreadable. At 06:14 UTC that snapshot
was moved into the shared deployment root's `.removed` directory by an external
operator, so the five live evaluator jobs cannot recover through polling and
would reject every subsequent candidate at the same preflight check. Preserve
the BDPA failure JSON, submitted adapter, merged checkpoint, and evaluator log;
do not count it as a score/result pair.

The replacement snapshot
`baseline_gemma-4-31b-ib/src/serve_api_v2/worker/worker_vllm.sh` is readable,
owned by the Run 7 user, and has the already pinned SHA-256
`913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361`.
Update only Run 7's worker-snapshot path while retaining the hash gate. Cancel
only evaluator jobs `1742454` through `1742458`, submit a replacement five-job
pool through the committed evaluator-recovery launcher, and leave research jobs
`1742199` through `1742203` running.

The devserver and HPC source worktrees are both on `multi_vllm` at pre-change
commit `a483b386c28eeffd294f36daae163bd508162375`. Transfer the focused recovery
commit directly over SSH to a unique temporary `refs/aar-sync/` ref, require a
fast-forward and path-collision checks, and preserve all HPC-local ignored
state. Planned runtime checks are: five distinct replacement evaluator IDs,
the hash-pinned worker path in each evaluator environment, and the mandatory
`backend=vllm`, vLLM 0.25.1, exact merged checkpoint,
`language_model_only=True`, and `lora_strategy=merged_checkpoint` markers on
the first fresh candidate. These are planned checks, not completion claims.
