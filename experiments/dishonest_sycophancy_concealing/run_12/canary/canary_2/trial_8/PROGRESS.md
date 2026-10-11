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
