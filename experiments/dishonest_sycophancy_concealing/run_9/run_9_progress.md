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
