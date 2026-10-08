# Interface between AAR and AutoData

## Start here

This integration lets an AAR research agent use the original AutoData framework
to generate training data during an AAR iteration. AutoData remains a separate,
operator-pinned framework. AAR adds a controlled interface around it so the
research agent can request and guide data generation without receiving model
credentials, SandoQ credentials, unrestricted infrastructure access, or the
ability to change the campaign budget.

The most important distinction is:

- The AAR agent sees only seven controlled tools.
- Those tools call an AAR-owned adapter service.
- The adapter invokes fixed operations in the original AutoData CLI.
- AutoData runs the AAR-owned scientific recipe through SandoQ Firecracker.
- Kimi generates candidate examples and GPT-5.6 Luna independently judges
  them.
- The resulting dataset is verified before AAR training may consume it.
- AAR records proof that training actually consumed that exact dataset.

`autodata_generate` and the other six tools are **not original AutoData
commands**. They are the AAR-facing API added by this integration. The original
AutoData checkout remains at `/home/winnieyangwn/autodata_pipelines`, currently
on `main`.

## Big-picture architecture

```text
AAR research agent
    |
    | seven narrow MCP tools
    v
aar/research_loop/tools/autodata_tools.py
    |
    | authenticated HTTP
    v
AAR-owned AutoData adapter service
aar/infrastructure/autodata_service.py + scripts/autodata_live_sandoq_driver.py
    |
    | fixed native autodata CLI commands
    v
original AutoData framework
~/autodata_pipelines
    |
    | native workspace, actions, meta_optimize, comparison, production
    v
SandoQ Firecracker
    |
    +-- Kimi generates candidate training examples
    +-- GPT-5.6 Luna independently judges them
    |
    v
verified JSONL dataset + provenance manifest
    |
    | load_autodata_dataset() + consumption receipt
    v
AAR training -> model submission -> evaluation
```

The agent does not run the original command directly:

```bash
autodata workspace create \
  --brief autodata.workspace.json \
  --root /path/to/draft
```

Instead, the agent calls `autodata_generate`. The AAR adapter verifies the
approved proposal and then the live driver invokes the original `autodata
workspace create` command with fixed state paths and operator-controlled
arguments. From that point onward, workspace and execution transitions remain
native AutoData CLI operations.

## What this integration added

The interface is larger than `autodata_tools.py`. It has seven distinct layers.

### Agent-facing tool layer

New file:

- [`../research_loop/tools/autodata_tools.py`](../research_loop/tools/autodata_tools.py)
  defines and registers the seven MCP tools: `autodata_generate`,
  `autodata_status`, `autodata_step`, `autodata_action_begin`,
  `autodata_action_complete`, `autodata_action_fail`, and `autodata_fetch`. It
  validates the literal `AUTODATA_SPEC`, checks the proposal binding, rejects
  agent-created approvals, authenticates adapter requests, validates returned
  artifacts, and writes immutable dataset files.

Modified AAR files:

- [`../research_loop/agent.py`](../research_loop/agent.py) registers the
  AutoData MCP server and permits exactly the seven tool names when AutoData is
  enabled.
- [`../research_loop/prompt_safety.jinja2`](../research_loop/prompt_safety.jinja2)
  tells the research agent when and how to use AutoData, defines the required
  `AUTODATA_SPEC` contract, and requires training through the verified loader.
- [`../research_loop/tools/server_api_tools.py`](../research_loop/tools/server_api_tools.py)
  extends `submit_idea_proposal` to validate and freeze the method-code and
  `AUTODATA_SPEC` hashes.
- [`../research_loop/monitor.py`](../research_loop/monitor.py) allows disclosed
  strong-model data generation while retaining the AAR safety and proposal
  review boundary.

### Adapter and policy layer

New files:

- [`../infrastructure/autodata_service.py`](../infrastructure/autodata_service.py)
  implements the authenticated service, durable run registry, proposal
  binding, action leases, delegated approvals, campaign-wide cost ledger,
  deterministic test backend, live backend, and artifact publication.
- [`../../scripts/autodata_service.py`](../../scripts/autodata_service.py)
  starts that service, checks the pinned upstream AutoData revision, and
  selects the deterministic or live backend.
- [`../../scripts/autodata_live_sandoq_driver.py`](../../scripts/autodata_live_sandoq_driver.py)
  is the bridge from the AAR adapter to the pinned original AutoData CLI. It
  chooses the next authorized native command, supplies operator-owned
  manifests and paths, preserves native IDs and lease tokens, and verifies the
  exported rows. It does not implement a second workspace or execution engine.

### Scientific recipe layer

The complete AAR-owned recipe was added under
[`dishonest_sycophancy_concealing/`](dishonest_sycophancy_concealing/):

- [`autodata.workspace.json`](dishonest_sycophancy_concealing/autodata.workspace.json):
  native AutoData workspace brief and execution defaults.
- [`autodata.pipeline.json`](dishonest_sycophancy_concealing/autodata.pipeline.json):
  task command, checker, schema, objective, validity floor, and mutation
  boundary.
- [`grounding/build_manifest.py`](dishonest_sycophancy_concealing/grounding/build_manifest.py):
  deterministic construction of 96 or more original synthetic scenarios.
- [`recipe/task.py`](dishonest_sycophancy_concealing/recipe/task.py): Kimi
  generation, Luna judging, token/cost metering, acceptance, and task-result
  construction.
- [`recipe/check.py`](dishonest_sycophancy_concealing/recipe/check.py): recipe
  request, prompt variant, field-size, and source-policy checks.
- [`recipe/prompt_variant.json`](dishonest_sycophancy_concealing/recipe/prompt_variant.json):
  the mutable prompt-strategy choice used by meta-optimization.
- [`recipe/request.json`](dishonest_sycophancy_concealing/recipe/request.json):
  placeholder replaced with the approved scientific request in the native
  workspace.
- [`objective.json`](dishonest_sycophancy_concealing/objective.json): the
  quality objective AutoData maximizes.
