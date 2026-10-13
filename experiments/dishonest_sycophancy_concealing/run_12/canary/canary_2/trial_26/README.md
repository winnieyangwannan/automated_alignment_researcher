# Run 12 Canary 2 Trial 26

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-12 16:54 PT
- Last updated: 2026-10-12 17:04 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 16:54 PT

Run one fresh Kimi Canary 2 lifecycle using Trial 25's exact model and
operational settings while routing `author_grounding`, `author_pipeline`,
`analyze_results`, and `mutate_candidate` through the same shared typed
coordinator implementations used by Claude.

## Context

Recorded: 2026-10-12 16:54 PT

Trial 25 live-proved coordinated Kimi `clarify_design`, the shared proposal and
workspace bootstrap, and shared signed approvals. It completed three native
meta-optimization iterations, but outer Kimi handled `analyze_results` and
`mutate_candidate` through the legacy action-result loop and produced accepted
semantic no-ops. The final held-out evidence was invalid, so the shared
production gate stopped the run before production.

Trial 26 is a focused coordinator-parity canary. It retains Trial 25's model,
deployment, budget, task counts, recipe, retry settings, and terminal target.
The only run-config change is the fresh run ID `run12-canary2-trial26`. Its
launcher additionally delegates the four named semantic actions to the shared
coordinator with the Kimi worker and gives host-only waiting an eight-hour
ceiling so the previously observed 4.5-hour production stage cannot exhaust the
old three-hour wait. Training-smoke coordination and whole-lifecycle ownership
remain unchanged.

## Launch

Recorded: 2026-10-12 16:54 PT

Not launched. After the focused Kimi ownership integration and this trial
record are committed, tested, and synchronized by exact commit to the matching
HPC worktree, run:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_26/submit_canary.sh
```

## Plan

Recorded: 2026-10-12 16:54 PT

1. Create fresh state and preserve all Trial 25 evidence.
2. Retain the shared proposal/bootstrap, `clarify_design`, and approval paths
   already live-proven with Kimi.
3. Route `author_grounding` and `author_pipeline` through their existing shared
   typed reconcilers with the isolated Kimi semantic worker.
4. Route every native `analyze_results` and `mutate_candidate` action through
   the existing shared typed reconcilers with the same isolated Kimi worker.
5. Require outer Kimi to yield each coordinator-owned action so that exactly
   one component owns every lease and native completion.
6. Reject any unchanged mutation before native completion and fail closed if
   the worker exhausts its bounded typed-output attempts.
7. Continue through production and verified one-step training smoke, then stop.

## Model and execution roles

Recorded: 2026-10-12 16:54 PT

- Outer AAR researcher: Kimi-K2.6 via `aar_8-kimi26` and Kimi Code.
- Shared typed semantic worker for `clarify_design`, `author_grounding`,
  `author_pipeline`, `analyze_results`, and `mutate_candidate`: isolated
  Kimi-K2.6 via `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 via `autodata_8-kimi26`.
- Grounding integrity monitor: Claude Opus through the existing shared monitor.
- Baseline approval: existing deterministic operational policy; no model.
- Target/training base: fixed Gemma 4 31B deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Meta Model API.
- Lifecycle, proposal binding, broker, leases, approvals, native state,
  digests, and receipts: pinned deterministic AAR/AutoData code.
- Evaluator inference and evaluator judge: not used; evaluator disabled.

## Configuration and invariants

Recorded: 2026-10-12 16:54 PT

- One alpha chain; concurrency 8.
- Native AutoData commit `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Recipe `aar/autodata_recipes/dishonest_sycophancy_concealing_v2`.
- Disjoint 64/32/32 meta partitions; minimum 3, maximum 10, patience 3.
- Production: 1,250 tasks to exactly 1,000 accepted rows.
- Campaign ceiling `$44,448`; stop after verified training smoke.
- Trial 25's settings are retained except for the fresh run ID, the four
  additional shared semantic-action coordinator flags, and the host-only wait
  ceiling described below.
- Trial-local host wait: 28,800 seconds, above the previously observed
  approximately 4.5-hour production runtime.
- `AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR` and
  `AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE` remain unset.

## Monitoring

Recorded: 2026-10-12 16:54 PT

Status reports use this lifecycle view. Legend: `✓` live-proven in this trial,
`△` implemented/tested but not yet live-proven in this trial, `✗` failed or
blocked, and `○` not reached.

```text
AAR research and method proposal
  ○ literature/method recovery
  ○ method validation and proposal approval
             │
             ▼
AutoData workspace
  ○ create/register fresh workspace
  ○ clarify_design — shared typed coordinator
  △ author_grounding — shared typed coordinator with Kimi
  ○ approve_grounding — shared signed trusted approval
  △ author_pipeline — shared typed coordinator with Kimi
             │
             ▼
Workspace finalization
  ○ post-pipeline reconciliation
  ○ authoring dry run and approve_baseline
  ○ freeze workspace and create canonical meta execution
             │
             ▼
Meta-optimization
  ○ baseline generation
  △ analyze_results — shared typed coordinator with Kimi
  △ mutate_candidate — shared typed coordinator with Kimi
  ○ complete the 3–10 iteration optimization loop
  ○ finalize and export a held-out-valid winning pipeline
             │
             ▼
Production
  ○ create/run production execution
  ○ generate 1,250 fresh tasks
  ○ retain 1,000 accepted rows
  ○ publish verified dataset handoff
             │
             ▼
Gemma training
  ○ consume the real production export
  ○ perform one optimizer step
  ○ verify consumption receipt and PEFT adapter
             │
             ▼
Stop at training_smoke
  ○ not reached
  ○ evaluator intentionally disabled
```

## Pass criteria

Recorded: 2026-10-12 16:54 PT

- Shared proposal/bootstrap, coordinated `clarify_design`, and both shared
  approval actions retain their prior single-owner behavior.
- Each of `author_grounding`, `author_pipeline`, `analyze_results`, and
  `mutate_candidate` completes through its existing shared typed reconciler and
  isolated Kimi worker, with exactly one native begin/completion and matching
  authoritative receipt, revision, and digest evidence.
- Outer Kimi receives no lease, action-result-file instruction, or native
  completion authority for a coordinator-owned action.
- Every accepted `mutate_candidate` operation changes the allowed candidate
  digest and responds to the dominant evidence, including
  `target_not_challenging`, challenge/valid margins, and generator attempts.
- A held-out-valid winner produces exactly 1,000 accepted rows and a verified
  one-step training-smoke receipt; no evaluator activity occurs.

## Stop criteria

Recorded: 2026-10-12 16:54 PT

Stop and preserve evidence on duplicate ownership, duplicate native action
completion, any legacy result-file instruction for a coordinator-owned action,
lease exposure, receipt/revision/digest mismatch, accepted mutation no-op,
coordinator stall, invalid winner, unattainable production yield, training
failure, or evaluator activity. Never repair an active attempt.

## After a pass

Recorded: 2026-10-12 16:54 PT

Retain source/configuration hashes, proposal and workspace binding, shared
semantic-action audits, coordinator/native receipts, mutation before/after
digests, winner proof, production handoff, training receipt, job IDs, and phase
timings. Decide whether to migrate later lifecycle boundaries only from this
live evidence.
