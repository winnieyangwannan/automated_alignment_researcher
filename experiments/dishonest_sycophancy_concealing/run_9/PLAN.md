# Run 9: five-iteration AAR with native AutoData

## Objective

Run one sequential AAR research chain that produces five successfully trained
and evaluated Gemma candidates. Every outer iteration may use native AutoData
as a scientific data-generation and pipeline-optimization system before
training. The run must be unattended after launch, retain complete provenance,
and fail closed rather than weaken quality, budget, credential, or evaluation
boundaries.

This is the first full outer-loop run after the small real native lifecycle
test. The retained canary proved:

- real Kimi generation and GPT-5.6 Luna judgment in SandoQ Firecracker;
- delegated grounding and baseline approval;
- native meta-optimization and digest-bound winner export;
- a separate fixed-winner production execution;
- four accepted production rows and verified training-data consumption.

The canary did not train or evaluate Gemma and used an operator-owned lifecycle
driver. Run 9 must additionally prove researcher-driven native CLI use,
production-scale replenishment, campaign-wide accounting, training, and
four-GPU vLLM evaluation.

## Meaning of the two optimization loops

### Outer AAR loop

The outer loop is the meta-meta-optimizer. Between outer iterations, the AAR
researcher may improve:

- grounding coverage and scenario-family distribution;
- domain, behavior, and difficulty balance;
- the structured generation strategy;
- allowed pipeline design choices;
- the requested inner-loop search effort within the operator envelope.

Each scientific revision creates a new native workspace with a new manifest,
split seed, workspace digest, execution IDs, dataset digest, training receipt,
candidate checkpoint, and evaluation result.

The held-out AAR evaluation suite, Luna scoring contract, model identities,
credentials, infrastructure, and campaign budgets are not researcher-mutable.

### Inner AutoData loop

Within one frozen workspace, native `meta_optimize` evaluates scoped pipeline
mutations. AutoData owns actions, leases, state transitions, candidate
comparison, winner selection, export, and production execution. AAR invokes
the original plugin CLI through the SDK Bash tool; there is no AAR AutoData
lifecycle MCP server.

The AAR researcher may author a scenario pool and visible tuning design. The
trusted launcher freezes the concrete partition before execution. The current
native contract hides validation outcomes and trajectories, although scenario
payloads in the combined grounding manifest are visible. Run 9 must not claim
that validation inputs themselves are secret unless stronger containment is
implemented and verified.

## Approved campaign configuration

```yaml
outer_aar:
  chains: 1
  scheduling: sequential
  successful_score_result_pairs: 5
  maximum_researcher_sessions: 8
  researcher_model: claude-opus-4.8
  target_model: Gemma-4-31B-it
  candidate_initialization: fresh_base_per_iteration

autodata_models:
  generator: Kimi-K2.6
  generator_deployment: winnieyangwn-kimi26
  judge: gpt-5.6-luna
  approval_monitor: gpt-5.6-luna

autodata_meta:
  hard_max_iterations: 10
  minimum_iterations: 3
  early_stop_patience: 3
  tuning_tasks: 64
  hidden_validation_tasks: 32
  untouched_test_tasks: 32
  target_concurrency: 16
  fallback_concurrency: 8

autodata_production:
  required_accepted_rows: 1000
  initial_source_tasks: 1250
  hard_source_task_limit: 1500
  judge_acceptance_threshold: 0.75
  target_concurrency: 16
  fallback_concurrency: 8

campaign_limits:
  autodata_max_cost_usd: 300
  autodata_execution_wall_hours: 8
  total_campaign_wall_hours: 72

evaluation:
  backend: vllm
  version: 0.25.1
  gpu_count: 4
  lora_strategy: merged_checkpoint
  suite: honesty_sycophancy_concealing_uncertainty
  reuse_validated_13_benchmark_baseline: true

storage:
  retained_root: /storage/home/winnieyangwn/aar-runs
  write_checkpoint_ram: false
```

The `$300` cap is a campaign-wide AutoData ceiling across all outer sessions,
not a fresh allowance for every workspace or iteration. It covers Kimi/Luna
generation and judging reservations. AAR researcher-model cost and GPU
training/evaluation consumption remain separately controlled by the validated
AAR launcher.

The retained baseline and shared base model may be read from existing
`/checkpoint/ram` paths. No new Run 9 dataset, checkpoint, merged candidate,
cache, log, state database, approval, or evaluation artifact may be written
there.

## Concurrency-16 admission gate

AutoData concurrency controls simultaneous source-task attempts. It is
independent of the four GPUs used later for Gemma evaluation. Each AutoData
task creates a SandoQ sandbox, calls Kimi, and then calls Luna.

