# Run 9 implementation changes

This log records meaningful implementation changes made while stabilizing Run 9.
Each entry identifies the observed problem, root cause, fix, validation, measured
effect, and source-control provenance. Run outputs and transient endpoint details
remain outside Git.

## Reduce repeated AutoData task-state writes

### Problem

During baseline generation, individual broker jobs normally completed in about
7–12 seconds (median approximately 9.1 seconds), but AutoData ingested completed
results much more slowly. Iteration 0 could remain active for tens of minutes,
with observed end-to-end ingestion near one result per minute despite 16-way
concurrency.

The broker was not the bottleneck. AutoData's `ExecutionEngine._wait` loop polled
each active task approximately every 200 milliseconds and called
`update_task_attempt` on every poll, even when the task remained in the same
state. At 16 concurrent tasks this could cause roughly 80 redundant SQLite
update attempts per second. The run's AutoData state database was on network
storage, making SQLite locking and filesystem synchronization unusually costly.
Repeated control-plane reads for wall-budget and cancellation checks added more
database traffic on the same polling path.

### Fix

The native AutoData execution engine now:

- remembers the last observed executor status and writes task state only when
  that status changes;
- continues polling the executor so terminal results are detected promptly;
- checks wall budget, cancellation state, and progress every two seconds rather
  than on every 200-millisecond executor poll; and
- preserves the existing terminal-state, cancellation, and error behavior.

No broker implementation or job-execution semantics were changed. This is a
control-plane persistence optimization inside AutoData.

### Validation and measured effect

- Added regression coverage in `tests/test_engine.py` for unchanged-state
  polling and state transitions.
- The AutoData test suite passed on the combined stabilized revision: 75 passed
  and 1 skipped.
- Broker jobs continued to complete in approximately 7–12 seconds.
- The new native lifecycle preflight initially ingested about 24 results per
  minute, compared with approximately one result per minute in the affected
  run. This is an observed run-specific improvement, not a general throughput
  guarantee.
- No result corruption was observed before or after the fix. The original
  failure mode was excessive latency, delayed batch replenishment, and poor
  utilization of configured concurrency.

### Provenance

- Repository: `autodata_pipelines`
- Core fix: `10c6d5e75c7753fd55fa7fbb68b32b389e103f47`
  (`Engine: avoid repeated task-state writes`)
- Bundled plugin wheel update: `559c4a9`
- The commits were synchronized to the FAIR HPC AutoData checkout used by the
  Run 9 preflight.

