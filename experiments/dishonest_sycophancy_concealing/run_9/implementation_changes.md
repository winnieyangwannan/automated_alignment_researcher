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

## Add a trusted AAR approval bridge for native AutoData gates

### Problem

AutoData already creates native `approve_grounding`, `approve_baseline`, and
`approve_resources` actions and pauses its lifecycle until they are completed.
The AAR research agent must not approve its own evidence, possess the approval
signing key, or directly write a fabricated approval result into AutoData.

At the same time, replacing AutoData's lifecycle with a second AAR-specific
orchestrator would duplicate behavior and make the integration harder to audit.
The integration therefore needed one narrow bridge between the sandboxed
researcher and AAR's trusted integrity monitor while preserving AutoData's
native actions, artifacts, state machine, and CLI.

### Fix

AAR now exposes one AutoData-specific MCP operation to the research agent:

```text
review_autodata_action(action_id)
```

The operation runs in the trusted AAR parent process, outside the research
agent's Bubblewrap sandbox. It performs the following sequence:

1. Resolve the exact action from the current native AutoData SQLite state and
   require it to be pending and workspace-scoped.
2. Accept only the three delegated native approval kinds.
3. Load the action's evidence from AutoData's content-addressed artifact store
   and recompute every referenced SHA-256 digest.
4. Verify deterministic requirements, including grounding coverage, successful
   baseline dry-run samples, bounded mutable paths, and the binding between the
   AutoData workspace and the approved AAR proposal.
5. Ask AAR's independent integrity monitor to judge the semantic questions for
   grounding or baseline approval. Resource readiness is checked
   deterministically.
6. Sign a payload containing the action identity, scope, evidence digests,
   decision, feedback, actor, and policy version with an owner-only private key
   that is unavailable to the research agent.
7. Use the original AutoData CLI to run `action begin`, obtain its lease token,
   and `action complete` the same native action with `approve`, `revise`, or the
   required resource retry result.
8. Write an owner-only audit record containing the proposal binding, monitor
   identity, evidence digests, decision, feedback, and signed-payload digest.

The MCP tool is therefore a constrained request to the trusted approval
principal, not an alternate AutoData lifecycle API. Normal workspace,
execution, meta-optimization, and export operations continue through the
existing AutoData plugin and CLI. A monitor failure or malformed evidence fails
closed.

The lightweight native preflight explicitly uses Luna for fast approval-path
validation. The full AAR chain defaults to Claude Opus 4.8 unless the monitor
model is overridden. This approval role is distinct from the Luna judge that
scores individual Kimi-generated examples.

### Architecture

![AAR, MCP, and AutoData trust boundary](autodata_mcp_boundary.svg)

Shareable copy: [Pixelcloud diagram](https://pxl.cl/fq5l4)

### Validation

- Unit coverage exercises invalid action IDs, missing evidence, proposal
  binding, signature/audit behavior, native CLI failures, and action completion.
- The native lifecycle preflight exercised real `approve_grounding` and
  `approve_baseline` actions through the MCP-equivalent trusted bridge.
- The preflight reached `workspace_frozen` and `meta_completed`, proving that
  AutoData accepted the delegated decisions and advanced its native lifecycle.
- The broker and all ordinary AutoData operations remain outside MCP.

### Provenance

- Initial delegated native approval flow: `5d49614`
- Proposal-to-workspace binding: `231f60f`
- Bootstrap diagnostics and native lifecycle preflight: `61257c2`
- Primary implementation: `aar/research_loop/autodata_approval.py`
- Agent-facing operation: `review_autodata_action` in
  `aar/research_loop/tools/server_api_tools.py`
