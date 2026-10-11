# Run 17 Canary 2 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Never
record generated rows, prompts, responses, credentials, or held-out content.

## 2026-10-11

<a id="run17-canary2-event-setup"></a>

### ⏳ 15:20 PT — PREPARING: source and launch contract

> [!NOTE]
> The canary is being configured and validated. No jobs or attempts exist.

```text
⏳ Source, typed config, Model API protocol, and launch wrapper
○ HPC synchronization
○ Explicit model/config confirmation
○ Claude/Gemma/Luna broker proof
○ Research and proposal approval
○ AutoData workspace registration and authoring
○ Meta-optimization iterations 1–3
○ Production and verified handoff
○ One-step training smoke
```

Source commit: not yet committed. Attempt: not created. Jobs: none. Evidence:
not yet generated. Decision: continue setup; no-go for the proof or main
canary until validation, synchronization, and explicit model confirmation are
complete.

<a id="run17-canary2-event-local-validation"></a>

### ✅ 15:27 PT — PASSED: local fail-closed contract checks

Focused validation passed for the exact Run 12-to-Run 17 configuration delta,
Claude Model API request shape, provider identity accounting, source-pinned
launch wrappers, shared controller compatibility, and shell syntax. The
validated focused suite completed with 105 tests and 10 subtests passing.

Jobs: none. Attempt: not created. Evidence: local test output only. Decision:
commit and synchronize; do not submit the broker proof or main canary before
explicit confirmation of the full model-role mapping.

<a id="run17-canary2-event-proof-path-correction"></a>

### ⚠️ 15:31 PT — CORRECTED: proof stopped before submission

The confirmed proof command failed closed before creating an attempt or Slurm
job because the configured pinned AutoData checkout path was absent on HPC.
The required clean commit was transferred and materialized at
`/storage/home/winnieyangwn/autodata-worktrees/judge-repair-28a9c22`, restoring
the exact path enforced by the wrapper. Retry is authorized after revalidation.

<a id="run17-canary2-event-launch"></a>

### 🚀 15:47 PT — RUNNING: proof passed and alpha chain launched

Retained failed proof: job `1820593` at attempt
`20261011T223441Z-d5f4a29a367b`; Claude generation and Gemma targeting
succeeded, while the Luna judge received a transient HTTP 429. The attempt was
not mutated.

Retained passing proof: endpoint preflight `1820609` and broker proof `1820614`
at `/checkpoint/ram/winnieyangwn/aar-runs/run17-adapter-target/20261011T224036Z-71fddb500dc4`.

The main training-smoke attempt launched from frozen source commit
`384a144bd495351c4abe92ba78b67dc6b5409402` at
`/checkpoint/ram/winnieyangwn/aar-runs/run17-bootstrap-canary/20261011T224631Z-384a144bd495`.
Launcher `1820659` emitted research chain `1820679` and dependent controller
`1820680`. Evaluator job: none. Decision: running; preserve evidence and stop
before evaluation as configured.
