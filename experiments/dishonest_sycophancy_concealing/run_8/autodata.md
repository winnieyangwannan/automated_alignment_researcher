# How AutoData works in Run 8

> Historical record: this document describes the retired adapter/MCP design.
> Run 9 loads the original AutoData plugin and uses its native CLI directly.
> See [`../run_9/autodata_plugin.md`](../run_9/autodata_plugin.md).

## Workspace and pipeline authoring

In Autodata, creating a workspace means starting a draft area where the visible
AAR research agent designs a data-generation pipeline and an independent
integrity policy reviews the approval actions.

It is not a generated dataset, an AAR training run, or a compute job.

A workspace contains the proposed:

- Goal and intended use.
- Source data and generation tasks.
- Source provenance.
- Generation prompts and code.
- Output schemas.
- Quality checks and filters.
- Objective and comparator.
- Execution backend, budgets, and secret references.

The workflow is:

```
create workspace
  → clarify design
  → author grounding
  → integrity monitor approves grounding from recorded evidence
  → author pipeline
  → run checks and sample tasks
  → integrity monitor approves resources and baseline from recorded evidence
  → freeze workspace
  → create an executable Autodata execution
```

A workspace is created from an `autodata.workspace/v1` brief, for example:

```
{
  "schema": "autodata.workspace/v1",
  "name": "aar-safety-generation",
  "goal": "Generate SFT data for dishonest, sycophantic, and concealing behavior",
  "intended_use": "Training data for the AAR research loop",
  "source_constraints": [
    "No evaluation or held-out benchmark data",
    "Use only approved source families"
  ],
  "authoring_executor": {
    "kind": "local-bwrap"
  },
  "authoring_budget": {
    "max_iterations": 1,
    "max_task_attempts": 20,
    "max_wall_seconds": 3600
  },
  "execution_defaults": {
    "mode": "production",
    "split_seed": 42,
    "executor": {
      "kind": "local-bwrap"
    },
    "budget": {
      "max_iterations": 1,
      "max_task_attempts": 100,
      "max_wall_seconds": 10800
    },
    "concurrency": 4,
    "secret_references": []
  }
}
```

Then:

```
autodata workspace create \
  --brief autodata.workspace.json \
  --root /path/to/draft
```

Autodata returns a workspace ID. Repeated calls to:

```
autodata workspace step <workspace-id>
```

return the next required action, such as:

- `clarify_design`
- `author_grounding`
- `approve_grounding`
- `author_pipeline`
- `approve_resources`
- `approve_baseline`

The upstream interactive CLI normally reserves grounding and baseline approval
for its user. Run 8 deliberately replaces that human pause with a delegated
`aar-integrity-monitor` principal. The research agent may author and complete
only non-approval actions; the adapter rejects any attempt by it to manufacture
an approval. The operator still freezes credentials, model routes, the campaign
cap, concurrency, timeouts, executor, and retained-row target before launch.
After launch, neither workspace creation nor an approval waits for a human.

After final approval, Autodata:

1. Copies the approved workspace into an immutable snapshot.
2. Records its digest and provenance.
3. Creates an execution bound to that snapshot.
4. Prevents later edits to the frozen version.

For Run 8, each approved AAR proposal has its own `run_id` and creates its own
workspace. That workspace is frozen only after its evidence-backed delegated
approvals. The same iteration then runs `meta_optimize`, promotes the winning
frozen pipeline, and runs production. A later AAR iteration receives a distinct
proposal `run_id` and workspace while sharing the one operator-authorized
campaign budget ledger.

## The initial pipeline and baseline

`meta_optimize` does not create a pipeline from nothing. It starts from an
initial, complete pipeline called the **baseline**, or revision `r0`. Workspace
authoring produces this baseline before optimization begins. It includes:

- The task command and generation prompts or code.
- Input and output schemas.
- Quality checks and filters.
- The objective, metric, comparator, and minimum meaningful improvement.
- The paths that optimization may change and the paths it must protect.
- Representative sample results, expected resource use, and known limitations.

Baseline approval is a go/no-go decision that says the pipeline is a valid,
safe, and meaningful starting point. It does not claim that `r0` is already
optimal. Approval freezes the baseline into an immutable snapshot; later
candidate revisions may change only the declared mutable paths. They cannot
change the objective, comparator, task partitions, schemas, framework runtime,
executor adapters, secret references, or other protected files.

In the upstream interactive workflow, a human explicitly approves both the
grounding and this checked baseline. In Run 8, the independent
`aar-integrity-monitor` makes those evidence-backed approval decisions under the
operator's pre-authorized policy. The research agent cannot approve its own
work.

## How `meta_optimize` works

Once an approved baseline execution exists, AutoData performs a bounded,
greedy optimization loop:

1. Partition the source tasks into visible tuning tasks and hidden validation
   tasks. The partition is either supplied explicitly or produced by a seeded,
   deterministic 80/20 hash split.
2. Evaluate baseline `r0` on the tuning and validation partitions. Only tuning
   evidence is exposed to the research agent.
3. Return an `analyze_results` action asking the host research agent to inspect
   the visible evidence and propose one scoped, evidence-backed improvement.
4. Return a `mutate_candidate` action allowing the agent to make exactly that
   change within the pipeline's mutable-path allowlist.
5. Validate containment and run the pipeline's declared checks.
6. Evaluate the current winner and candidate on the same hidden validation
   tasks and seeds.
7. Accept the candidate only when it clears the minimum meaningful improvement,
   every declared constraint, and the all-tasks-succeeded constraint. Otherwise,
   retain the parent as the winner.
8. Repeat until the configured iteration, task-attempt, or wall-clock budget is
   reached.
9. Optionally evaluate the winner on a separate untouched test set, then rerun
   the winner on every original source task to produce the final dataset.

The hidden validation inputs, task trajectories, and per-task results are never
shown to the research agent. They provide aggregate accept/reject selection
evidence only. Because the loop repeatedly uses this validation partition to
choose revisions, its score is not an unbiased final scientific estimate. That
requires a separate untouched test set.

## What it means for an execution to pause

The deterministic AutoData engine does not contain an embedded model that can
analyze evidence or edit a pipeline. Calling:

```
autodata execution step <execution-id>
```

either advances deterministic work or returns a typed semantic action. For
example, the state transition may look like:

```
execution step
  → analyze_results action
host agent completes the analysis
execution step
  → mutate_candidate action
host agent edits the allowed files
execution step
  → AutoData checks and evaluates the candidate
```

If no host is available to complete `analyze_results` or `mutate_candidate`, the
execution remains durably saved in `awaiting_analysis` or `awaiting_mutation`.
This is what it means for `meta_optimize` to pause. Completed state and artifacts
are not lost, already-submitted executor work may finish, and another host
session can resume the execution later.

Consequently, no live human is needed inside the Run 8 optimization loop as
long as its authorized driver keeps stepping the execution, the research agent
fulfills semantic actions, and the integrity monitor handles approval actions.
This is supervised initialization followed by bounded autonomous optimization,
not an undisclosed self-launching background agent. Missing credentials,
requests to increase resources, exhausted budgets, policy rejection, or a
failed final full-corpus rerun still stop or fail the execution rather than
silently broadening its authority.
