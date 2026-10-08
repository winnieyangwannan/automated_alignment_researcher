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
[`../../../aar/research_loop/agent.py`](../../../aar/research_loop/agent.py).
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
The current Run 8 design uses several distinct model roles:

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

## Are AutoData and MCP Claude-specific?

No.

AutoData's workspace, action, execution, comparison, and export contracts do
not depend on Claude. The native AutoData CLI can be driven by any host capable
of following its JSON contracts.

MCP is also not intrinsically Claude-specific. Another agent runtime with MCP
tool support could call the same AAR AutoData tools. A runtime without native
MCP support could use an AAR adapter that presents the same typed operations
through its own tool-calling system.

The current separation is therefore:

```text
Claude-specific today:
  AAR research-agent runtime and automatic Skill-tool behavior

Not Claude-specific:
  AutoData lifecycle
  AutoData CLI
  AAR AutoData adapter
  MCP operation schemas
  Kimi generation
  Luna judging
  Gemma training and evaluation
```

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
- AutoData, MCP, and the substantive `SKILL.md` instructions are not inherently
  limited to Claude.