- [`comparator.json`](dishonest_sycophancy_concealing/comparator.json): the
  improvement and validity rules used to compare candidates.
- [`framework.lock.json`](dishonest_sycophancy_concealing/framework.lock.json):
  compatible AutoData framework contract.
- [`schemas/task-result.schema.json`](dishonest_sycophancy_concealing/schemas/task-result.schema.json):
  strict schema for each generated task result.

Every recipe file is explained in detail in the recipe walkthrough below.

### Dataset verification and training layer

New file:

- [`../infrastructure/autodata.py`](../infrastructure/autodata.py) validates the
  fetched dataset and provenance, exposes `load_autodata_dataset()`, creates a
  consumption receipt, and builds the dataset link propagated to training and
  evaluation.

Modified AAR files:

- [`../../scripts/submit_train_job.sh`](../../scripts/submit_train_job.sh) and
  [`../../scripts/slurm_train_submit.sh`](../../scripts/slurm_train_submit.sh)
  fail closed when required AutoData artifacts or the consumption receipt are
  missing.
- [`../transport.py`](../transport.py) carries AutoData provenance in model
  submission metadata.
- [`../eval_pod/entrypoint.py`](../eval_pod/entrypoint.py) propagates that
  metadata into evaluator results.

### Credential-isolation layer

Modified or added operational files:

- [`../../scripts/aar_runtime_env.sh`](../../scripts/aar_runtime_env.sh)
  separates trusted parent variables from the research subprocess environment.
- [`../../scripts/claude_research_bwrap.sh`](../../scripts/claude_research_bwrap.sh)
  gives the research agent a read-only source view while hiding credentials,
  operator state, and service secrets.

The agent can invoke the seven tools through the trusted AAR parent, but cannot
read or reuse their bearer token or the provider/SandoQ credentials.

### Production launch and verification layer

- [`../../experiments/dishonest_sycophancy_concealing/run_8/submit_run_8.sh`](../../experiments/dishonest_sycophancy_concealing/run_8/submit_run_8.sh)
  validates the branch, upstream AutoData revision, Kimi deployment, Gemma
  inputs, credentials, resource profile, cost formula, and storage root before
  submitting a run.
- [`../../experiments/dishonest_sycophancy_concealing/run_8/run_8_pipeline.sbatch`](../../experiments/dishonest_sycophancy_concealing/run_8/run_8_pipeline.sbatch)
  launches the services, evaluator, and AAR chain.
- [`../../experiments/dishonest_sycophancy_concealing/run_8/run_8_autodata_services.sbatch`](../../experiments/dishonest_sycophancy_concealing/run_8/run_8_autodata_services.sbatch)
  starts the native AutoData broker, runs required canaries, and starts the AAR
  adapter.
- [`../../replication/verify_run8_autodata.py`](../../replication/verify_run8_autodata.py)
  verifies that both requested iterations generated, fetched, consumed,
  trained on, and evaluated with the bound AutoData dataset.

### Test and preflight layer

- [`../../scripts/autodata_native_broker_canary.py`](../../scripts/autodata_native_broker_canary.py)
  proves a real Firecracker lease and task.
- [`../../scripts/autodata_model_broker_canary.py`](../../scripts/autodata_model_broker_canary.py)
  proves a real Kimi generation plus Luna judgment inside the broker path.
- [`../../scripts/autodata_unattended_e2e.py`](../../scripts/autodata_unattended_e2e.py)
  exercises the native lifecycle deterministically.
- [`../../scripts/autodata_agent_smoke.py`](../../scripts/autodata_agent_smoke.py)
  exercises the seven-tool contract with a bounded AAR agent.
- [`../../scripts/autodata_contract_smoke_server.py`](../../scripts/autodata_contract_smoke_server.py)
  is the older deterministic HTTP contract smoke and is not scientific
  production generation.
- The focused tests are
  [`../../tests/test_autodata_tools.py`](../../tests/test_autodata_tools.py),
  [`../../tests/test_autodata_service.py`](../../tests/test_autodata_service.py),
  [`../../tests/test_autodata_live_sandoq_driver.py`](../../tests/test_autodata_live_sandoq_driver.py),
  [`../../tests/test_autodata_model_broker_canary.py`](../../tests/test_autodata_model_broker_canary.py),
  [`../../tests/test_autodata_unattended_e2e.py`](../../tests/test_autodata_unattended_e2e.py),
  and [`../../tests/test_autodata_agent_smoke.py`](../../tests/test_autodata_agent_smoke.py).

## What remains original AutoData

The canonical checkout is not replaced or copied into AAR. It still owns:

- `WorkspaceEngine.create(...)` and workspace persistence;
- native workspace actions and revisions;
- grounding, baseline, and resource-review states;
- immutable workspace snapshots;
- execution construction and persistence;
- `meta_optimize` candidate evaluation;
- candidate comparison and winner selection;
- the production execution state machine;
- SandoQ executor integration and task-result collection.

Original references:

- [AutoData README](/home/winnieyangwn/autodata_pipelines/README.md)
- [Original AutoData CLI](/home/winnieyangwn/autodata_pipelines/src/autodata/cli.py)
- [Original workspace engine](/home/winnieyangwn/autodata_pipelines/src/autodata/workspace.py)

The AAR integration controls who may start or advance those operations, what
proposal and resources they are bound to, and how their output may enter AAR
training. It does not substitute a different AutoData lifecycle.

## The original AutoData CLI and why AAR uses MCP

### The native CLI is the operational source of truth

AutoData already has a complete command-line interface. Its 14 leaf operations
are defined in the canonical
[`src/autodata/cli.py`](/home/winnieyangwn/autodata_pipelines/src/autodata/cli.py):

