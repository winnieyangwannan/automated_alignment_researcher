## Complete Run 12 lifecycle

```text
Run 12 campaign: five independent chains
│
├─ Pre-run preparation
│  ├─ Validate code/configuration and reused baseline
│  ├─ Verify researcher Kimi endpoint
│  ├─ Verify dedicated AutoData Kimi endpoint
│  ├─ Launch one initial base-Gemma target per chain
│  ├─ Publish evaluator-only holdout
│  └─ Launch one persistent evaluator per chain
│
└─ Each chain: target five successful AAR iterations
   │
   └─ AAR iteration i
      │
      ├─ 1. Prepare current target
      │  ├─ iteration 1: fixed base Gemma
      │  └─ later: fixed base + previous promoted adapter
      │
      ├─ 2. Start one CPU research session
      │
      ├─ 3. Research and method authoring
      │  ├─ Read existing literature summaries
      │  ├─ Inspect reviewed AutoData recipe
      │  ├─ Select method
      │  ├─ Copy candidate scaffold
      │  ├─ Write run.py
      │  └─ Validate method contract
      │
      ├─ 4. Proposal review
      │  ├─ Data-policy review
      │  ├─ Paper/code faithfulness and reproducibility review
      │  └─ Blind-forecasting leakage review
      │
      ├─ 5. AutoData workspace authoring
      │  ├─ Create proposal-bound workspace
      │  ├─ Build fixed grounding: 64 tuning + 32 validation + 32 test
      │  ├─ Check protected pipeline
      │  ├─ Run two-task authoring dry run
      │  └─ Approve grounding, baseline and resources
      │
      ├─ 6. AutoData meta-optimization
      │  ├─ Generate baseline using current strategy
      │  ├─ Evaluate candidate strategy
      │  ├─ Revise generation_strategy.json
      │  ├─ Repeat for exactly three meta-iterations
      │  ├─ Compare quality + target challenge
      │  └─ Finalize and export the winning pipeline
      │
      ├─ 7. AutoData production generation
      │  ├─ Build 1,250 fresh source tasks
      │  ├─ Run Kimi → Gemma target → Luna
      │  ├─ Require 1,000 accepted rows
      │  ├─ Retry deficient tasks once
      │  └─ Verify and publish the training handoff
      │
      ├─ 8. Training
      │  ├─ Revalidate method and AutoData handoff
      │  ├─ Run one-step GPU smoke
      │  ├─ Train the candidate adapter
      │  ├─ Verify consumption receipt
      │  └─ Submit adapter to evaluation queue
      │
      ├─ 9. Evaluation
      │  ├─ Merge fixed base + candidate adapter
      │  ├─ Serve merged Gemma through vLLM
      │  ├─ Run the locked multidimensional suite
      │  └─ Publish held-out-safe score
      │
      ├─ 10. Result publication
      │  ├─ Researcher reads score
      │  └─ share_finding publishes the result
      │
      └─ 11. Promotion
         ├─ Count score + result as one successful AAR iteration
         ├─ Select incumbent
         ├─ Deploy base + promoted adapter for the next iteration
         └─ Retire the previous target endpoint
```

## Timeout map

Run 12 has several independent clocks. They do not all measure the same
process, and the 30-minute researcher-turn limit does not impose a 30-minute
limit on an AAR iteration.

```text
Run 12 chain controller: 7 days
│
├─ Before each iteration: prepare and verify the Gemma target
│  └─ endpoint readiness polling: at most 40 minutes
│
└─ One research-session attempt: 72.5-hour Slurm allocation
   ├─ internal research-loop runtime target: 72 hours
   ├─ Kimi researcher turns: at most 30 minutes each
   ├─ trusted AutoData supervisor
   │  ├─ workspace authoring: 30 minutes native
   │  ├─ meta-optimization: 1 hour 45 minutes native / 2 hours hard
   │  └─ production: 7 hours 50 minutes native / 8 hours hard
   └─ coordinate separate GPU jobs
      ├─ training job: 2 hours after allocation
      └─ combined train-to-score wait: 6 hours after submission
```

### Research-session job: 72.5 hours

This is the CPU Slurm job started at lifecycle stage 2. It hosts the AAR
research controller, Kimi Code process, local AutoData broker, and AutoData
lifecycle supervisor. It coordinates stages 2 through 10, ending after
`share_finding` succeeds or the attempt fails.

Training and evaluation do not execute on this CPU allocation. They use
separate GPU Slurm jobs, while the research session waits for their durable
score or failure marker.

The 72.5-hour value is the scheduler's hard allocation limit. When it expires,
Slurm terminates the research-session job and its node-local processes. Durable
method files, proposal markers, AutoData artifacts, and retained SQLite state
remain available for a controller retry.

### Internal research-session runtime target: 72 hours

The AAR loop receives a 72-hour runtime target, leaving 30 minutes between that
target and the 72.5-hour Slurm limit for normal completion and cleanup. This is
a loop-level stop check, not a reliable interrupt for a currently running Kimi
session. The 72.5-hour Slurm allocation is therefore the actual hard backstop.

