# Run 9 progress

This file is the durable handoff for the five-successful-iteration AAR campaign.
All retained outputs are under `/storage/home/winnieyangwn/aar-runs`; shared
`/checkpoint/ram` inputs are read-only.

Historical entries retain their original date headings and embedded time-zone
labels. New entries use Pacific Time (`America/Los_Angeles`) and are labeled
`PT`.

## 2026-10-08 — implementation and prelaunch

- Approved configuration is recorded in [`PLAN.md`](PLAN.md).
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

Two fail-closed launcher attempts were preserved before child-job creation:

- Launch `1762839`, attempt
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T094719Z-1d7f01490829`,
  failed because fileless runtime mode removed a legacy `HARNESS_ENV` path that
  the Run 5 preflight still required. No evaluator or chain job was created.
- Launch `1762890`, attempt
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T095150Z-822af77bc04c`,
  passed that check and then failed because the old shared deployment worker
  path had been archived. No evaluator or chain job was created.
- The final launcher stages the previously validated generic vLLM worker into
  the retained attempt after enforcing SHA-256
  `913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361`.

The full campaign launch is active:

- AAR commit: `07346c202fcb99abb2db1de138258b389471d153`.
- AutoData commit: `f6da400ed9bd03e89919f95656213433a6a93405`.
- Attempt root:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T095530Z-07346c202fcb`.
- Team directory:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T095530Z-07346c202fcb/aar_teams/run9-gemma4-31b-opus48-autodata-five-success-v1`.
- Completed launcher job: `1762982` (`COMPLETED`, exit `0:0`).
- Evaluator job: `1763015`.
- Sequential AAR chain job: `1763016`.
- Launcher log:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T095530Z-07346c202fcb/logs/pipeline-1762982.out`.
- Evaluator log:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T095530Z-07346c202fcb/aar_teams/run9-gemma4-31b-opus48-autodata-five-success-v1/logs/aar-eval-honesty_sycophancy_concealing_uncertainty-1763015.out`.
- Chain log:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T095530Z-07346c202fcb/aar_teams/run9-gemma4-31b-opus48-autodata-five-success-v1/logs/aar-honesty_sycophancy_concealing_uncertainty-gemma4_31b-pilot_1763016.out`.
- At the durable handoff checkpoint, both child jobs were pending for Slurm
  priority. The launcher emitted distinct evaluator and chain IDs, so the full
  campaign is submitted; evaluator vLLM fail-closed startup markers must still
  be verified when job `1763015` starts.

## 2026-10-08 — final audited launch

The earlier child pairs were cancelled before useful work after progressively
finding fail-closed launch issues. All attempt directories remain preserved:

- `1763015` / `1763016` were cancelled while pending after the post-launch
  documentation commit advanced the shared checkout beyond their pinned source
  commit.
- `1763032` / `1763033` were cancelled while pending when audit showed that a
  staged `worker_vllm.sh` was not standalone; it also requires its sibling
  `container.sh` and `engine_common.sh`.
- In the next audited attempt, evaluator `1763107` started but was cancelled
  after chain `1763108` failed before research startup because its AutoData
  broker health probe referenced `PY` before initialization.

The final tested source commit is
`6dd1758073ccbb9e6ce6db27ac3f5c93a768709f`. The execution worktree is frozen at
that commit while the jobs run. Its launcher stages a hash-verified full vLLM
runtime snapshot, initializes the training lane, submits the evaluator with an
explicit single node, and initializes the trusted harness Python before the
AutoData broker health probe.

- Attempt root:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T100912Z-6dd1758073cc`.
- Team directory:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T100912Z-6dd1758073cc/aar_teams/run9-gemma4-31b-opus48-autodata-five-success-v1`.
- Completed launcher: `1763156` (`COMPLETED`, exit `0:0`).
- Running evaluator: `1763166`, one node.
- Running sequential AAR chain: `1763167`.
- Evaluator log:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T100912Z-6dd1758073cc/aar_teams/run9-gemma4-31b-opus48-autodata-five-success-v1/logs/aar-eval-honesty_sycophancy_concealing_uncertainty-1763166.out`.
- Chain log:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T100912Z-6dd1758073cc/aar_teams/run9-gemma4-31b-opus48-autodata-five-success-v1/logs/aar-honesty_sycophancy_concealing_uncertainty-gemma4_31b-pilot_1763167.out`.
- Confirmed chain health markers: campaign-scoped AutoData broker ready at
  concurrency 8, research mount/PID namespace verified, secure-internet Claude
  launcher started, and research process entered its jail.
- Evaluator startup confirmed its attempt-local ephemeral merged-checkpoint
  root. Image/version/checkpoint markers are emitted fail-closed when the first
  candidate arrives; no candidate had reached evaluation at this checkpoint.

## 2026-10-08 — safety-ordering stop

The final audited launch was intentionally stopped after inspecting the first
research session's AutoData activity. The native plugin path admitted real
generation before the AAR method had passed `submit_idea_proposal`. No proposal
tool-call marker, approval marker, proposal file, or proposal snapshot exists in
the retained team artifacts.

Before the stop, the agent created two native workspaces:

- `ws_affee2f4d11944819b2400ec473d206a` was the first workspace. It reached a
  dry-run but its first attempt was rejected because the executor omitted the
  campaign policy's required non-secret solve environment.
- `ws_ab00f6c36e4c4d0bae8e24710a107c68` was the corrected workspace. It reached
  the native dry-run after authoring and delegated grounding approval.

The signed approval records are retained under the attempt's
`autodata/approvals` directory:

- `act_a189dad61e4e7aa935e3b460`: `approve_grounding`, actor
  `aar-integrity-monitor`, decision `approve`, for the first workspace.
- `act_30b038198dafda21da50b043`: `approve_resources`, actor
  `aar-integrity-monitor`, decision `retry`, after the first workspace's
  configuration mismatch.
- `act_d72a6b5774880125771bd2ef`: `approve_grounding`, actor
  `aar-integrity-monitor`, decision `approve`, for the corrected workspace.

The corrected dry-run admitted broker jobs before proposal approval:

- `job_fafa4160937a4bcfb3b166bf920c4446` completed far enough for the native
  client to download its result (`GET .../results` returned HTTP 200).
- `job_90af1694fbc44f8b8a8b665de4791010` was created and uploaded, then remained
  in bounded retry after SandoQ returned retryable HTTP 429 pool exhaustion.

This demonstrated that the attempt-scoped broker correctly constrained model,
image, concurrency, and budget, but did not enforce the separate AAR
proposal-before-generation invariant. The chain was therefore not allowed to
continue to meta-optimization, production, training, or candidate evaluation.

Jobs `1763167` (sequential research chain) and `1763166` (evaluator) were
cancelled and became terminal after 25 minutes 28 seconds. Both report Slurm
state `CANCELLED` and exit code `0:0`. The complete attempt remains preserved at
`/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T100912Z-6dd1758073cc`.
There was no resubmission. The next launch must fail closed at broker admission
unless an approved proposal is cryptographically bound to the run and method.

## 2026-10-08 — proposal-binding fail-closed attempt

Commit `231f60f4f5df7ad0a5548c66a8c1a9ba58926bcb` added code-hash and
run-ID proposal binding to delegated AutoData approvals. Its full HPC test suite
passed before a fresh concurrency-8 attempt was submitted.

- Attempt root:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T104046Z-231f60f4f5df`.
- Completed launcher: `1763514` (`COMPLETED`, exit `0:0`).
- Evaluator: `1763540`.
- Sequential research chain: `1763541`.

