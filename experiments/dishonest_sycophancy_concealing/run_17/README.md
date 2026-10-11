# Run 17: Claude AutoData production-to-training canary

**Experiment code branch:** `autodata`

## Goal

Prove the same one-chain production data-to-training boundary as Run 12 Canary
2 while replacing both Kimi roles with Claude Opus 4.8 through API-backed
paths. The canary must complete three AutoData meta iterations, produce 1,000
verified accepted rows from 1,250 source tasks, consume all 1,000 rows through
the contracted loader, execute one real GPU optimizer step, save a valid
non-empty adapter, and stop before evaluation.

## Context

Run 17 derives from Run 12 Canary 2 Trial 12. Its data contract, target model,
row judge, concurrency, meta-optimization topology, production size, training
smoke, budget ceiling, and stop boundary are unchanged. The intended difference
is limited to the researcher and generator/teacher model paths.

## Model and execution roles

- Researcher: Claude Opus 4.8, model `claude-opus-4-8`, maximum effort, through
  the API-backed Meta Claude CLI with secure-internet and research isolation.
- Proposal/approval monitor: `claude-4-8-opus` through Meta Model API.
- AutoData generator/teacher: `claude-4-8-opus` through the Meta Model API
  Responses endpoint; logical deployment `meta-model-api-claude-4-8-opus`.
- Target probe and training base: fixed `gemma-4-31B-it`; the launch reuses the
  explicitly selected base deployment or starts from the same fixed checkpoint.
- Row judge: `gpt-5-6-luna` through Meta Model API.
- Evaluator inference model and evaluator judge: not used; evaluation is
  disabled by the `training_smoke` stop boundary.
- Trusted orchestration, broker, comparator, approval, contract, and lifecycle
  verification roles: deterministic code.

The exact mapping and the retained target deployment must be reconfirmed before
submission. A different model, backend, deployment, checkpoint, or adapter mode
requires a new confirmation.

## Launch

Do not launch until the exact source commit is synchronized to the matching HPC
worktree, the model mapping is explicitly confirmed, and
`AAR_RUN17_CANARY_ROOT` names a retained proof produced with the exact Claude
generator profile and selected Gemma target deployment.

From the Run 17 directory on HPC:

```bash
AAR_RUN17_CANARY_ROOT=/checkpoint/ram/$USER/aar-runs/<proof-root> \
  canary/canary_2/launch/launch.sh
```

The command is an operator entrypoint, not authorization to submit it.

## Pass criteria

Run 17 passes only when the exact conditions in
[`canary/canary_2/README.md`](canary/canary_2/README.md) are satisfied. A score
is not a pass condition because this is an infrastructure and data-to-training
lifecycle gate.

## Stop criteria

Stop and preserve evidence on model or deployment drift, Model API catalog or
authentication failure, source/configuration drift, lifecycle contract failure,
budget failure, insufficient accepted rows, training receipt mismatch, adapter
validation failure, unexpected evaluator work, or a user stop request.

## Directory layout

```text
run_17/
├── config/run.yaml
├── canary/canary_2/
│   ├── launch/prepare_proof.sh
│   ├── launch/launch.sh
│   ├── README.md
│   └── PROGRESS.md
├── README.md
├── PLAN.md
└── PROGRESS.md
```

The canary deliberately delegates scheduler execution to the shared Run 12
AutoData engine so it exercises the same target, broker, lifecycle, handoff,
and one-step training implementation.
