# Run 9: Native AutoData Plugin Integration Plan

## Goal

Run AutoData as part of the AAR research loop without recreating AutoData's
lifecycle inside AAR.

The final target is one sequential AAR chain whose researcher can:

1. load the original AutoData plugin and skill;
2. create and author a native workspace;
3. improve grounding and pipeline design between AAR iterations;
4. run bounded `meta_optimize`;
5. use the winning generation strategy for production-scale generation;
6. export independently accepted training rows;
7. train and evaluate the AAR candidate on those rows;
8. retain complete scientific, cost, and model provenance.

The run must require no human action after launch. Sensitive infrastructure,
budgets, and delegated approval authority are fixed before launch.

## Current status

### Completed

- AAR registers the original local AutoData plugin and the qualified
  `autodata:autodata` skill through the Claude Agent SDK.
- The AAR researcher uses the SDK `Bash` tool and the plugin's native CLI
  wrapper. There is no AAR AutoData MCP lifecycle.
- The canonical AutoData checkout is required to be on `main`, clean, and
  pinned to an exact SHA.
- AutoData's local Bubblewrap executor was fixed for shared hosts whose UID
  already owns more than 256 processes or threads.
- The native meta-optimization action-result contract was clarified in the
  original skill and engine instructions.
- The credential-free research-agent smoke test passed end to end:
  - the real AAR research session loaded `autodata:autodata`;
  - every AutoData operation used Bash and the packaged native wrapper;
  - no AutoData MCP tool was called;
  - native workspace authoring and approval actions completed;
  - the baseline improved from quality `0.5` to `1.0`;
  - the native execution exported 10 rows;
  - the independent verifier printed `AUTODATA_PLUGIN_AGENT_SMOKE_PASS`.
- The real recipe now has explicit grounding coverage, a structured mutable
  generation strategy, and native exclusion of judge-rejected rows.
- The AAR prompt now explains inner-loop versus outer-loop AutoData freedom and
  distinguishes the host researcher from the approval principal.
- Focused recipe, plugin, SDK, sandbox, canary, and smoke tests pass.

The successful smoke report is retained at:

```text
/home/winnieyangwn/aar-runs/run9-plugin-smoke-dev-20261007-2210/agent_smoke_report.json
```

### Not completed

- a real Kimi/Luna/SandoQ recipe execution;
- a real HPC run of the newly implemented delegated approval path;
- exact 64-tuning/32-validation execution configuration;
- campaign-wide model-call, token, and dollar enforcement;
- an HPC run of the new native digest-bound winner handoff and fixed-winner
  production mode;
- an accepted-row production target and verifier;
- training and evaluation that consume the native export;
- a complete two-iteration AAR chain.

Stage 1 therefore proves the plugin/CLI interface, not the real scientific or
production path.

## Design principles

### Keep AutoData as the lifecycle owner

AAR must not duplicate workspaces, actions, leases, execution state,
comparisons, candidate selection, or export.

```text
AAR research agent
  -> Claude Agent SDK
  -> Skill("autodata:autodata")
  -> SDK Bash tool
  -> ${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py
  -> native autodata.cli
  -> native workspace, actions, execution, comparison, and export
```

If lifecycle behavior is missing, prefer a small upstream AutoData operation or
contract change over an AAR-owned replacement state machine.

### Keep the integration thin

AAR should own only:

- selecting and verifying the pinned plugin;
- making the plugin visible read-only in the research environment;
- supplying writable retained run storage;
- supplying the trusted recipe seed and operator profile;
- invoking an independent approval monitor for native approval actions;
- verifying that the final export was consumed by training.

### Separate scientific freedom from infrastructure authority

The researcher may change scientific inputs within explicit boundaries. It may
not choose or alter credentials, hidden evaluation data, the independent judge
identity, campaign budgets, broker policy, container images, or the AutoData
revision.

### Fail closed

