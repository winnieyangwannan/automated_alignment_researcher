# Run 12 Canary 2 Trial 2 lifecycle timings

Human-readable timing and bottleneck report for the v1-recipe
production-data-to-training canary. All displayed timestamps use Pacific Time
(`PT`). This report is updated from durable run evidence and does not contain
credentials, generated training rows, target responses, evaluator traces, or
held-out information.

Operational events and recovery decisions are recorded separately in
[PROGRESS.md](PROGRESS.md).

## Attempt identity

- Current status at 2026-10-10 19:30 PT: attempt stopped at baseline approval
  after a deterministic provider-provenance serialization failure.
- Current source commit: `3421eb1548ecf5ae9865cb5bb2b531bb323bc2b6`.
- Fresh attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T021250Z-3421eb1548ec`.
- Fresh checkpoint root:
  `/checkpoint/ram/winnieyangwn/aar-checkpoints/run12-bootstrap-canary/20261011T021250Z-3421eb1548ec`.
- Fresh pipeline job: `1809610`.
- Revalidated reused target deployment:
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Research-chain job: `1809614`.
- Controller job: `1809615`.
- Evaluator job: absent (`-`) in durable `metadata/children.tsv`, as required.
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

Source timestamps stored in UTC are converted to PT. Durations come from
recorded timestamps or Slurm accounting rather than conversational estimates.

## Current lifecycle

```text
✓ Source/config validation
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Research and method authoring
✓ Proposal review and approval
✗ Baseline approval — provider provenance removed during serialization
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

### Fresh attempt and submission

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
- Native meta-optimization executions and candidates: 0.
- Production source tasks: 0/1,250.
- Production accepted rows: 0/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, as required.

## Provider and execution health

- Kimi researcher endpoint/MCP preflight: passed.
- Gemma worker: vLLM 0.25.1, BF16, language-model-only, healthy, and capable
  of direct generation.
- Proxy validation: failed because a simultaneous unrelated deployment won the
  same host port. The claimed Gemma proxy URL exposed `Kimi-K3`, so the
  model-aware smoke correctly rejected it with HTTP 400.
- One judge HTTP 429 occurred and the request succeeded on retry.
- Provider timeout, connection reset, broker, target, schema, task-execution,
  and model-loading failures: 0 observed in this attempt.
- Baseline diagnostic metrics for honesty, sycophancy resistance, and
  uncertainty disclosure were each `quality=1.0`, `challenge=0.0`, and
  `valid=0`. The rejected rows remained non-exportable.

## Bottleneck analysis

The pre-submission attempt did not reach the AutoData lifecycle because of a
control-plane proxy port-selection race. The fresh attempt bypassed that issue
with a separately verified identical fixed-base deployment and reached native
workspace authoring.

The fresh attempt's terminal blocker was serialization between the raw task
result and native baseline-review artifact. Raw task results contained complete
generator, target, and judge provenance. Pinned AutoData commit `823c594`
parsed them through a `TaskResult` model without a `provider_usage` field and
then built baseline samples from `TaskResult.to_dict()`, deterministically
dropping that list. The trusted AAR approval gate correctly rejected the
incomplete evidence. The failure occurred before content-aware baseline policy
could be evaluated.

## Unmeasured stages

Research and method authoring, proposal review, workspace authoring, baseline
approval, native meta-optimization, production, handoff verification, and
training smoke did not start in the first pre-submission attempt. The fresh
attempt completed through pipeline authoring, but baseline approval did not
complete. Meta-optimization, production, handoff verification, and training
smoke remain unmeasured.

## Trial 2 versus Trial 1 baseline behavior

- Trial 1 took approximately 11 minutes 27 seconds from workspace bootstrap to
  completion of its first baseline cycle. Trial 2 reached its first completed
  operational baseline about 4 minutes after workspace bootstrap.
- Trial 1 ran nine baseline cycles, 30 workspace revisions, and 18 dry-run
  tasks before exhausting its research session. Trial 2 authored one pipeline
  at revision 5 and completed three dry-run tasks before the serialization
  mismatch blocked approval.
- Trial 1 produced 17/18 invalid diagnostics and never placed both sampled axes
  in an acceptable content state. Trial 2 produced one trustworthy diagnostic
  per axis; all three were teacher-quality (`quality=1.0`) but did not challenge
  the target (`challenge=0.0`, `valid=0`) and remained non-exportable.
- Neither trial reached a first native meta execution. Trial 1 was blocked by a
  content-convergence gate; this Trial 2 attempt was blocked earlier by lost
  provider provenance in the native baseline artifact.
- Therefore this stopped attempt does not prove whether the v1 recipe removed
  Trial 1's convergence bottleneck. A fresh attempt with provenance-preserving
  serialization is required for that comparison.
