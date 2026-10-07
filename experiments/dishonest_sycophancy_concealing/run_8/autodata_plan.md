# Run 8 Autodata integration plan

## Goal

Run 8 will use Autodata for synthetic training-data generation inside the AAR
research loop. AAR remains the controller: its research agent chooses a method,
defines the generation objective, obtains integrity-monitor approval, invokes
Autodata, trains on the verified output, evaluates the resulting model, and uses
that score in the next AAR iteration.

Autodata is the execution and provenance framework. It must not choose the
research domain or substitute an unrelated recipe.

## Correction to the earlier approach

The earlier attempt selected the historical `legal-os/paper-baseline` branch
and prepared legal-document tasks through the old ProfAI SandoQ fleet/director
workflow. That is not an AAR data-generation path:

- the legal recipe emits legal question/rubric records, not AAR training rows;
- it does not bind generated data to an approved AAR proposal and run ID;
- it uses the old `sandoq_fleet` path rather than Autodata `main`'s native
  Firecracker broker and execution engine;
- completing it would not prove that the AAR agent called and consumed
  Autodata during an iteration.

No legal batch was submitted and no legal data was generated. The legal branch
and the temporary Kimi-routing branch must not be merged into the canonical
Autodata checkout or used for Run 8.

## Pinned framework state

The canonical Autodata checkout is `main` in both environments:

- devserver: `/home/winnieyangwn/autodata_pipelines`;
- FAIR HPC: `/storage/home/winnieyangwn/autodata_pipelines`;
- verified commit in both checkouts:
  `9e623eb25bab4c4ba50642f72ca338f887772e27`;
- both worktrees were clean when this plan was written.

The local `origin/main` ref points to this commit. A live GitHub refresh was
blocked by the development environment's destination filter, so the upstream
tip could not be independently refreshed. Before a production launch, either
restore approved GitHub access and refresh `main`, or explicitly retain this
commit as the reviewed framework pin.

## Ownership boundary

AAR owns:

- the research question and safety axis;
- the method package and literal `AUTODATA_SPEC`;
- proposal review and the immutable AAR `run_id`;
- the campaign-wide authorized model-spend cap and shared spend ledger;
- the AAR-specific generation recipe and row schema;
- training, model submission, evaluation, and iteration selection.

Autodata owns:

- durable execution state and idempotency;
- frozen pipeline snapshots and task fan-out;
- task-attempt budgets, retries, and concurrency;
- native SandoQ/Firecracker execution;
- generation artifacts, audit evidence, and dataset assembly.

The operator-owned adapter owns:

- the pinned Autodata framework, locked resource profile, and authoring template;
- broker, model-gateway, and provider credentials;
- mapping approved AAR runs to Autodata executions;
- model aliases and deployment routing;
- reserving and charging Autodata model spend against the AAR campaign-wide cap;
- conversion of the final Autodata dataset into the verified AAR artifact
  contract.

The AAR agent must never receive a pipeline path, Git ref, endpoint URL,
deployment ID, or credential as a tool parameter.

All new Run 8 outputs are retained below
`/storage/home/$USER/aar-runs/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run8_attempts/`.
The launcher rejects any output root outside the submitting user's
`/storage/home/$USER/aar-runs` tree, rejects symlinked artifact parents, and
specifically refuses `/checkpoint/ram`. Shared checkpoint paths may be read as
immutable inputs, but the launcher places the literature cache in enforced
read-only mode and writes no Run 8 attempt artifact there. Host-side temporary
files and agent job-ID bookkeeping also remain inside the retained attempt.

## Intended control flow

```text
AAR research agent
  |
  |  writes method package + literal AUTODATA_SPEC
  v
submit_idea_proposal / integrity monitor
  |
  |  approves and freezes the exact method-code hash; returns run_id
  v
autodata_generate(idea_name, run_id)
  |
  v
AAR-Autodata adapter service
  |
  |  validates run binding, framework pin, recipe pin, spec, and budget
  v
Autodata main ExecutionEngine (production mode)
  |
  v
SandoQFirecrackerExecutor -> autodata-broker -> SandoQ -> declared models
  |
  v
Autodata dataset + provenance and audit artifacts
  |
  v
autodata_status -> autodata_fetch
  |
  v
$TEAM_DIR/autodata/<run_id>/
  |
  v
AAR training job -> model evaluation -> next AAR iteration
```

