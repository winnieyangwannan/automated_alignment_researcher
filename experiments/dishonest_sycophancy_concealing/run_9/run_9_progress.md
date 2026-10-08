# Run 9 progress

This file is the durable handoff for the five-successful-iteration AAR campaign.
All retained outputs are under `/storage/home/winnieyangwn/aar-runs`; shared
`/checkpoint/ram` inputs are read-only.

## 2026-10-08 — implementation and prelaunch

- Approved configuration is recorded in `aar_run_plan.md`.
- AutoData native early stopping now enforces maximum 10, minimum 3, and
  patience 3 in its own execution engine.
- The attempt-scoped broker policy binds the image, SandoQ tier, resource
  ceiling, Kimi/Luna identities, token ceilings, rates, and campaign cost cap.
- Broker reservations and provider-usage reconciliation share one SQLite
  ledger across the sequential chain.
- The research process receives only a policy-limited broker capability. The
  SandoQ and provider credentials remain in the trusted broker process.
- Production-batch consumption verifies native exports, unique rows, fixed
  judge threshold, model provenance, and retains exactly the requested target.
- The outer loop stops only after five durable score/result intersections, with
  eight researcher sessions as the hard ceiling.
- Upstream AutoData tests: 66 passed, 1 skipped (host blocks unprivileged user
  namespaces). AutoData commit: `f6da400ed9bd03e89919f95656213433a6a93405`.
- AAR tests before admission: 230 passed with 35 subtests. The focused native
  canary regression tests subsequently passed 2/2 and Ruff passed. AAR commit
  before this progress update: `5ca219bc993d1deb0bd7d3fbe6a32d5e04d1dbb9`.

## 2026-10-08 — concurrency admission

- The concurrency-16 gate at
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/concurrency-gate-20261008`
  reached signed grounding approval, then repeatedly received SandoQ `429 pool
  exhausted` before its next lease. Its exact processes were stopped and all
  artifacts were preserved. Per the approved fallback rule, the campaign is
  pinned to concurrency 8.
- Two concurrency-8 diagnostic attempts found fail-closed canary-driver budget
  accounting errors after all submitted broker tasks succeeded. Their preserved
  roots are `concurrency-gate-8-20261008` and
  `concurrency-gate-8-rerun-20261008`. The driver now budgets every native meta
  phase plus bounded replenishment headroom.
- A third preserved attempt at `concurrency-gate-8-final-20261008` exposed an
  ambiguous idempotent broker request: the server durably created the job but
  replied after the client's timeout. The canary now retries the persisted
  native step up to three times only for broker reachability failures.
- The terminal concurrency-8 gate passed at
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/concurrency-gate-8-pass-20261008`.
  It used the native AutoData lifecycle with real SandoQ, Kimi generation, and
  independent Luna judgment. It completed workspace creation and delegated
  approvals, meta-optimization, winner export, production generation, verified
  export, and training-side consumption in 1,737.178 seconds.
- Gate workspace: `ws_4555ea925ebb49fbb2a6a4b2edcc3f19`.
- Gate meta execution: `exe_fa8dec666edc4e7eb266972011e2fd68`.
- Gate production execution: `exe_fed7eb16316a4663ad75f72f1c40175b`.
- Gate production retained 7 accepted rows from 8 tasks. Dataset digest:
  `sha256:6d35a16d4e6ce3e9c0640f9217a31fbaaf1ca4557114b8fb807b5aeb042e7073`.
- Gate report:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/concurrency-gate-8-pass-20261008/e2e/attempt/report.json`.
- All gate brokers were stopped after their attempts. Gate artifacts and logs
  remain preserved in place.

## Live job handoff

The full campaign is ready for submission at concurrency 8. Append the attempt
root, launch job, evaluator job, chain job, logs, and exact launch commit below
after submission. A launch wrapper alone is not evidence that the AAR chain is
running.
