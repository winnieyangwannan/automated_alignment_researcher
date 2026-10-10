# AutoData recipes used by AAR

For new AAR launchers, use the shared measured runtime profile described in
[AutoData runtime profiles](../../docs/autodata-runtime-profile.md). Do not copy
Run 9/12/13 concurrency, routing, or retry settings into another launcher.

## Purpose

AAR uses the original AutoData Claude plugin and native AutoData CLI directly.
There is no AAR-specific AutoData lifecycle MCP server, HTTP adapter, or
replacement state machine. One narrow trusted AAR operation,
`review_autodata_action`, reviews and signs native approval actions; it does
not create, step, mutate, execute, or export AutoData state.

The integration is:

```text
AAR research agent
  -> Claude Agent SDK
  -> autodata:autodata skill
  -> SDK Bash tool
  -> ${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py
  -> native autodata.cli
  -> native workspace, actions, executions, status, and export
```

The canonical AutoData checkout remains the source of truth for the framework,
plugin, skill, CLI, contracts, and execution behavior:

- [AutoData README](/home/winnieyangwn/autodata_pipelines/README.md)
- [Plugin manifest](/home/winnieyangwn/autodata_pipelines/plugin/autodata/.claude-plugin/plugin.json)
- [AutoData skill](/home/winnieyangwn/autodata_pipelines/plugin/autodata/skills/autodata/SKILL.md)
- [CLI reference](/home/winnieyangwn/autodata_pipelines/plugin/autodata/skills/autodata/references/cli.md)
- [Authoring reference](/home/winnieyangwn/autodata_pipelines/plugin/autodata/skills/autodata/references/authoring.md)
- [Meta-optimization reference](/home/winnieyangwn/autodata_pipelines/plugin/autodata/skills/autodata/references/meta-optimize.md)
- [Production reference](/home/winnieyangwn/autodata_pipelines/plugin/autodata/skills/autodata/references/production.md)

## Plugin, skill, Bash, and recipe are different things

The Claude Agent SDK registers the local AutoData **plugin** and makes the
qualified `autodata:autodata` **skill** available. The skill supplies workflow
instructions and references.

`Bash` is a standard Claude Agent SDK tool already enabled by AAR. It is not
contributed by the AutoData plugin. After loading the skill, the agent uses
Bash to run the plugin's packaged Python wrapper:

```bash
python3 "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py" <native-command>
```

A **recipe** is neither a plugin nor a tool. It is a collection of AutoData
input files: workspace brief, grounding, pipeline manifest, task code, schemas,
objective, comparator, and execution configuration. The research agent authors
or copies recipe files into a writable AutoData workspace and the native CLI
validates and executes them.

```text
SDK registration
  -> plugin + skill

Agent capability
  -> existing Bash tool

Executable
  -> plugin's native AutoData wrapper

Scientific workload
  -> recipe files in a writable workspace
```

## How AAR loads the original plugin

The trusted AAR launcher supplies:

```bash
export AAR_AUTODATA=1
export AAR_AUTODATA_PLUGIN_ROOT=/path/to/pinned/autodata_pipelines/plugin/autodata
export AAR_AUTODATA_SHA=<full-git-sha>
```

`aar/research_loop/autodata_plugin.py` verifies that:

- the plugin path is exactly `<checkout>/plugin/autodata`;
- the checkout is on `main`;
- the configured SHA equals the checkout's `HEAD`;
- the plugin directory is clean;
- the manifest, skill, wrapper, bootstrap, and wheel lock exist;
- the plugin tree contains no symlinks.

`aar/research_loop/agent.py` then passes the verified configuration to the
Claude Agent SDK:

```python
ClaudeAgentOptions(
    ...,
    plugins=[{"type": "local", "path": verified_plugin_path}],
    skills=["autodata:autodata"],
)
```

The AAR research sandbox mounts only that verified plugin directory read-only.
It gives the plugin a writable run-local bootstrap cache:

```bash
AUTODATA_CACHE_DIR="$AAR_RUNTIME_ROOT/autodata/plugin-cache"
```

The plugin itself is not copied, edited, or repackaged by AAR.

## Native AutoData operations

The research agent uses the operations documented by the original plugin:

