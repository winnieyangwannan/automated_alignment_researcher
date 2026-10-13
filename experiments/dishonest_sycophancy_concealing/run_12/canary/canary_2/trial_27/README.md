# Run 12 Canary 2 Trial 27

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-12 18:00 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Run one fresh Kimi Canary 2 lifecycle with Trial 26's exact model, budget,
retry, task-count, concurrency, coordinator, and host-wait settings. The only
behavioral change under test is a targeted `clarify_design` semantic-worker
prompt correction.

## Context

Trial 26 proved that outer Kimi yielded `clarify_design` to the shared typed
coordinator, but the isolated Kimi worker exhausted three typed-output attempts
before native completion. The targeted correction tells the worker that the
native workspace already passed schema validation, forbids inventing absent
top-level fields, requires updates to preserve the existing top-level keys and
types, and makes explicit that `goal`, `intended_use`, and
`source_constraints` can already constitute complete design intent. In that
case the correct outcome is `decision='confirm'` with no replacement document.

This is a live probe of that one correction. It does not widen coordinator
ownership or alter lifecycle settings. Trial 26 evidence remains immutable.

## Launch

After the targeted implementation, focused tests, commit, and exact-commit HPC
synchronization:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_27/submit_canary.sh
```

## Preserved execution envelope

- Outer researcher and typed semantic worker: Kimi-K2.6 via `aar_8-kimi26`.
- Generator: Kimi-K2.6 via `autodata_8-kimi26`.
- Target/training base: fixed Gemma 4 31B deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna`; evaluator disabled.
- One alpha chain, concurrency 8, request attempts and generation retries
  unchanged.
- Meta-optimization: disjoint 64/32/32 partitions, 3–10 iterations, patience
  3.
- Production: 1,250 initial tasks for exactly 1,000 accepted rows.
- Stop after verified training smoke; campaign ceiling `$44,448`.
- Shared typed coordinator enabled for `clarify_design`, `author_grounding`,
  `author_pipeline`, `analyze_results`, and `mutate_candidate`; signed shared
  approval coordination retained.
- Host-only wait remains 28,800 seconds. Training-smoke coordination and full
  lifecycle ownership remain unset exactly as in Trial 26.

The configuration differs from Trial 26 only in `run_id`:
`run12-canary2-trial27`.

## Monitoring

Legend: `✓` live-proven in Trial 27, `△` implemented/tested but not live-proven,
`✗` failed or blocked, and `○` not reached.

```text
AAR research and method proposal
  ○ literature/method recovery
  ○ method validation and proposal approval
             │
             ▼
AutoData workspace
  △ clarify_design — targeted Kimi prompt correction
  △ author_grounding — shared typed coordinator with Kimi
  ○ approve_grounding — shared signed trusted approval
  △ author_pipeline — shared typed coordinator with Kimi
             │
             ▼
Workspace finalization
  ○ authoring dry run, approve baseline, and freeze
             │
             ▼
Meta-optimization
  △ analyze_results — shared typed coordinator with Kimi
  △ mutate_candidate — shared typed coordinator with Kimi
  ○ held-out-valid winner and export
             │
             ▼
Production
  ○ 1,250 tasks / exactly 1,000 accepted rows
             │
             ▼
Gemma training
  ○ consume export and perform one optimizer step
  ○ verify receipt and PEFT adapter
             │
             ▼
Stop at training_smoke
  ○ not reached; evaluator intentionally disabled
```

## Stop criteria

Stop and preserve evidence on malformed semantic output exhaustion, schema or
digest mismatch, duplicate action ownership/completion, lease exposure,
accepted mutation no-op, coordinator stall, invalid winner, unattainable
production yield, training failure, or evaluator activity. Never repair an
active attempt.