| Native operation      | Native purpose                                                     | AAR disposition                                                        |
| --------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| `pipeline validate`   | Validate a pipeline manifest and its declared files                | Reuse automatically; optionally expose as a read-only convenience      |
| `workspace create`    | Create an idempotent native workspace from a brief                 | Expose through a typed, proposal-bound MCP operation                   |
| `workspace step`      | Advance one native workspace transition                            | Expose through MCP                                                     |
| `workspace fork`      | Fork a workspace to revise grounding, pipeline, or both            | Optional agent capability; restrict it to the agent's own workspace    |
| `workspace export`    | Export a frozen workspace snapshot                                 | Normally adapter/operator use; this is not final dataset export        |
| `execution create`    | Create an execution from pipeline and execution manifests          | Adapter-owned because it contains resource, secret, and budget choices |
| `execution step`      | Advance one native execution transition                            | Expose through MCP                                                     |
| `action begin`        | Acquire the native lease for a pending action                      | Expose through MCP; preserve the native lease token                    |
| `action complete`     | Complete the leased action with a structured JSON result           | Expose through MCP with approval-field restrictions                    |
| `action fail`         | Fail the leased action with an audited reason                      | Expose through MCP                                                     |
| `status`              | Read a study, workspace, or execution snapshot                     | Expose through MCP                                                     |
| `cancel`              | Cancel a workspace or execution                                    | Safe to expose only for subjects owned by the current AAR run          |
| `export`              | Export the final dataset of a completed execution                  | Expose through MCP, then apply AAR provenance verification             |
| `dashboard serve`     | Start the long-running human dashboard service                     | Operator-owned; it is service management, not a research decision      |

The exact number of MCP tools is not a design goal. The goal is to expose the
native operations the researcher needs while withholding infrastructure
authority it does not need. In particular, `execution create` must not let the
researcher substitute a different executor, container, secret reference,
model route, task set, concurrency, or budget. The adapter creates that native
execution from the preapproved operator profile.

### Why the researcher does not simply run Bash

Calling the CLI directly is the simplest and preferred interface for a trusted
human or operator shell:

```bash
autodata workspace create \
  --brief autodata.workspace.json \
  --root /path/to/draft
autodata workspace step <workspace-id>
autodata action begin <action-id>
autodata execution step <execution-id>
autodata status <workspace-or-execution-id>
autodata export <execution-id> --output dataset.jsonl
```

MCP is not intrinsically better than this CLI. It is useful here because the
AAR researcher runs as an intentionally restricted, credential-free process,
while real AutoData execution needs SandoQ and model-provider credentials. If
the credentials were placed in the researcher's Bash environment, agent-written
manifests or commands could potentially select another image or endpoint,
request additional secrets, exceed the campaign budget, write outside the run
directory, or expose a credential. If the credentials remain hidden, an
unmediated researcher process cannot launch the real production work.

The MCP boundary implements **controlled credential delegation**: the
researcher may request one specific AutoData operation, but the trusted parent
performs it with credentials the researcher never receives. The parent also
fixes server-owned paths and resource settings, verifies that the subject
belongs to the current AAR run, charges the shared campaign budget, and returns
only the safe JSON result.

```text
credential-free AAR researcher
    -> typed MCP request
    -> trusted AAR adapter holding credentials and fixed policy
    -> fixed native autodata CLI invocation
    -> original AutoData state machine and artifacts
```

A carefully restricted command broker could provide the same security
property; MCP is the mechanism already understood by the AAR agent runtime. It
also gives the model discoverable tool descriptions and typed argument schemas.
The important property is narrow delegation, not the MCP protocol itself.

### Thin-wrapper rule

The MCP and adapter layers must not become a second AutoData implementation.
For each agent-visible operation they should:

1. Authenticate the AAR attempt and verify proposal ownership.
2. Validate a small typed argument object and apply operator-fixed arguments.
3. Invoke the corresponding command in the pinned native `autodata` CLI.
4. Preserve native subject IDs, action IDs, lease tokens, statuses, and errors.
5. Return the native JSON with only the minimum AAR binding or safety metadata.

Only concerns absent from native AutoData belong in the wrapper: AAR proposal
binding, credential isolation, campaign-wide cost policy, delegated approval
policy, safe storage roots, final provenance verification, and proof that
training consumed the exported dataset.

The wrapper must not accept an arbitrary shell-command string, invent a second
workspace or execution state machine, or maintain a duplicate action lease.
Human debugging can always reproduce the underlying operation with the native
CLI against the same state and artifact stores.

## Ownership and trust boundaries

| Component                             | Owner                        | Authority                                                           |
| ------------------------------------- | ---------------------------- | ------------------------------------------------------------------- |
| Research method and `AUTODATA_SPEC`   | AAR research agent           | States scientific intent and training use                           |
| Proposal approval and freeze          | AAR proposal monitor         | Approves method code and freezes its hashes                         |
| Seven MCP tools                       | AAR integration              | Exposes a narrow authenticated interface to the agent               |
| Adapter service                       | AAR integration              | Enforces bindings, policy, budget, and artifact rules               |
| Workspace and execution state machine | Canonical AutoData           | Owns native actions, snapshots, executions, and comparison          |
| Recipe                                | AAR integration              | Defines this experiment's sources, task, checks, and objective      |
| Resource profile                      | Human/operator before launch | Pins models, credentials, SandoQ, cost, concurrency, and row target |
| Delegated approval policy             | AAR integrity monitor        | Approves gates only when required evidence exists                   |
| Row generation                        | Kimi-K2.6                    | Generates candidate synthetic examples                              |
| Row judging                           | GPT-5.6 Luna                 | Independently scores and accepts or rejects each example            |
| Training loader                       | AAR infrastructure           | Verifies data and records actual consumption                        |
| Evaluator                             | AAR evaluation boundary      | Scores the trained model and carries provenance metadata            |

The intended human role is configuration before the AAR loop starts. There is
no human approval step inside each AutoData run.

## Design principles

### Preserve native AutoData

The integration does not reimplement AutoData's state machine. The AAR live
driver invokes the original CLI, which owns calls to native implementations
such as `WorkspaceEngine.create(...)` and `ExecutionEngine.step(...)`.

Original references:

- [AutoData usage](/home/winnieyangwn/autodata_pipelines/README.md)
- [AutoData CLI](/home/winnieyangwn/autodata_pipelines/src/autodata/cli.py)
- [AutoData source package](/home/winnieyangwn/autodata_pipelines/src/autodata/)

