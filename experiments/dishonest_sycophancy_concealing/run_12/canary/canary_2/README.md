# Canary 2: production data-to-training

## Goal

This is a production-realistic data-to-training rehearsal using one AAR chain:

```text
Kimi AAR researcher
    → target-aware AutoData meta-optimization
    → 1,000 accepted production rows
    → verified production handoff
    → consume all 1,000 rows in one real GPU optimizer step
    → save and validate a non-empty PEFT adapter
    → stop before full training or evaluation
```

It exercises lifecycle approvals, strategy revision, challenging-row yield,
production throughput, native finalization, durable handoff verification, and
the complete data-loader-to-training boundary. It creates only a one-step smoke
adapter, does not allocate an evaluator, and does not require a score/result
pair.

Its measurement goal is to record how long every AutoData lifecycle stage
takes without imposing an elapsed-time deadline on workspace authoring,
meta-optimization, or production. A pass must publish
`autodata-lifecycle-timing.json` with end-to-end and per-stage durations,
per-action timing, per-task-phase latency and throughput, accepted-row
throughput, provider call counts, and retry/rate-limit signals. The pass marker
must also identify the training phase-timing artifact.

It uses the checked-in `target-aware-local-c32-v1` runtime profile, so this one
chain runs at concurrency 32. Run 9 sustained this setting for 256 target-aware
tasks; Canary 2 must confirm it with Run 12's actual endpoints and lifecycle.
This does not pre-authorize five chains at 32 each.

The capacity decision is an explicit Canary 2 outcome. Review per-phase task
wall time, effective throughput, long-tail latency, model/parse failures,
timeouts, resets, HTTP 429/rate-limit evidence, and provider completion counts.
Use that evidence to choose the full run's per-chain concurrency while treating
five chains as aggregate load (for example, 32 each would mean 160 tasks in
flight). Do not infer the five-chain setting from the single-chain pass alone.

## YAML control

Each Canary 2 trial has its own strict YAML. The active configuration is
[`trial_2/autodata_run.yaml`](trial_2/autodata_run.yaml). These checked-in
fields define its boundary independently from the full-run configuration:

```yaml
schema: aar.autodata.run-config/v1
runtime_profile: configs/autodata/target_aware_local_c32_v1.yaml
bootstrap_canary:
  stop_after: training_smoke
authoring:
  max_wall_seconds: 604800
stage_timing:
  mode: observe_only
  native_schema_wall_seconds: 604800
production:
  required_rows: 1000
  initial_tasks: 1250
```

The repository-relative `runtime_profile` reference is authoritative. The
shared launcher resolves it from this YAML, and the compiler rejects a
conflicting shell-supplied profile. `trial_2/submit_canary.sh` therefore selects
only the Trial 2 run YAML; it no longer selects the `c32` profile itself.

`observe_only` disables supervisor elapsed-stage deadlines. Native AutoData
requires a positive `max_wall_seconds` in its schema, so the YAML supplies
604,800 seconds—the same as the outer seven-day controller envelope. That value
is a compatibility sentinel, not a useful stage budget: the surrounding Run 12
job/session envelope ends first. Healthy authoring, meta-optimization, and
production are therefore measured rather than terminated for total duration.

`initial_tasks` is the configurable number of distinct source scenarios written
to the production manifest—not the number of accepted training rows. Canary 2
attempts 1,250 source tasks because Kimi/Gemma/Luna may reject some examples and
requires at least 1,000 accepted rows. The value is fixed after compilation and
launch: a running 1,250-task execution cannot append task 1,251. Native AutoData
may retry deficient tasks once, but it does not append new source tasks
dynamically. If those tasks do not yield 1,000 accepted rows, the canary fails
and preserves the evidence; it never weakens the judge or treats an unenforced
expansion ceiling as policy.
`source_tasks` would be a clearer future field name because `initial_tasks`
incorrectly suggests that this implementation can expand the corpus later.

