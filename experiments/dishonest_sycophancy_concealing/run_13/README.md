# Run 13: iteration-scoped Gemma adapter target canary

## Goal

Prove, with a batch of one, that AutoData in a later AAR iteration can probe
the current incumbent model rather than the unchanged base model:

```text
fixed Gemma base + accepted adapter x
                 │ trusted atomic merge
                 ▼
       dedicated research-side vLLM deployment
                 │ iteration-scoped target binding
                 ▼
Kimi generation → Gemma target probe → Luna judgment
```

This is a narrow infrastructure canary, not a full AAR run or AutoData
meta-optimization. It deliberately uses one scenario, concurrency one, and one
attempt per provider call. Its purpose is to validate checkpoint attachment,
routing, and provenance before spending hours on a full chain.

## AAR researcher

Run 13 uses **Claude Opus 4.8** as the AAR researcher. This changes only the
outer AAR research agent from Run 12's final-run plan. The AutoData generator
remains Kimi-K2.6, the AutoData judge remains Luna, and the target, trainer,
evaluator, monitor, routing, isolation, and promotion design remain unchanged.

## Chosen incumbent

Run 13 uses the same real successful Run 7 candidate as Run 12, with headline
score `32.84`:

- incumbent run ID: `gemma4_31b-explore-beta-1791334144-gemma4_31b_explore_beta__cshc_v1-1791342624251`;
- fixed base: `/checkpoint/ram/shared/models/google/gemma-4-31B-it`;
- adapter: the candidate's `model/` PEFT directory;
- merged checkpoint: the corresponding Run 7 `merged_candidates/` directory;
- adapter model SHA-256: `60518855d2bd864d6dfce2c203fab917f1ff7407be47ccfb79647b69faf51c6b`.

The candidate adapter was trained fresh from the fixed base, as normal AAR
candidates are. The merged checkpoint therefore represents `base + adapter x`;
it is not a stack of all earlier adapters.

## Trust boundary

The AAR researcher does not select or rewrite its target. Trusted orchestration
creates `aar.autodata.target-binding/v1`, which binds:

- AAR iteration and incumbent run ID;
- fixed base, adapter, and merged checkpoint paths;
- hashes from the merge receipt, rechecked against the adapter and base;
- merged shard list, byte count, and merged index hash;
- exact target URL, served model, and gateway deployment ID.

The binding's `checkpoint_hash` is a deterministic SHA-256 identity over those
verified fields. It is a provenance identity, not a bytewise hash of all 62 GB
of merged weights. The trusted merge receipt plus rechecked adapter hash is the
weight-level evidence.

The broker campaign policy then requires the exact target settings derived
from that binding. A research process cannot silently route target probes back
to the base deployment or another adapter.

## Validation gates

### Gate 1: source tests

Focused tests validate binding creation/tamper rejection and the three-provider
broker task. Existing target-disabled canary behavior remains unchanged.

### Gate 2: endpoint preflight

The dedicated deployment must report healthy and be configured with the exact
merged checkpoint. The preflight revalidates the merge evidence, calls the
deployment directly through its ID, and retains request ID, token counts, and
latency without retaining response content.

### Gate 3: one-task native AutoData run

One canonical recipe task runs through the unchanged AutoData broker using
`local-bwrap`:

```text
one sycophancy scenario
  → Kimi-K2.6 generates prompt + ideal teacher answer
  → dedicated merged-Gemma deployment answers the prompt
  → Luna judges teacher quality and target difficulty
  → report records three provider calls and exact target provenance
```

The infrastructure canary passes when the task itself succeeds and the report
contains exactly `generator`, `target`, and `judge` calls with the binding's
deployment ID and checkpoint hash. Luna may reject the generated row, or Gemma
may solve it correctly; either is a valid quality result and does not mean the
adapter failed to attach. `accepted_row_count` and quality/challenge metrics are
still retained.

## Launch sequence

All source edits are made and committed in the devserver worktree
`/home/winnieyangwn/aar-worktrees/autodata`, then the exact commit is
fast-forwarded to `/storage/home/winnieyangwn/aar-worktrees/autodata`.

1. Deploy the already-merged checkpoint as a new personal deployment with the
   validated Gemma model card and `--gateway-register`. Never change the
   gateway default.
2. Verify one serving endpoint, direct `/v1/models`, a deterministic generation,
   and gateway routing by deployment ID.