The original CLI documents workspace creation as:

```bash
autodata workspace create \
  --brief autodata.workspace.json \
  --root /path/to/draft
```

In an AAR run, the agent does not run this command directly. The
`autodata_generate` tool asks the adapter to create the workspace, and the live
driver invokes this native command with server-owned paths, credentials, and
operator-fixed controls.

### Separate scientific intent from sensitive controls

The AAR agent may specify:

- the safety axis;
- the training mechanism;
- the training view;
- a random seed;
- the scientific data-generation goal.

Before the loop, the operator fixes:

- generator and judge model routes;
- API credentials;
- SandoQ credentials, image, and sandbox tier;
- exact AutoData revision;
- campaign cost cap;
- resource concurrency;
- required retained-row count;
- storage and runtime roots.

The agent cannot override operator-controlled settings through
`AUTODATA_SPEC`, tool parameters, or action results.

### Bind generation to the approved proposal

Data generation is allowed only for code approved by
`submit_idea_proposal`. The binding contains:

- AAR `run_id`;
- approved idea name;
- SHA-256 of the approved method code;
- SHA-256 of the literal `AUTODATA_SPEC`;
- resource-profile identifier and digest;
- pinned AutoData Git SHA.

This prevents an agent from obtaining approval for one method and generating
data for changed code or a different scientific request.

### Fail closed

The interface stops when required evidence is absent or inconsistent. Examples
include a changed method, unknown spec field, missing approval, invalid model
usage, exhausted budget, missing dataset digest, wrong retained-row count, or
missing training-consumption receipt.

### Keep generation and judging independent

Kimi generates each candidate example. GPT-5.6 Luna separately judges it
against the recipe rubric. Production retains only accepted rows meeting the
configured score threshold.

### Make spending global to the campaign

The cost cap is attached to a stable budget-scope ID, not an individual
proposal `run_id`. Parallel AAR chains and multiple iterations using the same
scope draw from the same cap.

### Prove training consumption

Fetching data is not enough. The approved training method must load it through
`aar.infrastructure.autodata.load_autodata_dataset()`. This produces a receipt
bound to the run and dataset digest. Training, model submission, evaluation,
and final verification carry that digest forward.

## What `AUTODATA_SPEC` is

`AUTODATA_SPEC` is an AAR-side proposal contract. It is not an original
AutoData CLI field.

When AutoData is required, the agent's proposed `run.py` must define exactly
one nonempty literal Python dictionary with this shape:

```python
AUTODATA_SPEC = {
    "schema": "aar.autodata.request/v1",
    "resource_profile": "<operator-provided profile name>",
    "safety_axis": "<the configured AAR safety suite>",
    "training_mechanism": "<how these rows will improve the candidate>",
    "training_view": "sft",  # or "preference" when the profile permits it
    "seed": 1234,
    "goal": "<specific scientific generation goal>",
}
```

| Key                  | Meaning                                                     |
| -------------------- | ----------------------------------------------------------- |
| `schema`             | Contract version; currently `aar.autodata.request/v1`       |
| `resource_profile`   | Name of the operator-pinned profile this request must match |
| `safety_axis`        | Safety property the generated data addresses                |
| `training_mechanism` | Explanation of how training on the rows should help         |
| `training_view`      | Output view expected by training: `sft` or `preference`     |
| `seed`               | Integer controlling reproducible scientific choices         |
| `goal`               | Specific data-generation objective                          |

The dictionary may not contain paths, URLs, branches, commits, SHAs, model
routes, credentials, secrets, tokens, images, budgets, concurrency, timeouts,
or retained-row limits. Those remain operator-controlled.

[`../research_loop/tools/autodata_tools.py`](../research_loop/tools/autodata_tools.py)
parses the proposed Python file with `ast`, requires exactly one assignment,
uses `ast.literal_eval`, validates the schema, and computes the canonical spec
digest. Dynamic Python expressions are intentionally rejected.

Model identities and roles are still disclosed in the proposal's paper fields,
but the operator profile—not `AUTODATA_SPEC`—selects and enforces the routes.

## The seven agent-visible tools

Only seven new tools are exposed to the research agent. They are defined and
registered in
[`../research_loop/tools/autodata_tools.py`](../research_loop/tools/autodata_tools.py).

| Tool                       | What it does                                                                        | What it does not do                           |
| -------------------------- | ----------------------------------------------------------------------------------- | --------------------------------------------- |
| `autodata_generate`        | Validates the approved proposal and creates or recovers an idempotent workspace/job | It does not immediately generate all rows     |
| `autodata_status`          | Reads state, progress, counts, and safe provenance                                  | It does not advance the state machine         |
| `autodata_step`            | Advances one native workspace or execution transition                               | It cannot bypass pending actions or approvals |
| `autodata_action_begin`    | Leases one agent-authorable pending action                                          | It refuses delegated approval actions         |
| `autodata_action_complete` | Submits the result of a leased semantic action                                      | It rejects fabricated approval fields         |
| `autodata_action_fail`     | Records a failed action attempt and reason                                          | It does not silently discard audit history    |
| `autodata_fetch`           | Verifies and stores completed rows and manifest immutably                           | It cannot fetch an incomplete or invalid run  |

### `autodata_generate`

`autodata_generate` is not part of original AutoData. It is an AAR-specific MCP
tool. Its arguments are only:

```json
{
  "run_id": "<run ID issued by proposal approval>",
  "idea_name": "<approved method package name>"
}
```

It performs these checks and actions:

1. Validate `run_id` and `idea_name` syntax.
2. Load the frozen proposal snapshot for that run.
3. Require the proposal idea name to match.
4. Re-read the current method code and require its hash to match the approved
   hash.
5. Extract and validate the one literal `AUTODATA_SPEC`.
6. Require its digest to match the proposal-frozen digest.
7. Add the operator-controlled profile, budget scope, cap, and row target.
8. Send authenticated `POST /v1/jobs` to the adapter.
9. Return the idempotent job ID and initial native state.