Run 12 permits at most eight research-session attempts across the five required
successful score/result pairs. An attempt that produces no pair does not count
as a completed AAR iteration; the chain controller retries the same logical
iteration using retained state.

### Target endpoint readiness: 40 minutes

This belongs to lifecycle stage 1, before the CPU research session starts:

- Iteration 1 waits for that chain's fixed-base Gemma endpoint.
- Later iterations select the promoted adapter, use the verified merged
  `base + adapter` checkpoint, launch the next chain-specific endpoint, and
  wait for it to serve a real test completion.
- The controller polls up to 160 times at 15-second intervals, giving a
  40-minute readiness ceiling per deployment.

If the endpoint does not become healthy and identity-verified within that
window, the next research session is not started. This limit does not consume
the session's 72.5-hour allocation because endpoint preparation occurs in the
chain controller first.

### Kimi researcher turn: 30 minutes

One turn is one Kimi Code subprocess invocation. A turn may reason, read files,
and make tool calls, but it is terminated if it remains active for more than
1,800 seconds. The same research session can then invoke Kimi again with
`--continue`; Run 12 allows an initial turn plus at most 96 continuations.

The following state survives a turn timeout:

- files already written by the researcher;
- approved proposal and training-submission receipts;
- native AutoData workspace and execution IDs;
- retained AutoData SQLite snapshots and artifacts;
- the Kimi session state used by `--continue` while the research job remains
  alive.

A turn timeout therefore does not cancel a running AutoData execution. The
trusted AutoData supervisor is a separate process and continues until it needs
a researcher action, completes, or reaches its own timeout.

### What if literature review takes longer than 30 minutes?

Literature review is a stage, not one indivisible turn. Run 12 normally reads
the prebuilt literature summaries once and permits at most one focused
follow-up. If a Kimi literature-review turn reaches 30 minutes:

1. The controller terminates that Kimi process group.
2. It starts a continuation turn in the same research session.
3. The continuation retains completed reads, tool results, and files and
   proceeds to method selection.

The literature lookup is read-only, so repeating an interrupted lookup is safe.
If repeated timeouts exhaust all 96 continuations, the research-session attempt
fails. The chain controller may retry the logical AAR iteration, subject to the
chain-wide eight-attempt limit. A single literature call consistently requiring
more than 30 minutes should be treated as a hung service or infrastructure
failure, not as normal literature research.

### Proposal and approval operations

- Local method-contract validation: 60 seconds.
- Proposal review: three integrity reviews run in parallel.
- One integrity-monitor request: 150 seconds per attempt, with up to six total
  Model API attempts and backoff.
- One native AutoData approval CLI operation: 120 seconds.
- The enclosing Kimi turn still has its 30-minute hard limit.

### AutoData task and phase limits

- Workspace authoring: 1,800 seconds native; 7,200-second supervisor ceiling;
  20-minute no-progress watchdog.
- Meta-optimization: 6,300 seconds native; 7,200-second supervisor ceiling;
  20-minute no-progress watchdog; exactly three meta-iterations.
- Production: 28,200 seconds native; 28,800-second supervisor ceiling;
  30-minute no-progress watchdog.
- One scenario task process: 600 seconds.
- One recipe check: 30 seconds.
- One Kimi, Gemma, or Luna request attempt: 90 seconds.
- One model request: at most three attempts.
- Target-feedback generation: at most five rounds, still enclosed by the
  600-second task limit.

The full run and Canary 2 both use 1,250 source tasks and require 1,000 accepted
rows. The full run currently uses concurrency eight per chain; Canary 2 tests
concurrency 32 on one chain, then consumes the verified handoff in exactly one
real GPU optimizer step before stopping without evaluation.

### Training and evaluation limits

- Training-submission wrapper: 120 seconds.
- Method validation inside submission: 60 seconds.
- Training GPU job: two hours after Slurm allocation. Pending queue time does
  not consume those two hours.
- Research-side wait from training submission to score or failure: six hours.
  This includes training queue time, training, adapter merge, vLLM startup, and
  evaluation.
- Evaluator GPU job: seven days, with an idle exit after approximately six days
  23 hours 50 minutes.
- Per-candidate evaluation currently has no independent hard timeout. The
  six-hour research-side score wait is the practical candidate deadline.

If the six-hour score wait expires, that research-session attempt fails even if
the evaluator remains alive. A later controller retry can recover a score that
was published after the earlier session stopped.

### Limits that are not timeouts

These can stop work before a clock expires:

- 96 Kimi continuation turns per research session;
- eight research-session attempts per five-iteration chain;
- three AutoData meta-iterations;
- five target-feedback rounds per scenario;
- the provider-accounting budget;
- the accepted-row and successful-task thresholds;
- proposal, provenance, rubric, and target-challenge acceptance gates.
