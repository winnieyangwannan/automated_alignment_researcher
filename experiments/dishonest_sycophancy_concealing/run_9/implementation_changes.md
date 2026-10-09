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

## Switch trusted question-only generation from Firecracker to local Bubblewrap

### Why Firecracker was selected initially

Firecracker itself is a lightweight micro-VM technology, not an AutoData
invention. AutoData provides a broker runner that obtains a SandoQ Firecracker
lease, pulls and verifies a digest-pinned OCI image, runs the declared phases,
returns only allowlisted results, and releases the VM. This is AutoData's
prominent general-purpose execution path and provides strong isolation for
arbitrary code, OCI-dependent environments, and sealed-test verification.

Starting with Firecracker was therefore a conservative security choice.
However, Run 9 data generation is a fixed, operator-reviewed, question-only
Python recipe. It makes Kimi generation and Luna judging calls, writes one
declared result, and does not need an arbitrary OCI environment, hidden inputs,
or a verifier phase. Firecracker's stronger VM boundary added machinery that
this workload did not use.

AutoData already documents a more specific fit in
`docs/firecracker-broker.md` under **Trusted question-only local runner**. That
runner preserves the broker boundary while executing each solve phase in a
local Bubblewrap process sandbox.

### Observed Firecracker bottleneck

Every simultaneous Firecracker task required a separate lease from a finite
SandoQ warm pool:

```text
16 requested tasks
  → 16 Firecracker VM leases required
  → warm pool has fewer available VMs
  → HTTP 429, lease waiting, or timeout
```

The retained capacity probes showed:

- `oci-runner-firecracker-small` repeatedly had no available pod;
- `medium` admitted only three of four concurrent sessions before its fourth
  request exhausted the bounded lease wait; and
- `large` admitted four sessions in one canary, but a subsequent real attempt
  still encountered pool-exhaustion HTTP 429 responses at concurrency four.

Live events from the retained Firecracker attempt showed a median broker-task
duration of approximately 37 seconds: 19 seconds leasing a VM, 5 seconds
preparing it, and only about 9 seconds in the Kimi-plus-Luna solve. Firecracker
therefore spent substantially more time provisioning the execution boundary
than performing the actual Run 9 work.

### Change

Run 9 now selects AutoData's existing `local-bwrap` broker runner on a dedicated
CPU Slurm allocation:

```text
One CPU Slurm allocation
  → one authenticated loopback AutoData broker
  → up to 16 local Bubblewrap task sandboxes
  → Kimi generation and Luna judging
```

The broker implementation was not replaced or forked for this change. It still
owns the attempt-scoped authentication capability, model credential injection,
campaign cost reservations, idempotency ledger, result allowlist, and output
secret scan. AutoData still owns corpus fan-out, budgets, retries, candidate
history, meta-optimization, and comparison policy.

Bubblewrap removes the external VM-lease pool and the per-task VM/image
preparation path. The switch therefore removes these failure and latency
sources:

- SandoQ warm-pool dependence;
- lease HTTP 429 responses and lease timeouts;
- VM startup, renewal, release, and ambiguous disconnects;
- per-task OCI image preparation; and
- Firecracker gateway, registry, and token dependencies that a question-only
  task does not require.

### Internal model routing

The first local-runner probes correctly removed inherited proxy variables but
then showed that the external inference-gateway hostname was not reachable from
the HPC task environment. Those attempts failed before reaching Kimi and
recorded no provider usage.

The route changed from the external HTTPS ingress:

```text
https://ram-inference-gateway.ingress.fair-cw-use2-1.cw.metafb.cloud/v1
```

to the cluster-internal Slurm ingress:

```text
http://fair-cw-use2-1-ingress-slurm-ingress/v1
Host: ram-inference-gateway.ingress.
```

The campaign policy still pins and passes the same model and deployment headers,
so the generator remains `Kimi-K2.6` on deployment `winnieyangwn-kimi26`. Only
the path from the compute node to the inference gateway changed.

This restored model connectivity without reintroducing inherited proxy
variables into the task sandbox. It also removes external DNS, TLS, proxy, and
egress dependencies from this local cluster path. The corrected concurrency-16
canary reached Kimi and Luna for all 16 jobs. This change does not add Kimi
replicas, distribute the endpoint across more nodes, or by itself raise model
serving capacity; any higher request concurrency still requires a load test.

