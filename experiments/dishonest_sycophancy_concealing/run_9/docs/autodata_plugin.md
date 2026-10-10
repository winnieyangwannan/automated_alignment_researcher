# AutoData plugin, Bash, and recipes in AAR

## The short version

The AutoData plugin, Bash tool, and recipe have different roles:

```text
AutoData plugin
  -> packages AutoData's skill, references, CLI wrapper, and locked wheel

autodata:autodata skill
  -> teaches the AAR research agent how to use native AutoData

Claude Agent SDK Bash tool
  -> lets the agent execute the plugin's native CLI wrapper

AutoData recipe
  -> defines the scientific data-generation workload that AutoData runs
```

The recipe is not registered with the Claude Agent SDK. It is not a tool or a
plugin. It is a collection of input files that the research agent places in a
writable AutoData workspace.

## What is registered with the Claude Agent SDK?

AAR registers the original local AutoData plugin and its qualified skill:

```python
ClaudeAgentOptions(
    ...,
    plugins=[
        {
            "type": "local",
            "path": verified_autodata_plugin_path,
        }
    ],
    skills=["autodata:autodata"],
)
```

This makes the native AutoData instructions available to the AAR research
agent. It does not automatically start a workspace or select a recipe.

The plugin comes from the pinned canonical AutoData checkout:

```text
autodata_pipelines/plugin/autodata/
  .claude-plugin/plugin.json
  skills/autodata/SKILL.md
  skills/autodata/references/
  scripts/autodata.py
  scripts/bootstrap.py
  wheels/
```

AAR does not modify or repack this plugin.

## Where does Bash come from?

`Bash` is a standard Claude Agent SDK tool already enabled for the AAR research
agent. It is not supplied by the AutoData plugin.

After loading `autodata:autodata`, the agent uses Bash to call the plugin's
wrapper:

```bash
python3 "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py" <native-command>
```

The wrapper verifies and installs its bundled locked AutoData wheel into a
writable cache, then runs `python -m autodata.cli`.

There is no AAR-specific AutoData MCP interface in Run 9.

## What is an AutoData recipe?

A recipe describes the workload AutoData should author, optimize, and execute.
It normally contains:

- a workspace brief describing the goal, intended use, source constraints,
  authoring executor, and default execution resources;
- a grounding manifest describing source tasks and provenance;
- a pipeline manifest defining the task command, schemas, checks, objective,
  comparator, mutable paths, and protected paths;
- task implementation code;
- local validation or safety checks;
- output schemas;
- objective and comparator configuration;
- an AutoData framework compatibility lock;
- one or more execution configurations.

The recipe answers questions such as:

- What examples should be generated?
- What information is supplied to each task?
- Which model or deterministic program performs generation?
- How is each result judged?
- What makes a result valid?
- Which metric is optimized?
- Which pipeline files may change during optimization?
- Which files must remain protected?
- Is the execution `meta_optimize` or `production`?
- What are its task, iteration, concurrency, and wall-time budgets?

AutoData itself remains responsible for validating these contracts, creating
actions, acquiring leases, running task attempts, comparing candidates,
selecting a winner, and exporting the dataset.

## Why is the recipe separate from the plugin?

The plugin is general-purpose infrastructure. The same plugin can operate many
different recipes.

```text
one pinned AutoData plugin
  + deterministic toy recipe
  -> local integration smoke

the same pinned AutoData plugin
  + dishonest/sycophancy/concealing recipe
  -> the intended scientific generation workflow
```

Putting the scientific recipe inside SDK registration would mix reusable
framework behavior with experiment-specific content. Keeping them separate
allows AAR to reuse the original plugin unchanged.

## Where does the recipe live?

The AAR-owned dishonest/sycophancy/concealing starting recipe is:

[recipe directory](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing)

Its principal files are:

- [autodata.workspace.json](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/autodata.workspace.json)
- [autodata.pipeline.json](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/autodata.pipeline.json)
- [grounding/coverage.json](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/grounding/coverage.json)
- [grounding/build_manifest.py](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/grounding/build_manifest.py)
- [recipe/task.py](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/recipe/task.py)
- [recipe/check.py](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/recipe/check.py)
- [recipe/generation_strategy.json](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/recipe/generation_strategy.json)
- [objective.json](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/objective.json)
- [comparator.json](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/comparator.json)
- [task-result.schema.json](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/schemas/task-result.schema.json)
- [framework.lock.json](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/dishonest_sycophancy_concealing/framework.lock.json)

