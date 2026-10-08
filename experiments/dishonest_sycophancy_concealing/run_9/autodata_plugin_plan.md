# Run 9: Native AutoData Plugin Integration Plan

## Goal

Verify that the actual AAR research agent can discover and use the native
AutoData Claude plugin through the Claude Agent SDK, without using the
AAR-specific AutoData MCP tools.

The first test is intentionally credential-free. It proves that the plugin,
skill, packaged CLI, sandbox, and native AutoData lifecycle work together.
After that succeeds, a separate integration test will run one complete AAR
iteration with meta-optimization, production data generation, training, and
evaluation.

## Interface under test

```text
AAR research-agent process
  -> Claude Agent SDK
  -> Skill("autodata:autodata")
  -> Bash
  -> ${CLAUDE_PLUGIN_ROOT}/scripts/autodata.py
  -> native autodata.cli
  -> local AutoData workspace and execution
  -> exported dataset
```

The smoke test must not call any of the seven AAR AutoData MCP tools. It tests
the original plugin interface as shipped by the canonical AutoData repository.

## Plugin source and pinning

The canonical AutoData checkout must be on `main` and pinned to an exact Git
commit before the test starts.

The verified Run 9 checkout currently exists at:

```text
Devserver:
  /home/winnieyangwn/autodata_pipelines/plugin/autodata

HPC canonical path:
  /storage/home/winnieyangwn/autodata_pipelines/plugin/autodata
```

On HPC, `/home/winnieyangwn/autodata_pipelines` resolves to the corresponding
`/storage/home/winnieyangwn/autodata_pipelines` path. The launcher should use
an operator-controlled variable instead of hard-coding either location:

```bash
export AAR_AUTODATA_PLUGIN_ROOT=/storage/home/winnieyangwn/autodata_pipelines/plugin/autodata
```

Before launch, verify:

- the path resolves inside the expected canonical checkout;
- the checkout is on `main`;
- the checkout is clean;
- its Git SHA matches the operator-pinned SHA;
- `.claude-plugin/plugin.json` exists;
- `skills/autodata/SKILL.md` exists;
- `scripts/autodata.py` and the locked wheels exist;
- no symlink escapes the approved plugin directory.

At the time this plan was written, the devserver and HPC checkout both used:

```text
9e623eb25bab4c4ba50642f72ca338f887772e27
```

The launcher, rather than this document, remains authoritative for the pinned
revision used by an actual run.

## Required AAR integration changes

### Claude Agent SDK registration

Extend `BaseAgent` so it accepts `plugins` and `skills`, then forwards them to
`ClaudeAgentOptions`.

For the plugin smoke mode, construct the research agent with the equivalent of:

```python
ClaudeAgentOptions(
    ...,
    plugins=[
        {
            "type": "local",
            "path": os.environ["AAR_AUTODATA_PLUGIN_ROOT"],
        }
    ],
    skills=["autodata:autodata"],
)
```

The plugin path is selected and validated by the trusted launcher. The
research agent must not supply or modify it.

### Sandbox visibility

The Run 9 research subprocess uses `scripts/claude_research_bwrap.sh`, which
hides the user's home directory. The launcher must explicitly mount only the
validated plugin directory read-only inside the research sandbox.

Do not expose the entire user home, `.env` files, token files, or the rest of a
credential-bearing checkout merely to make the plugin visible.

### Writable plugin cache and run directory

The plugin remains read-only. Its bootstrap installs its bundled,
hash-verified wheels into a writable run-local cache:

```bash
export AUTODATA_CACHE_DIR="$AAR_RUNTIME_ROOT/autodata/plugin-cache"
```

The AutoData workspace, execution state, logs, and export must also live below
the retained run artifact directory. They must not be written into the plugin,
the source checkout, `/tmp`, or `/checkpoint/ram`.

### Explicit plugin-only mode

Introduce an explicit interface setting such as:

```bash
export AAR_AUTODATA_INTERFACE=plugin_cli
```

In this mode:

- load the native AutoData plugin and skill;
- keep the normal AAR proposal tools available if the test needs them;
- do not register the `autodata-tools` MCP server;
- do not add any `mcp__autodata-tools__*` operation to `allowed_tools`;
- permit the agent to use the native plugin wrapper through Bash;
- keep research-child credential scrubbing enabled.

## Stage 1: Research-agent plugin smoke test

### Does this launch an AAR loop?

It launches one real, bounded AAR research-agent session using the same
`BaseAgent`, Claude Agent SDK, prompt construction, tool permissions, and
bubblewrap isolation as the normal AAR loop.

It does **not** run an entire outer AAR experiment iteration. It stops after
the research agent completes and exports a small deterministic AutoData
execution. It therefore does not train Gemma or run candidate evaluation.

This distinction makes the test small while still proving that the AAR
research agent—not an operator shell—can use the native plugin.

### Test task given to the research agent

The trusted smoke launcher gives the agent a narrowly scoped task equivalent
to:

```text
Load the autodata:autodata skill. Using only the native AutoData plugin CLI,
create and finish the supplied deterministic toy workspace. Follow all visible
workspace and execution actions, export the completed execution under the
provided run artifact directory, and report the workspace ID, execution ID,
export path, and final status. Do not call AutoData MCP tools, use network
services, or request credentials.
```

The task supplies:

- the immutable toy workspace brief;
- the deterministic recipe inputs;
- the writable draft and artifact roots;
- the exact allowed executor configuration;
- fixed approval decisions for this specific local fixture;
- a strict timeout and model budget.

### Why fixed approvals are supplied

Native AutoData includes explicit workspace approval actions. The AutoData
skill correctly says that an agent must not invent a user's approval.

For this smoke test, the trusted launcher records predetermined operator
decisions for the exact immutable local fixture before the research session
starts. The agent may submit those already-authorized decisions when their
matching actions appear. It may not generalize them to a changed pipeline,
different resources, network access, or a production execution.

This keeps the smoke test unattended without pretending the research agent
independently approved its own work.

### Expected native operation sequence

The research agent should load the skill and then perform the necessary native
AutoData operations through the packaged wrapper. A representative sequence
is:

```text
Skill("autodata:autodata")

workspace create
workspace step
action begin
action complete or action fail
workspace step
... repeat until the workspace is approved and frozen ...

pipeline validate
execution create
execution step
action begin
action complete or action fail
execution step
... repeat until the deterministic execution completes ...

status
export
```

The exact actions are determined by the native AutoData state machine. The
test must not fake state transitions or duplicate that state machine in AAR.

The Bash form should use the plugin-provided root:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autodata.py" <native-command>
```

### Deterministic execution

Stage 1 must use a small local deterministic recipe and executor. It must not
call:

- Kimi;
- GPT-5.6 Luna;
- SandoQ;
- Firecracker;
- Model API;
- an external network destination.

This isolates plugin integration failures from credentials, model routing,
capacity, cost accounting, and remote executor failures.

### Required observations

Instrumentation must record enough evidence to prove that the intended path
was used:

- the actual `Skill` invocation for `autodata:autodata`;
- the research-agent session ID and model identity;
- sanitized Bash command names or operation names;
- native workspace and execution IDs;
- native final status;
- plugin path and pinned AutoData SHA;
- output manifest and dataset digests;
- test start, completion, timeout, and cost information;
- confirmation that no AutoData MCP operation was invoked.

Never record environment-variable values or credential contents.

### Pass criteria

Stage 1 passes only if all of the following are true:

1. A real AAR research-agent subprocess was launched through the production
   sandbox wrapper.
2. The SDK successfully discovered the local AutoData plugin.
3. The agent invoked `Skill("autodata:autodata")` before its first AutoData
   operation.
4. Every AutoData operation used Bash and the packaged native wrapper.
5. No `mcp__autodata-tools__*` call occurred.
6. The plugin bootstrapped from its bundled locked wheels without a network
   installation.
7. The agent created and advanced a native workspace.
8. The agent created and completed a native deterministic execution.
9. Native export succeeded.
10. An independent verifier accepted the export schema, row count, manifest,
    and digests.
11. All artifacts were retained under the configured run storage root.
12. No Kimi, Luna, SandoQ, model API, or other production credential was
    visible to the research subprocess.
13. The session ended within its wall-time and model-cost limits.

The agent's textual claim of success is not sufficient; the verifier must
inspect the native persisted state and exported artifacts.

### Failure reporting

On failure, retain:

- the sanitized agent transcript;
- skill and tool telemetry;
- native CLI stdout and stderr;
- workspace and execution status documents;
- the plugin and AAR Git SHAs;
- the deterministic fixture digest;
- the failure category and final successful lifecycle operation.

Classify failures at least as:

- plugin discovery or skill-loading failure;
- sandbox path or permission failure;
- offline bootstrap failure;
- prompt or agent-behavior failure;
- native workspace/action failure;
- native execution/export failure;
- timeout or model-budget failure;
- verifier failure;
- unexpected MCP, credential, or network use.

Do not automatically fall back to MCP during this test. A fallback would hide
whether the native plugin path works.

## Stage 2: One complete AAR iteration

Stage 2 begins only after Stage 1 passes. It launches one full AAR outer
iteration to validate the scientific handoff:

```text
AAR proposal
  -> AAR research agent loads native AutoData plugin
  -> AutoData workspace creation and authoring
  -> meta-optimization
  -> winning pipeline selection
  -> production generation
  -> dataset export and verification
  -> training consumes the exported dataset
  -> candidate evaluation completes
  -> AAR iteration result is retained
```

Stage 2 is where Kimi generation, GPT-5.6 Luna judging, SandoQ execution,
production budgets, and training provenance are tested. Their credential and
authority model must be explicitly approved before launch. Passing Stage 1
does not authorize exposing production secrets to the research subprocess.

Stage 2 passes only when the retained AAR result proves that:

- the research agent used the native plugin rather than AutoData MCP;
- meta-optimization completed with the configured visible tuning and hidden
  validation partitions;
- production completed with the configured retained-row target;
- the exported dataset and provenance were verified;
- training actually loaded that dataset;
- evaluation produced a valid scored result for the trained candidate.

## Non-goals of Stage 1

Stage 1 does not attempt to prove:

- safe delegation of production credentials;
- Kimi or Luna model quality;
- SandoQ or Firecracker availability;
- production-scale throughput;
- AAR training effectiveness;
- evaluator score improvement;
- completion of a full AAR outer iteration.

Those belong to Stage 2. Keeping the stages separate makes failures
diagnosable and establishes whether the original AutoData plugin works before
adding production infrastructure.
