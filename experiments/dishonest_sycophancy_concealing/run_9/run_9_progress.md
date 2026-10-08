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
- The concurrency-16 admission gate and full campaign submission are pending.

## Live job handoff

Not launched yet. Append the attempt root, launch job, evaluator job, chain job,
logs, source commits, and concurrency-gate decision here after submission. A
launch wrapper alone is not evidence that the AAR chain is running.
