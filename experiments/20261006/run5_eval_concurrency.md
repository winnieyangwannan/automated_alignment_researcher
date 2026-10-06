# Run 5 evaluator concurrency investigation

## Request

Determine the maximum useful evaluator concurrency for the Run 5 Gemma 4
workflow, measure it on FAIR GB300, and improve candidate-evaluation latency.

## State before synchronization

- Date: 2026-10-06
- Devserver worktree: `/home/winnieyangwn/aar-worktrees/multi_dimensional`
- HPC worktree: `/storage/home/winnieyangwn/aar-worktrees/multi_vllm`
- Branch in both worktrees: `multi_vllm`
- Devserver implementation commit before this log: `2d9e884`
- HPC commit before transfer: `fb2c4ba6d3a752f459b36647aa370343ffca0947`
- Transfer method: direct Git-over-SSH temporary ref, followed by a required
  fast-forward in the isolated HPC worktree; GitHub is not part of the transfer.

## Diagnosis and change

Run 5 requested four evaluator GPUs, but `launch_eval_worker.sh` passed
`EVAL_GPUS=auto`. The vLLM container intentionally forwards evaluator variables
but not Slurm's `CUDA_VISIBLE_DEVICES`, so `_resolve_ngpu()` fell back to one.
The launcher now passes its validated numeric GPU count into the worker.

The committed benchmark harness creates a fresh mode-700 checkpoint attempt,
copies the evaluator-side suite into that isolated attempt, selects six public
non-judge benchmarks with a 64-item cap, and measures otherwise identical
one-, two-, and four-engine runs in the validated vLLM 0.25.1 container. It
uses the base Gemma checkpoint because merged candidates have the same inference
shape but can fail the generation-health gate before producing comparable timing.

## Planned checks

1. Verify source and HPC repository identities, branch names, tracked status,
   and the destination fast-forward relationship.
2. Transfer the exact committed source through a unique temporary ref, check
   incoming-path collisions, fast-forward, verify the final SHA, and remove only
   that temporary ref.
3. Run focused tests with the HPC ARM64 environment and verify the published
   Run 5 suite contains every public benchmark selected by the harness.
4. Submit the committed concurrency benchmark and retain its job ID, source
   commit, configuration, logs, and timing artifacts under `/checkpoint`.
5. Compare wall time, engine initialization, GPU visibility, failures, and
   throughput for one, two, and four engines before deciding whether a
   multi-node or persistent-server design is justified.

## Attempt history

- Job `1740756`, attempt `20261006T195938Z-e904b6b34b4d`, failed after 22
  seconds before model loading. A published held-out entry reused a requested
  public benchmark name and had no explicit ID, so the first selector rejected
  it after name matching. The follow-up selector skips all held-out entries
  before matching; requesting only a held-out ID therefore fails as a missing
  public benchmark without copying it into the throughput suite.
- Job `1740794`, attempt `20261006T200613Z-c99ff855a868`, failed after 31
  seconds before model loading. The retained published suite has no
  `sciq_uncertainty` entry, despite that stale identifier appearing in an older
  environment list. The benchmark allowlist now uses the five available
  public, non-judge entries: `llm_uncertainty_bench`, `verbalized_ece`, `mmlu`,
  `gsm8k`, and `ifeval`.
- Job `1740812`, attempt `20261006T201010Z-ec1cd95fb9bb`, confirmed that both
  the GB300 batch job and the vLLM container see four CUDA devices, then stopped
  before model loading because the ARM host lacks `/usr/bin/time`. The harness
  now uses its already-retained start and end epochs as the sole wall-clock
  measurement and has no dependency on that optional executable.
- Job `1740846`, attempt `20261006T201739Z-71765b16a053`, again confirmed four
  visible container GPUs. Its three evaluator commands stopped before model
  loading because the reduced suite retained the original honesty and
  sycophancy dimensions without any selected safety benchmark in them. The
  selector now filters the dimension list to those represented by selected
  public safety benchmarks.