## Current integration status

The AAR-facing adapter is implemented. The research agent has seven narrow MCP
tools:

- `autodata_generate`;
- `autodata_step`;
- `autodata_status`;
- `autodata_action_begin`;
- `autodata_action_complete`;
- `autodata_action_fail`;
- `autodata_fetch`.

The durable adapter validates the approved AAR run binding, literal
`AUTODATA_SPEC`, framework pin, resource profile, retained-row requirement, and
shared campaign budget before driving the canonical Autodata lifecycle. It
also verifies manifests and rows before publishing immutable AAR artifacts and
requires a dataset-consumption receipt before training can count as complete.

One bounded `AutonomousAgentLoop` session has used this surface without a human
pause. It initiated workspace creation, completed native `meta_optimize`, ran
production from the winning frozen pipeline, fetched 10 deterministic rows,
and consumed their verified digest. This proves the AAR-to-Autodata control
flow, but the deterministic backend is test infrastructure rather than a
scientific data generator.

The production backend is now implemented: an AAR-owned live recipe, native
SandoQ/Firecracker wiring, the qualified `winnieyangwn-kimi26` deployment for
served model `Kimi-K2.6`, the `gpt-5-6-luna` judge, complete usage accounting,
and a two-iteration launcher. The live backend remains fail closed. The one
external launch prerequisite is the restricted per-environment Firecracker
Runner bearer, installed as an owner-only file; it is not a model credential
and cannot be minted from the AAR checkout. The lower-level broker's
`/v1/jobs` endpoint accepts `autodata.broker-job/v1`, not the AAR payload, so
the MCP client continues to call the authenticated adapter.

## Implementation work

### 1. Define the approved AAR generation specification

Keep exactly one literal `AUTODATA_SPEC` in each method package. Define and
validate a versioned schema containing only scientific choices available to the
research agent, including:

- the locked resource-profile identifier;
- safety axis and intended training mechanism;
- output view such as SFT or preference pairs;
- requested seed and the scientific goal for the Autodata workspace.

The dictionary must continue to reject Git refs, commits, SHAs, paths, URLs,
deployment IDs, and credentials. The adapter must cross-check the declared axis
against the approved AAR run rather than trusting a free-form value.

Prompts, grounding sources, model roles, filters, schemas, comparators, and
budgets are native Autodata workspace/pipeline concerns. They must be authored
through Autodata actions and approved by the delegated policy; they are not
smuggled into an execution through `AUTODATA_SPEC`.

### 1a. Lock the Run 8 resource and budget profile before launch

Run 8 uses an operator-configured immutable resource profile. The initial model
roles are:

- generator: `Kimi-K2.6`;
- judge: `gpt-5.6-luna`.

The operator sets one campaign-wide model-spend authorization, `max_cost_usd`,
before any AAR chains start. It applies across every parallel chain and every
iteration in the campaign and does not reset when a new chain or
proposal-issued `run_id` is created. The adapter reserves an Autodata allocation
for each iteration from the same campaign ledger and charges every Kimi
generator and GPT judge call to it. Unused reservation returns to the campaign
balance. Autodata must refuse a new model call when the remaining campaign
authorization cannot cover it. Existing AAR agent and evaluator spend controls
remain defense-in-depth limits, but they must not become independent pools that
permit total campaign spend to exceed `max_cost_usd`.

The ledger must therefore have a stable campaign `budget_scope_id` shared by
all parallel chains, in addition to chain and proposal-issued per-iteration
identifiers. Every charge is attributed to the campaign, chain, and iteration.
A new chain or `run_id` provides provenance and isolation; it does not create a
new pool of money. Run 8 does not require a separate user-configured per-chain
or per-iteration dollar cap. If either is added later, it is an additional
ceiling beneath `max_cost_usd`, never a reset or multiplier of that cap.

The cost cap is the primary user-facing budget control. The operator should not
have to hand-tune aggregate call, input-token, output-token, and task-attempt
limits for every run. The adapter derives schema-required task-attempt limits
from the frozen source corpus and iteration plan. It may derive conservative
aggregate call/token ceilings as fallback protection when a provider cannot
report reliable cost promptly. A per-call output-token ceiling remains a hard
safety limit so one malformed request cannot consume the entire budget.

