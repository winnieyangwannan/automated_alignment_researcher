# Run 12 Canary 2 Trial 4 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Never
record generated rows, raw prompts, target responses, credentials, or held-out
content here.

## Visual key

| Symbol | Status      | Meaning                                      |
| ------ | ----------- | -------------------------------------------- |
| ✅     | PASS        | Completed successfully or verified correct  |
| 🔴     | FAIL / STOP | Failed gate or deliberate stop condition     |
| 🐛     | BUG         | A concrete implementation defect identified |
| 🔎     | OBSERVATION | Important experimental evidence              |
| 💡     | CONCLUSION  | Conclusion supported by current evidence     |
| 🛠️     | FIX         | Corrective change implemented                |
| ⏭️     | NEXT        | Next action or outstanding work              |
| ⏳     | RUNNING     | Work currently in progress                   |

## 2026-10-10

<a id="trial4-event-setup"></a>

### ⏭️ 23:53 PT — NEXT: Trial 4 launch-blocked package initialized

> [!IMPORTANT]
> **Not launched.** Trial 4 is a fresh specification created after Trial 3's
> protocol failure. No attempt, workspace, execution, or Slurm job exists.

#### 💡 Trial 3 conclusion carried forward

Trial 3 proved that prompt instructions and late validation cannot safely leave
native execution creation or registration under researcher control. It accepted
an implicit default `0/1` execution with empty explicit partitions, contaminated
the intended held-out partition through fallback splitting, and exhausted the
campaign reservation before the required execution or production began.

Trial 4 requires these five safeguards before launch:

1. Trusted orchestration—not Kimi—constructs the canonical `3/3`, `64/32/32`
   execution manifest immediately after freeze.
2. A durable, idempotent intent atomically binds creation and registration, so
   crash recovery resolves the same content-bound execution.
3. A 60-second or three-attempt registration SLA fails loudly instead of
   idling.
4. Trusted pre-native validation rejects wrong iteration/production settings,
   empty or overlapping partitions, and missing or invalid holdout binding.
5. A freeze-created default is cancelled only when it is uniquely linked,
   still initial, and has zero attempts; all other cases fail closed.

#### 🔎 Budget observation

The setup retains the configured `$299` cap without claiming it is adequate.
Trial 3 reached that cap after 256 preliminary attempts and 41 final-corpus
attempts. The intended Trial 4 workload still includes three canonical meta
iterations plus 1,250 production tasks, so `$299` is likely insufficient. A
trusted phase-by-phase reservation bound and explicit operator decision are a
pre-launch requirement.

#### Lifecycle snapshot

```text
○ Guardrail implementation and regression validation
○ Budget reservation proof and operator decision
○ Fresh model-role and configuration confirmation
○ Source commit and HPC synchronization
○ Endpoint and MCP preflight
○ Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
○ Canonical execution create/register
○ Baseline approval
○ Three-iteration meta-optimization
○ Production
○ Training smoke
```

#### Evidence

- Intended run ID: `run12-canary2-trial4`
- Intended contract: `3/3/3`, `64/32/32`, production `1250` to `1000`,
  concurrency `32`, stop after `training_smoke`
- Source commit: pending repaired Trial 4 commit
- Attempt: not created
- Jobs: none

#### ⏭️ Next step

Finish and test the trusted execution-orchestration repair. Do not commit,
synchronize, or launch this package from this setup thread. After validation,
resolve the budget gate and obtain fresh explicit confirmation of the exact
model-role mapping and configuration revision.

## 2026-10-11

<a id="trial4-event-budget-approved"></a>

### ✅ 00:07 PT — PASS: Campaign ceiling raised from trusted reservation math

The user explicitly approved raising the Trial 4 campaign cap. Trusted policy
math reserves at most `$1.720896` per model-backed task. The corrected lifecycle
requires capacity for `608` meta evaluations and two `1,250`-task production
attempts, or `$5,348.544768`, before a small authoring margin.

Trial 4 now sets `max_cost_usd: "5500"`. This is a safety ceiling rather than a
spending target. Launch-time preflight must recompute the bound from the exact
resolved policy and fail closed on drift.

Concurrency remains `32`, the largest repository profile with completed
target-aware load evidence. A higher concurrency is not introduced into this
recovery canary; it requires a separate bounded load canary.

<a id="trial4-event-confirmed"></a>

### ✅ 00:11 PT — PASS: Trial 4 roles and launch configuration confirmed