On success, `autodata-lifecycle-timing.json` records workspace authoring,
meta-optimization, production, per-action, and per-task-phase wall times from
the native SQLite timestamps. The completion marker embeds the same report and
the one-step training job ID, exact consumed-row count, consumption receipt,
training phase timings, adapter identity, and adapter-weight hash.

## Timeout map

The researcher and the trusted AutoData supervisor are separate processes. A
researcher turn can expire and be resumed while the same registered AutoData
subject continues. Canary 2 does not impose total elapsed-time deadlines on
the three AutoData stages.

```text
Canary 2 campaign: one chain, one data-to-training lifecycle rehearsal
│
├─ Pre-run preparation
│  ├─ Validate code/configuration and reused baseline
│  │  └─ no independent timeout; must finish before submission
│  ├─ Verify researcher Kimi endpoint
│  │  └─ at most 420 s outer / 180 s internal health check
│  ├─ Verify dedicated AutoData Kimi endpoint
│  │  └─ must be ready before launch; each later request attempt ≤ 90 s
│  ├─ Launch the initial fixed-base Gemma target
│  │  └─ readiness and identity polling ≤ 40 min
│  ├─ Evaluator-only holdout
│  │  └─ not published for this training-smoke canary
│  └─ Persistent evaluator
│     └─ not launched for this data-to-training canary
│
└─ One partial AAR lifecycle attempt
   │  overall CPU research session: ≤ 72 h internal / 72.5 h Slurm hard limit
   │  Canary 2 permits at most two research-session attempts
   │
   ├─ 1. Prepare current target
   │  ├─ target: fixed base Gemma
   │  └─ readiness and identity polling ≤ 40 min before the session
   │
   ├─ 2. Start one CPU research session
   │  ├─ internal research-loop target ≤ 72 h
   │  └─ Slurm allocation hard limit ≤ 72.5 h
   │
   ├─ 3. Research and method authoring
   │  ├─ each Kimi researcher turn ≤ 30 min
   │  ├─ initial turn + at most 96 resumable continuation turns
   │  ├─ read existing literature summaries
   │  ├─ inspect recipe, select method, copy scaffold and write run.py
   │  └─ validate method contract ≤ 60 s
   │
   ├─ 4. Proposal review
   │  ├─ three integrity reviews run in parallel
   │  ├─ each monitor request attempt ≤ 150 s; at most six attempts
   │  └─ enclosing Kimi researcher turn still ≤ 30 min
   │
   ├─ 5. AutoData workspace authoring
   │  ├─ no elapsed stage deadline; measure actual duration
   │  ├─ native schema sentinel: 7 d, beyond the session envelope
   │  ├─ no-progress watchdog: 20 min
   │  ├─ build fixed grounding: 64 tuning + 32 validation + 32 test
   │  ├─ recipe check ≤ 30 s
   │  ├─ two-task authoring dry run: each task process ≤ 10 min
   │  └─ each native approval CLI operation ≤ 120 s
   │
   ├─ 6. AutoData meta-optimization
   │  ├─ exactly three meta-iterations at concurrency 32
   │  ├─ no elapsed stage deadline; measure actual duration
   │  ├─ native schema sentinel: 7 d, beyond the session envelope
   │  ├─ no-progress watchdog: 20 min
   │  ├─ each scenario task process ≤ 10 min
   │  ├─ each Kimi, Gemma or Luna request attempt ≤ 90 s
   │  ├─ each model request may make at most three attempts
   │  └─ target-feedback loop ≤ five rounds within the 10 min task limit
   │
   ├─ 7. AutoData production generation
   │  ├─ 1,250 fresh source tasks at concurrency 32
   │  ├─ require 1,000 accepted rows and ≥ 95% successful tasks
   │  ├─ retry deficient tasks once
   │  ├─ no elapsed stage deadline; measure actual duration
   │  ├─ native schema sentinel: 7 d, beyond the session envelope
   │  ├─ no-progress watchdog: 30 min
   │  ├─ each scenario task process ≤ 10 min
   │  ├─ each Kimi, Gemma or Luna request attempt ≤ 90 s
   │  └─ verify and publish the training-data handoff
   │
   ├─ 8. One-step training smoke
   │  ├─ load all 1,000 verified rows through the contracted dataset loader
   │  ├─ write and verify the exact consumption receipt
   │  ├─ use at most eight examples for exactly one optimizer step
   │  ├─ save and validate a non-empty loadable PEFT adapter
   │  └─ training Slurm allocation hard limit ≤ 2 h
   │
   └─ STOP after the verified training-smoke marker
      ├─ full training: not run
      ├─ 9. Evaluation: not run; no evaluator is allocated
      ├─ 10. Result publication: not run
      └─ 11. Promotion: not run; this does not count as an AAR score/result pair
```

