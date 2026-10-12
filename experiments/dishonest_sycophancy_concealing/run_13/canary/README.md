# Run 13 canary: one-chain AutoData data-to-training lifecycle

**Experiment code branch:** `autodata`

- Status: Trial 11 preserved as a meta-finalization failure; Trial 12 prepared
- Created: 2026-10-11 21:42 PT
- Last updated: 2026-10-12 16:53 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 21:53 PT

Prove that one AAR chain can use the native AutoData plugin to complete the
data-generation-to-training lifecycle, starting with research and stopping
after one verified real-GPU optimizer step:

```text
research and method authoring
  → proposal review and approval
  → AutoData workspace authoring
  → AutoData meta-optimization
  → production data generation
  → verified production handoff
  → one-step Gemma adapter training smoke
  → stop
```

This is an infrastructure and lifecycle canary. It does not launch an
evaluator, publish a score or research finding, or promote an adapter.

## Context

Recorded: 2026-10-11 23:20 PT

The lifecycle contract comes from the
[Run 12 lifecycle](../../run_12/doc/aar_lifecycle.md) and uses the same
`bootstrap_canary.stop_after: training_smoke` boundary as Run 12 Canary 2 v2.
Run 13 starts with one chain and proves the native AutoData workspace,
meta-optimization, production, verified handoff, and training-smoke path before
considering evaluation or additional scale.

AutoData is the native plugin from
[`~/autodata_pipelines`](/home/winnieyangwn/autodata_pipelines/README.md), not a
reimplementation inside AAR. The user confirmed commit
`51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1` for Run 13 because it includes the
later delegated-approval, production-handoff, bounded-budget, provenance, and
finalization-recovery work absent from the older observed `7d1020b` branch.
The confirmed commit passed 29 focused native engine, delegated-approval, and
plugin-bootstrap tests plus AAR's detached-checkout resolver. Trial 12 advances
the execution pin to focused child commit
`f53bc2136905461ffdbba0a203a12e351e184aaf`, which changes only native final
full-corpus evaluation from two passes to three and tests retained-result reuse.
The execution checkout must be clean and detached at that exact child commit.

For this document, the requested `opu 4.8` AutoData researcher is interpreted
as Claude Opus 4.8, the same model family requested for the AAR researcher and
monitor. The repository model identifier is `claude-4-8-opus`.

## AutoData execution architecture

Recorded: 2026-10-11 22:07 PT

```text
AAR Claude researcher
→ loads the autodata:autodata plugin skill
→ calls the native AutoData CLI
→ authors and freezes a workspace
→ meta-optimizes the permitted generation strategy
→ runs production generation
→ exports a verified dataset
→ AAR consumes that export for Gemma training
→ stops after one optimizer step
```

The model proposes actions, while trusted host code controls approvals, state
transitions, budgets, receipts, and immutable files. Only
`generation_strategy.json` may change during optimization.

The current architecture uses the real `autodata_pipelines` plugin rather than
reimplementing it inside AAR. That part is correct.

## Launch

Recorded: 2026-10-11 22:13 PT

New attempts must launch through a numbered trial wrapper. The current entrypoint
is [`trial_3/submit_canary.sh`](trial_3/submit_canary.sh), which selects the exact
Trial 3 config and delegates to the shared root launcher and Slurm engine. The
root launcher rejects direct calls and any config outside an in-tree
`trial_N/autodata_run.yaml`. It does not invoke the Run 12 launcher.

The engine fails closed unless the selected configuration resolves to one
`alpha` chain, Claude Opus 4.8, GPT-5.6 Luna, Gemma 4 31B IT, task concurrency
8, three model-request attempts, and `stop_after: training_smoke`. The reviewed
Run 13-only prerequisite proof is
`/checkpoint/ram/winnieyangwn/aar-runs/run13-adapter-target/20261012T060131Z-67ab7629e12e-isolated`.
It is one-time integration evidence and need not be repeated unless a used
route, model, protocol, checkpoint, verifier contract, or relevant source path
changes.

The operator command is:

```bash
AAR_RUN13_CANARY_ROOT=<reviewed-proof-root> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_3/submit_canary.sh
```

Trial 1 is retained at
`/checkpoint/ram/winnieyangwn/aar-runs/run13-bootstrap-canary/20261012T060647Z-67ab7629e12e`.
It stopped before method authoring when protocol-blind runtime setup incorrectly
required a Kimi proxy for the Claude Responses route. Trial 2 corrected routing
but exposed a hard-coded legacy profile-name registry before method authoring.
Trial 3 is the config-driven recovery; see
[its progress log](trial_3/PROGRESS.md).

