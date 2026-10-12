# Run 13 Canary Trial 6: reproducible recovery validation

**Experiment code branch:** `autodata`

- Status: prepared; not launched
- Created: 2026-10-12 03:40 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Run the same end-to-end contract as Trial 5 from a fresh pre-AutoData boundary,
after fixing the recovery helper to retain the trusted virtual-environment
Python entry point. AutoData owns native state transitions; the trusted AAR
supervisor reconciles actions through production and exactly one Gemma optimizer
step, then stops at `training_smoke` without evaluation.

## Trial 5 diagnosis

Trial 5 never entered AutoData. The recovery helper dereferenced
`.venv/bin/python` to its base interpreter, which removed the virtual
environment's packages. Fresh method validation therefore lacked `ruff` and
`requests`. The method itself was unchanged and hash-valid. Commit `22a37b7`
preserves the venv launcher path and records both launcher and real paths in the
recovery receipt.

## Lifecycle

```text
AAR Claude researcher
→ loads the autodata:autodata plugin skill
→ calls the native AutoData CLI
→ authors and freezes a workspace
→ meta-optimizes the permitted generation strategy
→ runs production generation
→ exports a verified dataset
→ AAR consumes that export for Gemma training
→ stops after one optimizer step
```

The model proposes actions, while trusted host code controls approvals, state
transitions, budgets, receipts, and immutable files. Only
`generation_strategy.json` may change during optimization. The architecture
uses the real `autodata_pipelines` plugin rather than reimplementing it in AAR.

## Model and execution roles

- AAR researcher: Claude Opus 4.8 through `meta-claude-cli-opus-4-8`, maximum effort.
- AAR proposal monitor: Claude Opus 4.8 through Meta Model API.
- AutoData semantic researcher: Claude Opus 4.8 through the typed worker interface.
- AutoData generator: `claude-4-8-opus` through `meta-model-api-claude-4-8-opus` using `model_api_responses`.
- AutoData row judge: `gpt-5-6-luna` through Meta Model API.
- Target probe and training base: Gemma 4 31B IT.
- Evaluation judge: GPT-5.6 Luna, configured but not invoked.
- Evaluator inference: disabled.
- AutoData revision: `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Concurrency: 8; model-request attempts: 3.

## Pass criteria

- Fresh attempt, team, proposal binding, AutoData workspace, executions,
  production export, and training state.
- Recovery validation runs through the recorded venv launcher and passes.
- Receipt-verified lifecycle reconciliation continues through all native actions.
- Production exports exactly 1,000 verified rows.
- Gemma consumes that export for exactly one optimizer step.
- No evaluator, score, promotion, or later AAR iteration starts.

## Stop criteria

Stop on recovery provenance drift, validator-environment drift, duplicate native
action begin, stale semantic outcome, mutation outside
`recipe/generation_strategy.json`, failed native receipt verification, more than
one optimizer step, or any evaluator process.
