# Run 12 Canary 2 v2: held-out-valid data-to-training gate

**Experiment code branch:** `autodata`

- Status: preflight-complete; launch retry pending after proof-path repair
- Created: 2026-10-11 19:33 PT
- Last updated: 2026-10-11 19:50 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 19:33 PT

Prove one complete AutoData data-to-training lifecycle with the combined recipe
`aar/autodata_recipes/dishonest_sycophancy_concealing_v2`. The trusted host
must block production unless meta-optimization selects a held-out-valid winner,
then monitor accepted-row yield while producing exactly 1,000 retained rows
from 1,250 production tasks and complete one real-GPU optimizer-step training
smoke. No evaluator is used.

## Context

Recorded: 2026-10-11 19:33 PT

This gate succeeds Canary 2 Trial 15. Trial 15 was intentionally stopped at
2026-10-11 19:19 PT after production had accepted only 1 of 319 processed
tasks. Meta-optimization had completed, but the baseline and final selected
winner both reported `constraints.valid=false`. Trusted orchestration
incorrectly entered production despite the invalid final winner.

Canary 2 v2 addresses that boundary directly. It combines the dishonest,
sycophancy, and concealment requirements in the v2 recipe, makes held-out
validity a strict pre-production prerequisite, and treats accepted-row yield as
a continuously monitored lifecycle-health signal rather than waiting for an
unproductive production run to finish.

## Model and execution roles

Recorded: 2026-10-11 19:38 PT

The user confirmed all assignments and lifecycle settings below at 19:38 PT.
The future checked-in configuration must match this contract exactly; any
change to a role, deployment, model, concurrency, or lifecycle setting requires
new confirmation before launch:

- Researcher: Kimi-K2.6 through logical deployment `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 through logical deployment
  `autodata_8-kimi26`.
- Target probe and training base: fixed Gemma 4 31B through logical deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Model API.
- Proposal monitor, lifecycle supervisor, broker, comparator, orchestration,
  validity gate, yield monitor, and approvals: deterministic trusted code from
  pinned AAR and AutoData source snapshots.
- Evaluator inference model and evaluator judge: not used; evaluator disabled.

## Launch

Recorded: 2026-10-11 19:33 PT

The strict run configuration, combined recipe, trusted pre-production validity
gate, accepted-yield monitor, and thin shared-submitter launcher are prepared
and locally validated. The `$44,448` campaign ceiling was approved at 19:44 PT.
Do not launch until the source is committed, synchronized, and validated on
HPC.

After those prerequisites pass, the only operator entrypoint is:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2_v2/submit_canary.sh
```

The wrapper fails closed on branch, experiment ID, mode, seed, target-pair
count, config identity, retained canary-proof root, and fixed target deployment
before delegating to the shared Run 12 submitter. The proof root is pinned to
the retained, verifier-approved bundle
`/checkpoint/ram/winnieyangwn/aar-runs/run12-adapter-target/20261011T221515Z-b6db78771f9c`.

Local compilation, artifact-integrity validation, shell syntax, ShellCheck,
fail-closed wrapper checks, and 198 relevant focused Python tests pass. The one
excluded Run 17 config test depends on pre-existing user-deleted Run 17 files
outside this change. Launch now remains blocked only by the immutable
commit/synchronization and HPC validation.

## Plan

Recorded: 2026-10-11 19:33 PT

1. Implement and validate the combined
   `dishonest_sycophancy_concealing_v2` recipe and its held-out constraints.
2. Add a trusted pre-production gate that requires the selected final winner's
   held-out `constraints.valid` value to be exactly `true`.
3. Encode meta-optimization minimum 3, maximum 10, and early-stop patience 3.
   A meaningful accepted improvement is a durable candidate promotion whose
   paired comparator improvement is at least `0.01` and whose `valid`,
   `quality`, and `challenge` constraints all pass.
4. Add accepted-row yield telemetry and a fail-closed forecast against the
   frozen 1,250-task, 1,000-row production contract.
5. Validate the prepared strict config and thin shared launcher locally and on
   HPC with the completed implementation.
6. Obtain approval for the compiler-required `$44,448` ceiling, verify the
   resolved configuration matches the confirmed role mapping, and launch one
   chain only after every prerequisite passes.

## Configuration and invariants

Recorded: 2026-10-11 19:33 PT

- Exactly one isolated AutoData/AAR chain.
- Overall task concurrency: 8.
- Model HTTP transport attempts: 3.
- Recipe root:
  `aar/autodata_recipes/dishonest_sycophancy_concealing_v2`.
- Exact disjoint task partitions: 64 tuning, 32 validation, and 32 held-out
  test tasks.
- Meta-optimization: minimum 3 iterations, maximum 10 iterations, and
  early-stop patience 3 consecutive rounds without meaningful accepted
  improvement. A meaningful improvement is a durable candidate promotion with
  paired improvement at least `0.01` and passing `valid`, `quality`, and
  `challenge` constraints; it resets the patience counter.
- Production may begin only when the selected final winner has held-out
  `constraints.valid=true`. If early stopping or the maximum iteration limit
  leaves no held-out-valid winner, fail closed before production.
- Production contract: 1,250 source tasks and exactly 1,000 retained accepted
  rows, with live accepted count, processed count, yield, and attainable-row
  ceiling retained as trusted telemetry.
- Training boundary: consume the verified handoff and complete exactly one
  real-GPU optimizer-step smoke with a non-empty loadable adapter.
- Trusted worst-case accounting reserves 4,100 task attempts and 14,900 model
  semantic rounds. It requires `$44,447.296`; the prepared config uses the
  smallest whole-dollar ceiling, `$44,448`. Trial 15's `$41,775` ceiling is
  insufficient for the 10-iteration maximum.
- Stop after verified training smoke; evaluator disabled.
- The prepared config is not launch authorization.

## Pass criteria

Recorded: 2026-10-11 19:33 PT

- The combined v2 recipe and exact partitions pass contract and isolation
  checks without weakening any of the three behavior dimensions.
- Meta-optimization runs at least 3 and at most 10 iterations; any early stop
  is supported by durable evidence of three consecutive rounds without the
  frozen definition of meaningful accepted improvement.
- The selected final winner has held-out `constraints.valid=true`, and the
  trusted gate proves that production started only after verifying it.
- Production retains exactly 1,000 contract-valid rows from 1,250 tasks, with
  complete accepted-yield and attainable-row telemetry.
- The verified 1,000-row handoff produces a real-GPU one-optimizer-step receipt
  and non-empty loadable adapter.
- No evaluator launches and no unresolved code-health warning remains.

## Stop criteria

Recorded: 2026-10-11 19:33 PT

Do not launch until the recipe, gate, yield monitor, config, launcher, source
snapshots, and confirmed role mapping are implemented and validated, and the
`$44,448` campaign ceiling is approved. Once launched, stop and preserve
evidence if the selected winner is not held-out-valid; production starts
before validity is proved; three-round early stopping is miscounted;
partitions or identities drift; accepted yield makes 1,000 rows unattainable
under the frozen production contract; retries make no durable progress; the
handoff or training smoke is invalid; or any evaluator activity appears.

## After a pass

Recorded: 2026-10-11 19:33 PT

Retain the resolved configuration, source and model identities, meta-iteration
history, per-round accepted-improvement evidence, held-out-validity proof,
production-entry authorization, yield trajectory, exact handoff and consumption
receipts, GPU training-smoke receipt, adapter manifest and hashes, job IDs, and
phase timings. A pass authorizes review of this one-chain gate only; it does not
authorize evaluation, promotion, or higher-scale execution.