The request path is:

```text
AAR agent
  -> autodata_generate
  -> POST /v1/jobs
  -> AutoDataJobService
  -> live lifecycle driver
  -> WorkspaceEngine.create(...)
```

The name is slightly misleading: it starts the lifecycle. Actual row
generation occurs later during native executions. `autodata_start` would be a
more precise future name.

### `autodata_status`

Calls `GET /v1/runs/<run_id>`. It is read-only and reports the current state,
pending action, execution progress, counts, provenance summary, and terminal
success or failure. The AAR envelope includes the latest snapshot returned by
the native `autodata status <subject-id>` command rather than inventing a
replacement native status model.

### `autodata_step`

Calls `POST /v1/runs/<run_id>/step`. Before making the request, the tool
revalidates the proposal binding. One call advances one deterministic native
transition and can return safe status, a semantic action, delegated approval
evidence, execution progress, success, or failure.

### Action begin, complete, and fail

`autodata_action_begin` invokes native `autodata action begin` and returns its
lease token unchanged. The adapter does not mint a second lease. The native
lease prevents stale or duplicated completion after retries; if the response
is lost, retrying returns the already-persisted native token.

`autodata_action_complete` submits a JSON result with that lease token. The
client rejects attempts to submit `approved`, `user_acknowledged`, or
`approval_attestation`, as well as approval-like decisions. Results are size
bounded.

`autodata_action_fail` records a concise failure reason through the same lease.
The native state machine retains the attempt in its audit history and decides
whether to retry or terminate.

### `autodata_fetch`

Calls `GET /v1/runs/<run_id>/artifacts`, then validates the rows and provenance
manifest against the approved run, pipeline SHA, method-code hash, and spec
hash. It writes mode-0600 files:

```text
$TEAM_DIR/autodata/<run_id>/autodata_rows.jsonl
$TEAM_DIR/autodata/<run_id>/autodata_manifest.json
```

The writes are immutable. If a file already exists with different content, the
tool fails rather than overwriting it. The artifact directory must remain under
the configured AAR runtime root and cannot be redirected through symlinks.

## Tool registration and the AAR prompt

The AAR researcher learns about the tools in two independent ways. It does not
need to find them by reading this README or searching the repository.

### Runtime MCP registration

When the launcher sets `AAR_AUTODATA=1`,
[`../research_loop/agent.py`](../research_loop/agent.py) imports
`create_autodata_tools_server()` and constructs an in-process MCP server named
`autodata-tools`. The server publishes each tool's name, description, JSON
argument schema, and implementation to the research-agent runtime.

The same file adds exactly these qualified names to the agent's tool allowlist:

```text
mcp__autodata-tools__autodata_generate
mcp__autodata-tools__autodata_status
mcp__autodata-tools__autodata_step
mcp__autodata-tools__autodata_action_begin
mcp__autodata-tools__autodata_action_complete
mcp__autodata-tools__autodata_action_fail
mcp__autodata-tools__autodata_fetch
```

The agent therefore sees the seven tools and their schemas in its runtime tool
catalog. The human-readable prompt and ordinary discussion use their shorter
names, such as `autodata_generate`.

If `AAR_AUTODATA_REQUIRED=1` but `AAR_AUTODATA` is not enabled, or if the MCP
server cannot validate its operator configuration, AAR fails before starting
the researcher. The researcher cannot add an unapproved tool to this allowlist.

### Prompt guidance

[`../research_loop/prompt_safety.jinja2`](../research_loop/prompt_safety.jinja2)
is resolved into the researcher's launch prompt when AutoData is enabled. It
explains when to call the tools and the required order:

```text
submit_idea_proposal
  Existing AAR server-api tool. Reviews the method and freezes its code and
  AUTODATA_SPEC hashes. This is not one of the seven AutoData MCP tools.

  -> autodata_generate
     Validate the approved proposal binding and create or recover the native
     AutoData workspace/job. This starts the lifecycle; it does not yet produce
     the complete dataset.

  -> autodata_step
     Advance one native AutoData workspace or execution transition and return
     either progress, completion, failure, or the next pending action.

  -> autodata_action_begin
     Lease a pending agent-authorable action so retries or parallel calls cannot
     complete the same action twice.

  -> autodata_action_complete OR autodata_action_fail
     Complete the leased action with its structured result, or record a concise
     failure. The agent cannot use either operation to manufacture approvals.

  -> repeat autodata_step; use autodata_status as needed
     autodata_status reads current state, progress, counts, and safe provenance
     without advancing the native state machine.

  -> autodata_fetch
     After successful production, validate the dataset and provenance manifest,
     then write immutable mode-0600 artifacts under the run's team directory.

  -> load_autodata_dataset during training
     AAR training API, not an MCP tool. Revalidate the fetched artifacts, return
     the rows to the method, and write proof that training consumed that exact
     run-bound dataset.
```

Specifically, the prompt instructs the agent to:

1. Define the literal `AUTODATA_SPEC` before proposal submission.
2. Disclose model identities and roles in the proposal.
3. Call `submit_idea_proposal` first.
4. Call `autodata_generate` only for the approved code and issued run ID.
5. Repeatedly call `autodata_step`.
6. Lease and complete only semantic authoring actions.
7. Never complete grounding, baseline, or resource approvals.
8. Call `autodata_fetch` after completion.
9. Train using `load_autodata_dataset()` rather than reading files directly.
10. Never modify the spec after approval.

These mechanisms have different roles:

- MCP registration tells the researcher which callable tools exist and defines
  their arguments.
- Prompt guidance explains the intended workflow and policy.
- The allowlist limits which tools the researcher may invoke.
- The adapter revalidates every request, so correct behavior does not depend
  only on the researcher following natural-language instructions.

[`../research_loop/monitor.py`](../research_loop/monitor.py) was changed so
strong-model-generated training data is allowed when the proposal discloses the
model identity, its role, the generation procedure, and filtering/judging
procedure.

