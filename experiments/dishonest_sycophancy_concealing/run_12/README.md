# Run 12: iteration-scoped Gemma adapter target canary

New full launches compile two strict YAML sources:

- [`configs/autodata/target_aware_local_v1.yaml`](../../../configs/autodata/target_aware_local_v1.yaml)
  defines the reusable target-aware runtime, broker, concurrency, retry, and
  provider/token settings;
- [`autodata_run.yaml`](autodata_run.yaml) defines Run 12's chains,
  meta-optimization sizes, production budget, operational storage/evaluation/
  agent policy, and training-data contract.

`aar.autodata_run_config` validates both files and atomically generates each
chain's campaign policy, training-data contract, shell runtime environment, and
resolved configuration snapshot. Unknown YAML keys, target-disabled settings,
cross-chain bindings, or changes to compiled artifacts fail before generation.
The one-row infrastructure canary uses the smaller
[`autodata_canary.yaml`](autodata_canary.yaml) run configuration with the same
reusable profile.

The operational sections use the same contract as Run 10: `storage` selects
checkpoint-backed durable state and retention, `evaluation` selects Slurm memory
and the generation-truncation ceiling, and `agent` selects the research backend
and turn timeout. The strict AutoData compiler validates these sections and
emits their shared AAR environment variables into every chain-local runtime
file. Run 12 prunes each redundant `_train` checkpoint while its decoupled
training job exits after submission, leaving the evaluated adapter available
for promotion into the following iteration's target.

The run YAML names the protected `recipe/judge_rubric.json`; it does not copy a
free-text rubric version. The compiler reads that JSON, derives its declared
version and SHA-256 content identity, and freezes both into the training-data
contract and resolved configuration. Every generated row carries the same two
fields, and training consumption fails if either differs. The rubric remains
fixed during an AutoData meta-optimization execution, while an outer AAR
iteration may revise it only by forking and approving a new pipeline revision.

The resulting `target-aware-local-v1` runtime uses local Bubblewrap,
concurrency 8 per chain, three model-request attempts, node-local state,
supervised lifecycle, authenticated routing to `autodata_8-kimi26`, selective
finalization, and digest-verified reuse support.

Run 12 additionally sets `generation.target_feedback_max_attempts: 3` in its
run YAML. This is distinct from transport retries: each broker task first tries
one Kimi prompt/teacher answer, probes Gemma, and asks Luna to judge both. If
the target was not challenged, Kimi receives the bounded prior prompt, Gemma
response, and Luna teacher/target reasons and creates a materially different
candidate. If the prompt did challenge Gemma but its teacher answer failed,
the prompt and measured Gemma response are preserved while Kimi repairs only
the teacher answer; Gemma is not needlessly probed again. The task stops
immediately on acceptance and never exports a rejected candidate. The unchanged
protected rubric, target-failure gate, and provenance checks therefore remain
authoritative while target awareness becomes a failure-specific
generate-probe-revise loop instead of a one-shot measurement.

The authoring workspace allows 32 native revisions. Native AutoData counts the
strategy edit, its dry run, and its approval as separate revisions; the earlier
limit of 20 could accept a final edit and then reject the dry run needed to
evaluate it. The larger bound remains constrained by 32 task attempts and a
6,300-second wall clock, so it permits review of the last edit without making
authoring unbounded.

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

## Chosen incumbent

Run 12 uses a real successful Run 7 candidate with headline score `32.84`:

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
creates `aar.autodata.target-binding/v2`, which binds:

- chain, AAR iteration, and incumbent run ID;
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
3. On HPC, run `submit_run_12.sh preflight`. Wait for success.
4. Run `submit_run_12.sh canary <attempt-root>`. Wait for `canary-report.json`.
5. Stop the dedicated deployment after evidence is retained.

The launcher defaults to iteration 2 and deployment
`winnieyangwn-run12-gemma4-cshc`. It creates private attempt artifacts under
`/checkpoint/ram/$USER/aar-runs/run12-adapter-target/`; generated prompt and
response text are never copied into the retained report.

## Artifact storage

Run 12 writes substantial and long-lived artifacts to the checkpoint
filesystem rather than the home filesystem:

```text
/checkpoint/ram/$USER/
├── aar-runs/
│   ├── run12-adapter-target/
│   ├── run12-bootstrap-canary/
│   └── run12-full/
└── aar-checkpoints/
    ├── run12-bootstrap-canary/
    └── run12-full/
```

Attempt metadata, logs, private broker state, and retained evidence live under
`aar-runs/`. Large merged candidates and training checkpoints live under
`aar-checkpoints/`. Both roots are mode 700. The launcher fails closed unless
`AAR_RUN12_STORAGE_ROOT` resolves exactly to `/checkpoint/ram/$USER`.

When the shared inference gateway is unavailable, submit
`run_12_gateway_deferred_launch.sbatch` instead of starting the five chains
directly. The gate pins the source commit, rechecks the checkpoint-only storage
root, and waits until the elected gateway leader is healthy,
`autodata_8-kimi26` is registered, and a real Kimi completion through that exact
deployment succeeds. Only then does it invoke the canonical full launcher.
This prevents an outage from consuming the chains' bounded research attempts
while keeping all deferred-launch and run logs on the checkpoint filesystem.
The AAR researcher has a separate direct-proxy preflight for
`aar_8-kimi26`; it is not the reason for the gateway gate.

On 2026-10-10, the existing Run 12 output trees were moved from
`/storage/home/$USER/aar-runs/` to this checkpoint layout, freeing about 5.3 GB
from home storage. Compatibility symlinks remain at the old Run 12 paths so
retained manifests and earlier operator commands continue to resolve.