```text
pipeline validate

workspace create
workspace step
workspace fork
workspace export

execution create
execution step
execution export-winner

action begin
action complete
action fail

status
cancel
export
dashboard serve
```

Global `--state`, `--artifacts`, and `--workspaces` arguments must remain stable
for a workspace or execution. AAR places all three below the retained run root.

A typical command is:

```bash
python3 "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py" \
  --state "$TEAM_DIR/autodata/$RUN_ID/native/state.db" \
  --artifacts "$TEAM_DIR/autodata/$RUN_ID/native/artifacts" \
  --workspaces "$TEAM_DIR/autodata/$RUN_ID/native/workspaces" \
  workspace create \
  --brief "$TEAM_DIR/autodata/$RUN_ID/input/autodata.workspace.json" \
  --root "$TEAM_DIR/autodata/$RUN_ID/draft"
```

The agent follows returned native actions by acquiring their leases with
`action begin`, performing only the declared work, and submitting the result
with `action complete` or `action fail`.

## Workspace authoring

AutoData deliberately separates authoring from execution. Native workspace
actions guide the visible host agent through:

```text
clarify_design
  -> author_grounding
  -> approve_grounding
  -> author_pipeline
  -> checks and dry run
  -> approve_baseline
  -> frozen workspace and execution
```

The research agent may edit only the `editable_root` and `allowed_paths`
returned by a native action. It must not invent approval. Approval actions must
be sent to `review_autodata_action`. The monitor reads the native review
artifact and signs a decision over the exact action ID, workspace revision, and
artifact digests. Native AutoData rejects a plain researcher-supplied
`user_acknowledged` result in delegated mode.

Once frozen, AutoData creates the native execution. The agent continues with
`execution step` and the same native action lease protocol.

## Meta-optimization and production

`meta_optimize` and `production` are native AutoData execution modes selected
by the execution JSON. AAR does not implement either loop.

In `meta_optimize`, visible tuning evidence can guide candidate mutation while
selection inputs remain hidden. AutoData evaluates candidates and selects the
winner through its native comparator.

The agent then uses the native integrity-checked handoff:

```bash
autodata execution export-winner <meta-execution-id> --output <winner-root>
```

The operation refuses a winner whose tree no longer matches the digest bound at
finalization. A separate production execution is created from this exported
root. Setting its `budget.max_iterations` to `0` performs fixed-winner mass
generation without another mutation loop.

In `production`, AutoData generates, audits, revises, and reruns the same source
corpus within the execution budget. It emits the final dataset after the native
execution reaches `completed`.

The agent exports a completed execution with:

```bash
python3 "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py" \
  --state <state.db> \
  --artifacts <artifact-dir> \
  --workspaces <workspace-dir> \
  export <execution-id> --output <dataset.json>
```

The output is the native `autodata.dataset/v1` document. Generated training
examples are in its `items` array.

## The dishonest/sycophancy/concealing recipe

The AAR-owned starting recipe is:

[dishonest_sycophancy_concealing](./dishonest_sycophancy_concealing)

It contains:

- `autodata.workspace.json`: workspace goal and resource defaults;
- `autodata.pipeline.json`: task command, schemas, checks, comparator, and
  mutable/protected paths;
- `grounding/coverage.json`: outer-loop-editable domains, behavior patterns,
  axes, and minimum coverage;
- `grounding/build_manifest.py`: deterministic synthetic scenario builder;
- `recipe/task.py`: Kimi generation, default target-model challenge probing,
  and GPT-5.6 Luna judging task;
- `recipe/check.py`: local request and recipe validation;
- `recipe/generation_strategy.json`: structured inner-loop-mutable generation
  prompt and sampling strategy;
- `recipe/request.json`: runtime scientific request;
- `objective.json` and `comparator.json`: balanced teacher-quality/target-challenge
  objective and comparison;
- `schemas/task-result.schema.json`: strict native task-result contract;
- `framework.lock.json`: exact AutoData framework version.

These files are recipe inputs, not SDK registrations. The source checkout is
read-only to the research subprocess, so a run must copy the approved starting
files into its writable workspace before native authoring actions edit them.

Target-aware generation is enabled by default and fails closed. A broker
campaign must provide all four of the following non-secret workload settings
together:

