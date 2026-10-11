# Run 12 Canary 2 Trial 11 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). This
log contains orchestration metadata only; never record generated rows, prompts,
responses, credentials, or held-out content.

### ⏳ 04:38 PT — PREPARING: fresh trial after heartbeat repair

Trial 10 is terminal and preserved. It completed the baseline and all three
canonical meta iterations, then failed closed during `final_pending` because a
live native step exceeded the stale supervisor-status SLA. No evaluator,
production handoff, training job, checkpoint, score, or submission was created.

Repair `9f81cdad899c51abc4cf589884f3ee0827c29ecd` refreshes the durable
`stepping` record every 30 seconds while the child is alive. Focused local and
HPC validation each pass 113 tests plus 6 subtests. The source and HPC `autodata`
branches match exactly at the repair commit; the temporary transfer ref was
removed and GitHub was bypassed.

```text
✓ Trial 10 terminal evidence preserved
✓ Supervisor heartbeat repair committed and synchronized
✓ Local and HPC focused regression gates
⏳ Trial 11 record commit and immutable preflight
○ Launcher and research allocation
○ Workspace authoring and freeze
○ Canonical baseline and three meta iterations
○ Production and verified handoff
○ One-step training smoke
```

The confirmed role mapping and fixed contract remain unchanged: Kimi-K2.6
researcher `aar_8-kimi26`, Kimi-K2.6 generator `autodata_8-kimi26`, Claude Opus
4.8 monitor, fixed Gemma 4 31B target/training checkpoint with retained
deployment `winnieyangwn-r12-alpha-i1-c0dab4f7`, `gpt-5-6-luna` row judge,
exact `3/3/3`, disjoint `64/32/32`, concurrency 32, 1,250→1,000 production,
`$5,500` ceiling, and evaluator disabled.

Next: commit and synchronize the Trial 11 records, launch through the committed
submitter, and monitor through verified `training_smoke`.

### 🛠️ 04:42 PT — FIX: generalized heartbeat coverage before launch

Independent review found that the initial repair covered the observed native
step but not every adjacent synchronous path. Trial 11 was held before `sbatch`.
The supervisor now:

- refreshes status during frozen-workspace reconciliation;
- pre-detects and refreshes status throughout meta-to-production and
  production-to-handoff transitions;
- refreshes status during arbitrary idle and retry backoffs;
- serializes concurrent status writes and fails closed if a refresh fails;
- keeps signal handlers out of the atomic status writer, then publishes
  `stopping` and `stopped` through the serialized main path after child cleanup;
- retains the existing native-step timeout, semantic-stall, and bounded cleanup
  behavior.

Focused validation passes 119 tests plus 6 subtests. The broader AutoData/Run 12
gate passes 326 tests plus 6 subtests; its sole failure is unrelated user-owned
dirty state where the Run 13 fixture files are deleted. An independent read-only
review found no remaining normal-path launch blocker; no Trial 11 job or durable
attempt exists yet.

### ⏳ 04:50 PT — RUNNING: immutable Trial 11 child chain launched

All committed preflight gates passed. Launcher `1814907` completed `0:0` after
emitting distinct child jobs:

```text
✓ Immutable AAR source 4511d687af23
✓ Immutable native source d6e5619bab0b
✓ Launcher 1814907 completed 0:0
✓ Research job 1814992 created
✓ Controller job 1814993 dependency-gated behind research
✓ Evaluator job absent
⏳ Research allocation and workspace authoring
○ Canonical meta baseline and three iterations
○ Production and verified handoff
○ One-step training smoke
```

Attempt root:
`/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T114652Z-4511d687af23`.
Team: `run12-gemma4-31b-kimi26-alpha-1814907`. At this update research job
`1814992` is pending allocation and controller `1814993` is correctly pending on
its dependency. The separate monitor is active; evaluator count remains zero.

### ⏳ 05:37 PT — RUNNING: canonical baseline started after verified freeze

Research `1814992` started at 04:51:41 PT. The proposal was approved after one
specific semantic-review correction, creating workspace
`ws_e09c3e2ee4384c0db53892fb3d432453`. Clarification, grounding, pipeline
authoring, deterministic reviews, and dry runs completed; the workspace froze at
revision 10.

