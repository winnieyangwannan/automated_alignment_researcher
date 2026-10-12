# Run 16 execution plan

## Objective

Run five independent Claude Opus 4.8 AAR chains against the same multidimensional Gemma-4
evaluation used by Run 12, while each researcher implements its own training
data generation without AutoData. Each chain may start at most 50 research
sessions, matching Run 7 semantics. Failed sessions consume the ceiling, so the
run can produce at most 250 complete score/finding pairs.

## Invariants

- `config/run.yaml` resolves `data_generation.backend: native` to
  `AAR_AUTODATA=0`.
- No AutoData checkout, plugin, broker, recipe, lifecycle state, judge, target
  binding, or production export is initialized.
- The five seeds are `alpha`, `beta`, `gamma`, `delta`, and `epsilon`.
- The research backend is `claude` and the exact researcher model is
  `claude-opus-4-8` at maximum effort; every other model and execution role
  matches Run 15.
- Every chain has a 50-started-session ceiling. Unsuccessful sessions consume
  the ceiling and do not count as complete score/finding pairs.
- Every method declares reproducible data provenance and passes the proposal
  monitor and source-bound method contract before GPU submission.
- Benchmark and held-out items remain unavailable to research chains.
- Full launch metadata retains either both ordered lifecycle proofs or the
  source-bound user-authorized proof override.

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
6. Launch the full run with the user's explicit lifecycle-proof override.
   Require five distinct research jobs and five distinct evaluator jobs in
   retained metadata before reporting the run active.
7. Monitor each isolated chain until it reaches 50 complete pairs or exhausts
   50 started sessions. Preserve and report terminal state rather than
   resetting retained work.

## Pass conditions

- Every completed result is a score/finding pair joined by run ID.
- All counted results have source-bound training receipts and evaluator
  provenance for vLLM 0.25.1, language-model-only mode, and an atomically
  merged exact adapter.
- No chain starts more than 50 sessions.
- Attempt metadata retains the resolved config, source commit, model identity,
  child job IDs, both ordered proofs and hashes, baseline/source provenance,
  and evaluator runtime snapshot.

## Stop conditions

Stop before scale-up if neither valid lifecycle proofs nor the explicit
user-authorized override is present; if the configured budget differs from 50
started sessions per chain; if model roles are unconfirmed; if AutoData loads;
if data provenance or the method contract fails; if the real-GPU adapter smoke
or score/finding join fails; or if evaluator-only data is exposed to research.

For an active full attempt, stop or recover from preserved state when a shared
orchestration defect makes further work unsafe. Never delete or reset completed
sessions, receipts, adapters, scores, findings, or logs to obtain a clean retry.