- `AUTODATA_TARGET_URL`: research-side OpenAI-compatible endpoint base URL;
- `AUTODATA_TARGET_MODEL`: served-model name used in the request body;
- `AUTODATA_TARGET_DEPLOYMENT_ID`: deployment selected by the gateway header;
- `AUTODATA_TARGET_CHECKPOINT_HASH`: SHA-256 identity of the exact checkpoint.

`AUTODATA_TARGET_HOST_HEADER` is optional for gateway routing. Token ceilings,
timeouts, and accounting rates use the corresponding
`AUTODATA_TARGET_MAX_INPUT`, `AUTODATA_TARGET_MAX_OUTPUT`,
`AUTODATA_TARGET_TIMEOUT`, `AUTODATA_TARGET_INPUT_USD_PER_MILLION`, and
`AUTODATA_TARGET_OUTPUT_USD_PER_MILLION` settings. When the target contract is
enabled, Luna must accept the teacher row and identify a material target-model
failure before the row is exportable. The task records a normalized
`challenge` metric and checkpoint provenance, but never stores the target's raw
response in the training dataset. The endpoint must be research-side; do not
expose the protected evaluator process or held-out inputs to AutoData.

Each grounding task declares exactly one primary alignment axis: honesty,
sycophancy resistance, or uncertainty disclosure. The deterministic grounding
builder balances those axes across the corpus. Luna treats the corresponding
teacher dimension as the row's learning objective and the other dimensions as
guardrails. A target response is challenging only when its failure mode matches
the task's primary axis.

The comparator maximizes `quality_challenge_utility`, the per-row harmonic mean
of axis-conditioned teacher `quality` and matching target `challenge`. It also
requires aggregate `valid >= 0.75`, `quality >= 0.75`, and `challenge >= 0.5`,
so neither a clean but easy dataset nor a difficult but low-quality dataset can
hide a component that falls below its required floor.

Set `AUTODATA_TARGET_ENABLED=0` only for an intentional smoke test or legacy
comparison that cannot run a research-side Gemma endpoint. Target settings must
be absent in that mode. Normal launches must not use this escape hatch; missing
or partial target configuration is an error.

## Credentials

The credential-free local plugin smoke uses the upstream deterministic toy
recipe and `local-bwrap`, so the research process receives no Kimi, Luna,
SandoQ, Firecracker, or Model API secret.

A real SandoQ production execution is a separate authority decision. If raw
credentials are inherited by the research process, its Bash tool can read
them. Keeping a token in an HPC environment does not isolate it from the agent
when the same process inherits that variable.

The real recipe uses the native AutoData Firecracker broker. The broker holds
the Firecracker and Luna credentials and injects only the Luna workload key
inside model-backed tasks. The trusted small-scale driver receives the broker
capability; it does not expose the underlying credentials to a researcher.
Restricting that broker capability for a full autonomous AAR session remains a
production-hardening item. The scientific lifecycle still uses the original
plugin and CLI.

## Plugin smoke test

[`../../scripts/autodata_agent_smoke.py`](../../scripts/autodata_agent_smoke.py)
launches one real bounded AAR research-agent session. It:

1. verifies the pinned original plugin;
2. copies the upstream canonical toy recipe into the writable run root;
3. registers `autodata:autodata` with the Claude Agent SDK;
4. exposes the normal SDK Bash tool;
5. asks the agent to create and finish a native workspace and deterministic
   execution;
6. requires native export of `autodata.dataset/v1`;
7. fails if any `mcp__autodata*` call is observed;
8. independently verifies the completion record and exported items.

The smoke does not train or evaluate a model and does not contact SandoQ or a
hosted model. It proves plugin discovery, skill loading, Bash invocation,
offline bootstrap, native authoring, execution, and export.

The detailed Run 9 plan is in:

[Run 9 AutoData plugin plan](../../experiments/dishonest_sycophancy_concealing/run_9/autodata_plugin_plan.md)

## Design rule

AAR must not reproduce AutoData's lifecycle in its own code. If new workflow
behavior is needed, prefer an upstream AutoData change or a recipe change. The
AAR integration should remain limited to:

- selecting and verifying the pinned plugin;
- registering its skill with the agent SDK;
- making the plugin readable in the research sandbox;
- providing writable run storage;
- supplying scientific recipe inputs;
- signing only native approval actions through the trusted monitor;
- observing that the native workflow and export completed.
