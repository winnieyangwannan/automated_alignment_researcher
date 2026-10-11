# Run 12 Canary 2 Trial 10 progress

All timestamps use Pacific Time (`PT`). This log contains orchestration metadata
only; never record generated rows, prompts, responses, credentials, or held-out
content.

### ⏳ 04:04 PT — PREPARING: Trial 10 created from the frozen contract

Trial 9 failed safely before `sbatch` after FAIR's `/home` and `/storage/home`
aliases caused an in-repository runtime profile to be misclassified as external.
Repair commit `d38aa7c` is synchronized exactly to the clean HPC `autodata`
worktree.

Validated repair coverage:

- launcher and shared runtime roots use physical canonical paths;
- `/home` invocation resolves repository and profile under `/storage/home`;
- the strict run-declared/explicit profile identity check remains enabled;
- the Trial 8 action-result normalization and private diagnostic repairs remain
  covered;
- HPC path/config/orchestration gate passes 48 tests;
- local/HPC action-result gate passes 114 tests plus 6 subtests.

Next: commit Trial 10 records, synchronize the exact commit, run immutable
preflight, launch one `alpha` bootstrap canary, and monitor through the verified
training-smoke boundary. Evaluator count must remain zero.

### ⏳ 04:09 PT — RUNNING: immutable Trial 10 child chain launched

The live Kimi/MCP, canonical-path, retained Gemma endpoint, pinned native-engine,
and exact adapter-contract gates passed. Launcher `1814684` emitted the required
separate child jobs:

```text
✓ Launcher 1814684 completed 0:0
✓ Immutable AAR source 9d6a25606a38
✓ Immutable native source d6e5619bab0b
✓ Research job 1814688 created
✓ Controller job 1814689 dependency-gated behind research
✓ Evaluator job absent
⏳ Research allocation and workspace authoring
○ Canonical meta baseline and three iterations
○ Production and verified handoff
○ One-step training smoke
```

Attempt root:
`/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T110535Z-9d6a25606a38`.
The attempt-local source is clean and immutable, so later documentation commits
cannot change this execution.