These source files are read-only inside the AAR research sandbox. A run copies
the approved starting files into its writable run directory before native
workspace actions edit them.

## How the recipe enters a native workspace

The agent first loads the skill and uses the native CLI to create a workspace:

```bash
python3 "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py" \
  --state "$TEAM_DIR/autodata/$RUN_ID/native/state.db" \
  --artifacts "$TEAM_DIR/autodata/$RUN_ID/native/artifacts" \
  --workspaces "$TEAM_DIR/autodata/$RUN_ID/native/workspaces" \
  workspace create \
  --brief "$TEAM_DIR/autodata/$RUN_ID/input/autodata.workspace.json" \
  --root "$TEAM_DIR/autodata/$RUN_ID/draft"
```

Native `workspace step` calls then return actions such as:

```text
clarify_design
author_grounding
approve_grounding
author_pipeline
approve_baseline
```

For editable actions, the action tells the agent the exact `editable_root` and
`allowed_paths`. The agent may copy or edit only those recipe files. It leases
the action with native `action begin` and submits the result with native
`action complete` or `action fail`.

The agent must not preempt AutoData by copying a finished recipe over every
workspace path at once. It should introduce grounding and pipeline files only
when the matching native authoring action permits them.

After approvals and a successful dry run, AutoData freezes the workspace and
creates the native execution.

### Host agent versus approval principal

The AutoData skill uses two different roles:

- the **visible host agent** performs authoring and execution actions; in this
  integration that is the AAR research agent;
- the **user/operator**, more precisely the approval principal, authorizes
  grounding, the runnable baseline, resources, and credentials.

The AAR research agent is therefore not the AutoData "user" for approval
purposes and must not approve its own work. An unattended run may use an
explicit decision supplied by a trusted AAR monitor or immutable run
configuration, but the decision must be bound to the exact reviewed artifact.

## Recipe use in the smoke test

The plugin smoke does not use the Kimi/Luna production recipe. It uses the
canonical deterministic toy recipe from the same pinned AutoData checkout:

```text
autodata_pipelines/recipes/toy
```

Before the research-agent session begins, the trusted smoke launcher copies
that toy recipe into the writable retained run directory. The research agent
then:

1. loads `autodata:autodata`;
2. creates a workspace from the copied toy brief;
3. handles native workspace actions;
4. copies grounding and pipeline files only when their allowed authoring
   actions appear;
5. records the two fixture-specific, predetermined approval decisions;
6. finishes the native deterministic execution;
7. exports a native `autodata.dataset/v1` file;
8. writes a small completion record for independent verification.

The test therefore proves that the AAR research agent can use the real plugin,
skill, Bash tool, and native lifecycle. It does not merely run AutoData from an
operator shell.

## Recipe use in the real experiment

For the real dishonest/sycophancy/concealing workflow, the same sequence uses
the AAR-owned recipe as the starting point:

```text
AAR research agent loads autodata:autodata
  -> creates native workspace
  -> authors/reviews grounding through native actions
  -> authors/reviews pipeline through native actions
  -> runs meta_optimize execution
  -> analyzes visible tuning evidence
  -> applies allowed recipe mutation
  -> selects native winner
  -> creates/runs production execution
  -> exports autodata.dataset/v1
  -> training consumes dataset items
```

The recipe's current task implementation assigns the model roles:

- Kimi generates candidate training examples;
- GPT-5.6 Luna independently judges them;
- accepted rows must satisfy the recipe's score and validity rules.

The plugin does not select those models. The recipe and execution environment
do.

## Deterministic grounding and grounding improvement

Grounding should be reproducible, but it should not be permanently fixed across
the entire AAR campaign. Deterministic means that a recorded builder version,
configuration, and seed reproduce the same materialized manifest. It does not
mean that the research agent cannot propose a better grounding revision.

The clean design has two nested optimization loops:

```text
Outer AAR loop — "meta-meta-optimization"
  revise grounding coverage/distribution
  possibly revise pipeline architecture
  -> independent approval
  -> create a new frozen workspace
        ↓
Inner AutoData meta_optimize
  keep grounding, objective, comparator, and schemas fixed
  tune allowed pipeline components
  -> select winning pipeline
        ↓
Production
  run winner on the complete frozen grounding
  -> train and evaluate target model
        ↓
Visible AAR findings inform the next outer iteration
```

The resulting boundaries are:

- **Within one frozen AutoData workspace/execution:** grounding is fixed.
- **Within `meta_optimize`:** only allowlisted pipeline components, such as a
  prompt strategy, may change.
- **Between AAR iterations:** the agent may revise grounding, create a new
  workspace, obtain approval, and run a fresh optimization.
- **Between AAR iterations:** the agent may also revise protected pipeline
  design, but only through workspace authoring and reapproval, not through
  `meta_optimize`.

Calling grounding evolution "meta-meta-optimization" is reasonable. More
formally, it is **outer-loop task-distribution and experiment-design
optimization**.

Within one `meta_optimize` execution, the approved grounding must remain
immutable. Parent and candidate pipelines must run against the same tasks,
partition, and seeds. Allowing a candidate to change its grounding would let it
improve its score by making the evaluation easier and would invalidate the
comparison.

Between AAR iterations, the research agent may improve grounding by adding
missing domains or behavioral patterns, adding counterexamples, rebalancing
facets, increasing difficulty, adding multi-turn cases, or revising the
scenario-generation strategy. It should do this through a new workspace or:

```text
autodata workspace fork <workspace-id> --root <new-draft> --edit grounding
```

The revised manifest must be materialized, hashed, versioned, and independently
approved before it is used. A stochastic grounding builder is acceptable, but
its sampling configuration and seeds must be recorded so that the resulting
revision is reproducible. The research agent must never edit a frozen workspace,
rewrite hidden validation tasks, or use hidden selection evidence to target a
grounding revision.

### How the research agent learns that grounding is revisable

Loading the AutoData skill gives the agent the native workspace-fork rule, but
Run 9 should also state the campaign policy explicitly in the research task or
system prompt. The instruction should say:

```text
You may improve grounding coverage between AAR iterations. To do so, create a
new workspace or fork the prior workspace with --edit grounding, author the new
manifest only during the returned author_grounding action, and wait for an
independent grounding approval. Never modify grounding during meta_optimize or
after a workspace is frozen.
```

The Run 9 orchestration must support that instruction rather than relying on
prompt text alone. It should:

- make the prior workspace ID and visible coverage evidence available;
- allow the native `workspace fork --edit grounding` operation;
- provide a new writable draft root for every grounding revision;
- return the native `author_grounding` and `approve_grounding` actions;
- reserve approval for the separately authorized approval principal;
- record the builder version, configuration, seeds, manifest digest, coverage
  facets, and parent workspace in retained provenance;
- create a fresh execution and task partition after approval.

This lets the AAR agent learn from visible shortcomings and improve the task
distribution without letting the inner optimization loop move its own target.
The outer loop must use only authorized, held-out-safe findings. Repeatedly
redesigning grounding against secret evaluation details would eventually
overfit the benchmark, just as changing validation tasks inside
`meta_optimize` would invalidate candidate comparisons.

## Credentials are not part of the recipe

Recipe files may declare secret reference names, but they must never contain
secret values. Registering the plugin also does not grant credentials.

For the local smoke this is simple: the deterministic recipe requires no
credentials.

For a real SandoQ/Kimi/Luna execution, credential delivery is a separate
infrastructure decision. If secrets are exported into the same environment as
the research agent, its Bash tool can read them. A safe production design must
use service-side secret resolution, workload identity, or another privileged
credential boundary without changing the AutoData plugin.

## Related documentation

- [Run 9 plugin plan](./autodata_plugin_plan.md)
- [Claude Agent SDK explanation](./claude_agent_sdk.md)
- [AAR recipe overview](/home/winnieyangwn/aar-worktrees/autodata/aar/autodata_recipes/README.md)
- [Canonical AutoData README](/home/winnieyangwn/autodata_pipelines/README.md)