The user explicitly confirmed the exact Trial 4 mapping and configuration:

- Researcher/host: Kimi-K2.6, deployment `aar_8-kimi26`
- Generator/teacher: Kimi-K2.6, deployment `autodata_8-kimi26`
- Proposal/semantic monitor: Claude Opus 4.8 via FAIR Model API
- Baseline approval: deterministic trusted AAR policy
- Target/training base: fixed `gemma-4-31B-it`, retained deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`, vLLM 0.25.1 language-model-only
- Row judge: `gpt-5-6-luna`
- Evaluator: none; stop after training smoke
- AutoData concurrency: `32`
- Campaign ceiling: `$5,500`

Launch remains blocked on completion of the shared repair suite, combined
validation, a focused commit, exact HPC synchronization, and final runtime
preflight. Any confirmed field drift requires fresh confirmation.

<a id="trial4-event-repair-local-pass"></a>

### ✅ 00:35 PT — PASS: Shared lifecycle repair passes the local gate

The reusable repair is implemented in shared production code, not only in the
Trial 4 wrapper. It now covers the original wrong-execution/idling failure and
the additional indefinite-wait or duplicate-work windows found by the
systematic audit:

- trusted construction and validation of exact `3/3/3`, `64/32/32`,
  concurrency, production, digest, and campaign settings before native calls;
- durable, idempotent native create/register intent with the three-attempt/
  60-second registration SLA and fail-closed default cancellation;
- deterministic supervisor-owned meta-to-production-to-training transitions;
- semantic progress detection, counter cross-checks, a repeated-failure
  breaker, and bounded control locks, SQLite snapshots, and process cleanup;
- durable broker accounting across research retries and fail-closed Slurm
  terminal-state and retry classification;
- host-FSM waiting without Kimi model turns, including the first resumed turn;
- durable training submission intent and exact Slurm-comment reconciliation,
  with dependency-lane state committed before the final receipt so a crash
  cannot silently create a duplicate or bypass the concurrency limit.

Local static validation passed (`git diff --check`, shell syntax, and Python
compilation). Fourteen directly runnable recovery tests passed, including both
new training-submission crash tests. The focused lifecycle implementation also
passed 34 tests in the repair thread. Complete collection is intentionally
deferred to the matching HPC environment because the devserver `.venv` lacks
pre-existing runtime dependencies such as `requests` and
`claude_agent_sdk`.

No attempt or Slurm job exists. The next mandatory gates are a focused commit,
exact fast-forward synchronization, the complete HPC regression suite, and
runtime endpoint/source/secret preflight.

<a id="trial4-event-launched"></a>

### ⏳ 00:38 PT — RUNNING: Trial 4 submitted after all pre-launch gates passed

The repair was committed, fast-forward synchronized to the clean matching HPC
worktree, and validated there. The complete touched-surface suite passed with
`275 passed, 5 subtests passed`. Live generation tests then passed for both
Kimi-K2.6 deployments and the retained Gemma target. The source checkout,
pinned AutoData checkout, fixed checkpoint, and mode-600 secret files matched
the confirmed contract.

The committed Trial 4 wrapper submitted exactly once with retained deployment
`winnieyangwn-r12-alpha-i1-c0dab4f7`.

#### Submission evidence

- Source commit: `9b993a73310a7280508921c7ef662dc2af277500`
- Launch/pipeline job: `1811750`
- Attempt root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T073731Z-9b993a73310a`
- Checkpoint root:
  `/checkpoint/ram/winnieyangwn/aar-checkpoints/run12-bootstrap-canary/20261011T073731Z-9b993a73310a`
- Resolved contract: c32, exact three meta iterations, production `1250` to
  `1000`, `$5,500` hard campaign ceiling
- Stop boundary: verified `training_smoke`; evaluator forbidden

The dedicated monitor thread is awaiting distinct research/controller job IDs
and the first durable lifecycle state. No evaluator has started.

<a id="trial4-event-pipeline-complete"></a>

### ✅ 00:40 PT — PASS: Pipeline completed and emitted distinct child jobs

Pipeline job `1811750` completed with exit code `0` after 21 seconds. It emitted
distinct research job `1811790` and controller job `1811791` for team
`run12-gemma4-31b-kimi26-alpha-1811750`. Both child jobs were pending at this
transition.

The pipeline explicitly recorded `bounded canary: skipping evaluator holdout
publication`; evaluator job ID is `-`. No evaluator or held-out scoring began.
