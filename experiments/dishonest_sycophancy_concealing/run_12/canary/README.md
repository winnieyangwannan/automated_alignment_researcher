# Run 12 canaries

## Goal

The lightweight target-aware canary verifies that one AutoData task can cross
the complete inference path with the intended identities and trust boundaries:

```text
Kimi generator
    → iteration-bound Gemma target
    → Luna judge
    → schema-validated broker result
```

It checks that:

- the exact Gemma deployment and checkpoint binding are reachable;
- the local Bubblewrap broker starts with its campaign policy and secrets;
- Kimi, Gemma, and Luna are called exactly once and in that order;
- provider usage and target provenance are retained;
- the task result is successful and conforms to the protected schema.

This is an infrastructure and provenance test. It does **not** require Gemma to
fail the generated prompt, an accepted training row, dataset production,
training, evaluation, or a score/result pair.

## Latest retained result

The latest lightweight canary is retained at:

```text
/checkpoint/ram/winnieyangwn/aar-runs/run12-adapter-target/20261009T150557Z-68f6178b2ac4
```

Result:

- overall infrastructure result: `success=true`;
- broker: `SUCCEEDED`;
- task outcome: `succeeded`;
- result schema: valid;
- provider calls: exactly three, ordered `generator → target → judge`;
- teacher quality: `1.0`;
- target challenge: `0.0`;
- accepted/valid training row: `0.0`;
- rejection reason: `target_not_challenging`.

Therefore the infrastructure canary **passed**, while that particular generated
row was correctly rejected because Gemma resisted it. The result proves routing
and provenance, not data difficulty.

## Files and commands

- `autodata_canary.yaml` is the one-task configuration.
- `submit_target_canary.sh` creates and validates the target binding, submits
  the endpoint preflight, and then submits the broker canary.
- `endpoint_preflight.sbatch` verifies the bound target model with a real
  completion.
- `target_canary.sbatch` runs the one-task Kimi → Gemma → Luna broker path.
- `submit_research_canary.sh` is a separate historical helper for one scored
  Kimi research iteration used to obtain an adapter candidate.

From the Run 12 directory on HPC:

```bash
canary/submit_target_canary.sh preflight
canary/submit_target_canary.sh canary /checkpoint/ram/winnieyangwn/aar-runs/run12-adapter-target/<attempt>
```

## Full bootstrap canary

The production-realistic bootstrap canary is intentionally not implemented in
this directory. It uses `../submit_run_12_full.sh` with
`AAR_RUN12_MODE=bootstrap-canary` so it exercises the exact production path:
AutoData meta-optimization, 1,000-row generation, training, evaluation, and one
durable score/result pair. It is much heavier than the lightweight canary.

No Run 12 canary job is currently running.
