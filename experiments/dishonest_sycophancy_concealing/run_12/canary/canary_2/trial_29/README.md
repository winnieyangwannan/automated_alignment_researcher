# Run 12 Canary 2 Trial 29

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-12 21:55 PT
- Last updated: 2026-10-12 21:58 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 21:55 PT

Prove one complete Kimi-driven AutoData lifecycle through verified Gemma
training smoke while live-proving automatic trusted campaign-cap derivation.

## Context

Recorded: 2026-10-12 21:55 PT

Trial 28 passed workspace authoring and freeze, then failed before meta baseline
because its copied `$44,448` campaign ceiling was below the newly calculated
`$64,523.1552` requirement. Trial 29 preserves every model and lifecycle
setting but declares `budget.max_cost_usd: auto`. Trusted compilation derives
the exact numeric ceiling from the validated workload and provider bounds, and
only the numeric result is written to runtime artifacts.

## Launch

Recorded: 2026-10-12 21:55 PT

After focused tests, commit, and exact-commit HPC synchronization:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_29/submit_canary.sh
```

## Model and execution roles

Recorded: 2026-10-12 21:58 PT

- Outer researcher: Kimi-K2.6 through Kimi Code, logical deployment
  `aar_8-kimi26`.
- Typed semantic worker for clarify, grounding, pipeline, analysis, and
  mutation actions: isolated Kimi-K2.6 through `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 through the OpenAI chat-completions-compatible
  FAIR gateway, logical deployment `autodata_8-kimi26`.
- Proposal and grounding-integrity monitor: Claude 4.8 Opus
  (`claude-4-8-opus`) through FAIR Model API.
- Baseline approval: deterministic trusted policy; no model controls it.
- Target and training base: fixed Gemma 4 31B deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7` through the target vLLM path; fixed-base
  mode with no promoted adapter.
- Row judge: Luna `gpt-5-6-luna` through Model API Responses JSON Schema.
- Evaluator inference and evaluator judge: intentionally disabled.
- Trusted orchestration, cap derivation, approvals, execution construction, and
  lifecycle reconciliation: deterministic AAR/AutoData host code.

## Plan

Recorded: 2026-10-12 21:55 PT

Use one alpha chain at concurrency 8, disjoint 64/32/32 meta partitions,
3–10 iterations with patience 3, 1,250 production tasks for exactly 1,000
accepted rows, and stop after verified training smoke. The compiler must resolve
`auto` to exactly `$64,523.1552` for the current `21,630` worst-case semantic
rounds before submission proceeds.

## Pass criteria

Recorded: 2026-10-12 21:58 PT

- Compiled and runtime campaign policies contain the exact numeric derived cap,
  never the `auto` sentinel.
- Meta-optimization selects and exports a held-out-valid winner.
- Production publishes exactly 1,000 accepted rows from the configured 1,250
  initial tasks with an authoritative handoff.
- Training consumes that export, completes one Gemma optimizer step, and emits
  a verified training-smoke receipt plus a nonempty PEFT adapter.
- No evaluator runs and no isolation boundary is crossed.

## Stop criteria

Recorded: 2026-10-12 21:58 PT

Stop and preserve evidence on source/config mismatch, unresolved or incorrect
cap, malformed semantic-output exhaustion, schema/digest/receipt mismatch,
duplicate action ownership or completion, lease exposure, coordinator stall,
accepted mutation no-op, invalid winner, unattainable production yield,
training failure, or evaluator activity. Never repair an active attempt.

## After a pass

Recorded: 2026-10-12 21:58 PT

Retain the exact compiled cap, source/config hashes, native receipts, production
handoff, and training-smoke proof. Treat `max_cost_usd: auto` as the default for
future runs; change workload or provider bounds in source config rather than
copying a previously derived number.

## Monitoring

Recorded: 2026-10-12 21:55 PT

Legend: `✓` live-proven, `△` implemented/tested but not live-proven, `✗` failed,
and `○` not reached.

```text
AAR research and method proposal
  ○ literature/method recovery
  ○ method validation and proposal approval
             │
             ▼
AutoData workspace
  △ clarify_design — shared typed coordinator
  △ author_grounding — shared typed coordinator
  △ approve_grounding — shared signed approval
  △ author_pipeline — shared typed coordinator
             │
             ▼
Workspace finalization
  △ dry run, baseline approval, and freeze
  △ automatic exact campaign-cap derivation
             │
             ▼
Meta-optimization
  ○ baseline generation
  ○ analyze_results and mutate_candidate loop
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