The researcher wrote and successfully submitted proposal
`gemma4_31b_explore_pilot__epistemic_sft_v1`. The integrity review approved its
code hash
`e55cbc3a1c6d907fba49ca8799d1252ad31677678093edf8aaf7d55da070ee5d`.
However, the proposal marker contained `run_id: null` and no immutable run
proposal file was created. The cause was that `AAR_NO_LOCAL_GPU` had been
scrubbed from the research runtime, so the decoupled proposal code did not mint
the required run ID. The agent noticed the missing ID and invented a fallback
string, but the trusted binding code did not accept that substitute.

The new gate therefore failed closed correctly:

- proposal marker: approved, but missing `run_id`;
- signed AutoData approvals: 0;
- broker job admissions: 0;
- generated model rows: 0.

Jobs `1763541` and `1763540` were cancelled and became terminal with Slurm state
`CANCELLED` and exit code `0:0`. Their elapsed times were 24 minutes 16 seconds
and 21 minutes 44 seconds, respectively. The attempt is preserved. There was no
resubmission pending a fix that preserves the decoupled-run marker and tests
run-ID minting through the actual scrubbed research environment.

## 2026-10-08 — active proposal-bound launch

Commit `4a55052` preserves the decoupled-run marker through the research
environment and adds end-to-end coverage for proposal run-ID minting. The full
HPC suite passed 241 tests plus 35 subtests. The exact launch checkout includes
that fix at `cc7797c51afbd88720f7ff952e42c2b5232931a3` and is frozen while the
jobs run.

