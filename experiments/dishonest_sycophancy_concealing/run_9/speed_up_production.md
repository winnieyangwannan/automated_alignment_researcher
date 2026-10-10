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
| 3 | Job `1795876`; node-local native SQLite; authenticated loopback bridge to the unchanged healthy Kimi deployment; local-bwrap concurrency 16 | A one-row end-to-end canary first succeeded in 11s with Kimi and Luna usage, quality 1.0, and valid 1.0. The five-minute production window then added 303 successful model tasks with no transport/parse failures; 231 were judge-accepted. The retained snapshot passed its digest, SQLite integrity, and stale-sidecar checks. | 303 tasks / 303s = 60.0 tasks/min; 231 accepted / 303s = 45.7 accepted rows/min; 1.31s per accepted row aggregate | The routing and SQLite fixes work. Total accepted is 278/1,000. Test concurrency 24 for two minutes and retain it only if accepted throughput rises without model failures. |
| 4 | Job `1795961`; broker limit 24 requested; two-minute window | The native execution remained pinned to concurrency 16, so only 15–16 tasks ran at once. After a 71s recovery scan, it added 61 successful tasks and 47 accepted rows with no model failures. | Full window: 23.1 accepted rows/min. Post-scan steady state: about 68.8 accepted rows/min. | Not a valid concurrency-24 comparison. Record and apply the requested execution concurrency as an infrastructure-only recovery change, then repeat. Total accepted is 325/1,000. |
| 5 | Job `1796003`; execution and broker both set to concurrency 24; five-minute observation window | The broker sustained 23–24 tasks in flight. After a 148s recovery scan, the run added 211 successful model tasks, including 164 newly accepted rows, with no new model/parse failures. Durable state passed `PRAGMA quick_check`. The observation stop occurred after the first pass over all 1,250 source tasks; 596 earlier gateway failures and 148 judge-rejected empty results remain eligible for AutoData's selective final retry. | Full job: 164 accepted / 337s = 29.2 accepted rows/min. Active generation: 211 tasks / 134s = 94.5 tasks/min and 164 accepted / 134s = 73.4 accepted rows/min. | Concurrency 24 is stable and improves active successful-task throughput by about 57% over Attempt 3's measured 60.0 tasks/min. Retain 24 for completion. Total accepted is 489/1,000; 511 remain. |
| 6 | Job `1796067`; uncapped completion at concurrency 24; restored the prior retained broker ledger | After the recovery scan, one retry succeeded and was accepted. The next retry failed closed with broker HTTP 409: its idempotency key existed in the old broker ledger with a different job specification from before the Kimi routing repair. The job was cancelled after 3m02s and retained native state remained valid. | 1 accepted row; not a throughput measurement | Do not restore a broker transport ledger across repaired recovery attempts. Start each attempt with a fresh node-local ledger, archive it under the unique attempt label, and rely on native AutoData state for durable task reconciliation. Total accepted is 490/1,000; 510 remain. |
| 7 | Job `1796231`; fresh attempt-local broker ledger; uncapped completion at concurrency 24 | Reconciled 16 orphaned tasks, then sustained 23–24 concurrent retries without broker conflicts or transport failures. Native AutoData reached terminal `completed` and emitted a digest-verified 1,083-row SFT dataset from 1,250 source tasks. All source tasks have a successful terminal result; the retained SQLite snapshot passes `PRAGMA quick_check`. | Full job: 593 accepted / 643s = 55.3 accepted rows/min. Active generation: 761 task completions / 549s = 83.2 tasks/min and 593 accepted / 549s = 64.8 accepted rows/min. | Production recovery succeeded. Dataset digest: `sha256:968ebf53895811fbd227855c29f051b46133410fdf4265e9f738e9ac2159ea93`; artifact size: 4,346,885 bytes. Resume AAR consumption, training, and evaluation. |

## Completion attempt

Attempt 7 completed this plan successfully. The retained production execution
is terminal `completed`, and the final dataset contains 1,083 rows, exceeding
the 1,000-row requirement by 83.

The completion attempt will use:

- a node-local live native SQLite database restored from an immutable retained
  snapshot;
- periodic online SQLite backups with integrity checks and SHA-256 manifests;
- a fresh node-local broker ledger archived under the unique attempt label, so
  obsolete job specifications cannot collide with retry idempotency keys;
- AutoData `823c5948854df14664f3168bc5e6c49a2cecb975`, which includes serialized
  writes, recovery reconciliation, selective final retries, and target-aware
  production stopping;
- the unchanged local-bwrap broker at validated concurrency 24;
- an explicit 25-hour controller ceiling, which exceeds the retained native
  24-hour wall budget plus its ten-minute shutdown grace;
- no artificial observation cutoff; the supervisor will run until native
  finalization reaches a terminal state.

It will start only after one end-to-end task produces non-empty provider usage
and a non-`model_or_parse_failure` result. At the end of Attempt 2 the shared
gateway ingress returned HTTP 503, while deployment `winnieyangwn-kimi26`
remained healthy with one ready endpoint and zero load. Raising AutoData
concurrency cannot help that condition.

Attempt 5 validated 24-way concurrency on the current one-endpoint, four-GPU
Kimi deployment. Concurrency 32 is deliberately skipped for this recovery:
24 already keeps the endpoint busy, and another short probe would pay the
roughly 2.5-minute retained-state scan again without reducing the remaining
work enough to justify the delay.
