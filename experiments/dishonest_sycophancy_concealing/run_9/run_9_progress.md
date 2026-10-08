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
