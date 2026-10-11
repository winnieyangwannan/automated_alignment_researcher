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