Missing configuration, evidence, provenance, usage, approval, digest, model
identity, or budget state must stop the run. The researcher's textual claim of
success is never sufficient.

## Terminology and authority

### Host agent

In AutoData terminology, the visible host agent performs semantic actions and
scoped edits. In this integration, the host agent is the AAR research agent.

It may:

- author grounding during `author_grounding`;
- author or stage a pipeline during `author_pipeline`;
- analyze visible tuning or production evidence;
- edit only paths returned in `allowed_paths`;
- create or fork a workspace between AAR iterations;
- relay a valid approval supplied by the trusted control process.

### Operator

The operator is not a new research agent. It is the human who configures the
campaign plus the trusted AAR launcher/parent that enforces that configuration.

Before launch, the operator fixes:

- the AutoData checkout and plugin SHA;
- the recipe-kernel digest;
- Kimi and Luna model routes and roles;
- SandoQ broker policy, tier, image, and image digest;
- secret-reference names and credential-delivery mechanism;
- concurrency and wall-time limits;
- model-call, token, and campaign-wide dollar caps;
- meta-optimization partition sizes;
- the accepted-row production target;
- the delegated approval policy and monitor identity.

The researcher must not change these settings.

### Approval principal

The generic AutoData skill says that approval actions require an explicit
"user" response. Here, "user" means the authorized approval principal, not the
AAR researcher itself.

For an unattended run, the operator delegates narrowly scoped approval
authority to a trusted AAR monitor. The monitor may approve only the exact
native action, workspace revision, and artifact digests it reviewed.

## Plugin source and pinning

The canonical checkout is:

```text
Devserver:
  /home/winnieyangwn/autodata_pipelines

HPC:
  /storage/home/winnieyangwn/autodata_pipelines
```

The plugin root is selected by the launcher:

```bash
export AAR_AUTODATA_PLUGIN_ROOT=/storage/home/winnieyangwn/autodata_pipelines/plugin/autodata
export AAR_AUTODATA_SHA=<full pinned SHA>
```

Before launch, verify:

- the checkout is on `main`;
- the checkout and plugin tree are clean;
- `HEAD` equals `AAR_AUTODATA_SHA`;
- the plugin path is exactly `<checkout>/plugin/autodata`;
- the manifest, skill, wrapper, bootstrap program, wheel, and wheel lock exist;
- the plugin tree contains no symlink escapes.

The Stage 1 smoke used:

```text
7d0c2e50e10f681355d2f936406402a110aed007
```

The launcher, not this document, is authoritative for future runs.

## Plugin, skill, Bash, and recipe

These have separate roles:

```text
AutoData plugin
  packages the skill, references, CLI wrapper, and locked wheel

autodata:autodata skill
  teaches the researcher the native workflow and safety rules

SDK Bash tool
  invokes the packaged native CLI wrapper

AutoData recipe
  defines the scientific workload run by AutoData
```

The recipe is not registered as an SDK tool or plugin. The launcher makes a
trusted recipe seed available read-only, and the researcher introduces files
only through the matching native workspace authoring actions.

## Minimum real recipe

### Strict technical minimum

`workspace create` technically needs only:

```text
autodata.workspace.json
```

Allowing an autonomous researcher to invent every later contract would be too
permissive for a credentialed training run.

### Minimum safe starting bundle

The trusted starting bundle is:

```text
recipe-root/
├── autodata.workspace.json
├── autodata.pipeline.json
├── framework.lock.json
├── objective.json
├── comparator.json
├── grounding/
│   ├── coverage.json
│   └── build_manifest.py
├── recipe/
│   ├── task.py
│   ├── check.py
│   ├── request.json
│   └── generation_strategy.json
└── schemas/
    └── task-result.schema.json
```

Responsibilities:

- `autodata.workspace.json` declares the goal, intended use, source policy,
  authoring budget, and default execution mode.