Do not assume that 16 is optimal. Before the full campaign:

1. run a representative model-backed load test at concurrency 16;
2. require at least 99% task completion;
3. reject sustained throttling, lease failures, timeouts, or retry storms;
4. compare throughput and tail latency with the proven lower-concurrency path;
5. use 16 only if the gate passes, otherwise pin 8 and record the fallback.

The broker-wide maximum must be at least the chosen execution concurrency. No
parallel outer AAR chains are permitted, so one chain cannot multiply this
limit through concurrent workspaces.

## Inner-loop stopping and winner policy

The three controls have distinct meanings:

- `hard_max_iterations: 10` is the operator ceiling and cannot be raised by
  the researcher.
- `minimum_iterations: 3` prevents premature stopping after one fortunate or
  uninformative comparison.
- `early_stop_patience: 3` stops after three consecutive evaluated mutations
  fail to improve the incumbent.

The researcher may request between three and ten iterations for a new outer
workspace, but cannot weaken the envelope. The trusted state machine—not an
unverified textual claim—calculates patience and finalization eligibility.

If all mutations are rejected, the approved baseline remains the native
winner. That is not automatically a run failure: it may mean the baseline was
already better than the proposed changes. Production may proceed only when the
incumbent passes the fixed validity and untouched-test requirements. Record
this outcome explicitly as `no_meta_improvement`.

If the incumbent fails the quality requirements after the allowed search:

- do not lower Luna's threshold;
- do not expose hidden validation evidence;
- do not train Gemma;
- fail that outer attempt and let a later researcher session create a new
  versioned workspace and scientific design.

Native AutoData must support the early-finalization contract directly. Do not
simulate it by editing state, accessing internal candidate paths, or cancelling
an execution and treating it as complete.

## Grounding, validation, and fixed scoring

AAR may improve the validation *design* between outer iterations as part of
meta-meta-optimization. It may propose domains, behavior patterns, difficulty,
and coverage. It must not write or alter the resulting validation evidence.

For each workspace:

1. AAR authors or revises the scenario-pool contract.
2. The trusted launcher freezes and digests the materialized pool.
3. It assigns 64 tuning IDs and 32 validation IDs before execution.
4. A separate 32-task test partition is not used for mutation selection.
5. Kimi and Luna generate the task evidence.
6. AAR sees tuning evidence and bounded decisions, not hidden task-level
   validation outcomes.

The Luna rubric is campaign-fixed. It must use explicit anchored dimensions
for self-containment, factual honesty, sycophancy resistance, uncertainty
disclosure, helpfulness, and safety. A row is retained only when Luna returns
`accept=true` and its fixed aggregate score is at least `0.75`. This is a
training-row quality gate, not the Gemma alignment benchmark score.

AAR may optimize data to satisfy this fixed definition. It cannot change the
judge identity, rubric, weights, required dimensions, threshold, or hidden
evidence during the campaign.

## Production semantics

`required_accepted_rows: 1000` is an output requirement, not a source count,
meta batch size, or training minibatch size.

Production begins with 1,250 distinct source scenarios. Judge-rejected rows do
not enter the dataset. If fewer than 1,000 rows are accepted, the trusted
production controller generates bounded fresh scenarios in additional batches,
stopping when either:

- exactly 1,000 verified rows have been retained; or
- 1,500 total source tasks have been attempted.

Reaching 1,500 attempts without 1,000 accepted rows fails the outer attempt.
The controller must not duplicate rows, reuse request IDs, weaken the rubric,
or continue without a reservation in the campaign ledger.

The production execution must use the digest-bound winner exported by native
AutoData. Any controlled grounding expansion must retain both the winner
pipeline digest and the new production-manifest digest so the handoff is
auditable.

## Campaign accounting

Before accepting each broker job, the trusted boundary must reserve its
worst-case cost from the shared campaign ledger using pinned input/output token
ceilings and rates. After completion, reconcile the reservation against
provider-reported token usage. Failed or malformed model outputs still retain
usage and cost evidence.

The ledger must cover all workspaces, outer sessions, retries, load tests,
meta-optimization, and production tasks. It must fail closed when a reservation
would exceed the `$300` campaign cap. The researcher cannot read credentials,
replace models, change rates, reset the ledger, or mint a new budget scope.

## Training handoff

Training must load data only through the verified AutoData dataset loader. The
loader verifies:

- native production execution identity;
- dataset and manifest digests;
- exactly 1,000 accepted rows;
- Kimi generation and Luna judgment provenance;
- provider usage and request IDs;
- fixed judge/rubric identity;
- campaign ledger state.

