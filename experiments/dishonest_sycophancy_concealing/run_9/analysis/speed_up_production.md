# Run 9 production speed-up log

This log records measured production-recovery attempts for native AutoData
execution `exe_570e1daeb28c4a7795a2be9fac37fdf9`. A speed-up counts only durable
`task_attempt.completed` events and accepted exported rows. The
`taskAttemptsUsed` reservation counter is not treated as completed throughput.

## What made production fast and stable

The most important improvements, in impact order, were:

1. **Move hot native SQLite state to node-local storage.** The controller now
   restores the retained database into `$SLURM_TMPDIR`, performs live reads and
   writes there, and publishes periodic online backups only after integrity and
   digest checks. This removed the network-filesystem SQLite stall that produced
   zero durable rows during Attempt 0.
2. **Route directly to the healthy Kimi deployment through an authenticated
   loopback bridge.** The shared inference ingress was returning HTTP 503 even
   though Kimi itself was healthy. Attempt 2 therefore processed work quickly
   but accepted zero rows. The direct bridge restored real model generation;
   Attempt 3 immediately reached 45.7 accepted rows/min over its full window.
3. **Use Local Bubblewrap instead of one Firecracker lease per example.** The
   trusted question-only recipe can run as lightweight sandboxed processes on
   the already allocated CPU node. This removes VM-pool 429s, lease latency,
   OCI preparation, and other per-task gateway failure points.
4. **Raise measured concurrency from 16 to 24, then validate 32 and 64.**
   Attempt 5 sustained 23--24 jobs in flight and reached 94.5 successful
   tasks/min during active generation, about 57% above Attempt 3's 60.0
   tasks/min at concurrency 16. Post-completion canaries then validated 64 on
   the real chain's 8-CPU resource shape at 219.4 completed tasks/min and 137.1
   accepted rows/min without transport or client failures.
5. **Give every recovery/chain job a fresh node-local broker ledger.** Native
   AutoData state is the durable authority. Reusing an old transport ledger
   caused HTTP 409 when a retry's repaired routing changed its job
   specification. Per-job ledgers eliminate that collision and are archived
   by attempt for auditability.
6. **Use the recovery-aware, target-aware AutoData engine.** Pinned AutoData
   `823c594` includes serialized SQLite writes, interrupted-finalization
   reconciliation, selective final retries, and production-target stopping.
   Together with the persistent lifecycle supervisor, this allowed Attempt 7
   to finish in 10m43s with 1,083 accepted rows.

The final active-generation rate was 64.8 accepted rows/min. The full Attempt
7 rate, including restore, reconciliation, and final export, was 55.3 accepted
rows/min.

### Speed-up in numbers

- **Worst observed interval:** 0 new durable rows in 19m07s. The controller was
  stalled before inference, so a multiplicative speed-up is undefined.
- **Original pre-fix production period:** 47 accepted rows in 83m25s, or 0.56
  accepted rows/min and 106.5 aggregate seconds per accepted row.
- **First healthy concurrency-16 window:** 45.7 accepted rows/min, about 81x
  the original end-to-end rate.
- **Peak measured concurrency-24 window:** 73.4 accepted rows/min during active
  generation, about 130x the original end-to-end rate.
- **Successful completion run:** 64.8 accepted rows/min during active
  generation and 55.3 accepted rows/min including restore, reconciliation, and
  export. Those are about 115x and 98x the original end-to-end rate,
  respectively.
- **Sandbox overhead context:** the earlier infrastructure canaries reduced
  median broker-task latency from approximately 37 seconds with Firecracker to
  approximately 9 seconds with Local Bubblewrap, while removing the finite VM
  lease pool as the concurrency limiter.
- **Sustained concurrency-64 canary:** 256 tasks completed in 70.0 seconds on
  8 CPUs, or 219.4 tasks/min; 160 rows were accepted, or 137.1 accepted
  rows/min. This was about 2.1x Attempt 7's active accepted-row rate, with zero
  transport/client failures. The 62.5% accepted yield requires the existing
  production over-generation and selective retry headroom.

The end-to-end ratios include the original SQLite stall and therefore represent
operator wall-clock improvement. The concurrency-16 versus concurrency-24
comparison isolates healthy generation more directly: successful-task
throughput rose from 60.0 to 94.5 tasks/min, a 57% improvement.

## What future runs get automatically

A new **Run 9** launched through the committed `launch/submit_full.sh` and
`slurm/pipeline.sbatch` gets these defaults:

- Local Bubblewrap with supervised node-local native SQLite state;
- a fresh node-local broker ledger for each chain job;
- the authenticated Kimi loopback bridge when the configured proxy contract is
  present;
- pinned AutoData `823c594` or a fail-closed launch instead of silently using a
  different engine; and
- durable retained snapshots and cleanup.

Run 9's normal launcher now selects a measured default from the data path:
concurrency **32** with up to three transient model-request attempts for the
normal target-aware Kimi-to-Gemma-to-Luna path, or concurrency **64** with one
attempt for an explicitly target-disabled Kimi-to-Luna path. The production
recovery launcher remains question-only and defaults to 64. The launchers
reject values above 64.