- `grounding/coverage.json` declares domains, behavior patterns, safety axes,
  and minimum coverage.
- `grounding/build_manifest.py` deterministically materializes tasks from the
  coverage contract, count, and seed.
- `autodata.pipeline.json` connects the task command, checks, schema,
  comparator, and mutation boundary.
- `recipe/task.py` calls Kimi to generate and GPT-5.6 Luna to judge, then emits
  one native typed task result with provider usage.
- `recipe/check.py` validates request, coverage, and mutable strategy without
  contacting a model.
- `recipe/request.json` binds the approved scientific request.
- `recipe/generation_strategy.json` is the structured inner-loop research
  surface.
- `schemas/task-result.schema.json` validates results, metrics, provenance, and
  usage.
- `objective.json` and `comparator.json` define success and acceptance floors.
- `framework.lock.json` records exact framework/plugin compatibility and must
  be strengthened to an exact production pin before launch.

### How files enter the workspace

The draft must not be pre-populated with a finished recipe in a way that
bypasses native actions.

```text
workspace create
  -> only the workspace brief is present

author_grounding
  -> stage coverage, builder, sources, and materialized manifest

approve_grounding
  -> trusted monitor reviews native grounding-review evidence

author_pipeline
  -> stage pipeline kernel and generation strategy

native checks and dry run
  -> AutoData produces baseline-review evidence

approve_baseline
  -> trusted monitor reviews exact runnable revision

freeze
  -> immutable snapshot and native execution
```

## Research freedom and mutation boundaries

### Inner AutoData loop

Within one frozen workspace and `meta_optimize` execution:

- grounding is fixed;
- tuning and validation task IDs are fixed;
- objective, comparator, schemas, judge, task code, and resource settings are
  fixed;
- the researcher may edit only:

```json
{
  "mutable_paths": ["recipe/generation_strategy.json"]
}
```

The structured strategy permits bounded changes to the generation system
prompt, scenario framing, strategy name, and sampling temperature. It does not
permit changing models, credentials, judge rules, task code, or cost limits.

### Outer AAR loop

Between AAR iterations, the researcher may use visible findings to revise:

- domain and behavioral coverage;
- scenario difficulty and balance;
- synthetic task construction;
- generation strategy;
- proposed protected pipeline design when scientifically justified.

It must create a new workspace or use:

```text
autodata workspace fork <workspace-id> --root <new-root> --edit grounding|pipeline|both
```

The revised workspace receives fresh native validation and delegated approval.
The researcher must never edit a frozen workspace or use hidden validation or
evaluator details to redesign grounding.

### Prompt responsibility

The generic skill covers the native fork operation and immutable-workspace
rule, but it does not know AAR's outer campaign policy. The AAR prompt must
therefore state the inner/outer distinction explicitly. It must also state that
the AAR researcher is the host agent, not the approval principal.

## Delegated AutoData approvals

### Do not expose AutoData to the monitor

The monitor does not need the plugin, CLI, Bash, credentials, or write access
to a workspace. It receives one immutable read-only review package.

AutoData already supplies most of that package:

- `approve_grounding` attaches `grounding-review.json` with coverage counts,
  provenance, and representative samples;
- `approve_baseline` attaches `baseline-review.json` with dry-run results,
  execution defaults, and mutation boundaries;
- native state records the action ID, workspace ID, revision, and artifact
  digests.

The trusted bridge should add the proposal snapshot, trusted recipe-kernel
digest, changed-path list, and operator-profile digest. The monitor must review
the native artifacts, not a researcher-written summary.

### One narrow trusted operation

Add one AAR approval operation:

```text
review_autodata_action(action_id)
```

This is not an AutoData lifecycle MCP server. It handles only native approval
actions and leaves all lifecycle transitions in AutoData.

The trusted operation:

1. resolves the action from the current run's native state;
2. accepts only `approve_grounding`, `approve_baseline`, or
   `approve_resources`;