### Node-local broker ledger

The broker's hot SQLite idempotency ledger now lives under the compute node's
`$SLURM_TMPDIR` rather than inside the retained network-filesystem directory.
Uploads and declared results remain on retained storage, and clean shutdown
checkpoints and copies a broker-database snapshot into the attempt directory.

This follows the AutoData broker runbook for a network-backed broker root. It is
separate from the AutoData `ExecutionEngine` SQLite fix above: the engine fix
reduces repeated writes to native lifecycle state, while node-local placement
keeps the broker's distinct job ledger away from network-filesystem lock and
WAL latency.

Without this placement, a low-load run might still work, but concurrent broker
state transitions are more likely to suffer slow locking, delayed idempotency
lookups, write timeouts, or misleading broker stalls. The node-local ledger is
therefore stability hardening rather than a change to job semantics.

### Validation and measured effect

- The corrected concurrency-16 local canary completed in 2 minutes 3 seconds.
  All 16 broker jobs and task envelopes succeeded and recorded both Kimi and
  Luna usage. Ten samples were accepted and six were intentionally filtered by
  the judge; there were no model, parsing, broker, lease, or routing failures.
- Subsequent local broker jobs completed in approximately 7–12 seconds, with a
  median near 9.1 seconds, compared with the observed Firecracker median near
  37 seconds.
- The measured per-task reduction is approximately 28 seconds, or 76%, making
  the broker task about four times faster before considering concurrency.
- Validated concurrency increased from approximately four Firecracker sessions
  to 16 local tasks. The improvement comes from using the CPU allocation
  already held by the run rather than requesting one scarce external VM per
  example.

There is no clean full-production A/B because the Firecracker attempts failed
or were stopped before completing the same production workload. The 37-second
to 9.1-second comparison is a broker-task measurement, not a guarantee for
end-to-end AutoData duration. AutoData lifecycle work, SQLite ingestion, model
rate limits, and quality acceptance still affect total runtime.

### Security and scaling boundary

Local Bubblewrap is appropriate here only because the recipe is trusted,
operator-reviewed, solve-only, and question-only. Firecracker remains the
correct choice for arbitrary or adversarial code, task-specific OCI images,
sealed inputs, alternate work directories, or hidden-test verification.

Concurrency 16 is validated. Concurrency 32 is not assumed safe: Bubblewrap
removes the Firecracker lease constraint, but higher concurrency can still
exhaust the Slurm allocation or hit Kimi/Luna endpoint limits and must pass a
separate load test.

### Provenance

- Select the trusted local broker path: `c8dea84`
- Route local Kimi calls through internal ingress: `583673b`
- Record the successful local concurrency canary: `1cd196a`
- Keep the broker ledger node-local with retained snapshots: `eb57e64`
- The original AutoData broker and `local-bwrap` runner code remain unchanged.

## Bootstrap the pinned AutoData plugin without `ensurepip`

### Problem

The AAR parent process needs an isolated, version-pinned AutoData Python runtime
to invoke the plugin wrapper and complete native approval actions. The plugin
already bundles a locked AutoData wheel, and its bootstrap originally prepared
that runtime with this sequence:

```text
create virtual environment with pip
  → Python invokes ensurepip to install pip
  → pip installs the bundled AutoData wheel
```

`ensurepip` is the optional CPython component that seeds `pip` into a new
virtual environment. The minimal FAIR Python installations used by both the
chain host and dedicated broker runtime omit it. Consequently,
`venv.EnvBuilder(with_pip=True)` failed before AutoData could import or the MCP
approval bridge could review an action.

The affected full attempt spent time planning and preparing a workspace but
then failed at the first delegated approval boundary. It created no broker
generation jobs, made no Kimi or Luna calls, and produced zero durable AAR
score/result pairs. This was a host-runtime bootstrap failure, not an AutoData
lifecycle, monitor-policy, or broker failure.

### Fix

The bootstrap now creates the virtual environment with
`venv.EnvBuilder(with_pip=False)`. Because the locked plugin currently contains
only hash-verified, dependency-free, pure-Python wheels, it can safely install
the package without a general-purpose package installer:

```text
verify lock and every bundled wheel SHA-256
  → reject the lock if external dependencies are declared
  → create a pip-free virtual environment
  → find that environment's pure-Python package directory
  → reject unsafe wheel paths and extract the verified wheel
  → import AutoData and verify its pinned version
```

