# Run 9 production speed-up log

This log records measured production-recovery attempts for native AutoData
execution `exe_570e1daeb28c4a7795a2be9fac37fdf9`. A speed-up counts only durable
`task_attempt.completed` events and accepted exported rows. The
`taskAttemptsUsed` reservation counter is not treated as completed throughput.

## Measurement contract

- Preserve the original retained database and all failed-attempt logs.
- Use the frozen production pipeline and manifest; orchestration fixes must not
  mutate generated examples, the rubric, or source-task inputs.
- Record durable completed tasks before and after each attempt, elapsed wall
  time, broker jobs, endpoint activity, errors, and retained-state digest.
- Run the hot native SQLite database on node-local storage and publish only
  integrity-checked, digest-recorded snapshots to retained storage.
- Stop production retries once native finalization confirms the configured
  accepted-row and coverage targets.

## Attempts

| Attempt | Configuration | Result | Durable rate | Decision |
| ------- | ------------- | ------ | ------------ | -------- |
| 0 | Recovery job `1795274`; AutoData `223af462`; hot native SQLite on network storage; local-bwrap concurrency 16 | Cancelled at user request after 19m07s. Durable completions stayed at 62, the new broker ledger received zero jobs, and Kimi reported zero load while `taskAttemptsUsed` rose. The CLI held many simultaneous handles to the network-mounted SQLite database. | 0 new rows / 19m07s = 0 rows/min | Confirmed orchestration/SQLite as the pre-inference bottleneck. Do not raise concurrency on this configuration. |
| 1 | Job `1795630`; node-local native SQLite; AutoData `823c594`; local-bwrap concurrency 16; five-minute observation requested | Failed closed after 35s before model work. Restore, broker health, execution registration, and metrics succeeded, but the supervisor rejected the existing execution's 24-hour native wall budget because its default production ceiling was eight hours. The failure-status snapshot originally obscured the error by rewriting status to `running`. | 0 new rows; 0 broker jobs; no inference cost | Add an explicit 25-hour production-controller ceiling for this retained execution and preserve `failed` supervisor status after its final snapshot. Retry without changing the frozen pipeline. |
| 2 | Job `1795675`; node-local native SQLite; AutoData `823c594`; local-bwrap concurrency 16; corrected controller ceiling | Infrastructure processed 596 new tasks in 304s with 15–16 continuously in flight and no broker failures. Outcome validation then showed that all 596 were `model_or_parse_failure` with empty provider usage: the cluster inference gateway returned HTTP 503, so no request reached healthy Kimi. The main retained snapshot is valid and contains all events, but stale network-era WAL/SHM sidecars made an ordinary reader incorrectly report corruption. | 117.6 tasks/min infrastructure throughput, but 0 accepted rows/min | Preserve and remove stale retained sidecars; make restore ignore untrusted sidecars; do not increase concurrency. Repair or safely bypass the failed Kimi gateway, then run a one-row provider canary before resuming production. |

## Next attempt

The next production attempt will use:

- a node-local live native SQLite database restored from an immutable retained
  snapshot;
- periodic online SQLite backups with integrity checks and SHA-256 manifests;
- AutoData `823c5948854df14664f3168bc5e6c49a2cecb975`, which includes serialized
  writes, recovery reconciliation, selective final retries, and target-aware
  production stopping;
- the unchanged local-bwrap broker and initial concurrency 16;
- an explicit 25-hour controller ceiling, which exceeds the retained native
  24-hour wall budget plus its ten-minute shutdown grace;
- a short genuine-throughput observation window before any 24/32 concurrency
  test.

It will start only after one end-to-end task produces non-empty provider usage
and a non-`model_or_parse_failure` result. At the end of Attempt 2 the shared
gateway ingress returned HTTP 503, while deployment `winnieyangwn-kimi26`
remained healthy with one ready endpoint and zero load. Raising AutoData
concurrency cannot help that condition.

Concurrency will increase only after completed-row throughput—not attempt
reservations—shows that SQLite is no longer the bottleneck. The current Kimi
deployment has one ready four-GPU endpoint, so endpoint saturation will be
measured before requesting additional GPU endpoints.
