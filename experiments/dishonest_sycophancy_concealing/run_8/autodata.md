# Workspace

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