The profile also fixes the model routes, secret references, SandoQ executor,
digest-pinned image, network destinations, concurrency, timeouts, and per-call
limits. The AAR agent sees the profile identifier, model-role disclosure,
remaining safe budget information, and the required output count, but not
deployment IDs or credential values. It cannot replace the judge or increase a
limit.

For Run 8:

- `max_concurrency: 4` means at most four Autodata source-task attempts execute
  simultaneously during one fan-out phase. It is not four AAR iterations and
  it is not a training or meta-optimization batch size. Because one task may
  make generator and judge requests, the gateway must also enforce the same
  profile's provider-side concurrency constraints. Four is the conservative
  canary and smoke-test setting, not a permanent production limit. It may be
  increased in a later approved resource-profile revision to accelerate data
  generation after measurements show that the SandoQ capacity, model-provider
  rate limits, failure rate, and shared budget ledger remain healthy. The new
  value is frozen before an execution starts; the AAR agent cannot raise it
  during a run. Increasing concurrency improves wall-clock throughput but does
  not increase the retained-row target or authorize additional spend.
- `required_retained_rows` is an execution-specific AAR output requirement, not
  an Autodata budget field. A retained row is a final training example that
  passed task execution, schema validation, policy checks, deduplication, and
  the configured judge/filter. Rejected or malformed candidates do not count.
  It is not the batch size used during `meta_optimize`; Run 8 uses production
  mode, and the training recipe chooses its own minibatch size separately.
- Earlier two-row and 16-row designs were test-only proposals and are not
  launch gates. The mandatory real-provider canary makes exactly one Kimi
  generation call and one Luna judgment call without publishing training rows.
  Each production iteration requires 64 accepted SFT rows. That target is
  frozen before launch and cannot be reduced by the agent.
- `max_wall_seconds: 10800` remains an independent operational stop for a
  stalled execution. Money alone cannot bound hangs.

Run 8 freezes a $100 campaign authorization across both sequential iterations,
64 accepted SFT rows per iteration, and concurrency 4. Calls, tokens,
estimated and provider-reported cost, model role, and remaining authorization
must be recorded for the campaign and attributed to each chain and AAR `run_id`.
If the cap is exhausted before an iteration reaches its approved retained-row
target, that iteration fails closed, training does not start, and later
iterations cannot obtain a new reservation.

`gpt-5.6-luna` availability and a real judged response must be verified through
the operator-configured route during launch preflight. The manifest records the
exact served identity and role, not only the friendly alias.

### 2. Build an AAR-owned Autodata recipe

Place the domain-specific recipe in the AAR repository, separate from the
Autodata framework. A proposed location is:

```text
aar/autodata_recipes/dishonest_sycophancy_concealing/
```

The recipe must include:

- `autodata.pipeline/v1` and `autodata.execution/v1` manifests;
- grounding built only from approved non-benchmark sources;
- a task command that invokes the declared generator model;
- typed `autodata.task-result/v1` output;
- AAR row schemas for each supported training view;
- deterministic checks and a comparator;
- exact framework and runtime pins;
- an OCI image pinned by digest for the SandoQ Firecracker executor.

Use one stable task/seed identity per generation unit so retries and final
full-corpus reruns are attributable. The generator must propagate the Autodata
task seed to model sampling where supported.

The recipe must reject all evaluation sources named by the AAR prompt, their
mirrors, and held-out data. It should target the underlying behavior without
mimicking benchmark prompt or answer formats.

### 3. Approve and freeze autonomously within the locked profile

Use the Autodata workspace workflow to co-author grounding and the baseline
pipeline. The AAR research agent performs authoring, but it does not approve its
own work. Replace the two human approval results with delegated attestations
that require both:

1. deterministic policy checks for sources, digests, schemas, paths, resource
   limits, and benchmark exclusions;
2. approval from the separate AAR integrity monitor for grounding quality,
   prompt/procedure disclosure, benchmark mimicry, and sampled outputs.

The attestation is bound to the AAR run ID, method-code hash, workspace revision,
grounding digest, pipeline digest, resource-profile digest, and approval-policy
digest. Autodata verifies the attestation before freezing the snapshot.