Trusted reconciliation safely cancelled the freeze-created default execution
at zero attempts and registered canonical meta execution
`exe_3055ea6409f34720a908bb8b5039da4f`. Its durable native contract is three
iterations with a 699-attempt ceiling. The execution entered `baseline_pending`.

```text
✓ Endpoint, MCP, immutable-source, and adapter preflight
✓ Proposal review and approval
✓ Workspace clarification and grounding
✓ Pipeline authoring, checks, and dry runs
✓ Deterministic baseline review and workspace freeze
⏳ Canonical meta baseline (execution exe_3055ea6409f34720a908bb8b5039da4f)
○ Meta iterations 1–3
○ Production and verified handoff
○ One-step training smoke
```

The repaired supervisor heartbeat has live proof: a native step ran from
05:35:58 through 05:37:04 PT while the durable `stepping` status refreshed every
30 seconds. Kimi did not raise the stale-heartbeat failure that stopped Trial 10.
Evaluator count remains zero.

### 🔴 06:04 PT — FAIL: trusted retry reserve exhausted during finalization

> [!CAUTION]
> Trial 11 failed closed after completing its baseline and all three required
> meta iterations. No production, handoff, training, evaluator, score, or
> checkpoint boundary began.

```text
✓ Endpoint, MCP, immutable-source, and adapter preflight
✓ Proposal review, workspace authoring, and freeze
✓ Canonical baseline and meta iterations 1–3
✗ Final full-corpus retry exhausted the trusted native attempt ceiling
○ Production and verified handoff
○ One-step training smoke
```

Research job `1814992` failed at 06:02:52 PT. Controller `1814993` then ran
from 06:03:24 through 06:03:40 PT and failed closed on the terminal research
state. The canonical execution consumed exactly `699/699` native attempts and
remained at `final_pending`; the preserved supervisor record is `failed` with
`lifecycle_step_failed`.

The trusted budget formula reserved `608` model-backed meta evaluations, three
pipeline checks, and only `88` finalization-recovery attempts. Native
finalization is allowed to retry every task in the 96-task tuning+validation
corpus once. In this attempt the retry set contained 93 tasks, so only 88 could
start before the native ledger returned `task_attempts budget exceeded`.
Because the batch was charged incrementally, the execution did not reach its
normal `failed/final_incomplete` transition. The supervisor then repeated the
same permanent step error instead of surfacing the budget diagnostic
immediately.

The minimum safe native ceiling for this fixed contract is therefore
`608 + 3 + 96 = 707`. The campaign must authorize `704` model-backed meta tasks
plus `2,500` production tasks, or `3,204` total; at the pinned worst-case rates
their one-round subtotal is `$5,513.750784`. Trial 11 is preserved and will not
be resumed.
The repair must reject partial retry funding before launch, atomically preflight
native batches, transition finalization failures durably, and propagate typed
budget feedback before a fresh Trial 12 is submitted.

### 🐛 06:24 PT — BUG: comprehensive budget audit found broader under-accounting

> [!WARNING]
> The `$5,513.750784` task-only subtotal is not a safe campaign ceiling for the
> configured five-round final-generation policy. Trial 12 remains held.

The follow-up audit found that the broker reserved only one generator/judge
round per model-backed job even though every `final-full-corpus*` job may run up
to five bounded feedback rounds. It also found that pre-freeze authoring jobs
were absent from the campaign derivation, target-provider pricing was absent
from native reservations, cost-result archive lookup silently missed the
leading `.autodata` path, and a reconciliation overage could leave a broker job
nonterminal. Three transport attempts per model request also made timeout
billing impossible to account for exactly.

For the fixed Trial 12 contract, the fail-closed upper bound is `14,004`
provider-round reservations: `1,472` meta, `12,500` production, and a
conservative `32` authoring jobs. At `$1.720896` per round this is
`$24,099.427584`; the next rounded operator ceiling is `$24,100`. This is a
safety authority, not expected spend. The c32 profile will use one transport
attempt per model request, while native feedback remains bounded at five
semantically visible rounds.

Native repair `da9e12a43710ced9d407822e55c6e7c541e57a27` adds atomic
idempotent batch reservations, terminal budget states, policy-correct meta
retry selection, phase-aware five-round cost reservation, target cost fields,
correct task-result cost discovery, and prompt failure on reconciliation
overage. Deterministic checks no longer receive model-backed authority. The AAR
gate independently derives the same worst-case bound in integer micro-USD and
rejects a cap even one micro-dollar below it.
