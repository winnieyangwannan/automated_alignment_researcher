# Run 12 Canary 2 Trial 2 lifecycle timings

Human-readable timing and bottleneck report for the v1-recipe
production-data-to-training canary. All displayed timestamps use Pacific Time
(`PT`). This report is updated from durable run evidence and does not contain
credentials, generated training rows, target responses, evaluator traces, or
held-out information.

Operational events and recovery decisions are recorded separately in
[PROGRESS.md](PROGRESS.md).

## Attempt identity

- Terminal status at 2026-10-10 19:56:21 PT: fixed-source attempt stopped at
  baseline approval after repeated generator-deployment provenance rejection;
  no native meta execution was created.
- Current AAR source commit:
  `aea267ecc1de1152cd188f94f4069cf8ec5a90e1`.
- Current AutoData source commit:
  `8ed79b55843d259deea9132cf257f02ff7eb5ee9`.
- Fixed-source attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T023831Z-aea267ecc1de`.
- Fixed-source checkpoint root:
  `/checkpoint/ram/winnieyangwn/aar-checkpoints/run12-bootstrap-canary/20261011T023831Z-aea267ecc1de`.
- Pipeline job: `1809688`; research-chain job: `1809692`; controller job:
  `1809693`.
- Study: `study_8d9774729dd3b46b6cea72485b18a0ca`; workspace:
  `ws_c4ae868015a64b18a697335a9724c99e`.
- Evaluator job: absent (`-`) in durable `metadata/children.tsv`, as required.
- Revalidated reused target deployment:
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Previous serialization-loss attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T021250Z-3421eb1548ec`;
  pipeline `1809610`, research `1809614`, controller `1809615`.
- Failed-attempt source commit:
  `484ea65f3c019dcd7496db39a205b4f4943ee907`.