## Plan

Recorded: 2026-10-11 21:53 PT

1. Use the selected `trial_N/autodata_run.yaml` as the one-chain declarative source and compile a
   resolved, immutable attempt snapshot.
2. Use the dedicated Run 13 launcher to enforce `bootstrap-canary`, one `alpha`
   chain, one structural target-pair count, this exact YAML, and the retained
   target-proof root without invoking the Run 12 launcher.
3. Preflight the Opus researcher paths, Luna judge paths, fixed Gemma target,
   native AutoData plugin, broker, and storage boundaries.
4. Start one bounded AAR research session and author a method that passes the
   local method contract.
5. Review and approve the proposal, then deterministically bootstrap and
   register the proposal-bound AutoData workspace.
6. Complete workspace authoring, the configured meta-optimization iterations,
   and production generation through the native AutoData lifecycle.
7. Verify the production handoff, train one real Gemma PEFT adapter, complete
   one optimizer step, and validate that the resulting adapter is non-empty and
   loadable.
8. Emit one fail-closed machine-readable proof that joins every stage by chain,
   source revisions, configuration hash, model identity, handoff receipt, and
   training-smoke receipt, then stop without evaluation.

## Model and execution roles

Recorded: 2026-10-11 21:53 PT

```text
AAR control plane
├─ AAR researcher
│  └─ Claude Opus 4.8 (`claude-4-8-opus`)
│     Claude agent model `claude-opus-4-8`, maximum effort, through logical
│     deployment `meta-claude-cli-opus-4-8`
├─ Proposal and approval monitor
│  └─ Claude Opus 4.8 (`claude-4-8-opus`) through Meta Model API
│     Separate review role; no ephemeral endpoint is recorded here
├─ Training base and target model
│  └─ Gemma 4 31B IT
│     Fixed base: `/checkpoint/ram/shared/models/google/gemma-4-31B-it`
│     Target deployment: attempt-local and bound to that exact checkpoint
│     Candidate: fixed base + newly trained PEFT adapter
├─ Evaluator inference model
│  └─ Not used; evaluator disabled by the `training_smoke` boundary
└─ Evaluation judge
   └─ Not used in this canary; the requested future full-run judge is
      GPT-5.6 Luna (`gpt-5-6-luna`)

AutoData data plane
├─ AutoData researcher / generator-teacher
│  └─ Claude Opus 4.8 (`claude-4-8-opus`) through Meta Model API
│     Logical deployment: `meta-model-api-claude-4-8-opus`
├─ AutoData target probe
│  └─ The same iteration-bound Gemma 4 31B IT target
├─ AutoData row-quality and target-challenge judge
│  └─ GPT-5.6 Luna (`gpt-5-6-luna`) through Meta Model API
├─ AutoData plugin, lifecycle supervisor, broker, and approvals
│  └─ Trusted deterministic code from pinned source snapshots
└─ AutoData comparator
   └─ Deterministic code; not another model endpoint
```

The AAR monitor and AutoData row judge are independent calls. The evaluation
judge assignment is recorded for the broader experiment but is not invoked by
this gate. Any change to a used model, backend, deployment, checkpoint, or
adapter mode invalidates prior launch confirmation.

## Configuration and invariants

Recorded: 2026-10-11 23:20 PT

- Exactly one `alpha` chain and one bounded bootstrap-canary attempt are in
  scope. `target_pairs_per_chain: 1` satisfies the dedicated controller contract;
  this stop boundary intentionally produces no score/finding pair.
- The native AutoData contract uses the combined v2 recipe, 64 tuning tasks,
  32 validation tasks, 32 test tasks, 3–10 meta-optimization iterations, 1,250
  production tasks, and exactly 1,000 retained rows.
- The selected runtime profile uses per-chain task concurrency 8 and five
  transport attempts per model request. Target-feedback and judge-format repair
  remain separately bounded by the run configuration.
- Trial 12's campaign ceiling is `max_cost_usd: 62000`. This is a fail-closed
  worst-case reservation ceiling for the configured bounded lifecycle, not an
  expected-spend estimate.
- The native AutoData source is pinned to
  `f53bc2136905461ffdbba0a203a12e351e184aaf`, a focused child of confirmed
  commit `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`, and must execute from a clean,
  detached snapshot of the child revision.
- The canonical launcher must set `bootstrap-canary` mode and preserve
  `bootstrap_canary.stop_after: training_smoke`. The lifecycle must stop after
  the verified one-step training receipt.