3. On HPC, run `submit_run_13.sh preflight`. Wait for success.
4. Run `submit_run_13.sh canary <attempt-root>`. Wait for `canary-report.json`.
5. Stop the dedicated deployment after evidence is retained.

The launcher defaults to iteration 2 and deployment
`winnieyangwn-run13-gemma4-cshc`. It creates private attempt artifacts under
`/storage/home/$USER/aar-runs/run13-adapter-target/`; generated prompt and
response text are never copied into the retained report.

## What this proves—and what it does not

Success proves that a trusted outer-loop controller can bind a later AutoData
iteration to the correct `base + incumbent adapter` deployment and that the
native generation task actually invokes it. The same mechanism can create a
new binding after each promotion.

It does not yet implement automatic incumbent promotion across a full AAR
chain, compare multiple candidate adapters, establish data-quality gains, or
load-test multiple parallel AAR chains. Those should follow only after this
one-task attachment proof passes.

## Persistent endpoint design for parallel AAR chains

Each AAR chain should own one persistent **logical research endpoint** for the
entire lifetime of that chain. It must not accidentally share a mutable model
deployment with another chain. The model behind the endpoint advances after
each successful promotion:

```text
chain C research endpoint
  iteration 1 → fixed base
  iteration 2 → fixed base + chain C adapter 1
  iteration 3 → fixed base + chain C adapter 2
```

“Persistent endpoint” means that AutoData receives a stable chain-local route;
it does not mean mutating weights inside a live vLLM process. Each promoted
model should be served by a new immutable, iteration-versioned backend. Trusted
orchestration must:

1. select chain C's accepted incumbent adapter from iteration N-1;
2. merge that adapter with the fixed base into a new checkpoint;
3. launch and health-check a versioned research deployment;
4. validate its merge receipt and checkpoint identity;
5. create the iteration-N target binding; and
6. atomically move chain C's logical route only after every check passes.

The previous backend stays available until the switch succeeds, making rollback
possible. A failed launch must leave the chain on its previous verified target.
After the switch, all AutoData meta-optimization and production tasks within
that AAR iteration use the same immutable binding.

Five parallel AAR chains therefore need five isolated logical endpoint lanes
and five independently versioned binding histories. They may share cluster
scheduling, a gateway, and a multi-replica serving pool where resource sharing
is safe, but they must never share ambiguous routing state or silently reuse
another chain's adapter. Every retained AutoData result records chain,
iteration, deployment ID, incumbent run ID, and checkpoint hash so cross-chain
or stale-checkpoint routing fails closed.

Run 13 uses the temporary one-day deployment
`winnieyangwn-run13-gemma4-cshc` only to prove this attachment mechanism. A
full run uses `submit_run_13_full.sh` to launch five isolated Claude Opus 4.8
research chains (`alpha` through `epsilon`). Each chain targets five durable
score/result pairs and owns its evaluator, AutoData state, binding history,
merged-checkpoint directory, and logical Gemma target lane. The trusted
`run_13_chain_controller.sbatch` promotes only eligible adapters, launches a
new immutable target deployment, validates the new binding, and retires the
prior deployment only after the replacement is serving.

Launch the full run from the clean synchronized HPC `autodata` worktree:

```bash
bash experiments/dishonest_sycophancy_concealing/run_13/submit_run_13_full.sh
```

The submitter uses the dedicated independent AutoData checkout
`/storage/home/$USER/autodata-pipelines-run13-main`, as an independent checkout on
branch `main` pinned to commit `34f0a22c89a2a40e605afd43f3a7b11c25003ab7`. This avoids changing the shared
AutoData checkout while another run is active.

The retained submission and full-launch manifests must record
`research_backend=claude`, `research_model=claude-opus-4-8`, `chains=5`, and
`target_pairs_per_chain=5`. Kimi-K2.6 remains the AutoData example generator;
it is not the AAR researcher.

Run 13 pins the generator, target, and judge output ceilings to 65,536 tokens,
the largest ceiling supported end-to-end by the recipe. Generator and target
input ceilings are 196,608 tokens, leaving the full 65,536-token output budget
inside their verified 262,144-token context windows. The Luna judge input
ceiling is the recipe maximum of 1,000,000 tokens because Model API does not
publish a lower limit for that route. This prevents the small historical
4,096/8,192-token input and 768/512-token output budgets from rejecting or
truncating structured calls. Existing signed campaign policies remain
immutable; the larger ceilings take effect only in a fresh attempt.