- Failed pre-submission attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T015716Z-484ea65f3c01`.
- Failed target deployment: `winnieyangwn-r12-alpha-i1-9ff00df8`.
- Coordinator job: `1809523`.
- Gemma worker job: `1809545` on `g3-140-211`.
- Proxy job: `1809583` on `cpu-128-117`.
- Pipeline, research-chain, controller, training, and evaluator jobs: not
  submitted for this attempt.

## Measurement sources

- Slurm `sacct`, `squeue`, and job records for coordinator, worker, and proxy
  timestamps and states.
- The deployment's durable `spec.yaml`, coordinator status, endpoint record,
  `proxy_info.json`, and Slurm logs.
- `metadata/kimi_mcp_preflight.json` in the failed attempt root.
- The submitter's terminal output and model-aware endpoint response.
- Direct and proxied `/v1/chat/completions` and `/v1/models` checks that did not
  retain response content in this report.
- Durable `metadata/children.tsv`, Slurm accounting, native workspace state,
  lifecycle-supervisor status, native baseline summary, broker task-result
  archives, and staged recipe hashes for the fixed-source attempt.

Source timestamps stored in UTC are converted to PT. Durations come from
recorded timestamps or Slurm accounting rather than conversational estimates.

## Current lifecycle

```text
✓ Source/config validation
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Research and method authoring
✓ Proposal review and approval
✗ Baseline approval — generator deployment provenance absent
○ Meta-optimization
○ Production
○ Training smoke
```

## Completed intervals

### Failed pre-submission attempt

- Attempt setup began at 18:57:16 PT.
- Kimi endpoint/MCP preflight completed by 18:57:47 PT, approximately 31
  seconds after attempt creation.
- Target deployment application: 18:57:47 PT.
- Coordinator `1809523` started at 18:58:44 PT.
- Gemma worker `1809545` started at 19:00:14 PT after approximately 1 minute
  27 seconds of queue time.
- vLLM API initialization began at 19:02:53 PT.
- The 58.25-GiB two-shard checkpoint loaded in 19.62 seconds; total reported
  model loading took 26.53 seconds and 57.91 GiB.
- `torch.compile` took 36.15 seconds. Initial profiling/warmup took 7.48
  seconds, and engine initialization took 73.19 seconds.
- The worker became healthy and published its endpoint at 19:05:11 PT.
- Proxy `1809583` started at 19:08:20 PT after approximately 3 minutes of
  queue time and published port `8102` at 19:08:38 PT.
- The model-aware smoke request failed at 19:08:55 PT, approximately 11 minutes
  39 seconds after attempt creation. The submitter exited before `sbatch`.

### Previous serialization-loss attempt

- Fresh attempt setup began at 19:12:50 PT.
- The retained fixed-base deployment's model-aware smoke completed
  successfully before submission.
- Pipeline job `1809610` was submitted by 19:13:33 PT, approximately 43 seconds
  after fresh attempt creation.
- Pipeline queue: submission to 19:14:52 PT, approximately 1 minute 19 seconds.
- Pipeline execution: 19:14:52–19:15:11 PT, 19 seconds, completed successfully.
- At 19:15:11 PT the pipeline published research-chain job `1809614` and
  controller job `1809615`.
- Research-chain queue: 19:15:11–19:17:18 PT, 2 minutes 7 seconds.
- Research-chain execution began at 19:17:18 PT and remains active.
- Runtime/plugin/broker/supervisor bootstrap completed by approximately
  19:17:27 PT.
- Research and method authoring: approximately 19:17:30–19:20:44 PT, 3 minutes
  14 seconds.
- Proposal review: 19:20:44–19:20:50.956 PT, 6.134 seconds, successful.
- Proposal-bound workspace bootstrap completed at approximately 19:20:51 PT.
- Native `clarify_design`: 19:20:51–19:21:13 PT, approximately 22 seconds.
- Native `author_grounding`: 19:21:14–19:21:54 PT, approximately 40 seconds.
- Grounding approval completed on its first decision by 19:22:25 PT.
- Pipeline authoring completed on its first action by approximately 19:22:52
  PT.
- Baseline recipe check and three sequential dry-run tasks ran from
  approximately 19:23:40 to 19:24:54 PT; exact task intervals remain available
  in native SQLite and broker metadata.
- Baseline approval retries began at 19:25:05 PT. The same structural
  provenance error persisted until the attempt was stopped at 19:29:55 PT.
- Research-chain allocation: 19:17:18–19:29:55 PT, 12 minutes 37 seconds.
- Controller `1809615` was canceled while dependency-held and never started.

## Configuration and provenance identity

- Resolved configuration SHA-256:
  `5d2bf400a987327b8c5053d9f0020604878b773ccef2d303784ac45e21b325da`.
- Run YAML SHA-256:
  `fbcd72eda62bb3dcb3cff6c0f72c20be43fc9ff0e0525af96128898a29521ef8`.
- Runtime profile SHA-256:
  `8163e3ec445743a9041fe254dd7eb67240d593dbdabea59a5e6bf4e25b44fa1e`.
- Target binding SHA-256:
  `1565d310f85f78b750f95f5d08000287236f1ac680afde2e8be8aceac501757b`.
- Target checkpoint identity:
  `6285c621740a6305dd1986b1270cb56c23bf54addfd388faacbe049c63d7a78c`.
- Rubric version: `run9-axis-conditioned-v4`; rubric SHA-256:
  `e7d0cfd17f9095675c9b2a65e75244faa0504190d4d2c89f42c143a626de1938`.
- Recipe root: `aar/autodata_recipes/dishonest_sycophancy_concealing_v1`.
- Only `recipe/generation_strategy.json` is mutable; pipeline/workspace,
  grounding, lock, objective, comparator, schemas, rubric, task, check, request,
  and training contract are protected.

## Work and quality counters

- Workspace-authoring completed actions: design clarification, grounding
  authoring, grounding approval, and pipeline authoring; baseline approval did
  not complete.
- Workspace revision: 5.
- Authoring checks: 1/1 operationally successful.
- Authoring dry-run tasks: 3/3 operationally successful.
- Dry-run diagnostics:
  - honesty: `quality=0.933333`, `challenge=0`, `valid=0`,
    `target_not_challenging`;
  - sycophancy resistance: `quality=1`, `challenge=0`, `valid=0`,
    `target_not_challenging`;
  - uncertainty disclosure: `quality=1`, `challenge=0.5`, `valid=1`.
- Baseline review calls: three for the same action. Two returned the identical
  deployment-provenance rejection and the third made no progress before the
  stop boundary.
- Native meta-optimization executions and candidates: 0.
- Production source tasks: 0/1,250.
- Production accepted rows: 0/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, as required.

## Provider and execution health

- Kimi researcher endpoint/MCP preflight: passed.
- Gemma worker: vLLM 0.25.1, BF16, language-model-only, healthy, and capable
  of direct generation.
- The reused Gemma proxy passed the model-aware smoke before submission.
- Fixed-source authoring used exactly three completed/request attempts for each
  of generator, target, and judge: 9 provider calls, 9 request attempts, and 0
  provider retries.
- Provider timeout, connection reset, broker, target, schema, task-execution,
  and model-loading failures: 0 in the fixed-source attempt.
- All three results preserve top-level generator, target, and judge
  `provider_usage`. Target entries contain the expected deployment and valid
  checkpoint hash; Kimi generator entries omit `deployment_id`.
- The two rejected diagnostic rows remained non-exportable.

## Bottleneck analysis

The pre-submission attempt did not reach the AutoData lifecycle because of a
control-plane proxy port-selection race. The fresh attempt bypassed that issue
with a separately verified identical fixed-base deployment and reached native
workspace authoring.

The previous attempt's blocker was serialization between the raw task result
and native baseline-review artifact. AutoData commit `8ed79b5` corrected that
loss: all three fixed-source raw task results and the native baseline summary
contain the same three-role provider-usage lists.

The fixed-source attempt exposed the next fail-closed provenance boundary.
The committed recipe's `_generate` path sends
`AUTODATA_GENERATOR_DEPLOYMENT_ID` in the request header but does not copy it
into the returned generator usage record. Consequently every Kimi generator
entry lacks `deployment_id`, although every target entry contains deployment
`winnieyangwn-r12-alpha-i1-c0dab4f7` and the correct checkpoint hash. The
trusted AAR verifier requires nonempty deployment IDs for both generator and
target roles. It therefore rejected the baseline before native action
completion. This was a provenance-shape failure, not a content-score rejection.

## Unmeasured stages

The fixed-source attempt completed research/method authoring, proposal review,
workspace registration, grounding, pipeline authoring, one recipe check, and
three dry runs. Baseline approval did not complete. Native meta-optimization,
production, handoff verification, and training smoke never started and remain
unmeasured.

## Trial 2 versus Trial 1 baseline behavior

- Trial 1 took approximately 11 minutes 27 seconds from workspace bootstrap to
  completion of its first baseline cycle. The fixed-source Trial 2 attempt took
  approximately 2 minutes 47 seconds from workspace bootstrap at 19:48:27 PT
  to completion of its three dry runs at 19:51:14 PT.
- Trial 1 ran nine baseline cycles, 30 workspace revisions, and 18 dry-run
  tasks before exhausting its research session. The fixed-source Trial 2
  attempt authored one pipeline, reached revision 5, and completed three
  dry-run tasks before the deployment-provenance check blocked approval.
- Trial 1 produced 17/18 invalid diagnostics and never placed both sampled axes
  in an acceptable content state. The fixed-source attempt produced one valid
  uncertainty-disclosure diagnostic and two teacher-quality but
  target-not-challenging diagnostics; the rejected rows remained
  non-exportable.
- Neither trial reached a first native meta execution. Trial 1 was blocked by a
  content-convergence gate; the fixed-source attempt was blocked by incomplete
  generator deployment provenance before the operational baseline decision.
- Time to first native meta execution is therefore unmeasured for both trials.
  The v1 recipe reduced time and revisions to the first baseline and produced
  one valid diagnostic, but this stopped attempt cannot prove that it removed
  Trial 1's convergence blocker because the independent provenance gate
  prevented baseline approval.

## Fresh fixed-source attempt — `20261011T023831Z-aea267ecc1de`

- 19:38 PT: focused HPC validation completed, 57/57 tests passed.
- 19:38 PT: an initial launcher invocation stopped before attempt creation or
  job submission because the exact AutoData checkout was attached to a feature
  branch. It was detached at the unchanged pinned commit to satisfy the
  production-source guard.
- 19:39 PT: committed launcher created the fresh attempt and submitted pipeline
  job `1809688`.
- Kimi/MCP and reused Gemma endpoint preflights passed before submission.
- Pipeline `1809688`: submitted 19:39:02 PT; queued until 19:40:10 PT; ran
  19:40:10–19:40:30 PT for 20 seconds and completed successfully.
- Research `1809692`: submitted 19:40:19 PT; queued until 19:41:52 PT for 1
  minute 33 seconds; ran 19:41:52–19:56:20 PT for 14 minutes 28 seconds.
- Controller `1809693` remained dependency-held, never started, and was
  canceled at the terminal boundary. No evaluator job was created.
- 19:48:27 PT: corrected proposal review and workspace bootstrap completed;
  native workspace `ws_c4ae868015a64b18a697335a9724c99e` entered
  `clarify_pending` at revision 0.
- `clarify_design` attempt 1: 19:48:28–19:48:55 PT.
- `author_grounding` attempt 1: 19:48:56–19:49:32 PT.
- `approve_grounding` attempt 1: 19:49:33–19:50:03 PT.
- `author_pipeline` attempt 1: 19:50:05–19:50:20 PT.
- Baseline recipe check and three sequential dry runs: 19:50:21–19:51:14 PT;
  all 4/4 task attempts succeeded with zero task errors.
- Baseline action `act_34089aac5d9609284631dcc7` was reviewed three times.
  Identical deployment-provenance rejections returned at 19:51:37 and
  19:51:56 PT; a third call dispatched at 19:52:02 PT made no progress.
- The documented repeated-baseline/no-meta stop criterion was applied at
  19:56:20 PT. Research `1809692` and held controller `1809693` were canceled;
  the lifecycle supervisor recorded `stopped` at 19:56:21 PT.
- Terminal workspace state: active/`baseline_review`, revision 5, four task
  attempts used, baseline approval pending, and zero native executions.
- Meta-optimization, production, handoff, and training durations are
  unmeasured because those stages never started.
