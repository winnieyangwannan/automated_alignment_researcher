# Canary 1: lightweight infrastructure

## Goal

This fast canary sends one AutoData task across the intended inference path:

```text
Kimi generator
    → iteration-bound Gemma target
    → Luna judge
    → schema-validated local Bubblewrap broker result
```

It verifies the exact Gemma binding, broker startup, provider ordering, target
provenance, and result schema. It does not require Gemma to fail, an accepted
row, dataset production, training, evaluation, or a score/result pair.

## Result: passed

Retained result:

```text
/checkpoint/ram/winnieyangwn/aar-runs/run12-adapter-target/20261009T150557Z-68f6178b2ac4
```

- infrastructure result: `success=true`;
- broker: `SUCCEEDED`;
- task outcome and schema: valid;
- provider calls: exactly `generator → target → judge`;
- teacher quality: `1.0`;
- target challenge: `0.0`;
- accepted rows: `0` (`target_not_challenging`).

The rejected sample does not fail this routing canary.

## Files and launch

- `autodata_canary.yaml`: one-task configuration;
- `submit_target_canary.sh`: target binding, preflight, and submitter;
- `endpoint_preflight.sbatch`: real completion against the bound target;
- `target_canary.sbatch`: one Kimi → Gemma → Luna broker task.

From the Run 12 directory on HPC:

```bash
canary/canary_1/submit_target_canary.sh preflight
canary/canary_1/submit_target_canary.sh canary /checkpoint/ram/winnieyangwn/aar-runs/run12-adapter-target/<attempt>
```