The remaining limits isolate failed operations; they are not total stage
budgets. Parallel work normally finishes much sooner. Canary 2's
experiment-specific values come from its own `autodata_run.yaml`; shared task,
provider, and local-runner limits come from the referenced
`target-aware-local-c32-v1` runtime profile and protected AutoData pipeline.

- **Researcher turn — 1,800 seconds:** one launched Kimi Code AAR researcher
  process using `aar_8-kimi26`. This is neither one AutoData generator call nor
  the entire lifecycle. If it expires, retained native state can be resumed by
  a later researcher turn.
- **AutoData stages — observe only:** workspace authoring, meta-optimization,
  and production have no supervisor elapsed-time deadline. Their native
  seven-day schema value is outside the effective per-session envelope.
- **Task process — 600 seconds:** one scenario's whole recipe invocation in
  authoring, meta-optimization, or production. It includes all Kimi generation,
  Gemma probing, Luna judgment, feedback rounds, parsing, and output writing.
- **Recipe check — 30 seconds:** one local `recipe/check.py` validation. It does
  not call Kimi, Gemma, or Luna.
- **Model HTTP attempt — 90 seconds:** one request to Kimi, Gemma, or Luna. A
  request may be tried at most three times. Target feedback may run as many as
  five generation/probe/judge rounds, but the enclosing task still has the
  600-second hard limit.
- **No-progress watchdogs — 20/30 minutes:** authoring and meta retain a
  20-minute liveness watchdog; production retains 30 minutes. These clocks
  reset whenever native SQLite state changes, so they do not cap a progressing
  stage.

The outer Run 12 scheduler envelopes are safety ceilings rather than generation
budgets: the launch job has two hours, the chain controller has seven days, an
individual chain session is submitted for up to 72.5 hours, and the one-step
training job has a two-hour allocation after scheduling. Canary 2 stops after
the verified training-smoke marker; evaluation timeouts do not apply.

The lifecycle timing artifact aggregates task wall time, median and p95 latency,
throughput, accepted-row throughput, completed calls by provider, and retry
signals by provider (HTTP 429/rate limit, timeout, and connection reset). This
is the evidence used to choose the full five-chain concurrency.

The strict compiler freezes the values into the resolved configuration,
training-data contract, and runtime environment. Trusted host code only marks
the canary complete after read-only verification of the native
meta-to-production lineage, at least 1,000 accepted rows, exact 1,000-row
training consumption, one optimizer step, and a non-empty adapter. The pipeline
launches no evaluator. Full mode rejects an inherited canary stop boundary.

## Launch

From the Run 12 directory on HPC:

```bash
canary/canary_2/trial_2/submit_canary.sh
```

The wrapper selects the one-chain bootstrap mode and invokes the shared
production launcher while supplying Canary 2's YAML. The implementation is
deliberately shared so this gate tests the same AutoData path the five-chain run
will use; its training path stops after the contractually defined one-step GPU
smoke and its AutoData timing mode is observational.

## Trial status

- [`trial_1/`](trial_1/PROGRESS.md) preserves the stopped first trial, its timing
  report, failure analysis, and proposed improvements.
- [`trial_2/`](trial_2/README.md) selects the reviewed
  `dishonest_sycophancy_concealing_v1` recipe and has not been launched yet.

No Run 12 Canary 2 job is currently running.
