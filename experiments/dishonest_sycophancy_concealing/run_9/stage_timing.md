# Run 9 stage timing and efficiency log

This file records UTC timing evidence for the successful five-result Run 9
chain, identifies bottlenecks, and separates measured improvements from
proposals. A session counts as successful only when its matching evaluator score
and result record are both retained.

## Active production attempt

- Attempt: `20261009T042010Z-9177dca332eb`
- Launch job: `1780581`
- Evaluator job: `1780609`
- Sequential chain job: `1780610`
- AAR source: `9177dca332eb2b4096cdebf35559951ba1e3ea7f`
- AutoData source: `223af462f69b2fd2d5eca6849ae3a6f5fff47d5b`
- AutoData runner: `local-bwrap`, concurrency 16
- Target: five durable score/result pairs

### Launch and Session 0 timing

| Stage                         | Start (UTC)          | End (UTC)            | Duration | Status             |
| ----------------------------- | -------------------- | -------------------- | -------- | ------------------ |
| Launcher queue                | 2026-10-09 04:20:12  | 2026-10-09 04:21:28  | 1m 16s   | Complete           |
| Launcher execution            | 2026-10-09 04:21:28  | 2026-10-09 04:22:41  | 1m 13s   | Complete           |
| Evaluator/chain queue         | 2026-10-09 04:22:30  | 2026-10-09 04:23:45  | 1m 15s   | Complete           |
| Chain/bootstrap to Session 0  | 2026-10-09 04:23:45  | 2026-10-09 04:23:57  | 12s      | Complete           |
| Session 0 research/planning   | 2026-10-09 04:23:57  | —                    | —        | Active             |
| AutoData workspace approvals  | —                    | —                    | —        | Not started        |
| AutoData meta-optimization    | —                    | —                    | —        | Not started        |
| AutoData production           | —                    | —                    | —        | Not started        |
| Tokenization/training/save    | —                    | —                    | —        | Not started        |
| Evaluation and result handoff | —                    | —                    | —        | Not started        |

The chain prebootstrapped the pinned plugin, started an authenticated loopback
broker with a node-local ledger, and verified the agent sandbox before Session 0.

## Native lifecycle preflight baseline

The retained native preflight
`native-preflight-20261009T031217Z-61257c251bb7` exercised real approvals,
meta-optimization, fixed-winner production, export, and training consumption.

| Stage                              | Cumulative end | Stage duration | Evidence                    |
| ---------------------------------- | -------------- | -------------- | --------------------------- |
| Budget preflight                   | 0.000s         | 0.000s         | Budget reservation passed   |
| Grounding approval                 | 10.905s        | 10.905s        | Signed audit retained       |
| Baseline approval                  | 32.937s        | 22.032s        | Signed audit retained       |
| Workspace frozen                   | 34.371s        | 1.434s         | Native snapshot exported    |
| Meta-optimization                  | 559.598s       | 525.227s       | Winner exported             |
| Production, export, and consumption| 963.116s       | 403.518s       | 13 accepted rows retained   |
| Final report                       | 963.123s       | 0.007s         | Report status `passed`      |

### Broker utilization inside the preflight

- Broker jobs: 76, all succeeded.
- Typical model-backed job: approximately 9 seconds; observed range was mostly
  7–12 seconds.
- First-to-last broker task span: 834 seconds.
- Time with at least one broker task active: approximately 233 seconds.
- Time with no broker task active inside that span: approximately 601 seconds,
  or 72%.
- Many job submissions appeared in groups of only one to four despite declared
  concurrency 16. Creation gaps frequently clustered near 30–31 seconds.

The model calls are therefore not the dominant preflight bottleneck. AutoData's
host controller leaves the broker idle for most of the generation interval.

## Current bottleneck hypothesis

`ExecutionEngine` evaluates tasks in a 16-thread pool. Each task thread performs
several native-state writes through a separate SQLite connection. The retained
state database is network-backed, and every transaction uses `BEGIN IMMEDIATE`
with a 30-second busy timeout. Threads therefore contend through SQLite/NFS
locking before they can submit work to the already-fast broker. The observed
30–31-second submission gaps closely match that timeout behavior.

The earlier polling fix removed repeated unchanged-state writes, but it did not
serialize the remaining legitimate writes made concurrently during task setup,
completion, budget accounting, and event recording.

## Optimization work and validation plan

### P0: serialize native SQLite writes within the AutoData process

- Add one reentrant lock around `SQLiteStateStore._write` so sibling task
  threads queue in memory instead of contending through SQLite's 30-second busy
  timeout.
- Preserve transaction order, durability, idempotency, and all native lifecycle
  semantics.
- Run the complete AutoData test suite and rebuild the deterministic bundled
  plugin wheel.
- Rerun the same native lifecycle preflight and compare stage time, task-launch
  burst size, broker active fraction, and job latency against the baseline above.

### P1: move native state to node-local storage if P0 is insufficient

Keep the hot native SQLite database under `$SLURM_TMPDIR`, checkpoint it at
phase boundaries and clean shutdown, and retain verified snapshots with the run.
This removes network-filesystem locking entirely but adds recovery and snapshot
complexity, so it should be used only if in-process serialization does not
provide sufficient improvement.

### P2: increase model-serving capacity only after controller saturation

Multiple Kimi replicas or a load-balanced endpoint can help only after AutoData
keeps 16 tasks continuously in flight. With 72% controller-side idle time,
adding endpoint capacity now would leave the new capacity unused. Once host
utilization is fixed, test concurrency 16 versus 32 while recording Kimi and
Luna latency, HTTP throttling, acceptance rate, CPU/memory pressure, and cost.

### P3: reduce attempts per accepted production row

Track judge acceptance per strategy and rejection reason. Improve the generation
prompt or winning strategy only when evidence shows a recurring quality failure.
Raising acceptance from 62.5% to 80% reduces expected attempts for 1,000 rows
from roughly 1,600 to 1,250 without increasing infrastructure concurrency.

### P4: tune request size after correctness is stable

Kimi already uses instant mode (`thinking=false`) and a 768-token output limit.
Measure actual token use before reducing generator or Luna limits. Shorter limits
can reduce latency and cost but must not truncate the structured example or judge
verdict.

## Per-session measurements to retain

For each outer AAR session, record:

- planning and proposal-approval duration;
- grounding and baseline approval duration;
- each of the three meta-optimization iterations, including task counts;
- production attempts, accepted rows, acceptance rate, broker job latency,
  active concurrency, and controller idle fraction;
- data loading, tokenization, model loading, training, and checkpoint-save time;
- training and evaluator Slurm queue time;
- vLLM startup and candidate evaluation duration;
- score/result handoff latency; and
- cumulative successful score/result-pair count.
