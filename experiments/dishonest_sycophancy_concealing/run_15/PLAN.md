# Run 15 execution plan

## Objective

Run five independent Kimi AAR chains against the same multidimensional Gemma-4
evaluation used by Run 12, while each researcher implements its own training
data generation without AutoData. Each chain targets 50 complete score/finding
pairs and may start at most 60 research sessions, for 250 target pairs across
the run and up to 10 unsuccessful sessions of headroom per chain.

## Invariants

- `config/run.yaml` resolves `data_generation.backend: native` to
  `AAR_AUTODATA=0`.
- No AutoData checkout, plugin, broker, recipe, lifecycle state, judge, target
  binding, or production export is initialized.
- The five seeds are `alpha`, `beta`, `gamma`, `delta`, and `epsilon`.
- Every chain targets 50 complete score/finding pairs and has a 60-session
  ceiling. Unsuccessful sessions consume the ceiling but not the target.
- Every method declares reproducible data provenance and passes the proposal
  monitor and source-bound method contract before GPU submission.
- Benchmark and held-out items remain unavailable to research chains.
- By default, full launch metadata retains both ordered lifecycle proofs,
  verifies that the five-chain proof is SHA-256-bound to the exact one-chain
  proof, and records the hash of each retained copy. An exact explicit
  user-authorized bypass may replace those proofs only when its scope, source
  commit, and researcher deployment are durably recorded and validated.
- Every launch executes from an independent detached clone of the exact clean
  source commit under the attempt runtime. The clone has no remote or shared
  object alternates, and the scheduled pipeline rejects source/config drift
  before starting any child job.

## Ordered gates

1. Validate YAML resolution, shell syntax, focused unit contracts, and the
   shared method/failure-feedback hardening.
2. Produce and retain a passed one-chain native-generation proof: one research session,
   one real optimizer step, a two-item `verbalized_ece` evaluation, and one
   matching finding, with no AutoData process or artifact.
3. Run a five-chain topology check bound to that exact one-chain
   proof. Use one session per seed, five parallel research chains, the bounded
   real-GPU smoke path, and one on-demand evaluator.
4. Require five complete score/finding pairs and a passed topology proof. A
   partial adapter count, aggregate score-file count, or session count is not a
   pass.
5. Reconfirm the exact model-role mapping and synchronize the exact clean
   source revision to the matching HPC `autodata` worktree.
6. Create and validate the attempt-local immutable source snapshot before the
   endpoint preflight and scheduler submission.
7. Launch the full run with both exact proof files by default, or with the
   narrowly scoped recorded user override confirmed on 2026-10-11. Require
   five distinct research jobs and five distinct evaluator jobs in retained
   metadata before reporting the run active.
8. Monitor each isolated chain until it reaches 50 complete pairs or exhausts
   60 sessions. Preserve and report terminal state rather than resetting
   retained work.

## Pass conditions

- All five chains publish 50 complete score/finding pairs joined by run ID.
- All 250 counted results have source-bound training receipts and evaluator
  provenance for vLLM 0.25.1, language-model-only mode, and an atomically
  merged exact adapter.
- No chain starts more than 60 sessions.
- Attempt metadata retains the resolved config, source commit, immutable
  source-snapshot root and manifest hash, model identity, child job IDs, either
  both ordered proofs and hashes or the validated user-override record,
  baseline/source provenance, and evaluator runtime snapshot.

## Stop conditions

Stop before scale-up if neither correctly bound lifecycle proofs nor the exact
validated user override is present; if the configured budget differs from 50 successful pairs
and 60 sessions per chain; if model roles are unconfirmed; if AutoData loads;
if data provenance or the method contract fails; if the real-GPU adapter smoke
or score/finding join fails; or if evaluator-only data is exposed to research.

For an active full attempt, stop or recover from preserved state when a shared
orchestration defect makes further work unsafe. Never delete or reset completed
sessions, receipts, adapters, scores, findings, or logs to obtain a clean retry.
