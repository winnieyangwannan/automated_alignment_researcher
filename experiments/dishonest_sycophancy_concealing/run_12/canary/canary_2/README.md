# Canary 2: production data generation

## Goal

This is a production-realistic data-generation rehearsal using one AAR chain:

```text
Kimi AAR researcher
    → target-aware AutoData meta-optimization
    → 100 accepted production rows
    → verified production handoff
    → stop before training or evaluation
```

It exercises lifecycle approvals, strategy revision, challenging-row yield,
production throughput, native finalization, and durable handoff verification.
It intentionally does not create an adapter, allocate an evaluator, or require
a score/result pair.

## YAML control

Canary 2 has its own strict
[`autodata_run.yaml`](autodata_run.yaml). These checked-in fields define its
boundary independently from the full-run configuration:

```yaml
bootstrap_canary:
  stop_after: production
production:
  required_rows: 100
  initial_tasks: 125
  maximum_tasks: 200
```

The strict compiler freezes the values into the resolved configuration,
training-data contract, and runtime environment. Trusted host code only marks
the canary complete after read-only verification of the native
meta-to-production lineage and at least 100 accepted rows. It suppresses SFT
submission, and the pipeline launches no evaluator. Full mode rejects an
inherited canary stop boundary.

## Launch

From the Run 12 directory on HPC:

```bash
canary/canary_2/submit_canary.sh
```

The wrapper selects the one-chain bootstrap mode and invokes the shared
production launcher while supplying Canary 2's YAML. The implementation is
deliberately shared so this gate tests the same AutoData path the five-chain run
will use; only its declared scope and budgets are smaller.

## Result: not passed yet

No attempt has produced the required verified production marker:

- `20261010T181939Z-6f244e966ed6` reached target-aware authoring and found one
  `challenge=1.0` prompt, but no baseline passed every acceptance gate. It was
  canceled before production.
- `20261010T185308Z-6fd1306cc68e` was canceled during benchmark publication,
  before child chain jobs were created.

No Run 12 canary job is currently running.