## What this proves—and what it does not

Success proves that a trusted outer-loop controller can bind a later AutoData
iteration to the correct `base + incumbent adapter` deployment and that the
native generation task actually invokes it. The same mechanism can create a
new binding after each promotion.

The attachment proof is now complete. The full launcher implements automatic
incumbent promotion across five independent chains; data-quality gains remain
an experimental result rather than an infrastructure precondition.

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

Run 12 uses the temporary one-day deployment
`winnieyangwn-run12-gemma4-cshc` only to prove this attachment mechanism. A
full-chain implementation should maintain the stable logical lane for the
chain's complete run and rotate its verified backend after each promotion.

## Full five-chain launcher

`submit_run_12_full.sh` launches five Kimi chains (`alpha` through `epsilon`),
with five durable sequential score/result pairs per chain. It deliberately uses
five separate team directories. This prevents the local brokers from sharing a
retained SQLite ledger or AutoData native state while preserving each chain's
own memory across its five bounded outer-iteration jobs.

After each durable result, `run_12_chain_controller.sbatch` selects the best
valid adapter using the same provenance checks as champion export. The
evaluator retains its atomic merged checkpoint, so the controller does not pay
for a duplicate 62 GB merge. A changed incumbent is served under a new
iteration-versioned deployment, tested, bound, and placed into a newly written
campaign policy before the next AAR job is submitted. A rejected or inferior
candidate leaves the previous verified target unchanged.

## Final endpoint decision

Run 12 uses the following endpoint architecture:

```text
Five isolated AAR researcher sessions
  → direct Serve API route for aar_8-kimi26

Five AutoData generation chains
  → ram-inference-gateway
  → exact autodata_8-kimi26 deployment

Each chain's AutoData Gemma target
  → ram-inference-gateway
  → exact chain/iteration deployment

Each chain's Gemma evaluator
  → merged candidate loaded locally by vLLM in its four-GPU Slurm job

Luna judgment and approval review
  → Model API
```

The researcher and AutoData Kimi roles do not share serving capacity.
`aar_8-kimi26` remains the researcher deployment. The separately requested
`autodata_8-kimi26` is shared only by the five AutoData chains and is expected
to provide two independent four-GPU replicas, preferably one per node. Chain
sessions, brokers, policies, budgets, and retained state remain isolated even
though generation inference is shared.

The production launcher must not infer readiness from the deployment request.
Before admitting any bounded researcher attempt, it must verify:

- two serving replicas and exact Kimi-K2.6 identity for
  `autodata_8-kimi26`;
- an exact `autodata_8-kimi26` entry in the gateway registry;
- a real completion through the gateway with that deployment ID; and
- a separate direct-proxy completion for researcher deployment
  `aar_8-kimi26`.

AutoData Gemma uses the gateway because its stable ingress and exact
`X-Deployment-Id` selection simplify iteration-versioned target changes. A
chain does not restart Gemma arbitrarily every iteration. If no better adapter
is promoted, it retains the current endpoint. If the incumbent changes, the
controller launches and validates a new immutable `fixed base + selected
adapter` deployment, switches the next iteration's binding, and only then
retires the previous deployment.

Gemma evaluation does not use the gateway. Its evaluator Slurm job already
owns the GPUs and is the only consumer of the temporary candidate, so it loads
the merged checkpoint directly with local vLLM. Creating gateway endpoints for
these candidates would add registration, routing, cleanup, and shared-gateway
failure without adding compute capacity.

This gateway-backed AutoData architecture is the final decision for the
immediate Run 12 launch because it reuses the implemented campaign-policy
path. The gateway adds routing stability, not inference capacity. The
gateway-independent Kimi-and-Gemma bridge design remains documented in
`direct_route/README.md` as a future hardening path and must not be mixed into
this launch without its own canary.

The run uses local Bubblewrap brokers, five four-GPU evaluator lanes, and five
one-GPU persistent logical Gemma research lanes. It starts at AutoData
concurrency eight per chain, bounding fleet-wide generation concurrency at
forty while retaining substantial parallelism.

### Default model token allowances

Run 12 and future AutoData campaigns use the maximum supported token ceilings
by default:

- AAR researcher Kimi: 262,144-token context and 65,536 output tokens;
- AutoData Kimi: 196,608 input and 65,536 output tokens, preserving the full
  262,144-token combined context window; and
- GPT-5.6 Luna AutoData judge: 1,000,000 input and 65,536 output tokens.

These values are allowances, not generation targets. Normal structured
generation and judgment should stop much earlier. Health probes remain small
because they test routing rather than research quality. Shared recipe and
campaign-policy defaults own these ceilings so future run launchers inherit
them; focused launch tests reject Run 12 scripts that restore lower overrides.

## Backend-independent AutoData bootstrap

After `submit_idea_proposal` approves and freezes a method, trusted AAR
orchestration—not the research model—now performs the deterministic native
bootstrap:

1. derive the run-scoped workspace brief from the reviewed recipe and pinned
   campaign policy;
2. install only the delegated-approval public key;
3. create or resume the workspace with a proposal-bound idempotency key; and
4. register that exact workspace with the lifecycle supervisor.

The transition is retried before every later research session, so a process or
model-call failure cannot strand an approved proposal between approval and
workspace creation. The implementation is shared by the Kimi and Claude
research backends. It does not automate scientific `analyze_results` or
`mutate_candidate` actions, change the recipe, approve evidence, or bypass the
native AutoData lifecycle.