The dependency check is deliberately fail-closed. If the plugin later gains
dependencies, bootstrap refuses to guess how to install them; its locked
installer design must be updated explicitly. Wheel members are also checked
for path traversal before extraction.

### Lifecycle and caching

Run 9 sets an attempt-local plugin cache and executes bootstrap before starting
the research agent. The resulting interpreter is reused for every AutoData
phase, task, meta-optimization iteration, and AAR session within that chain
attempt. It is not rebuilt per generated example.

A new full AAR attempt currently prepares a new environment once because it
gets a new attempt directory. This favors reproducibility and prevents stale
cross-run environments. The setup is offline and lightweight; no package is
installed globally and no network download is performed.

Moving bootstrap to chain startup also makes a missing or incompatible runtime
fail before the agent spends time on literature review, method authoring, or
workspace construction.

### Validation

- Added `tests/test_plugin_bootstrap.py` for pip-free creation, import, cache
  reuse, and lock validation.
- The complete AutoData suite passed on the combined stabilized revision: 75
  passed and 1 skipped.
- The exact dedicated Python executable used on FAIR HPC successfully created
  the environment and imported AutoData `1.0.0`.
- The chain now logs a successful pinned bootstrap before starting an AAR agent.

### Provenance

- AutoData implementation and tests: `223af462f69b2fd2d5eca6849ae3a6f5fff47d5b`
  (`Bootstrap plugin without ensurepip`)
- AAR chain startup preflight and clearer subprocess diagnostics: `61257c2`
- AutoData implementation: `plugin/autodata/scripts/bootstrap.py`

## Bound meta-optimization and add production acceptance headroom

### Evidence from the native lifecycle preflight

The lightweight preflight completed the real native path in 963.12 seconds:

```text
budget preflight
  → signed grounding approval
  → signed baseline approval
  → frozen workspace
  → meta-optimization
  → fixed-winner production
  → dataset export and training-side consumption
```

It produced 13 accepted production rows from 16 tasks, retained both approval
audits, and verified the exported dataset digest. The report status was
`passed`. Slurm marked the job failed only because the initial fail-fast check
required completion within 900 seconds, so a functionally successful lifecycle
missed that provisional ceiling by 63.12 seconds.

The ceiling is now 1,200 seconds. This remains a strict 20-minute end-to-end
gate inside a 30-minute Slurm job, but it is grounded in the measured healthy
runtime rather than rejecting the proven path at 16 minutes.

### Meta-optimization bound

The production configuration previously allowed between 3 and 10 native
meta-optimization iterations. Each additional iteration generates and judges
new tuning, validation, and test partitions. With five sequential outer AAR
sessions, the seven optional iterations could multiply model traffic without
being required by the Run 9 study design.

The production chain now sets both the minimum and maximum to three iterations.
This guarantees the required three complete optimization rounds while reducing
the worst-case meta-optimization count by 70% relative to the former ceiling.
It does not skip iteration 0, validation, comparison, winner selection, or the
separate fixed-winner production execution.

### Production acceptance headroom

The retained local canary accepted 10 of 16 examples (62.5%), while the native
lifecycle preflight accepted 13 of 16 (81.25%). The former 1,500-task ceiling
could retain only about 938 rows at the lower observed rate, below the required
1,000-row dataset.

The final production controls are:

```text
accepted-row target:       1,000
initial generation tasks:  1,250
maximum generation tasks:  2,000
validated concurrency:     16
meta iterations:           exactly 3
```

AutoData can therefore replenish after the initial batch and still reach 1,000
rows at a 50% aggregate acceptance rate. The target dataset size is unchanged;
only the bounded attempt headroom increased. The campaign-wide USD reservation
limit remains `$299` and continues to fail closed before work that cannot be
funded.

Concurrency remains 16 because that exact load passed. It was not raised to 32
without a separate endpoint and node-capacity test.

### Validation and provenance

- Focused Run 9 infrastructure, native lifecycle, and approval tests passed: 15
  passed.
- Both modified Slurm scripts passed Bash syntax validation.
- Production-setting implementation and regression assertions: `50da35f`
- Successful native report:
  `native-preflight-20261009T031217Z-61257c251bb7/lifecycle/report.json`

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

Shareable copy: [Pixelcloud diagram](https://pxl.cl/fq88B)

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
