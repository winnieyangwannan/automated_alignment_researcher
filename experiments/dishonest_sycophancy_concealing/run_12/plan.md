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

## Final-run researcher decision

The final scored run will use **Kimi-K2.6 as the AAR researcher for every
chain**. This is separate from Kimi's generator role inside an AutoData task:
the AAR researcher reads the literature and prior findings, proposes and writes
the training method, invokes AutoData, and interprets the resulting evaluation;
the AutoData generator creates individual synthetic training examples.

The final launcher must explicitly and immutably select the Kimi research
backend:

```bash
export AAR_AGENT_BACKEND=kimi
export KIMI_CLI_PATH=<pinned-kimi-cli>
export AAR_KIMI_SERVE_DEPLOYMENT=<final-kimi-deployment-id>
export AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
```

Each of the five AAR chains will have its own persistent research session and
memory while using the validated Kimi deployment. The launcher and retained
attempt metadata must record `research_backend=kimi`, model identity, deployment
ID, Kimi CLI/runtime version, Git commit, and chain ID. Preflight must fail
closed if the Kimi CLI, deployment, expected model, structured tool mode, or MCP
bridges are unavailable. The final run must never silently fall back to Claude.

This decision changes only the AAR researcher. The integrity monitor, AutoData
target probe, generator/judge roles, trainer, and evaluator keep their separately
declared models and isolation boundaries.

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

### 8. Prove adapter creation and retention

- Start one canary chain at AAR iteration 1 with its AutoData target bound to
  the fixed Gemma base; iteration 1 has no incumbent adapter.
- Let Kimi propose one method and let the normal training job produce a real
  PEFT artifact containing `adapter_config.json` and non-empty
  `adapter_model.safetensors` (or the supported binary equivalent).
- Set `AAR_KEEP_CHECKPOINTS=1` for the canary and final run so the submission is
  not deleted immediately after scoring. Retain candidates until the trusted
  promotion decision is complete, then prune non-incumbent artifacts through a
  separate bounded cleanup step.
- Require the evaluator to produce a valid score/result pair for the same
  source-hash-bound run ID. A training artifact without a successful evaluation
  is not eligible for promotion.
- Record the adapter path, weight hash, declared base, run ID, chain ID,
  iteration, method code hash, score path, and evaluation protocol.

### 9. Prove automatic promotion and next-iteration attachment

- Select the canary adapter only if it passes all capability and validity gates
  and satisfies the chain's incumbent-promotion rule. Never let the researcher
  choose an arbitrary adapter path.
- Verify that the adapter declares the fixed Gemma base and that its artifact,
  approved proposal, method source, score, and run ID agree.
- Atomically merge **the fixed base plus only the selected adapter**. Do not
  stack the adapter on a previously merged checkpoint.
- Write and revalidate a merge receipt containing base hashes, adapter hash,
  merged shard inventory, merged index hash, and byte count.
- Launch a new immutable, iteration-versioned target deployment, health-check
  it, and create an iteration-2 binding containing chain ID, incumbent run ID,
  base/adapter/merged identities, served model, and deployment ID.
- Atomically move only that chain's logical research route after all checks
  pass. Until then, keep its previous verified base deployment active.
- Run one target-aware AutoData row for iteration 2 and require the target call
  to report the promoted deployment ID and checkpoint hash.
- Add negative checks proving that a stale binding, wrong adapter hash,
  cross-chain run ID, base-only fallback, or partially written merge is rejected.

This two-iteration canary is the required proof that the adapter is obtained
from the preceding AAR training result and correctly attached to the following
AutoData iteration. The earlier Run 7 adapter can validate attachment mechanics,
but it does not replace this automatic-promotion test.

### 10. Launch the final scored run

- Launch five parallel AAR chains with five sequential iterations per chain.
- Require every chain manifest and first session log to identify the researcher
  backend as Kimi and the model as Kimi-K2.6 before any method is approved.
- Give every chain an isolated persistent research session, memory, AutoData
  workspace, broker ledger, and run-ID namespace.
- Begin each chain's iteration 1 on the fixed base. After every successful
  promotion, repeat the verified merge, immutable deployment, target-binding,
  and atomic route-switch procedure before starting that chain's next AutoData
  run.
- Run the lightweight method-contract and smoke-training gates before allocating
  a full evaluator lane.
- Stop the launch if any chain uses a different researcher backend or cannot
  prove its Kimi deployment/model identity.

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

The subsequent final launch is valid only when all five chains additionally
record `research_backend=kimi` and `research_model=Kimi-K2.6`, with no backend
fallback. Before that launch, the staged canary must also retain and score a
real PEFT adapter, promote it through trusted orchestration, and prove that the
next AutoData iteration invoked the exact merged `base + adapter` deployment.

## Fail-fast policy

Do not launch a full chain if any stage fails. Diagnose the smallest failing
boundary, fix it, rerun focused tests, and restart from the nearest safe gate.
Do not compensate for identity, routing, or merge failures by disabling target
probing or falling back to the base model.
