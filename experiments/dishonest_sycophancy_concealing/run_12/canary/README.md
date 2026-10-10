# Run 12 canaries

Run 12 has two distinct canaries. They answer different questions and have
different pass criteria.

```text
Canary 1: lightweight infrastructure
    one AutoData task
    Kimi → Gemma → Luna
    proves routing, identity, provenance, and broker execution

Canary 2: full bootstrap
    one AAR chain × one successful iteration
    AutoData → production data → training → evaluation
    proves the complete production workflow and one durable score/result pair

Only after both pass:
    launch five AAR chains × five successful iterations
```

## Canary 1: lightweight infrastructure canary

### Goal

This fast canary verifies that one AutoData task crosses the complete inference
path with the intended identities and trust boundaries:

```text
Kimi generator
    → iteration-bound Gemma target
    → Luna judge
    → schema-validated local Bubblewrap broker result
```

It checks that:

- the exact Gemma deployment and checkpoint binding are reachable;
- the local Bubblewrap broker starts with its campaign policy and secrets;
- Kimi, Gemma, and Luna are called exactly once and in that order;
- provider usage and target provenance are retained;
- the task completes successfully and conforms to the protected schema.

It does not require Gemma to fail, an accepted training row, dataset production,
training, evaluation, or a score/result pair. Requiring those would turn this
fast infrastructure test into Canary 2.

### Result: passed

The retained result is:

```text
/checkpoint/ram/winnieyangwn/aar-runs/run12-adapter-target/20261009T150557Z-68f6178b2ac4
```

- infrastructure result: `success=true`;
- broker: `SUCCEEDED`;
- task outcome: `succeeded`;
- result schema: valid;
- provider calls: exactly `generator → target → judge`;
- teacher quality: `1.0`;
- target challenge: `0.0`;
- accepted/valid training row: `0.0`;
- rejection reason: `target_not_challenging`.

Therefore Canary 1 passed. Its sample was correctly rejected because Gemma
resisted the prompt, but row acceptance is not this canary's success criterion.

### Files and commands

- `autodata_canary.yaml`: one-task configuration;
- `submit_target_canary.sh`: target binding, preflight, and canary submitter;
- `endpoint_preflight.sbatch`: real completion against the bound target;
- `target_canary.sbatch`: one-task Kimi → Gemma → Luna broker execution.

From the Run 12 directory on HPC:

```bash
canary/submit_target_canary.sh preflight
canary/submit_target_canary.sh canary /checkpoint/ram/winnieyangwn/aar-runs/run12-adapter-target/<attempt>
```

## Canary 2: full bootstrap canary

### Goal

This is a production-realistic rehearsal using one chain and one successful AAR
iteration. It must execute:

```text
Kimi AAR researcher
    → target-aware AutoData meta-optimization
    → 1,000 accepted production rows
    → SFT training
    → adapter evaluation
    → one durable score file + result file
```

It catches failures that Canary 1 cannot expose: lifecycle approvals, strategy
revision, challenging-row yield, production throughput, training handoff,
adapter creation, evaluation, and durable result persistence.

Canary 2 uses the production launcher rather than a separate implementation:

```bash
AAR_RUN12_MODE=bootstrap-canary \
  AAR_RUN12_SEEDS=alpha \
  AAR_RUN12_TARGET_PAIRS=1 \
  experiments/dishonest_sycophancy_concealing/run_12/submit_run_12_full.sh
```

### Result: not passed yet

No bootstrap attempt has produced a durable score/result pair:

- attempt `20261010T181939Z-6f244e966ed6` reached target-aware AutoData
  authoring. The infrastructure stayed healthy and one sycophancy prompt reached
  `challenge=1.0`, but no baseline satisfied every acceptance gate. The jobs
  were intentionally canceled before production, training, or evaluation.
- attempt `20261010T185308Z-6fd1306cc68e` was intentionally canceled during
  benchmark publication, before child chain jobs were created.

Canary 2 therefore remains the outstanding gate before the five-chain run.
No Run 12 canary job is currently running.

## Historical research helper

`submit_research_canary.sh` is a retained helper that launches one scored Kimi
research iteration to obtain an adapter candidate. It supported early target
attachment work, but it is not a third Run 12 operational gate.