The following are not universal defaults:

- An explicit concurrency override remains available for a differently sized
  target deployment, but it must pass its own target-aware capacity canary.
- The direct bridge requires a valid `AAR_KIMI_PROXY_INFO` for the intended
  deployment. Run 9 supplies its known path automatically; another experiment
  or deployment must supply and verify its own proxy contract.
- A running Slurm job does not acquire later source changes. Relaunch or resume
  through the updated chain launcher to receive these fixes.
- Other AAR experiment launchers benefit from the generic fresh-ledger and
  bridge code only when they enable supervised AutoData, choose `local-bwrap`,
  provide `AAR_KIMI_PROXY_INFO`, and pin AutoData `823c594` or a newer commit
  containing the same fixes.
- The 25-hour controller ceiling is specific to the retained Run 9 recovery
  launcher. Ordinary fast production should finish well below the standard
  ceiling; unusually long retained executions must set a compatible timeout.

## Post-completion concurrency promotion

These tests used the unchanged `winnieyangwn-kimi26` generator, Luna judge,
Local Bubblewrap broker, and one model-request attempt. Judge rejection and
recipe-level model/parse failure were recorded separately from transport or
client failure.

1. Job `1797215`, concurrency 24, completed all 24 broker tasks in 12.6
   seconds. The initial client classified five valid `model_or_parse_failure`
   task results as client failures. This exposed a measurement bug, not a
   provider failure; the validator was fixed to retain failed task outcomes.
2. Job `1797243`, concurrency 24, was the clean control: 24/24 tasks, zero
   client/task failures, 23 accepted rows, 107.3 tasks/min, and 102.8 accepted
   rows/min.
3. Job `1797244`, concurrency 32, completed 32/32 tasks with zero client or
   transport failures: 132.0 tasks/min and 119.6 accepted rows/min. One task
   result failed and 29 rows were accepted.
4. Job `1797245`, concurrency 64, completed 64/64 tasks with zero client or
   transport failures: 237.6 tasks/min and 200.5 accepted rows/min. Eight task
   results failed and 54 rows were accepted.
5. Job `1797305`, the first 256-task sustained attempt, stopped after the
   canary's `$2` campaign reservation ceiling admitted 150 jobs. It also used
   an unrealistic 256 simultaneous client processes. This was a harness-budget
   failure, not an endpoint-capacity result. The canary ceiling was raised to
   `$10` and submissions were bounded to waves of 64.
6. Job `1797320`, 256 tasks at concurrency 64 on 8 CPUs and 64 GB, completed
   all broker and client work in 70.0 seconds with no transport failures. It
   measured 219.4 tasks/min and 137.1 accepted rows/min. Of 256 results, 187
   reached the judge, 160 were accepted, 27 were judge-rejected, and 69 were
   generator `model_or_parse_failure` results. Production's 2,000-task ceiling
   supplies headroom for this measured 62.5% accepted yield.

Decision: promote 64 as the default for Run 9's question-only generation path.
Keep the explicit upper bound at 64; higher concurrency has not been tested.

## Target-aware capacity result

Target probing was tested separately through the full Kimi generator → pinned
Gemma target → Luna judge path. Short one-attempt bursts completed at 85.3,
91.0, and 158.8 tasks/min for concurrency 24, 32, and 64 respectively, but the
number of tasks that stopped before Luna rose from 4 to 7 to 20. Allowing up to
three transient model-request attempts at concurrency 64 recovered most of
those calls: 61/64 reached Luna and throughput remained 136.1 tasks/min.

The sustained tests determined the stable default:

- Job `1797559`, concurrency 32, 256 tasks, three attempts: all broker/client
  work completed, all 256 tasks reached Gemma, 253 reached Luna, and throughput
  was 93.4 tasks/min. There were 20 recipe-level model/parse failures, 30 judge
  rejections, 204 target-not-challenging results, and two accepted rows.
- Job `1797527`, concurrency 64, 256 tasks, three attempts: 255 tasks completed,
  but one local broker upload was reset and remained nonterminal. This 0.4%
  transport failure is enough to reject 64 as the stability default for
  target-aware production.

The two accepted rows do not estimate production yield: the capacity harness
deliberately repeats one scenario, and the pinned Gemma checkpoint usually
handled it correctly. The test establishes endpoint and transport capacity.
The resulting launcher default is target-aware concurrency 32 with three
request attempts; question-only generation retains concurrency 64.

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

The completion attempt used:

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

It started only after one end-to-end task produced non-empty provider usage
and a non-`model_or_parse_failure` result. At the end of Attempt 2 the shared
gateway ingress returned HTTP 503, while deployment `winnieyangwn-kimi26`
remained healthy with one ready endpoint and zero load. Raising AutoData
concurrency cannot help that condition.

Attempt 5 validated 24-way concurrency on the current one-endpoint, four-GPU
Kimi deployment. Concurrency 32 is deliberately skipped for this recovery:
24 already keeps the endpoint busy, and another short probe would pay the
roughly 2.5-minute retained-state scan again without reducing the remaining
work enough to justify the delay.