Missing credentials or a request outside the resource profile fails closed; it
does not emit a human resource-approval request during the unattended run.

### 4. Implement the AAR-Autodata adapter service

The adapter should live with AAR integration infrastructure and import the
pinned Autodata `main` package. It must expose the existing AAR client contract
on a service address distinct from the lower-level broker:

- `POST /v1/jobs` accepts `{run_id, pipeline_sha, spec}` and returns a durable
  job identity;
- `GET /v1/runs/<run_id>` returns safe state, progress, counts, and provenance;
- `GET /v1/runs/<run_id>/artifacts` returns final rows and the AAR manifest only
  after successful completion.

On submission it must:

1. verify the exact proposal-issued AAR `run_id` and approved method-code hash;
2. require the configured Autodata framework commit;
3. require the configured resource-profile and authoring-template digests;
4. validate and normalize `AUTODATA_SPEC`;
5. create an idempotent Autodata workspace and persist its AAR binding;
6. expose native workspace and execution steps to the AAR host agent;
7. verify delegated approval attestations and create the frozen snapshot;
8. reserve the iteration's Autodata allocation from the shared chain ledger;
9. derive native task-attempt and operational ceilings, then create and operate
   a production execution with a schema-valid positive budget;
10. charge every generator and judge request to the shared ledger, refusing
    requests that cannot fit in the remaining authorization;
11. persist the AAR run-to-workspace/execution mapping in durable state.

The AAR integration must add MCP operations for `autodata_step`,
`autodata_action_begin`, `autodata_action_complete`, and
`autodata_action_fail`. `autodata_status` remains read-only. Semantic authoring,
analysis, and mutation actions are handled by the visible AAR host agent through
this native protocol rather than silently by a background service.

Autodata currently requires `max_iterations >= 1`; Run 8 must use a valid
positive native budget and complete the corresponding production action loop.
Its finalization reruns the complete source corpus, so the adapter must include
baseline, comparisons, retries, and finalization when deriving task-attempt and
cost forecasts. The forecast does not authorize extra spend beyond the shared
AAR cap.

### 5. Use Autodata's native SandoQ backend

Configure `SandoQFirecrackerExecutor` and `autodata-broker` from Autodata
`main`. Do not use the historical `sandoq_fleet`, legal ProfAI director, or
legal task workspace.

The adapter resolves the profile's `Kimi-K2.6` generator and `gpt-5.6-luna`
judge aliases to operator-owned routing. Strong-model generation and judging
are permitted, but the manifest must record the actual model identities, roles,
procedure, sampling, and selection policy. Credentials and routes remain
outside the AAR agent and generated artifacts.

### 6. Export and verify the AAR dataset

The adapter must preserve the original `autodata.dataset/v1` artifact and emit
an AAR-facing `aar.autodata.dataset/v1` manifest with at least:

- AAR `run_id`, idea name, and approved method-code hash;
- Autodata framework commit;
- frozen recipe and pipeline digests;
- Autodata study and execution IDs;
- source revisions and content hashes;
- generator, critic, and judge model identities and roles;
- prompt/procedure hashes, seeds, and sampling settings;
- generated, rejected, and retained counts with rejection reasons;
- training-view schema and row count;
- final dataset SHA-256.

`autodata_fetch` must continue to write immutable artifacts under
`$TEAM_DIR/autodata/<run_id>/`. Extend
`aar.infrastructure.autodata.load_autodata_dataset` to verify the new fields and
row schema before returning data.

Generation must fail rather than silently returning fewer than the execution's
approved `required_retained_rows`. This count describes accepted output rows;
it does not configure the training minibatch size or an Autodata
`meta_optimize` split. Production must not inherit the 16-row smoke setting.

### 7. Make Autodata use enforceable in the AAR loop

Add an `AAR_AUTODATA_REQUIRED=1` launch mode for Run 8. In this mode:

- proposal approval requires one valid literal `AUTODATA_SPEC`;
- training submission is blocked until a verified manifest exists for the
  proposal-issued `run_id`;
- the method must load data through `load_autodata_dataset`;
- the training result or harness metadata must record the consumed dataset
  digest;
