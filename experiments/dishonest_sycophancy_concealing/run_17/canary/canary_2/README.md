# Run 17 Canary 2: Claude production data-to-training

**Experiment code branch:** `autodata`

- Status: planned; not launched
- Created: 2026-10-11 15:20 PT
- Last updated: 2026-10-11 15:20 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 15:20 PT

Complete one production-realistic AutoData lifecycle from research through a
verified one-step training adapter, using Claude Opus 4.8 for both the AAR
researcher and AutoData generator/teacher, then stop before evaluation.

## Context

Recorded: 2026-10-11 15:20 PT

This gate preserves the Run 12 Canary 2 Trial 12 contract and changes only the
two Kimi-backed roles. The generator protocol is changed explicitly because the
Meta Model API Responses shape and bearer authentication are not compatible
with the Serve API chat-completions route used by Kimi.

## Model and execution roles

- Researcher: `claude-opus-4-8`, maximum effort, API-backed Meta Claude CLI.
- AutoData generator/teacher: `claude-4-8-opus`, Meta Model API Responses,
  logical deployment `meta-model-api-claude-4-8-opus`.
- Proposal monitor: `claude-4-8-opus`, Meta Model API.
- Fixed target/training base: `gemma-4-31B-it`.
- Row judge: `gpt-5-6-luna`, Meta Model API.
- Evaluator inference and evaluator judge: not used.
- Trusted broker, comparator, approval, lifecycle, and receipt checks:
  deterministic code.

## Launch

Recorded: 2026-10-11 15:20 PT

Prerequisites are a clean synchronized source commit, an available selected
Gemma base deployment, and explicit confirmation of the full model-role
mapping. Produce the exact retained Claude/Gemma/Luna broker proof in two
ordered submissions:

```bash
canary/canary_2/launch/prepare_proof.sh preflight
canary/canary_2/launch/prepare_proof.sh canary \
  /checkpoint/ram/$USER/aar-runs/run17-adapter-target/<attempt>
```

The first command prints the proof root. Run the second only after its
`preflight.json` exists and the preflight job completed successfully.

```bash
cd /storage/home/$USER/aar-worktrees/autodata/experiments/dishonest_sycophancy_concealing/run_17
AAR_RUN17_CANARY_ROOT=/checkpoint/ram/$USER/aar-runs/<proof-root> \
  canary/canary_2/launch/launch.sh
```

## Plan

Recorded: 2026-10-11 15:20 PT

Run one alpha chain through source-pinned preflight, method authoring, proposal
approval, workspace authoring, canonical baseline, exactly three meta
iterations, production, verified handoff, and one-step GPU training smoke.

## Pass criteria

Recorded: 2026-10-11 15:20 PT

1. The retained preflight and broker proof match `claude-4-8-opus`, logical
   deployment `meta-model-api-claude-4-8-opus`, the selected Gemma deployment
   and checkpoint hash, `gpt-5-6-luna`, and the pinned broker image.
2. The researcher preflight proves `claude-opus-4-8`, maximum effort, secure
   internet mode, bounded paper search, and research isolation.
3. Trusted orchestration registers one canonical execution with exactly three
   required meta iterations over disjoint `64/32/32` partitions.
4. Production yields exactly 1,000 verified accepted rows from 1,250 source
   tasks without weakening teacher quality or target challenge gates.
5. The verified handoff and consumption receipt identify the same 1,000 rows.
6. One real optimizer step saves a non-empty loadable adapter with retained
   provenance and phase timings.
7. The run stops at the training-smoke marker; no evaluator or held-out
   publication starts.

## Stop criteria

Recorded: 2026-10-11 15:20 PT

Stop and preserve evidence on source/config drift, missing Model API catalog
access, authentication or quota failure, provider identity mismatch, target
checkpoint drift, protected recipe mutation, budget failure, incomplete meta
iterations, insufficient production yield, handoff/receipt mismatch, adapter
failure, unexpected evaluator activity, or a user stop request. Never weaken a
gate or mutate a failed retained attempt.

## After a pass

Recorded: 2026-10-11 15:20 PT

Retain the immutable attempt, provider proof, lifecycle timing artifact,
verified handoff, consumption receipt, training proof, and adapter provenance.
Do not begin evaluation or a larger run without separate authorization.