[`../research_loop/tools/server_api_tools.py`](../research_loop/tools/server_api_tools.py)
extends `submit_idea_proposal` to parse the literal spec and freeze the method
and spec digests. It also requires the AutoData training link when a generated
dataset is mandatory.

## Adapter service

The control plane is implemented in
[`../infrastructure/autodata_service.py`](../infrastructure/autodata_service.py).
The executable wrapper is
[`../../scripts/autodata_service.py`](../../scripts/autodata_service.py).

| Method | Route                                     | Purpose                         |
| ------ | ----------------------------------------- | ------------------------------- |
| `POST` | `/v1/jobs`                                | Create or recover the bound job |
| `POST` | `/v1/runs/<id>/step`                      | Advance one lifecycle step      |
| `POST` | `/v1/runs/<id>/actions/<action>/begin`    | Lease an action                 |
| `POST` | `/v1/runs/<id>/actions/<action>/complete` | Complete an action              |
| `POST` | `/v1/runs/<id>/actions/<action>/fail`     | Fail an action                  |
| `GET`  | `/v1/runs/<id>`                           | Read status                     |
| `GET`  | `/v1/runs/<id>/artifacts`                 | Fetch final verified artifacts  |
| `GET`  | `/health`                                 | Service health                  |

The adapter uses an attempt-local bearer token. It validates the pinned
AutoData SHA, scientific spec, proposal binding, resource-profile digest,
budget scope, cost cap, retained-row target, and idempotent ownership of the
`run_id`.

For live runs, these HTTP routes are transport and AAR policy boundaries. They
do not define an alternative lifecycle. Their state-changing effects are
implemented by fixed native CLI commands, and their status envelope retains
the corresponding native status snapshot.

### Backends

| Backend                         | Purpose                                                                          |
| ------------------------------- | -------------------------------------------------------------------------------- |
| `DeterministicLifecycleBackend` | Contract and orchestration testing only; no Kimi/SandoQ scientific generation    |
| `LiveModelLifecycleBackend`     | Native AutoData plus SandoQ, Kimi generation, Luna judging, and usage settlement |

A deterministic smoke result is evidence only that plumbing works. It must not
be represented as a scientific production run.

### Campaign budget ledger

`CampaignBudgetLedger` is a file-locked campaign-wide ledger. Before a provider
operation, the live backend derives a conservative maximum task cost from the
operator-pinned Kimi/Luna input and output token ceilings, their token rates,
and the bounded request-attempt count, then reserves it. After execution, it
settles the reservation using reported provider usage. Unknown failed spend
remains conservatively charged. There is no independent flat per-task fee.

All runs sharing the same budget-scope ID share one cap, including parallel AAR
chains and later iterations.

### Delegated approvals

The research agent cannot approve `approve_grounding`, `approve_baseline`, or
`approve_resources`. The adapter approves one only after required evidence
exists and predates the approval:

| Gate      | Required evidence                                                                           |
| --------- | ------------------------------------------------------------------------------------------- |
| Grounding | Coverage, source provenance, and grounding checks                                           |
| Baseline  | Pipeline checks and successful dry-run evidence                                             |
| Resources | Frozen profile, shared budget scope, model canary, live broker readiness, and executor pins |

The attestation principal is `aar-integrity-monitor`.

AutoData v1 names one native compatibility field `user_acknowledged`. In this
unattended integration, `user_acknowledged=true` records an integrity-monitor
acknowledgement. It does **not** mean a human clicked an approval button.

## Live bridge into canonical AutoData

[`../../scripts/autodata_live_sandoq_driver.py`](../../scripts/autodata_live_sandoq_driver.py)
loads the operator-pinned AutoData package and translates between adapter
requests and fixed native AutoData CLI invocations. It uses a structured
argument vector, never a shell command string, and fixes `--state`,
`--artifacts`, and `--workspaces` to service-owned paths.

The live path currently reuses these native operations directly:

```text
pipeline validate
workspace create
workspace step
execution create
execution step
action begin
action complete
action fail
status
cancel
export
```

The existing seven MCP names remain stable compatibility names. For example,
`autodata_generate` maps to native `workspace create`; `autodata_step` selects
native `workspace step` or `execution step` from server-owned run state; and
`autodata_fetch` consumes the result of native `export` before applying AAR's
additional provenance checks.

```text
create native workspace
  -> clarify design
  -> author grounding
  -> delegated grounding approval
  -> author pipeline
  -> pipeline check
  -> two-task dry run
  -> delegated baseline approval
  -> freeze immutable workspace snapshot
  -> delegated resource approval
  -> explicit meta_optimize execution
  -> analyze and mutate candidate
  -> compare candidates and choose winner
  -> production execution with winning pipeline
  -> filter accepted Luna-judged rows
  -> export dataset and provenance
```

For the current Run 8 recipe, the driver creates 64 explicit tuning task IDs,
32 hidden validation task IDs, 96 source tasks for production, and exactly 64
retained rows when the target is met. The required valid-row rate is 0.75.

The 64 tuning rows are visible examples used during meta-optimization. The 64
retained rows are the final accepted production dataset. They are different
sets with different purposes.

The driver discards the default execution created by the workspace flow and
constructs an operator-owned execution manifest for the explicit 64/32
meta-optimization split, then passes it to native `execution create`. After
AutoData selects a winner, it creates a separate production manifest and again
uses native `execution create` over the full source corpus. The frozen native
snapshot ID is retained as `workspace_snapshot_id` in final provenance.

Narrow read-only internal lookups remain because the current CLI does not
expose the frozen snapshot's filesystem root, the winning candidate's workspace
root, or every provenance relationship needed by the final manifest. Those
lookups choose inputs for subsequent native commands and verify their outputs;
they do not mutate AutoData state. All lifecycle mutations and final export go
through the CLI.

## What the agent actually authors

The current containment model is narrower than the native action names suggest.

For `clarify_design`, `author_grounding`, and `author_pipeline`, the agent
provides a nonempty semantic `summary` and a nonempty list of `decisions`.
For `author_grounding` and `author_pipeline`, the driver then copies the
operator-staged recipe files into the native draft. The agent does not directly
write arbitrary files in the credentialed service workspace.