- a missing, failed, mismatched, or unconsumed dataset ends the iteration
  without training or evaluation.

This should be enforced in the launch/training wrapper, not only described in
the research-agent prompt. Keep the prompt instructions as guidance, but treat
runtime checks as authoritative.

### 8. Preserve evaluation isolation

The adapter and recipe must not receive benchmark rows, held-out items, private
scores, or evaluation credentials. The generation service receives only the
approved method specification, allowlisted generation sources, and safe AAR run
metadata.

Research-readable status may expose task counts, rejection categories, timing,
cost, remaining authorized spend, and provenance. It must not expose
evaluator-private information.

## Validation sequence

Do not launch a multi-iteration production run until every preceding stage
passes.

1. **Unit contract tests**
   - schema and forbidden-field validation;
   - method-code and `run_id` binding;
   - idempotent duplicate submission;
   - framework/recipe digest checks;
   - shared-ledger reservation, idempotent charging, cap exhaustion, and cost
     reconciliation;
   - derived task-attempt ceiling and per-call output-token enforcement;
   - concurrency enforcement;
   - row-count, row-schema, and dataset-digest verification;
   - fail-closed behavior for unexpected host actions and generation failures.

2. **Local Autodata engine test**
   - run the AAR recipe with a deterministic fake provider through the native
     engine;
   - verify the final Autodata dataset and AAR export without SandoQ.

3. **Real SandoQ canaries**
   - use the native Firecracker broker for a lease/image canary;
   - run one qualified Kimi generation and one `gpt-5.6-luna` judgment inside
     the Firecracker workload;
   - verify model provenance, task-result schema, safe usage, and cleanup.

4. **One complete 64-row AAR iteration**
   - proposal -> Autodata -> verified fetch -> training -> model evaluation ->
     finding publication;
   - confirm that training metadata names the consumed dataset digest.

5. **Production readiness test**
   - complete the second sequential 64-row AAR iteration with a distinct run ID;
   - verify no cross-run artifact reuse, duplicate submission, orphaned jobs, or
     credential leakage;
   - measure generation yield, latency, model cost, training time, and cleanup.

## Launch gates

Run 8 is launchable only when all of the following are true:

- canonical Autodata framework checkout is clean on the reviewed `main` commit;
- the AAR-owned workspace template, recipe, and delegated approval policy are
  frozen; each iteration creates its own workspace snapshot and approval
  evidence after proposal approval;
- adapter service and native broker pass readiness checks;
- one campaign-wide model-spend cap is authorized, each Autodata allocation is bound
  to it, and Kimi/Luna calls cannot bypass the shared ledger;
- the locked `Kimi-K2.6` generator and `gpt-5.6-luna` judge routes pass real
  completions;
- `AAR_AUTODATA_REQUIRED=1` fail-closed checks pass;
- the native lease/image canary and the one-generation/one-judgment Kimi/Luna
  canary pass inside SandoQ Firecracker before the adapter becomes available;
- the 64-row production target is affordable under the conservative
  worst-case reservation and frozen independently of the canary;
- the first full AAR iteration must consume the fetched digest and produce a
  score/result pair before the second iteration can satisfy completion;
- retained outputs include framework, recipe, source, model, seed, prompt, and
  dataset provenance.

## Cleanup before implementation

The incorrect exploratory infrastructure is outside this plan. At the time of
the correction, the following jobs were still live and should be stopped with
explicit operator approval before Run 8 implementation or launch:

- old SandoQ fleet job `1743168`;
- Qwen endpoint worker job `1743169` and its `shared-qwen3.5-4b` deployment.

Stopping those jobs is cleanup only; it does not constitute progress toward a
Run 8 launch.

## Completion definition

Run 8 is successful only when both sequential AAR research iterations call
Autodata after proposal approval, Autodata `main` generates and verifies each
method's requested AAR training data through its native backend, each training
job demonstrably consumes its exact dataset, and each resulting model receives
the configured real vLLM evaluation and produces a score/result pair. This Run
8 launcher uses the documented same-user functional evaluator, so its scores
are operational evidence rather than kernel-isolated scientific evidence. A
standalone Autodata generation, a legal-domain generation, or a deterministic
contract smoke does not satisfy this definition.