It writes a mode-0600 consumption receipt. The training submission, resulting
adapter, merged checkpoint, model submission, and evaluation score must all
carry the same dataset digest. Merely generating or exporting rows is not
sufficient.

Each outer candidate starts from the same clean Gemma-4-31B-it base unless the
approved AAR method explicitly studies a different training mechanism within
the existing safety and compute envelope. Iterations do not silently continue
training the previous candidate.

## Gemma evaluation

Training produces a PEFT/LoRA adapter. The committed atomic merge helper merges
that adapter with a copy of the base weights, validates the complete output,
and publishes a standalone candidate checkpoint. It never modifies the shared
base model.

The evaluator must use the validated vLLM 0.25.1 container with
`language_model_only=True`, BF16, and `lora_strategy=merged_checkpoint`.
Runtime LoRA and Transformers fallback are forbidden. vLLM 0.20.1 is invalid
for heterogeneous Gemma 4 attention dimensions.

The four allocated GB300 GPUs run separate model replicas and score benchmark
groups in parallel; Gemma is not tensor-sharded across all four GPUs. Evaluator
logs must identify the exact checkpoint, vLLM version, container, backend, and
merge strategy before a candidate can receive a valid score.

The retained complete 13-benchmark Gemma baseline is reused only after the
committed validator confirms model identity, protocol, full score set, source
hashes, and baseline hash. The reuse decision and validation output belong in
the Run 9 attempt metadata.

## Five-iteration success semantics

The ordinary AAR `max_iterations` counter counts researcher sessions, including
sessions that fail before scoring. Run 9's scientific target is five atomic
score/result pairs, not merely five started sessions.

The launcher may start at most eight sequential researcher sessions to obtain
five successful pairs. Stop immediately after the fifth valid pair. If eight
sessions finish without five pairs, the campaign fails and must not be reported
as a five-iteration success.

For each successful outer iteration retain:

- proposal and monitor decision;
- workspace and action IDs;
- signed approval audits;
- partition IDs and digests;
- meta execution, winner, and test evidence;
- production executions and replenishment history;
- accepted dataset and usage ledger digests;
- training-consumption receipt;
- training job and candidate adapter metadata;
- merged checkpoint manifest;
- evaluation submission, score, and result finding.

## Source integration and launch discipline

The AutoData work is on the `autodata` branch, while the validated Gemma vLLM
launcher has additional `multi_vllm` history. Build one reviewed integrated
source commit without altering the active `uv` worktree or its jobs. Preserve
the native plugin architecture and use the validated committed launcher as the
source of truth rather than reconstructing a large `sbatch` command.

Commit source and documentation on the devserver, synchronize the exact commit
to an isolated HPC execution worktree by Git fast-forward, and preserve all
HPC-local ignored environments and credentials. The canonical AutoData checkout
must be clean, on `main`, and pinned to an exact SHA.

Every retry gets a fresh attempt directory. Never delete or overwrite a failed
attempt. Do not call the AAR chain running until the launcher has emitted
distinct evaluator and sequential-chain Slurm job IDs.

## Launch gates

The committed submitter must fail before expensive work unless all of the
following pass:

1. exact AAR and AutoData branches, commits, and clean tracked trees;
2. ARM64 environment, CUDA PyTorch, BF16 computation, and visible GB300;
3. exact plugin wheel and framework lock;
4. mode-600 credential files present without printing values;
5. SandoQ Firecracker token and authenticated broker health;
6. real Kimi/Luna canary;
7. concurrency-16 admission test or recorded fallback to 8;
8. delegated approval signing and replay checks;
9. campaign ledger reservation/reconciliation test;
10. accepted-row replenishment and hard-ceiling test;
11. anchored Luna rubric and protected digest;
12. pinned public evaluation sources and manifest hashes;
13. validated retained 13-benchmark baseline provenance;
14. vLLM 0.25.1 merged-checkpoint evaluator configuration;
15. retained storage root resolved below `/storage/home/winnieyangwn/aar-runs`.

## Monitoring and progress record

The durable operator record is
[`PROGRESS.md`](PROGRESS.md).
Record at least:

- source commits and synchronization evidence;
- chosen concurrency and load-test report;
- attempt root and immutable configuration digest;
- launch, broker, evaluator, chain, training, and recovery job IDs;
- log paths and current Slurm states;
- per-outer-iteration workspace, execution, dataset, training, and evaluation
  identifiers;
- campaign task, call, token, and cost totals;
- failures, fixes, and fresh retry attempt roots;
- final count of atomic score/result pairs.

Status reports must distinguish setup, queued, running, training, evaluating,
completed, and failed. A wrapper job alone is not evidence that the AAR chain
is running.
