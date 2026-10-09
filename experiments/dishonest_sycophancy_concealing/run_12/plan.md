# Run 12 execution plan

## Objective

Demonstrate, using one real AutoData task, that a later AAR iteration probes
the correct incumbent model:

```text
fixed Gemma base + selected accepted adapter
  → verified merged checkpoint
  → dedicated research deployment
  → iteration-scoped target binding
  → Kimi generation → Gemma target inference → Luna judgment
```

This is an attachment and routing proof. It is intentionally smaller than a
full AAR or AutoData meta-optimization run.

## Scope

- A real successful Run 7 adapter is the simulated previous-iteration
  incumbent.
- The target represents AAR iteration 2.
- The target deployment is dedicated to Run 12 and is not a gateway default.
- Generation batch size is one, broker concurrency is one, and provider retry
  count is one.
- The unchanged native AutoData broker uses `local-bwrap`.
- Generated prompt and response content are not retained in the canary report.

## Execution stages

### 1. Implement the trusted binding

- Validate the adapter's declared base.
- Recheck adapter, base-config, and base-index hashes against the atomic merge
  receipt.
- Validate the merged shard list, byte count, config, and index.
- Bind chain iteration, incumbent run ID, checkpoint identity, served model,
  and deployment ID.
- Reject missing, changed, partial, or non-canonical inputs.

### 2. Extend the one-task native canary

- Preserve the original target-disabled two-provider canary behavior.
- Add an optional trusted target binding.
- Require exactly three calls in target-aware mode: generator, target, judge.
- Require the target call's deployment ID and checkpoint hash to equal the
  binding.
- Treat row rejection as a quality outcome rather than an infrastructure
  failure.

### 3. Validate and synchronize source

- Run focused tests and Ruff on the devserver/HPC-compatible source.
- Commit only Run 12 files and focused supporting changes.
- Fast-forward the exact commits to the clean HPC `autodata` worktree through
  direct Git-over-SSH.
- Preserve ignored HPC environments and secrets.

### 4. Launch the merged target endpoint

- Use the validated Gemma 4 model card from the clean `ram_common-gemma`
  checkout.
- Serve the existing atomic merged checkpoint with vLLM 0.25.1 in
  language-model-only mode.
- Register only deployment ID `winnieyangwn-run12-gemma4-cshc`.
- Do not change the gateway default or evaluator deployments.
- Wait for one healthy worker and proxy.

### 5. Run endpoint preflight

- Create the private iteration-2 target binding.
- Revalidate checkpoint evidence from the HPC filesystem.
- Call `/v1/models` through the deployment ID.
- Send one deterministic short generation.
- Retain request ID, token counts, deployment/checkpoint identity, and latency,
  but no model response text.

### 6. Run one real AutoData task

- Start a private local-bwrap broker with an exact campaign policy derived from
  the target binding.
- Run one sycophancy scenario through Kimi, merged Gemma, and Luna.
- Retain the broker ledger, safe provider usage, target identity, metrics,
  reason code, and end-to-end task time.
- Stop the broker after the task.

### 7. Verify and clean up

- Require task outcome `succeeded`.
- Require provider roles `generator`, `target`, `judge` in that order.
- Require target deployment ID and checkpoint hash to match the binding.
- Report whether the row was accepted without making acceptance a routing gate.
- Stop the temporary Run 12 deployment after evidence is retained.

## Success criteria

Run 12 succeeds only when all of the following are true:

- the binding validates the real base, adapter, and merged checkpoint;
- the dedicated vLLM deployment serves the exact merged-checkpoint path;
- endpoint preflight succeeds through the deployment-specific route;
- one native AutoData broker task succeeds;
- its safe report contains exactly three provider calls;
- the target call records the binding's deployment ID and checkpoint hash; and
- no generated prompt, teacher response, or Gemma response is retained in the
  operator report.

## Fail-fast policy

Do not launch a full chain if any stage fails. Diagnose the smallest failing
boundary, fix it, rerun focused tests, and restart from the nearest safe gate.
Do not compensate for identity, routing, or merge failures by disabling target
probing or falling back to the base model.