3. loads attached artifacts from the content-addressed store;
4. verifies action, revision, artifact, proposal, recipe, and operator digests;
5. runs deterministic policy checks;
6. invokes the existing AAR monitor infrastructure for semantic review when
   required;
7. completes the exact native action with `approve` or `revise` and retained
   feedback;
8. records monitor model, policy version, evidence digests, and decision.

The researcher never constructs the approval result.

### Deterministic checks versus model review

Code, not an LLM prompt, must verify:

- action kind and scope;
- artifact and workspace-revision digests;
- proposal and recipe binding;
- prohibited source declarations;
- protected-file hashes and mutation boundaries;
- successful native checks and dry run;
- executor, image, model route, concurrency, and budget policy;
- absence of persisted credentials;
- non-replay across action IDs or revisions.

The monitor model reviews semantic questions:

- whether grounding covers the intended behavior rather than trivial proxies;
- whether examples and facets expose meaningful gaps or unsafe sources;
- whether the baseline implements the disclosed scientific method;
- whether generator/judge separation and acceptance logic are credible;
- whether limitations require revision before execution.

`approve_resources` should normally be deterministic: it compares the request
against the operator profile rather than asking an LLM to choose infrastructure.

### AutoData-specific monitor prompt

Add a distinct prompt and function to `aar/research_loop/monitor.py`, reusing
the existing model invocation, retries, strict JSON parsing, failure handling,
and audit metadata.

The prompt must:

- identify the approval action type;
- describe the scientific goal and source restrictions;
- provide only the exact native review package;
- forbid reliance on researcher claims not present in evidence;
- fail closed on missing evidence;
- distinguish a request for revision from approval;
- return strict structured JSON with decision and concise feedback.

Do not reuse `submit_idea_proposal` directly. Proposal approval evaluates the
method paper and `run.py`; native workspace approval evaluates materialized
grounding, runnable pipeline, and dry-run evidence.

### Enforce approval beyond prompting

Direct CLI access currently lets a researcher attempt to submit
`user_acknowledged: true`. Prompting alone cannot make delegated approval
tamper-resistant.

Add the smallest upstream AutoData contract extension that supports either:

- the existing human acknowledgement; or
- a delegated approval attestation bound to action ID, workspace revision,
  reviewed artifact digests, decision, actor, and policy version.

In delegated mode, AutoData must reject unsigned, altered, stale, or replayed
approvals. The signing authority remains outside the researcher sandbox; only
verification material is available to AutoData. Preserve the human approval
path for ordinary interactive use.

Required tests:

- valid grounding approval advances;
- valid baseline approval freezes;
- monitor revision returns to the correct authoring phase;
- researcher-authored acknowledgement is rejected in delegated mode;
- artifact tampering is rejected;
- revision and action replay are rejected;
- missing monitor evidence fails closed;
- deterministic resource over-ask is rejected.

## Credentials and controlled delegation

Recipe files contain only secret-reference names, never values.

The preferred thin architecture is:

```text
AAR researcher and native CLI
  -> attempt-scoped, policy-limited AutoData broker capability
  -> trusted AutoData broker daemon
  -> SandoQ Firecracker and model-backed workload
```

The broker daemon, not the researcher, holds the real Firecracker and Model API
credentials. The capability visible to the researcher must be limited to the
pinned image, executor tier, model-backed task shape, concurrency, time, and
campaign budget. Reading that scoped capability must not grant general access
to the underlying credentials or arbitrary SandoQ jobs.

Inside the Firecracker workload:

- Kimi generates candidate training examples;
- GPT-5.6 Luna independently judges them;
- the broker injects required model credentials;
- the recipe records provider request IDs, model identities, token usage, and
  derived cost without recording secret values.

## Budget and scale policy

The operator profile should initially set:

```text
max_concurrency: 4
meta tuning tasks: 64
meta hidden validation tasks: 32
```

