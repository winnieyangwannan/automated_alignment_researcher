# Run 12 Canary 2 Trial 28

**Experiment code branch:** `autodata`

- Status: failed closed; terminal
- Created: 2026-10-12 21:00 PT
- Last updated: 2026-10-12 21:58 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Run one fresh Kimi Canary 2 lifecycle with Trial 27's exact model, budget,
retry, task-count, concurrency, coordinator, and host-wait settings. The only
behavioral change under test is an explicit top-level response-shape prompt for
the confirm-only `author_grounding` and `author_pipeline` semantic actions.

## Context

Trial 27 live-proved coordinated `clarify_design`, then failed closed at
`author_grounding`. Kimi returned its decision inside the `decisions` array but
omitted the required top-level `decision` string. The targeted correction
shows the complete JSON response shape and explicitly states that `decision`
is a top-level string. It does not weaken validation, alter the typed outcome,
or change coordinator ownership.

Trial 28 subsequently passed authoring and workspace freeze, then failed before
meta baseline because its copied `$44,448` cap was below the trusted
`$64,523.1552` requirement for `21,630` worst-case reservations. Its retained
attempt is terminal.

A bounded live probe against Trial 27's exact saved grounding action passed:
Kimi returned the bound action ID, revision, and digest; a top-level
`decision='confirm'`; non-empty `summary` and `decisions`; and
`updated_workspace=null`. The equivalent pipeline prompt uses the same shape.

## Launch

Do not relaunch Trial 28. Its source cap is intentionally retained for
provenance. Use Trial 29, which derives the cap automatically.

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
  lifecycle ownership remain unset exactly as in Trial 27.

The configuration differs from Trial 27 only in `run_id`:
`run12-canary2-trial28`.

## Monitoring

Legend: `✓` live-proven in Trial 28, `△` implemented/tested but not live-proven,
`✗` failed or blocked, and `○` not reached.

```text
AAR research and method proposal
  ✓ literature/method recovery
  ✓ method validation and proposal approval
             │
             ▼
AutoData workspace
  ✓ clarify_design — shared typed coordinator
  ✓ author_grounding — shared typed coordinator
  ✓ approve_grounding — shared signed trusted approval
  ✓ author_pipeline — shared typed coordinator
             │
             ▼
Workspace finalization
  ✓ authoring dry run, approve baseline, and freeze
  ✗ trusted campaign-cap validation
             │
             ▼
Meta-optimization
  ○ baseline generation
  ○ analyze_results — shared typed coordinator with Kimi
  ○ mutate_candidate — shared typed coordinator with Kimi
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