- Attempt root:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T111258Z-cc7797c51afb`.
- Launcher: `1764315` (`COMPLETED`, exit `0:0`).
- Evaluator: `1764390`.
- Sequential research chain: `1764391`.
- Configured AutoData concurrency: 8.

The launch monitor must verify this exact order before treating generation as
admitted: an approved proposal with a nonempty minted `run_id` and immutable
run file; a signed grounding audit containing the same `proposal_binding`; then
the first broker job.

## 2026-10-08 — proposal ordering passed, lifecycle stopped

The active proposal-bound launch passed its security-ordering boundary:

1. Proposal `gemma4_31b_explore_pilot__ich_sft` was approved with code hash
   `d05aaf3323161fbfe5701b284949f65cc42a3d2853fdd3e8e55a684ed43db944`
   and minted run ID
   `gemma4_31b-explore-pilot-1791458266-gemma4_31b_explore_pilot__ich_sft-1791459677272`.
   The matching immutable run-proposal file existed before AutoData approval.
2. Corrected workspace `ws_1333126060b64459af1dbc4702c128a1`
   received signed grounding approval
   `act_5144a358fce52e5a2f784b14`. Its `proposal_binding` contained the exact
   proposal run ID and code hash above, actor `aar-integrity-monitor`, and
   decision `approve`.
3. Only then did the broker accept job
   `job_816d807bc66b47dea730ce1e27f0c5c1`. Its result was downloaded
   successfully over HTTP 200.

The attempt was nevertheless stopped because the agent violated the required
native lifecycle after this boundary. The authoritative AutoData database
showed:

- Meta execution `exe_c6cfd9d2c09d44d284664c0ab62a2da8` remained `active`,
  phase `baseline_pending`, iteration 0. Its stored execution contract was
  correctly partitioned into 64 tuning tasks and 32 hidden-validation tasks at
  concurrency 8, with minimum 3 iterations and patience 3. It had neither
  completed its baseline nor produced a mutated candidate or winner.
- While that meta execution was still active, the agent started production
  execution `exe_732e36ec33764d249407676b4ac45bc5`. It was `active`, phase
  `final_pending`.
- Although `grounding/prod_manifest.json` existed with 1,250 tasks, the
  production execution's stored contract incorrectly referenced
  `grounding/manifest.json` and its 96-task meta-grounding digest. It therefore
  could not meet the required 1,000 accepted production rows.

The run had no training submission, candidate score, or result finding. It was
not counted as an outer AAR iteration. Chain `1764391` and evaluator `1764390`
were cancelled after 1 hour 1 minute 12 seconds; both became terminal Slurm
state `CANCELLED` with exit code `0:0`. The broker recorded 38 accepted job
admissions and 12 result downloads before shutdown; the admission count then
remained stable at 38. All attempt artifacts remain preserved.

No relaunch is allowed until trusted code enforces both conditions rather than
depending on agent instructions: production creation requires a terminal
successful meta execution and its selected winner, and production must bind the
approved 1,250-task production grounding plus the 1,000-row retention target.

## 2026-10-08 — trusted lifecycle gate ready for relaunch

The relaunch prerequisite above is now implemented at the training boundary.
The new read-only verifier authenticates the native AutoData SQLite state and
refuses both training submission and model upload unless all of the following
are true:

- meta-optimization is natively completed with exactly 64 tuning, 32 hidden
  validation, and 32 disjoint test tasks, using 3--10 iterations, minimum 3,
  and early-stop patience 3;
- the finalized meta winner and its canonical tree digest match a pristine
  native `execution export-winner` export;
- production was created only after that finalization, remains in the same
  native study, uses fixed-winner production mode with zero optimization
  iterations, and differs from the winner only by its dedicated manifest;
- that manifest has exactly 1,250 fresh task IDs disjoint from all meta/test
  IDs, and the finalized production dataset contains at least 1,000 unique
  Luna-accepted rows bound by the native artifact digest;
- the approved training method loads exactly 1,000 rows through the
  receipt-producing AutoData loader, and the receipt is created by the active
  training process before the model can enter evaluation.

The research prompt now also forbids duplicate/background steppers, tells the
agent to resume rather than skip a slow native execution, and distinguishes the
pristine winner export from the production copy. The grounding builder supports
fresh `safety-prod-*` IDs. The complete devserver suite passed 250 tests plus 35
subtests; Python compilation, shell syntax checks, and `git diff --check` also
passed. The exact commit and fresh Slurm IDs will be recorded after synchronization
and submission.

## 2026-10-08 — trusted-lifecycle-gate launch

The trusted lifecycle guard was synchronized to HPC at exact source commit
`6045c49eaad746a85c7e29fd983c87db9630c27c`. The pinned native AutoData commit
is `f6da400ed9bd03e89919f95656213433a6a93405`. The complete HPC suite passed
250 tests plus 35 subtests before submission.

- Attempt root:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T123357Z-6045c49eaad7`.
- Launcher: `1766326` (`COMPLETED`, exit `0:0`).
- Evaluator: `1766341`.
- One sequential research chain: `1766342`.
- AutoData concurrency: 8.
- Target: five durable score/result pairs in one sequential chain.