`max_concurrency` controls how many task attempts run simultaneously. Four is a
conservative starting value and may be increased after measuring broker,
endpoint, and Firecracker capacity.

The accepted production-row target is separate from tuning batch size. The
initial full target should be pinned before launch; 1,000 accepted rows is the
current planning value, not 16 or 64.

The campaign requires one cap shared across all outer iterations and parallel
chains, not a new dollar allowance for every execution. Do not hard-code a
`$0.05` per-task allowance. Derive conservative reservation and actual cost
from operator-pinned token ceilings and rates.

Native AutoData currently enforces iterations, task attempts, and wall time,
but not a campaign-wide model-call, token, or dollar ledger. Add enforcement at
the trusted broker/control boundary before production. Usage recorded only
after a call is not sufficient by itself.

## Meta-optimization and production semantics

### Exact meta-optimization partition

Do not rely on AutoData's default 80/20 split. Materialize at least 96 tasks and
create an explicit native execution containing exactly:

```text
64 tuning_task_ids
32 validation_task_ids
```

The two sets must be disjoint and fixed before execution. Validation payloads
and trajectories remain hidden from the researcher.

### Accepted rows

Judge-rejected candidates now produce no `generated_items`; usage remains in
the task result for audit. Consequently, native dataset export includes only
accepted training examples.

A source-task count does not guarantee the same accepted-row count. Production
must use bounded replacement/retry behavior or controlled over-generation and
must finish only when the independent verifier confirms the configured
accepted-row target.

### Winner-to-production gap

The current native interface does not provide a clean public operation for
exporting or promoting the winning candidate pipeline into a new execution.
Also, current `production` mode performs an additional generate/audit/mutate
loop over the complete corpus; it is not simply a fixed high-volume rerun.

Do not depend on internal candidate-directory paths. Before claiming literal
meta-optimization followed by production, choose the smallest native AutoData
extension, for example:

- export the winning pipeline as an immutable snapshot and create production
  from it; and
- explicitly support fixed-winner generation, or document and budget the
  additional production optimization iteration.

Until that native contract exists, a `meta_optimize` final full-corpus rerun can
exercise the winning strategy on a larger source corpus, but it must not be
reported as a separate native production execution.

## Sandbox and retained storage

The launcher must expose only the verified plugin directory and trusted recipe
seed read-only. Do not expose the whole home directory or credential-bearing
checkout.

The plugin uses a writable run-local bootstrap cache:

```bash
export AUTODATA_CACHE_DIR="$AAR_RUNTIME_ROOT/autodata/plugin-cache"
```

Native state and retained artifacts use stable paths below the run storage
root:

```text
$TEAM_DIR/autodata/<run_id>/
├── input/
├── draft/
├── native/
│   ├── state.db
│   ├── artifacts/
│   └── workspaces/
├── approvals/
├── export/
└── verification/
```

Do not write retained results to `/checkpoint/ram`, the plugin checkout,
source-control directories, or an untracked temporary directory.

The Stage 1 smoke used Meta's native Claude sandbox directly because nesting it
inside the AAR Bubblewrap wrapper failed while the inner launcher constructed
its user namespace. A real production launch must validate the final HPC
sandbox and credential boundary separately; Stage 1 did not prove that piece.

## Implementation and validation stages

### Stage 1 — native plugin smoke: complete

Purpose:

- prove SDK plugin discovery and skill loading;
- prove Bash/native CLI invocation;
- prove offline wheel bootstrap;
- prove native workspace, actions, execution, and export;
- prove that no AutoData MCP lifecycle is required.

This stage used the upstream deterministic toy recipe and no network,
credentials, Kimi, Luna, SandoQ, training, or evaluation.

### Stage 2 — real recipe contract and local tests: in progress

Complete and verify:

