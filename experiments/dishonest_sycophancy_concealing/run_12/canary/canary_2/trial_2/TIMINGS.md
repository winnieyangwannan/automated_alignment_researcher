# Run 12 Canary 2 Trial 2 lifecycle timings

Human-readable timing and bottleneck report for the v1-recipe
production-data-to-training canary. All displayed timestamps use Pacific Time
(`PT`). This report is updated from durable run evidence and does not contain
credentials, generated training rows, target responses, evaluator traces, or
held-out information.

Operational events and recovery decisions are recorded separately in
[PROGRESS.md](PROGRESS.md).

## Attempt identity

- Current status at 2026-10-10 19:11 PT: first pre-submission attempt stopped;
  a fresh attempt is pending.
- Source commit: `484ea65f3c019dcd7496db39a205b4f4943ee907`.
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
✗ Endpoint and MCP preflight — target proxy port collision
○ Infrastructure bootstrap
○ Research and method authoring
○ Proposal review and approval
○ AutoData workspace authoring
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

## Work and quality counters

- Workspace-authoring actions: 0.
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
- HTTP 429, provider timeout, connection reset, and model-loading failures: 0
  observed in this attempt.

## Bottleneck analysis

The first attempt did not reach the AutoData lifecycle. The blocker was a
control-plane proxy port-selection race, not Gemma loading, provider health,
recipe compilation, baseline convergence, or production throughput. Generic
proxy health was insufficient because it could succeed against the foreign
process; the existing model-aware generation smoke prevented a misbound target
from entering the run.

## Unmeasured stages

Research and method authoring, proposal review, workspace authoring, baseline
approval, native meta-optimization, production, handoff verification, and
training smoke did not start. Trial 2 versus Trial 1 baseline-convergence and
time-to-first-native-meta comparisons remain unmeasured until a fresh attempt
crosses the endpoint gate.