The HPC execution checkout is frozen at the exact source commit above while
the child jobs run. At this checkpoint the launcher had emitted both distinct
child IDs; their proposal, native meta-optimization, production, training, and
evaluation gates remained to be observed.

## 2026-10-08 — native proposal boundary and meta recovery

The live chain passed the required ordering boundary before any model-backed
generation: `submit_idea_proposal` approved a nonempty minted run ID, the
immutable proposal run file was present, and the integrity monitor signed the
grounding approval with the exact proposal run ID and code hash. Only then did
the broker admit the three successful Kimi/Luna dry-run jobs.

The first explicit meta execution,
`exe_16876e9520a34af2a02c0db6943f86e8`, had the required 64 tuning, 32 hidden
validation, and 32 disjoint test tasks at concurrency 8, with minimum 3,
maximum 3, and early-stop patience 3. It reached 61 completed baseline tasks
and three infrastructure failures before exposing a native retry defect:
interrupted physical attempts reused stable logical idempotency keys, so a
cancelled broker handle could not be retried and AutoData raised
`idempotency key reused for a different event`. No production execution or
training was started. The execution is preserved in terminal `cancelled`
state with 64 task attempts recorded.

The research agent recovered only through native lifecycle operations. It
created a fresh execution with an explicit unique idempotency key and changed
its attempt-local driver so a native `execution step` is never killed by a
short wrapper timeout. The clean recovery execution is
`exe_a96c544b2eb048ee863572261bcfc5e2`; its stored contract was independently
checked as `meta_optimize`, concurrency 8, 64 tuning, 32 validation, the
32-task test manifest, and budget `min=3`, `max=3`, `patience=3`. At launch it
had exactly one controller/step process and remained in native
`baseline_pending`. The upstream interrupted-attempt retry bug remains a
separate resilience issue; this run did not patch its state database or skip
the required meta stage.

## 2026-10-08 — attempt stopped for the upstream retry fix

The clean recovery execution began making progress without duplicate
controllers, but the run was intentionally stopped once the underlying native
AutoData retry/resume defect had been fixed and tested upstream. Continuing
with the attempt-local no-timeout workaround would have left production
dependent on an obsolete plugin build.

