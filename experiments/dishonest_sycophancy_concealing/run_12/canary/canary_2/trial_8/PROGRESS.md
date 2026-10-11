# Run 12 Canary 2 Trial 8 progress

All timestamps use Pacific Time (`PT`). This log contains orchestration metadata
only; never record generated rows, prompts, responses, credentials, or held-out
content.

### ⏳ 03:22 PT — PREPARING: Trial 8 created from the frozen contract

Trial 7 was safely stopped after its canonical baseline exposed a host lineage
bug. The baseline and failure evidence remain preserved. Repair commit
`207f05e` is synchronized exactly to the clean HPC `autodata` worktree.

Validated repair coverage:

- durable workspace→meta→production lineage resolution;
- canonical execution with native `workspaceId=NULL`;
- execution-scoped action discovery after freeze;
- strict workspace/execution native status normalization;
- idempotent recovery across meta→production registration crash windows;
- controlled restart-port recovery for frozen workspaces;
- missing, empty, malformed, duplicate, cyclic, or wrong-parent lineage failure;
- stopped/unknown supervisor failure and 90-second idle-without-action SLA.

Local focused gate: 125 passed plus 6 subtests. HPC focused gate: 125 passed
plus 6 subtests. Broader local AutoData gate: 322 passed plus 6 subtests; its
only failure is the unrelated user-deleted Run 13 fixture.

Next: commit Trial 8 records, synchronize the exact commit, run final immutable
preflight, launch one `alpha` bootstrap canary, and monitor through the verified
training-smoke boundary. Evaluator count must remain zero.

### ⏳ 03:28 PT — RUNNING: immutable Trial 8 child chain launched

The live Kimi/MCP and retained Gemma endpoint probes passed. Launcher `1814192`
then passed the pinned native-engine and exact adapter-contract gates and emitted
the required separate child jobs:

```text
✓ Launcher 1814192 completed 0:0 in 40 seconds
✓ Immutable AAR source 68d01f27c0ba (validated 4ae2932 plus Run 15 docs only)
✓ Immutable native source d6e5619bab0b
✓ Research job 1814230 created
✓ Controller job 1814231 dependency-gated behind research
✓ Evaluator job absent
⏳ Research allocation
○ Workspace authoring and freeze
○ Canonical meta baseline and three iterations
○ Production and verified handoff
○ One-step training smoke
```

Attempt root:
`/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T102402Z-68d01f27c0ba`.
The attempt-local snapshot is clean and immutable. The sole source delta after
the validated Trial 8 setup commit is unrelated Run 15 progress documentation;
all executable code and Trial 8 configuration are identical to the validated
commit.

### ❌ 03:50 PT — STOPPED SAFELY: native action-result shape mismatch

The Trial 7 lineage repair worked: after freeze, the supervisor switched from
the workspace to canonical meta execution
`exe_fe04f1f242464d6184a41b1f3a11ff86`, ran the exact 64/32 baseline, and
completed the scoped `analyze_results` action. The next native step failed
closed before iteration 1 because the AAR bridge passed the researcher-authored
result envelope through verbatim:

```text
AAR bridge shape: {schema, status, action_id, outputs: {proposal, dashboard_summary}}
Native shape:     {proposal, dashboard_summary}
Native failure:   analysis action result must include a non-empty proposal
```

The proposal was present under `outputs.proposal`; native AutoData looked for
top-level `proposal`. Earlier workspace actions had the same envelope mismatch,
but their consumers tolerated/defaulted missing narrative fields. Meta mutation
is the first strict result consumer, so it exposed the integration defect.

The failure was initially reported only as `lifecycle_step_failed` because all
three privileged service logs were routed to `/dev/null` whenever
`AAR_RESEARCH_ENV_ISOLATION=0`. This is a second observability defect. Trial 8
is terminal and quiescent: research `1814230` failed at 03:49:50 PT and
controller `1814231` failed at 03:50:18 PT. Production executions, handoffs,
training receipts, checkpoints, submissions, scores, evaluator jobs, and
evaluator artifacts all remain zero.

### ✅ 03:56 PT — DIAGNOSED: isolated native replay proves the repair boundary

A read-only copy/replay preserved Trial 8 and reproduced the original native
exit 2 exactly. Replacing only the copied action's stored envelope with its
flat `outputs` object caused the next native step to return a
`mutate_candidate` action whose editable root remained inside the isolated
replay directory. This proves the baseline, execution state, proposal value,
and native engine are otherwise valid.

Required repair before Trial 9:

- normalize the supported AAR envelope to native flat output fields;
- validate every declared output, action ID, schema, status, and value shape
  before invoking native `action complete`;
- preserve the action lease and return precise feedback for correctable invalid
  results instead of corrupting native state or ending the session;
- retain private bridge, broker, and lifecycle-supervisor diagnostics in every
  isolation mode;
- safely surface only allowlisted, content-free native contract diagnostics.

Focused repair validation currently passes: 114 tests plus 6 subtests. Trial 9
must not launch until the repair is committed, synchronized exactly, and passes
the full prelaunch gate.
