# Canary 2 Trial 2

## Context

Trial 2 uses a new version of the root AutoData recipe:
`aar/autodata_recipes/dishonest_sycophancy_concealing_v1`. This reviewed,
minimal starting recipe was created from the analysis and recommendations in
[`autodata_recipe_v1.md`](autodata_recipe_v1.md). It keeps the experiment's
isolation, provenance, target-aware judging, schema, and export-safety
requirements while reducing the prescriptive generation policy that made the
original baseline difficult to establish.

Trial 1 used the original
`aar/autodata_recipes/dishonest_sycophancy_concealing` root recipe. Its
pipeline executed reliably, but baseline approval was requested to revise in
all nine rounds. Seventeen of eighteen dry-run results had `valid=0`; the only
valid result was an honesty example in Baseline 6, while the paired sycophancy
example was not challenging to Gemma. Because every rewrite regenerated both
axes, a passing axis could regress while the researcher repaired the other.
The loop exhausted all 96 Kimi continuation turns before native
meta-optimization began. See the retained
[`Trial 1 progress report`](../trial_1/PROGRESS.md#run12-canary2-baseline-rejection-diagnostics).

## Goal

The primary goal is to determine whether the new v1 root recipe fixes Trial
1's baseline-convergence failure. Trial 2 must show that workspace authoring
can establish a trustworthy operational baseline and advance into native
meta-optimization without requiring the starting strategy to produce two
simultaneously accepted training rows.

The broader Canary 2 success boundary remains unchanged: if the baseline gate
passes, continue through meta-optimization, produce and verify 1,000 accepted
rows, consume them through the contracted training loader, execute one real
optimizer step, save a valid non-empty adapter, and stop before evaluation.
Passing the baseline alone diagnoses the Trial 1 blocker but does not make the
full canary successful.

## Selected recipe

Trial 2 starts from the reviewed minimal v1 recipe:

```yaml
recipe_root: aar/autodata_recipes/dishonest_sycophancy_concealing_v1
training_contract:
  objective: sft
  judge_rubric: recipe/judge_rubric.json
```

The rubric path is relative to the selected recipe root. At launch, the strict
Run 12 compiler validates the repository-relative recipe directory and exports
`AAR_AUTODATA_RECIPE_ROOT`; workspace bootstrap then copies that reviewed recipe
into the proposal-bound writable workspace. Native AutoData may modify only the
pipeline's allowlisted mutable paths.

Trial 1 evidence remains under [`../trial_1/`](../trial_1/PROGRESS.md). Trial 2
has not been launched yet. Live status will be recorded in
[`PROGRESS.md`](PROGRESS.md).

## Pass Criteria

Trial 2 passes only when every condition below is satisfied:

1. The compiled configuration records
   `aar/autodata_recipes/dishonest_sycophancy_concealing_v1` as the recipe root,
   and the staged workspace files and rubric identity match that reviewed
   source.
2. All authoring checks and dry-run tasks complete operationally with valid
   schemas and complete generator, target, and judge provenance.
3. Baseline approval acts as an operational gate: trustworthy diagnostic rows
   may have `valid=0`, while rejected rows remain excluded from exportable
   training data.
4. The workspace advances beyond baseline review into native
   meta-optimization. This is the specific proof that Trial 1's blocker is
   fixed, but it is not sufficient by itself for the canary to pass.
5. Native AutoData completes exactly three configured meta-iterations, compares
   candidate strategies using the protected comparator, and finalizes a
   winning pipeline with intact target and rubric provenance.
6. Production attempts the configured 1,250 source tasks at concurrency 32,
   maintains at least the required `0.95` successful-task fraction, and
   publishes exactly 1,000 accepted rows without weakening any teacher-quality
   or target-challenge gate.
7. The verified handoff and consumption receipt identify those same 1,000
   rows. The contracted SFT loader validates the full dataset, one real
   optimizer step runs, and a non-empty loadable PEFT adapter is saved and
   verified.
8. Lifecycle timing evidence records authoring, meta-optimization, production,
   provider retry/rate-limit signals, accepted-row throughput, handoff, and
   training-smoke duration.
9. The run stops after the verified training-smoke marker. No evaluator,
   held-out scoring, result publication, or promotion is started.

## Stop Criteria

Stop the trial, preserve its evidence, and do not continue to the next stage if
any of the following occurs:

- The compiled or staged recipe root, rubric digest, target checkpoint,
  deployment identity, chain identity, or protected file set differs from the
  reviewed Trial 2 configuration.
- Baseline approval is rejected solely because a trustworthy diagnostic row
  has low `quality`, `challenge`, or `valid=0`. That reproduces Trial 1's gate
  mismatch and means the v1 baseline fix is not active.
- A rejected diagnostic row becomes exportable, appears in the production
  dataset, or bypasses teacher-quality, target-challenge, schema, or provenance
  checks.
- Workspace authoring repeatedly revises the baseline without creating a
  native meta execution, or reaches the configured continuation, research
  attempt, no-progress, task-attempt, provider-retry, or outer Slurm limit.
- Meta-optimization does not complete all three configured iterations, changes
  a protected file, cannot compare candidates, or cannot finalize a
  provenance-bound winner.
- Production cannot produce 1,000 accepted rows from the fixed 1,250-task
  corpus after its allowed retry, falls below the `0.95` successful-task
  fraction, or encounters unresolved provider, broker, gateway, target, or
  storage failures.
- The training handoff, row count, hashes, rubric identity, target provenance,
  or consumption receipt does not match the finalized production artifact.
- Training cannot load the contracted SFT fields, performs anything other than
  the authorized one optimizer step, or fails to save a valid non-empty
  adapter.
- An evaluator or held-out evaluation starts unexpectedly. The intended
  successful stop boundary is the verified training-smoke marker.
- The user requests a stop.

## Monitor Criteria

Monitoring must remain read-only and must not approve rows, change the recipe,
relax acceptance gates, or expose generated rows or target responses in Git.
It must track and report:

- **Lifecycle position:** current stage, last completed action, next expected
  boundary, job IDs and states, and a compact lifecycle snapshot whenever the
  run advances, fails, or stops.
- **Recipe identity:** resolved run-config hash, compiled v1 recipe root,
  rubric version and digest, mutable/protected path sets, source commit, and
  chain/iteration identity.
- **Baseline behavior:** number of pipeline revisions, checks and dry-run
  tasks; operational outcomes; per-axis `quality`, `challenge`, and `valid`;
  approval decision and reason; whether rejected rows remain non-exportable;
  and whether the first trusted operational baseline creates a native meta
  execution. Immediately flag any Trial 1 pattern in which content scores alone
  cause repeated baseline rejection.
- **Meta-optimization:** execution and candidate IDs, completed iteration count
  out of three, comparison decisions, winner lineage, per-axis metrics,
  strategy changes, and any protected-file or provenance drift.
- **Production:** completed, successful, failed, and retried source tasks out of
  1,250; accepted rows toward 1,000; successful-task fraction; acceptance and
  rejection rates by axis; effective rows per minute; and projected ability to
  satisfy the fixed corpus contract without weakening standards.
- **Provider health:** completed Kimi, Gemma, and Luna calls; request latency and
  long-tail latency; retries; timeouts; empty responses; parse failures;
  connection resets; HTTP 429/rate-limit evidence; and exact target deployment
  and checkpoint identity.
- **Execution health:** Local Bubblewrap task latency, concurrency actually
  achieved versus 32, broker failures, no-progress watchdog state, SQLite
  progress, Slurm queue/running/terminal state, disk usage, and checkpoint
  storage health.
- **Training handoff:** finalized dataset and contract hashes, available and
  retained row counts, consumption receipt, exact consumed-row count, loader
  schema validation, optimizer-step count, adapter path, adapter-weight hash,
  and loadability verification.
- **Timing:** PT timestamps and durations for endpoint preflight, research and
  proposal authoring, workspace authoring, baseline establishment, each meta
  iteration, production, handoff verification, queue waits, and training smoke.

Every meaningful progress update must include an ordered lifecycle snapshot in
this form, updated to reflect the actual Trial 2 state:

```text
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Method authoring and contract check
✓ Proposal review and approval
✓ AutoData workspace registration
✗ First workspace-authoring action
○ Meta-optimization
○ Production
○ Training smoke
```

Use `✓` only for completed stages, `⏳` for the currently running stage, `✗`
only for the stage that failed or is blocked, and `○` for pending or unstarted
stages. Replace “First workspace-authoring action” with the precise active or
failed boundary, such as grounding approval, baseline approval, meta-iteration
2 of 3, production row generation, handoff verification, or the optimizer
step. The snapshot must never imply that a later stage started when it did not.

Monitoring must also create and continuously update a Trial 2 `TIMINGS.md` in
this directory, following the structure and evidence standard of
[`Trial 1's TIMINGS.md`](../trial_1/TIMINGS.md). The report must be derived from
durable Slurm accounting, native AutoData state, lifecycle events, broker result
metadata, handoff receipts, and training records rather than conversational
estimates. It must include attempt identity, measurement sources, the current
lifecycle snapshot, completed stage intervals, task and acceptance counters,
throughput and latency, provider/retry evidence, bottleneck analysis, and any
stages that remain unmeasured. All displayed timestamps must use PT, and the
report must not contain generated rows, raw prompts, target responses,
credentials, or held-out information.

At the terminal boundary, `TIMINGS.md` must explicitly compare Trial 2 with
Trial 1's baseline-authoring behavior: time to baseline approval, pipeline
revision count, dry-run task count, per-axis validity/challenge pattern, time to
the first native meta execution, and whether the v1 recipe removed the previous
convergence bottleneck. If the trial stops early, the report must still be
finalized with the measured intervals and clearly label every unstarted stage.

The monitor must alert immediately when a Stop Criterion is met. Otherwise it
should continue observing and update [`PROGRESS.md`](PROGRESS.md) at meaningful
stage transitions or material changes, rather than treating an unchanged
healthy state as a failure.

## Launch

From the Run 12 directory on FAIR HPC:

```bash
canary/canary_2/trial_2/submit_canary.sh
```

This invokes the shared Run 12 production launcher with Trial 2's local YAML. It
does not launch the five-chain full experiment.
