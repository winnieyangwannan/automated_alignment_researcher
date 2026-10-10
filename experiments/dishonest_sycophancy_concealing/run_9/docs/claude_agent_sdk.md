# Claude Agent SDK and the AAR research agent

## What is an SDK?

SDK means **Software Development Kit**. It is a library and supporting tools
that let one program use another system without implementing the entire
integration itself.

For example, an AI-agent SDK may provide code for:

- starting an agent;
- sending prompts and receiving responses;
- maintaining a conversation session;
- exposing tools to the agent;
- receiving and executing tool calls;
- loading skills and plugins;
- enforcing tool permissions and budgets;
- resuming a session after an interruption.

## What is an agent SDK?

An agent SDK is an SDK designed for running AI models as agents rather than for
making only single model calls.

A basic model API might accept one prompt and return one answer. An agent SDK
also manages a loop in which the model can inspect files, call tools, observe
their results, make another decision, and continue working toward a goal.

```text
application
  -> send task to agent runtime
  -> model reasons and selects a tool
  -> application executes the tool
  -> tool result returns to the model
  -> model continues
  -> final result returns to the application
```

## What is the Claude Agent SDK?

The Claude Agent SDK is Anthropic's library for programmatically running a
Claude Code-style agent. It provides the agent runtime used by AAR's current
research loop.

The current relationship is:

```text
AAR Python process
  -> Claude Agent SDK
  -> Claude Code agent runtime
  -> configured Claude model
  -> file, Bash, MCP, and skill tools
```

AAR constructs this runtime in
[`../../../../aar/research_loop/agent.py`](../../../../aar/research_loop/agent.py).
The important SDK classes currently used by AAR are `ClaudeSDKClient` and
`ClaudeAgentOptions`.

The SDK provides facilities such as:

- agent sessions and conversation history;
- prompts and model selection;
- `Read`, `Write`, `Edit`, and `Bash` tools;
- MCP tool registration;
- skills and local plugins;
- tool permissions and sandbox integration;
- model-cost and turn limits;
- session streaming, resumption, and error handling;
- optional subagents.

The SDK does not implement AAR's scientific process. AAR supplies the research
prompt, proposal review, evaluation tools, AutoData tools, filesystem boundary,
budgets, and experiment loop. The SDK supplies the general-purpose agent
runtime in which those pieces are presented to the model.

## Does this mean the AAR research agent can only use Claude models?

With the current implementation, the main AAR research agent is effectively
Claude-specific.

The research loop constructs `ClaudeSDKClient` and `ClaudeAgentOptions` and
launches a Claude Code-compatible CLI process. Therefore, the model making the
research decisions and invoking AAR tools currently runs through the Claude
Agent SDK.

This does not mean every model involved in an AAR experiment must be Claude.
The current Run 9 design uses several distinct model roles:

- the AAR research agent uses the Claude Agent SDK;
- Kimi generates candidate AutoData examples;
- GPT-5.6 Luna judges those examples;
- Gemma is the model trained and evaluated;
- proposal or integrity-monitor decisions can use separately configured
  models.

These roles are independent. Using Kimi for data generation, for example, does
not make Kimi the AAR research agent.

## Could AAR use a non-Claude research agent?

Yes, but this requires an alternative agent runtime, not merely changing a
model-name string.

A replacement runtime would need to provide behavior equivalent to what AAR
currently receives from the Claude Agent SDK:

- multi-turn session management;
- reliable structured tool calling;
- MCP support, or an equivalent bridge to the same tools;
- file and command tools;
- permission enforcement and sandbox compatibility;
- skill loading or equivalent instruction injection;
- streaming tool results and progress;
- retry, resume, timeout, and failure handling;
- token or dollar budget enforcement.

A model endpoint that supports only ordinary text completion is not sufficient
by itself.

## A model-independent AAR design

A more portable architecture would introduce an AAR-owned interface between
the research loop and any particular agent SDK:

```text
AAR research loop
        |
        v
ResearchAgentRuntime interface
        |
        +-- ClaudeAgentRuntime
        +-- OpenAIAgentRuntime
        +-- KimiAgentRuntime
        +-- another compatible runtime
```

The interface would define common operations such as:

- start or resume a session;
- send the research task;
- register allowed tools;
- receive tool calls;
- execute tools through AAR's policy boundary;
- stream progress;
- stop on budget or timeout;
- return the final result and usage records.

The existing Claude implementation could then become one implementation of
that interface rather than being embedded directly throughout the research
loop.

## Is AutoData Claude-specific?

No.

AutoData's workspace, action, execution, comparison, and export contracts do
not depend on Claude. The native AutoData CLI can be driven by any host capable
of following its JSON contracts.

The current separation is therefore:

```text
Claude-specific today:
  AAR research-agent runtime and automatic Skill-tool behavior

Not Claude-specific:
  AutoData lifecycle
  AutoData CLI
  Kimi generation
  Luna judging
  Gemma training and evaluation
```