Canonical AutoData `main` now contains the retry/resume fix at commit
`f334c19`; its complete upstream suite passed 68 tests with one skipped, and
the plugin wheel was rebuilt and hash-verified. The active HPC attempt remained
pinned to the older native commit and was not modified in place.

Chain `1766342` and evaluator `1766341` were cancelled at 2026-10-08
14:07:24Z. Both reached terminal Slurm state `CANCELLED`, exit `0:0`; their
elapsed times were 1:28:36 and 1:20:37 respectively. The broker log stabilized
at 87 accepted job admissions and 106 result downloads over a 30-second
post-stop observation. No production execution, training submission, model
evaluation score, or result finding was produced, so this attempt does not
count as an outer AAR iteration. All artifacts remain preserved under the
attempt root. A fresh launch must wait until the patched AutoData commit and
matching AAR pin/plugin bundle pass HPC synchronization and validation.

## 2026-10-08 — retry-safe, cross-architecture plugin validated

Canonical AutoData `main` is now synchronized and clean on both the x86_64
devserver and ARM64 HPC at commit
`61304d889dee6c0ced007322540998a36d85f664`. This includes the native
interrupted-attempt retry fix and a deterministic plugin-wheel builder.

The wheel now stores entries without DEFLATE, avoiding architecture-dependent
zlib byte streams. Rebuilding it independently on both machines produced the
same SHA-256 digest:
`3d4cc03a6194920f25875555f2fd96ccca95ca1949f76db435a0c400e0bdf1d6`.
Both complete AutoData test runs passed 68 tests with one skipped, and the HPC
rebuild left no Git diff. The fresh AAR launch may therefore pin and verify one
identical native framework and plugin payload across both architectures.

## 2026-10-08 — retry-safe fresh launch

The matching AAR source and HPC execution worktrees were clean at exact commit
`7c5310ce17f012afc6b9987d91d6c981a4be2ca4`. The HPC AAR suite passed 250
tests plus 35 subtests before submission. The committed Run 9 submitter was
launched at AutoData concurrency 8 and recorded:

- Attempt root:
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T141415Z-7c5310ce17f0`.
- Launcher: `1768037`.
- Evaluator: `1768082`.
- One sequential research chain: `1768083`.
- AAR commit: `7c5310ce17f012afc6b9987d91d6c981a4be2ca4`.
- Native AutoData commit: `61304d889dee6c0ced007322540998a36d85f664`.
- AutoData concurrency: 8.
- Target: five durable score/result pairs in one sequential chain.

The launcher published the complete retained suite and emitted distinct
evaluator and chain IDs before completing. At this checkpoint both child jobs
were pending placement; proposal approval, bound grounding approval, native
meta-optimization, production, training consumption, and evaluation remained
to be observed.

## 2026-10-08 — Firecracker capacity failure and stabilization

The retry-safe attempt never reached an outer AAR result. The SandoQ
`oci-runner-firecracker-small` warm pool repeatedly returned HTTP 429 because
no pod was available. Broker requests then outlived the client's 60-second
HTTP timeout, producing ambiguous disconnects, broken-pipe noise, and repeated
`could not reach AutoData broker` failures. No production dataset, training
submission, score, or result finding was produced; the attempt therefore has
zero durable score/result pairs.

Evaluator `1768082` and chain `1768083` were cancelled at 2026-10-08
19:17:52Z and reached terminal Slurm state `CANCELLED`. The complete attempt is
preserved at
`/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T141415Z-7c5310ce17f0`.

The stabilization path keeps SandoQ Firecracker—the only supported isolated,
model-backed executor—but no longer assumes the `small` warm pool. Run 9 now
accepts an explicitly validated Firecracker tier, records it in submission
metadata, and defaults to `large` with concurrency 4. AutoData transport now
replays bounded transient disconnects and 429/5xx responses under the original
idempotency key, suppresses harmless response-write disconnects, and serializes
broker SQLite writes in-process. A fresh attempt remains gated on an HPC
model-backed canary of the selected tier and exact synchronized commits.

## 2026-10-08 — Firecracker tier capacity evidence

AutoData transport hardening is committed at
`6dcf7aee84948a7924d7a725218029a75cfb20c3`; its plugin wheel SHA-256 is
`78552d5ba639237bee41b97f2b1e8117702c62c23586b7da6ccf5f457c863fa9`.
Independent x86_64 and ARM64 builds matched, and the complete AutoData suite
passed 71 tests with one skipped on both hosts.

Two preserved four-way model-backed capacity probes distinguish the available
SandoQ tiers:

- Medium job `1774433` admitted three distinct Firecracker sessions, but its
  fourth broker job exhausted the bounded lease wait with `TimeoutError` after
  repeated pool-exhaustion 429s. Its root is
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/capacity-20261008T192714Z-86071a7b2169`.
- Large job `1775619` admitted four distinct Firecracker sessions. All four
  broker jobs reached `SUCCEEDED` with solve exit code 0. Three canary clients
  retained schema-valid accepted samples; the fourth client rejected a
  zero-item task result after the broker job succeeded. That is sample-quality
  filtering, not an infrastructure failure. Its root is
  `/storage/home/winnieyangwn/aar-runs/run9-five-iteration/capacity-20261008T202259Z-86071a7b2169`.