- AutoData workspace authoring, approvals, meta-optimization, production, and
  export must use the pinned native plugin and its durable state database.
- The resolved configuration must state exact seeds, session ceilings,
  timeouts, concurrency, source-task counts, accepted-row requirement, training
  mode, training GPU allocation, and retention.
- Training must consume only the verified AutoData handoff and run on a real
  compatible GPU.
- Held-out examples, raw evaluator traces, credentials, and partial held-out
  scores remain evaluator-only.
- Durable outputs belong under the approved checkpoint root. Git retains only
  source, configuration, small held-out-safe proofs, and documentation.
- Evaluator allocation, score publication, `share_finding`, promotion, and a
  second research iteration are out of scope and must not start.

## Pass criteria

Recorded: 2026-10-11 21:53 PT

The canary passes only when one machine-readable proof verifies all of the
following against the same resolved attempt:

- endpoint, model-identity, native-plugin, broker, storage, and MCP/tool
  preflights passed;
- method authoring and contract validation completed, and the proposal monitor
  approved the exact frozen proposal;
- the proposal-bound AutoData workspace was registered and completed its
  grounding, baseline, resource, and approval gates;
- the configured meta-optimization and production executions completed with
  valid lineage, provider accounting, accepted-row count, and export receipt;
- a real GPU training job consumed that exact export and produced a non-empty,
  loadable PEFT adapter plus a source-bound one-step training receipt; and
- the retained completion proof records `stop_after: training_smoke` and
  confirms that no evaluator, score, finding, or promotion was created.

Scientific improvement and row-level judge acceptance rates are not canary
pass conditions. The exact accepted-row requirement is a data-validity and
training-input contract, not a scientific score threshold.

## Stop criteria

Recorded: 2026-10-11 21:53 PT

Do not launch while the runnable config, launcher, exact source pins, role
mapping, deployment/checkpoint identities, budgets, retained prerequisite
proof, or explicit user confirmation is missing. Once launched, stop and
retain evidence if any of the following occurs:

- source, plugin, config, model, checkpoint, target binding, adapter, or run-ID
  identity differs from the resolved attempt;
- credentials or evaluator-only information crosses into research-readable
  state;
- a lifecycle stage fails, times out, loses durable state, or advances without
  its required approval or receipt;
- AutoData is bypassed, emulated, or replaced by an unpinned implementation;
- training does not consume the verified production export or does not prove a
  real compatible GPU optimizer step;
- any evaluator, score publication, `share_finding`, promotion, second
  iteration, or additional chain starts.

Do not patch around a failed stage inside the live attempt. Preserve its state,
record the failure in a future append-only `PROGRESS.md`, and require a new
reviewed attempt for any changed contract.

## After a pass

Recorded: 2026-10-11 21:53 PT

Retain the resolved configuration, AAR and AutoData commits, model and
checkpoint identities, seeds, job IDs, receipts, timing, workspace and
execution IDs, strategy lineage, production handoff, training manifest,
adapter hashes, one-step GPU receipt, and final lifecycle proof.

A pass authorizes review of the evidence and design of the next bounded gate.
It does not authorize evaluation, promotion, more chains, more iterations,
higher concurrency, a full experiment, or a scientific claim.

## Directory layout

Recorded: 2026-10-11 22:13 PT

The current canary source package contains:

```text
canary/
├─ trial_3/                      # current config-driven recovery
│  ├─ submit_canary.sh           # only operator entrypoint for Trial 3
│  ├─ autodata_run.yaml          # Trial 3 machine-readable run contract
│  ├─ README.md                  # Trial 3 specification
│  └─ PROGRESS.md                # Trial 3 append-only history
├─ trial_2/
│  ├─ submit_canary.sh           # preserved Trial 2 entrypoint
│  ├─ autodata_run.yaml          # Trial 2 machine-readable run contract
│  ├─ README.md                  # Trial 2 specification
│  └─ PROGRESS.md                # Trial 2 append-only history
├─ launch/launch.sh              # shared, wrapper-selected fail-closed engine
├─ slurm/pipeline.sbatch         # shared attempt bootstrap and chain submission
├─ slurm/chain_controller.sbatch # shared training-smoke completion controller
├─ autodata_run.yaml             # preserved pre-trial-layout Trial 1 contract
├─ README.md                     # stable specification and operator guide
├─ PROGRESS.md                   # append-only PT operational history
└─ winnie_nots.md                # AutoData revision comparison and pin decision
```