## What is the difference between a skill and a plugin?

A **skill** is a set of instructions that teaches an agent how to perform a
particular kind of work. Its main entry point is a `SKILL.md` file. The skill
can explain a workflow, tell the agent which commands or tools to use, define
safety rules, and link to more detailed reference documents.

A **plugin** is an installable package that can contain one or more skills and
other capabilities. Depending on the plugin, it may include:

- skills;
- MCP server definitions and callable MCP tools;
- command wrappers or helper scripts;
- hooks;
- supporting reference files and packaged dependencies.

The concise distinction is:

```text
plugin = the package that is installed or loaded
skill  = instructions inside that package that the agent can load
MCP    = callable runtime operations that the agent can invoke
```

A plugin is not itself a tool call. Loading a plugin makes its contributed
capabilities available. The agent then invokes a skill, MCP tool, or other
capability contributed by that plugin.

## How AutoData is packaged

The canonical AutoData checkout already packages its agent guidance as a
Claude plugin:

```text
/home/winnieyangwn/autodata_pipelines/plugin/autodata/
  .claude-plugin/plugin.json
  skills/autodata/SKILL.md
  skills/autodata/references/
  scripts/autodata.py
  wheels/
```

The plugin manifest is:

[`../../../../../../autodata_pipelines/plugin/autodata/.claude-plugin/plugin.json`](../../../../../../autodata_pipelines/plugin/autodata/.claude-plugin/plugin.json)

The AutoData skill entry point is:

[`../../../../../../autodata_pipelines/plugin/autodata/skills/autodata/SKILL.md`](../../../../../../autodata_pipelines/plugin/autodata/skills/autodata/SKILL.md)

When this local plugin is loaded into the Claude Agent SDK, its qualified
skill name is:

```text
autodata:autodata
```

The first `autodata` is the plugin name. The second `autodata` is the skill
name. Loading that skill gives the research agent AutoData's native workflow
instructions and lets it consult the relevant authoring, meta-optimization,
production, and CLI references only when needed.

## Should AutoData be exposed as a plugin?

Yes, the documentation and workflow knowledge are best exposed through the
existing AutoData plugin. That avoids copying a large version of AutoData's
instructions into the AAR research prompt and keeps the guidance versioned
with the pinned AutoData checkout.

Conceptually, AAR should configure the Claude Agent SDK like this:

```python
ClaudeAgentOptions(
    plugins=[
        {
            "type": "local",
            "path": "/path/to/pinned/autodata_pipelines/plugin/autodata",
        }
    ],
    skills=["autodata:autodata"],
)
```

The exact path must come from AAR's operator-controlled, pinned AutoData
configuration rather than from a path chosen by the research agent. AAR must
also make the plugin readable inside the research sandbox.

Loading the plugin does **not** by itself give the agent production
credentials or permission to bypass AAR policy. It makes the skill and its
packaged CLI wrapper available to the agent. AAR must separately decide what
filesystem paths, credentials, and infrastructure that CLI process may use.

## Why AutoData does not use an AAR MCP interface

Run 9 uses the original AutoData plugin and native CLI directly. The earlier
seven-tool AAR AutoData MCP server, HTTP adapter, and lifecycle driver have
been removed.

```text
AutoData plugin and skill
  -> teach the AAR researcher the native lifecycle

SDK Bash tool
  -> runs the plugin's packaged CLI wrapper

Native AutoData
  -> owns workspaces, actions, executions, status, and export
```

This keeps AutoData as the single lifecycle implementation. Credential
delegation for a future production run remains a separate infrastructure
decision; it must not cause AAR to recreate the AutoData state machine.

## How to install the plugin in the AAR research agent

This is a local-plugin registration, not a package upload or a conventional
`pip install`. The plugin already contains its locked Python wheels and creates
its own offline environment when its wrapper is first invoked.

### 1. Select the pinned plugin

The operator selects the plugin from the pinned canonical AutoData checkout:

```text
/home/winnieyangwn/autodata_pipelines/plugin/autodata
```

AAR should verify the checkout revision and resolve this path itself. The
research agent must not be allowed to select a different plugin path or
AutoData revision.

### 2. Pass the plugin and skill to the SDK

Extend `BaseAgent` in
[`../../../../aar/research_loop/agent.py`](../../../../aar/research_loop/agent.py) so
it accepts `plugins` and `skills` and includes them in the options passed to
`ClaudeAgentOptions`.

The research agent should then be constructed with the equivalent of:

```python
BaseAgent(
    ...,
    plugins=[
        {
            "type": "local",
            "path": "/home/winnieyangwn/autodata_pipelines/plugin/autodata",
        }
    ],
    skills=["autodata:autodata"],
)
```

This corresponds to the following SDK configuration:

```python
ClaudeAgentOptions(
    ...,
    plugins=[
        {
            "type": "local",
            "path": "/home/winnieyangwn/autodata_pipelines/plugin/autodata",
        }
    ],
    skills=["autodata:autodata"],
)
```

The SDK makes the qualified `autodata:autodata` skill available through its
`Skill` tool. The AAR prompt should tell the researcher to load this skill
before attempting to author or run an AutoData workflow.

### 3. Expose the plugin inside the research sandbox

The Run 9 research subprocess is launched through
[`../../../../scripts/claude_research_bwrap.sh`](../../../../scripts/claude_research_bwrap.sh).
That sandbox hides the user's home directory and currently restores only
approved paths. Because the canonical AutoData checkout is separate from the
AAR checkout, the plugin would otherwise be invisible even if the SDK were
given its host path.

The launcher must therefore:

1. resolve the operator-configured plugin directory;
2. verify that it belongs to the pinned AutoData checkout;
3. reject symlink or path-containment escapes;
4. mount only the required plugin directory read-only inside the sandbox.

The entire user home or canonical AutoData repository should not be exposed
when only the plugin is required.

### 4. Provide writable cache and workspace locations

The plugin itself can remain read-only. Its bootstrap code installs the
bundled, hash-checked wheels into a writable cache. Set that cache to an
attempt-local or run-local directory:

```bash
export AUTODATA_CACHE_DIR="$AAR_RUNTIME_ROOT/autodata/plugin-cache"
```

AutoData draft workspaces and execution artifacts must also be created under
the writable retained run directory, not inside the read-only plugin or source
checkout.

### 5. Let the agent use the native wrapper

After loading the skill, the research agent can invoke native AutoData
operations through Bash:

```bash
python3 "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py" workspace create \
  --brief /path/to/autodata.workspace.json \
  --root /path/to/writable/draft

python3 "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py" workspace step \
  <workspace-id>

python3 "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py" status \
  <workspace-or-execution-id>
```

The same wrapper exposes the other native AutoData CLI operations. No MCP
operation is involved in this path:

```text
AAR research agent
  -> Skill("autodata:autodata")
  -> Bash
  -> plugin scripts/autodata.py
  -> native autodata.cli
```

### 6. Run a credential-free smoke test first

The first test should prove the native plugin path independently of SandoQ and
hosted models:

1. load `autodata:autodata`;
2. create a small workspace;
3. fulfill its visible workspace actions;
4. validate the pipeline;
5. create and complete a local deterministic execution;
6. export and inspect the result.

This tests plugin discovery, skill loading, Bash invocation, offline wheel
bootstrap, writable workspace handling, and the native AutoData lifecycle.

### 7. Treat real production as a separate authority decision

A direct local CLI process does not automatically receive Kimi, Luna, or
SandoQ credentials. A real production run would require either:

- exposing carefully scoped credentials to the research subprocess;
- using an external privileged credential broker.

The credential-free plugin smoke test should be completed first. Success means
the native plugin integration works; it does not by itself prove that granting
the agent direct production credentials is safe.

## How AAR activates the AutoData plugin

The Run 9 implementation passes `plugins` and `skills` through `BaseAgent` to
`ClaudeAgentOptions`. The research sandbox exposes only the verified plugin
directory read-only and supplies a writable run-local bootstrap cache.

The integration performs these steps:

1. Resolve and verify the plugin from the pinned AutoData checkout.
2. Expose that plugin read-only inside the AAR research sandbox.
3. Pass the local plugin and `autodata:autodata` skill to
   `ClaudeAgentOptions`.
4. Give the wrapper an approved writable cache and workspace location.
5. Tell the researcher to load the skill and use its native CLI wrapper.
6. Verify in an agent smoke test that the skill was loaded before AutoData
   operations were used.

This preserves one source of truth for AutoData guidance. Production
credential authority remains a separate design decision after the
credential-free direct-plugin smoke test.

## Are AutoData skills Claude-specific?

The contents of `SKILL.md` are Markdown instructions, so the knowledge itself
is portable. The automatic discovery and invocation of the skill through the
built-in `Skill` tool is a Claude Agent SDK feature.

For a different agent runtime, AAR could reuse the same instructions by:

- inserting the relevant `SKILL.md` content into the system prompt;
- implementing an AAR-owned skill loader;
- providing a typed `load_skill` tool;
- translating the skill into that runtime's native skill mechanism.

The important contract is the AutoData workflow described by the skill, not
the particular mechanism used to deliver the instructions to the model.

## Summary

- An SDK is a library for integrating with another system.
- An agent SDK manages multi-turn, tool-using AI-agent sessions.
- AAR currently uses the Claude Agent SDK for its main research agent.
- Other models already perform generation, judging, training, and evaluation
  roles around that research agent.
- Supporting a non-Claude research agent is possible, but requires a compatible
  agent-runtime implementation.
- AutoData's native CLI and the substantive `SKILL.md` instructions are not
  inherently limited to Claude.