Run 9 therefore pins `oci-runner-firecracker-large` at concurrency 4. The
capacity-gate summary checks the broker database for four successful jobs,
distinct nonempty SandoQ sessions, and solve exit code 0; it records accepted
sample count separately so ordinary quality filtering cannot masquerade as a
capacity failure.

## 2026-10-08 — local broker acceleration

The attempt rooted at
`/storage/home/winnieyangwn/aar-runs/run9-five-iteration/20261008T204038Z-e05baf8e3b61`
was stopped after zero durable score/result pairs. Evaluator `1775911` and chain
`1775912` were cancelled and the complete attempt was preserved. Live broker
events showed a 37-second median task duration: 19 seconds leasing, 5 seconds
preparing, and only 9 seconds in the Kimi-plus-Luna solve. The large pool was
again returning retryable pool-exhaustion 429 responses at concurrency 4.

The replacement design retains the authenticated loopback broker, its
campaign-wide cost reservations, result allowlist, idempotency ledger, and
daemon-owned `MODEL_API_KEY`, but selects its restricted local Bubblewrap
runner for this fixed question-only recipe. The research agent still receives
only the attempt-scoped broker capability. A concurrency-16 real Kimi/Luna
canary is required before a fresh full launch; concurrency 32 may be admitted
only after a separate successful load test.

## 2026-10-08 — local Bubblewrap canary passed

The first local-runner probes, jobs `1777762` and `1777833`, showed that the
external inference-gateway hostname was not reachable from the HPC host after
Bubblewrap correctly removed inherited proxy variables. Those probes produced
no provider usage and are retained as routing failures rather than evidence
against Kimi capacity.

AAR commit `583673b8cc892dd8b1e2435e1059dde3c7d99487` routes local-runner Kimi
requests through the cluster-internal FAIR ingress while preserving the
required host and deployment headers. The corrected one-task probe `1777931`
completed in 55 seconds and retained one accepted Kimi/Luna sample.

The corrected concurrency-16 probe `1777949` completed in 2 minutes 3 seconds.
All 16 broker jobs reached `SUCCEEDED`, all 16 task envelopes reported
`outcome=succeeded`, and every task recorded both Kimi generation and Luna
judgment usage. Ten samples were accepted and six were deliberately filtered
with `reason_code=judge_rejected`; there were no model, parsing, broker, lease,
or routing failures. This satisfies the production admission gate for the
local Bubblewrap runner at concurrency 16 without resizing the one-endpoint
`winnieyangwn-kimi26` deployment.

## 2026-10-10 — source organization

- 2026-10-10 16:12 PT — Reorganized the Run 9 source directory using the
  proven Run 12 responsibility-based structure. Launchers, Slurm payloads,
  configuration, recovery tools, runtime helpers, canaries, documentation,
  and analysis now have distinct homes. Stable launcher root discovery and
  repository references were updated with the moves.
  Source commit: this organizational commit (resolved by Git history)
  Attempt: not created
  Jobs: none
  Evidence: [`README.md`](README.md), the reorganized source tree, and focused tests
  Decision: use the new operator paths; preserve all retained run artifacts and
  operational history unchanged.