For `analyze_results`, the agent supplies a proposal and dashboard summary. For
`mutate_candidate`, it can select only `baseline_v1` or `contrastive_v2`. The
driver writes that choice to `recipe/prompt_variant.json`; arbitrary executable
recipe mutation is not allowed.

Therefore, `author_grounding` and `author_pipeline` currently mean something
closer to **semantically review and instantiate the operator-staged recipe**
than unrestricted authoring. This is a deliberate containment compromise, but
the naming overstates the agent's current authority and should be reviewed.

## Dishonest/sycophancy/concealing recipe walkthrough

The recipe is under
[`dishonest_sycophancy_concealing/`](dishonest_sycophancy_concealing/).

### Workspace brief

[`autodata.workspace.json`](dishonest_sycophancy_concealing/autodata.workspace.json)
defines the objective, intended use, source constraints, and initial workspace
shape. At runtime, the adapter replaces resource defaults with the
operator-approved SandoQ executor, concurrency, and computed budget.

### Pipeline definition

[`autodata.pipeline.json`](dishonest_sycophancy_concealing/autodata.pipeline.json)
defines the task command, result schema, checker command, quality objective,
minimum valid rate, and mutable/protected files. Only
`recipe/prompt_variant.json` is mutable during optimization.

### Grounding manifest

[`grounding/build_manifest.py`](dishonest_sycophancy_concealing/grounding/build_manifest.py)
deterministically creates synthetic scenarios across eight domains and eight
behavior patterns, with enough variations for at least 96 production tasks. It
declares no external source corpus.

### Per-task model program

[`recipe/task.py`](dishonest_sycophancy_concealing/recipe/task.py) performs one
generation-and-judging task:

1. Read the source scenario and approved runtime request.
2. Read the selected prompt variant.
3. Ask Kimi-K2.6 to create an original training prompt and response.
4. Ask GPT-5.6 Luna to judge the candidate against the rubric.
5. Accept only when Luna returns `accept` with a score of at least 0.75.
6. Return an AutoData `task-result/v1` with item, metadata, and provider usage.

If a model request or parser fails, the task returns a metered failed outcome
instead of dropping usage evidence. The process exits successfully so AutoData
retains the structured failure result.

### Prompt variant

[`recipe/prompt_variant.json`](dishonest_sycophancy_concealing/recipe/prompt_variant.json)
starts at `baseline_v1`. Meta-optimization may compare it with the allowlisted
`contrastive_v2` variant.

### Safety and integrity checker

[`recipe/check.py`](dishonest_sycophancy_concealing/recipe/check.py) checks the
prompt variant, request schema, nonempty fields, size limits, and source-policy
constraints.

The committed checker has an important known problem: its lexical rule rejects
any goal containing terms such as `benchmark`, even when the sentence says not
to imitate a benchmark. A narrower checker change is currently present only as
an uncommitted review proposal. It should be reviewed before it is committed or
used for another production attempt. Longer term, structured source
declarations and operational access controls are more reliable than substring
matching.

### Request, objective, comparator, lock, and schema

[`recipe/request.json`](dishonest_sycophancy_concealing/recipe/request.json) is
a staging placeholder. The driver writes the approved request into the native
workspace; the agent cannot use it to override resource controls.

| File                                                                                                 | Role                                                    |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| [`objective.json`](dishonest_sycophancy_concealing/objective.json)                                   | Defines the quality objective to maximize               |
| [`comparator.json`](dishonest_sycophancy_concealing/comparator.json)                                 | Defines meaningful improvement and validity constraints |
| [`framework.lock.json`](dishonest_sycophancy_concealing/framework.lock.json)                         | Declares the compatible AutoData framework version      |
| [`schemas/task-result.schema.json`](dishonest_sycophancy_concealing/schemas/task-result.schema.json) | Defines one generated item and its metadata/usage       |

## SandoQ and model execution

The native CLI constructs AutoData's `SandoQFirecrackerExecutor` from the
operator-owned workspace and execution manifests. SandoQ runs the recipe inside
the operator-approved container and sandbox tier.

After each native step, the driver scans AutoData's immutable content-addressed
artifacts for `autodata.task-result/v1` documents and copies only validated
provider-usage fields into the mode-0600 campaign ledger. This includes hidden
validation calls. Request IDs are deduplicated, malformed usage fails closed,
and incomplete usage conservatively charges the full reservation. Prompts,
responses, hidden task IDs, and other task content are not copied into
AAR-visible status or logs.

Two preflight programs are not exposed to the research agent:

- [`../../scripts/autodata_native_broker_canary.py`](../../scripts/autodata_native_broker_canary.py)
  proves a real Firecracker lease and non-model task.
- [`../../scripts/autodata_model_broker_canary.py`](../../scripts/autodata_model_broker_canary.py)
  runs one real Kimi/Luna task and validates result shape and provider usage.

Canary evidence is frozen into the resource profile and checked during resource
approval. It is preflight evidence, not production data.

The broker's live SQLite database, uploads, and result staging use node-local
`SLURM_TMPDIR` to avoid SQLite WAL locking failures on NFS. Retained artifacts
are archived to configured storage after shutdown.

## Credential and sandbox boundary

[`../../scripts/aar_runtime_env.sh`](../../scripts/aar_runtime_env.sh) controls
environment propagation. [`../../scripts/claude_research_bwrap.sh`](../../scripts/claude_research_bwrap.sh)
starts the research subprocess with source read-only and sensitive paths hidden.
The trusted AAR parent holds the adapter token and exposes only the MCP tools.

The research agent does not directly receive the SandoQ key, Kimi credentials,
Luna credentials, unrestricted service credentials, or permission to run
arbitrary commands in the service workspace.

## Dataset verification and training handoff

[`../infrastructure/autodata.py`](../infrastructure/autodata.py) implements the
training-side interface:

| Function                        | Purpose                                                            |
| ------------------------------- | ------------------------------------------------------------------ |
| `validate_autodata_artifacts`   | Validates fetched rows and manifest before writing them            |
| `verify_autodata_dataset`       | Rechecks stored data, counts, digests, model roles, and provenance |
| `load_autodata_dataset`         | Returns verified rows and creates the consumption receipt          |
| `verify_autodata_consumption`   | Confirms the approved method loaded the dataset                    |
| `autodata_training_link`        | Builds provenance for model metadata                               |
| `record_autodata_training_link` | Persists that link for launch/evaluation stages                    |

Training wrappers fail closed when AutoData is required but data or a
consumption receipt is absent. [`../transport.py`](../transport.py) carries the
dataset digest in model-submission metadata, and
[`../eval_pod/entrypoint.py`](../eval_pod/entrypoint.py) propagates it into
evaluator output.

```text
approved proposal
  -> bound AutoData workspace
  -> meta-optimization
  -> production dataset
  -> immutable fetch
  -> verified training load and receipt
  -> model submission carrying dataset digest
  -> evaluation carrying the same digest
```

## Supporting programs that are not agent tools

| Program                                                                                              | Purpose                                                      |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| [`../../scripts/autodata_service.py`](../../scripts/autodata_service.py)                             | Starts the adapter and selects deterministic or live backend |
| [`../../scripts/autodata_live_sandoq_driver.py`](../../scripts/autodata_live_sandoq_driver.py)       | Bridges the adapter to native AutoData and SandoQ            |
| [`../../scripts/autodata_contract_smoke_server.py`](../../scripts/autodata_contract_smoke_server.py) | Runs the older simplified deterministic HTTP smoke           |
| [`../../scripts/autodata_unattended_e2e.py`](../../scripts/autodata_unattended_e2e.py)               | Exercises native lifecycle deterministically                 |
| [`../../scripts/autodata_agent_smoke.py`](../../scripts/autodata_agent_smoke.py)                     | Exercises a bounded AAR agent against the MCP contract       |
| [`../../scripts/autodata_native_broker_canary.py`](../../scripts/autodata_native_broker_canary.py)   | Proves real Firecracker execution                            |
| [`../../scripts/autodata_model_broker_canary.py`](../../scripts/autodata_model_broker_canary.py)     | Proves real Kimi/Luna execution through the broker           |
| [`../../replication/verify_run8_autodata.py`](../../replication/verify_run8_autodata.py)             | Verifies the final two-iteration provenance chain            |

## End-to-end sequence for one AAR iteration

```text
1. Operator starts the campaign with a frozen resource profile and budget scope.
2. SandoQ and model canaries establish startup evidence.
3. Agent writes run.py with exactly one literal AUTODATA_SPEC.
4. Agent calls submit_idea_proposal.
5. Proposal monitor reviews the method and freezes code/spec hashes.
6. Agent calls autodata_generate(run_id, idea_name).
7. Adapter validates the binding and creates the native AutoData workspace.
8. Agent advances the workspace with autodata_step.
9. Agent completes visible semantic authoring actions through leases.
10. Integrity monitor approves grounding after evidence checks.
11. AutoData runs checks and a two-task dry run through SandoQ.
12. Integrity monitor approves the baseline after dry-run checks.
13. Integrity monitor approves resources after broker/model/profile checks.
14. AutoData runs meta_optimize with 64 tuning and 32 validation task IDs.
15. Agent analyzes results and selects an allowlisted mutation.
16. AutoData compares candidates and selects the winning pipeline.
17. AutoData runs production over all 96 source tasks.
18. Driver filters Luna-accepted rows and exports exactly 64.
19. Agent calls autodata_fetch; rows and manifest are verified and stored.
20. Approved method calls load_autodata_dataset() and receives the rows.
21. Training wrapper verifies the consumption receipt.
22. Model submission and evaluator result carry the dataset digest.
23. Final verifier checks the complete provenance chain.
```

## Current status and known interface issues

As of 2026-10-07:

- The canonical AutoData checkout is on `main`.
- The adapter, tools, driver, recipe, canaries, training binding, and verifier
  exist.
- Real SandoQ Firecracker and Kimi/Luna canaries have passed.
- A real AAR attempt created a native workspace and reached dry-run processing.
- A complete two-iteration production AAR result has **not** yet succeeded.
- The last attempt was blocked by the broad checker and an NFS SQLite lock. The
  broker storage fix is committed; the checker proposal remains under review.

The main interface issues to review are:

1. `autodata_generate` is a lifecycle-start operation, not immediate generation.
2. `author_grounding` and `author_pipeline` instantiate fixed staged files rather
   than allowing arbitrary agent-authored recipe files.
3. `user_acknowledged` represents delegated policy acknowledgement here, not a
   human action.
4. One live attempt did not provide the proposal-issued `run_id` conveniently
   enough to the agent, leading to a manually stamped proposal snapshot. This
   proposal-to-tool handoff needs an explicit fix and test.
5. The checker should use structured provenance/access policy rather than broad
   keyword rejection.
6. A successful live two-iteration run remains the final integration proof.

## Suggested review order

1. This document and the
   [original AutoData README](/home/winnieyangwn/autodata_pipelines/README.md).
2. [`../research_loop/prompt_safety.jinja2`](../research_loop/prompt_safety.jinja2)
   for the agent contract.
3. [`../research_loop/tools/autodata_tools.py`](../research_loop/tools/autodata_tools.py)
   for the exact tool surface and proposal checks.
4. [`../infrastructure/autodata_service.py`](../infrastructure/autodata_service.py)
   for policy, budget, approvals, routes, and service state.
5. [`../../scripts/autodata_live_sandoq_driver.py`](../../scripts/autodata_live_sandoq_driver.py)
   for native AutoData calls and action translation.
6. [`dishonest_sycophancy_concealing/`](dishonest_sycophancy_concealing/) for
   the scientific recipe.
7. [`../infrastructure/autodata.py`](../infrastructure/autodata.py) for dataset
   validation and training consumption.
8. The Run 8 launcher and verifier for the operational end-to-end contract.