- explicit coverage configuration and deterministic manifest generation;
- structured generation strategy as the sole inner-loop mutable path;
- protected task code, judge, objective, comparator, schemas, and grounding;
- rejected-row exclusion;
- exact framework/plugin lock;
- native pipeline validation;
- unit tests for malformed strategies, prohibited sources, provenance, usage,
  and accepted-row semantics;
- AAR prompt coverage for outer-loop workspace evolution.

Current focused validation passes, but SandoQ configuration and exact execution
files remain incomplete.

### Stage 3 — delegated approval and credentialed canaries

Implement and test:

- `review_autodata_action(action_id)`;
- AutoData-specific grounding and baseline monitor prompts;
- deterministic resource approval;
- delegated approval attestation and replay protection;
- attempt-scoped broker capability;
- one real Kimi generation plus Luna judgment in Firecracker;
- a small native real-recipe workspace dry run;
- a small explicit meta-optimization canary.

Use small task counts for infrastructure diagnosis where the recipe contract
permits them. Do not start the full production target until these checks pass.

### Stage 4 — one complete outer AAR iteration

Run:

```text
AAR proposal approval
  -> native workspace authoring
  -> delegated grounding approval
  -> native checks and real model-backed dry run
  -> delegated baseline approval
  -> exact 64/32 meta_optimize
  -> winning pipeline selection
  -> native winner handoff
  -> production accepted-row target
  -> export and independent verification
  -> training consumes exact export digest
  -> candidate evaluation
  -> retained AAR finding
```

Pass only if retained evidence proves every transition and the training receipt
binds the model to the verified native dataset digest.

### Stage 5 — two-iteration AAR chain

Run one sequential chain for two outer iterations. The second researcher
session receives only authorized visible findings and prior AutoData provenance.
It may fork or create a workspace to improve grounding or pipeline design,
obtain fresh approvals, rerun AutoData, train, and evaluate.

Pass only if both iterations have distinct proposal/workspace/execution/model
identities and each trained model is bound to its own verified AutoData export.

## Stage 4 acceptance criteria

The first complete iteration succeeds only when:

1. the exact AAR and AutoData Git SHAs are retained;
2. the researcher loaded the pinned original plugin and skill;
3. no AAR AutoData lifecycle MCP call occurred;
4. native workspace actions and leases were used;
5. delegated approvals are exact, audited, and non-replayable;
6. the researcher could not access underlying Firecracker or model secrets;
7. meta-optimization used exactly 64 tuning and 32 hidden validation IDs;
8. Kimi and GPT-5.6 Luna roles and provider usage are recorded;
9. campaign-wide call, token, time, and dollar caps were enforced;
10. rejected examples are absent from exported training items;
11. the configured accepted-row target was verified;
12. the winning pipeline's production provenance is retained;
13. training loaded the verified native export rather than an alternate file;
14. evaluation produced a valid bound score record;
15. all artifacts were retained in approved storage.

## Immediate next actions

1. Synchronize AAR and the pinned AutoData commit to HPC.
2. Start the native broker with isolated Firecracker and Luna credential files.
3. Run the model-backed Firecracker canary.
4. Run `scripts/autodata_native_real_e2e.py` with four tasks, a 2/2 explicit
   meta partition, digest-bound winner export, fixed-winner production, at
   least one accepted row, and a verified training-consumption receipt.
5. Inspect the retained native state, signed approval audits, provider usage,
   dataset digest, and report before increasing scale.
6. Add the campaign-wide broker ledger and run a complete outer AAR training /
   evaluation iteration before claiming Stage 4.

## Explicit non-goals

- Reintroducing the seven AutoData MCP lifecycle tools.
- Recreating AutoData state transitions in AAR.
- Letting the researcher approve its own grounding, baseline, or resources.
- Giving the monitor general AutoData, Bash, workspace-write, or credential
  access.
- Letting an LLM choose infrastructure or override deterministic budget policy.
- Treating task count as accepted-row count.
- Claiming Stage 1 proves production, credential isolation, training, or
  scientific improvement.
