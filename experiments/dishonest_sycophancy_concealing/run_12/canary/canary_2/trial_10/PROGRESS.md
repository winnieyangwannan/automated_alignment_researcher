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
