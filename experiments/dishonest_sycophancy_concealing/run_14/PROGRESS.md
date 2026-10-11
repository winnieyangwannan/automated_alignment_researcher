# Run 14 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Do not
record credentials, held-out examples, raw evaluator traces, or partial
held-out scores here.

## Visual key

| Symbol | Status      | Meaning                                      |
| ------ | ----------- | -------------------------------------------- |
| ✅     | PASS        | Completed successfully or verified correct  |
| 🔴     | FAIL / STOP | Failed gate or deliberate stop condition     |
| 🔎     | OBSERVATION | Important experimental evidence              |
| 🛠️     | FIX         | Corrective change implemented                |
| ⏭️     | NEXT        | Next action or outstanding work              |
| ⏳     | RUNNING     | Work currently in progress                   |

## 2026-10-10

<a id="run14-event-created"></a>

### 🛠️ 17:02 PT — FIX: Created the native-generation run package

> [!IMPORTANT]
> Run 14 is source-only and has not launched any Slurm job.

- Added a validated YAML backend setting that emits `AAR_AUTODATA=0`.
- Added independent launcher and scheduled-pipeline checks that reject AutoData.
- Preserved Run 12's five-chain, five-result scientific target while removing
  its AutoData plugin, broker, recipes, workspaces, generator/judge route, and
  per-iteration AutoData target rotation.

```text
○ Source validation
○ One-chain native-generation lifecycle
○ Full five-chain launch
```

#### ⏭️ Next step

Run local source validation, synchronize the resulting commit to HPC, and then
execute the bounded lifecycle check before authorizing the full run.

<a id="run14-event-source-validation"></a>

### ✅ 17:05 PT — PASS: Source validation completed

> [!TIP]
> The Run 14 package and shared declarative-config extension passed all local
> checks. No Slurm job or external service was mutated.

| Check                              | Result                       |
| ---------------------------------- | ---------------------------- |
| Run 14 YAML resolution             | PASS                         |
| Focused Python tests               | PASS: 39 + 5 subtests        |
| ShellCheck                         | PASS                         |
| Bash syntax                        | PASS                         |
| Python compilation                 | PASS                         |
| Git whitespace validation          | PASS                         |

```text
✓ Source validation
○ One-chain native-generation lifecycle
○ Full five-chain launch
```

#### ⏭️ Next step

Commit and synchronize the source package, then run the one-chain lifecycle
check on FAIR HPC.

<a id="run14-event-one-chain-passed"></a>

### ✅ 18:11 PT — PASS: one-chain lifecycle proof completed

> [!TIP]
> The retained one-chain attempt completed its method, proposal, native-data,
> real-GPU training, evaluator, and finding lifecycle. A narrow finding-only
> recovery reused the existing score and did not retrain or reevaluate.

```text
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Method authoring and contract check
✓ Proposal review and approval
✓ Native data generation
✓ Training smoke and adapter validation
✓ Evaluator and score publication
✓ Finding publication
✓ One-chain lifecycle proof
○ Five-chain topology proof
○ Full five-chain run
```

#### Evidence

- Attempt:
  `/checkpoint/ram/aar/winnieyangwn/run14_native_generation/canary_attempts/20261011T002500Z-c8d5bc8da647`
- Attempt source: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
- Recovery source: `766e7f1a0844bae66b1330a46e9b9b8c5705425f`
- Lifecycle-proof SHA-256:
  `f2c3e180ddb6f9fcd94c72d528ad89c57bcb358d18f75b4f2b93779548bd50ad`
- Decision: authorize only the bounded five-chain topology gate.

<a id="run14-event-five-chain-stopped"></a>

### 🔴 19:03 PT — STOP: first five-chain topology attempt could not pass

> [!CAUTION]
> The user stopped the remaining jobs after multiple chain failures made the
> required five-chain proof impossible. All known jobs were terminal or absent
> from `squeue` by 19:03:19 PDT; retained artifacts were preserved.

```text
✓ Validate exact one-chain prerequisite proof
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Launch five parallel research chains
✓ Retain three training receipts
✓ Complete one real-GPU training smoke
✗ Complete five method-to-finding lifecycles
○ Stage five verified adapters
○ Launch on-demand evaluator
○ Produce five score/result pairs
○ Five-chain topology proof
○ Full five-chain run
```

| Role             | Slurm job | Terminal state      | End (PT) |
| ---------------- | --------- | ------------------- | -------- |
| Pipeline         | 1809352   | CANCELLED by 686293 | 19:03:19 |
| Alpha research   | 1809357   | CANCELLED by 686293 | 19:03:19 |
| Beta research    | 1809358   | FAILED              | 18:55:30 |
| Gamma research   | 1809359   | FAILED              | 18:49:56 |
| Delta research   | 1809360   | CANCELLED by 686293 | 19:03:19 |
| Epsilon research | 1809361   | FAILED              | 18:50:41 |
| Epsilon training | 1809387   | FAILED              | 18:50:05 |
| Alpha training   | 1809418   | COMPLETED           | 18:51:28 |
| Delta training   | 1809577   | CANCELLED by 686293 | 19:03:19 |

#### 🔎 Observation

- Beta and gamma exhausted their bounded Kimi continuations during proposal
  work and produced no approved adapter.
- Epsilon reached approval, but its causal-SFT method supplied an unsafe
  sequence-to-sequence collator. The input-only batch produced `labels=None`,
  so Gemma returned logits without a loss. The structured failure marker was
  retained, but the one-session canary had no repair turn.
- Alpha completed the only successful GPU smoke. Delta training was active when
  cancelled. No evaluator launched, and no score/finding pair was produced.

#### Evidence

- Attempt:
  `/checkpoint/ram/aar/winnieyangwn/run14_native_generation/canary_attempts/20261011T012524Z-766e7f1a0844`
- Attempt source: `766e7f1a0844bae66b1330a46e9b9b8c5705425f`
- Inventory: three training receipts, one successful GPU smoke, one failed
  training job, zero evaluator jobs, and zero score/finding pairs.
- Decision: preserve the attempt, do not issue a topology proof, and do not
  launch the full run.

<a id="run14-event-shared-hardening-and-full-budget"></a>

### 🛠️ 19:07 PT — FIX: shared failures hardened and full budget resolved

> [!IMPORTANT]
> The fixes are shared infrastructure rather than attempt-specific workarounds.
> A corrected five-chain canary must exercise them before the full run.

- Commit `e6dd257` makes the method contract reject
  `DataCollatorForSeq2Seq` in causal `SFTTrainer` methods before GPU submission
  and explains how to use a collator that emits valid causal labels.
- Commit `342bfa8` gives stalled required Kimi checkpoints a separate bounded
  retry allowance, so malformed no-tool turns do not consume the productive
  continuation budget.
- The user selected five chains with 50 successful score/finding pairs per
  chain and a ceiling of 60 sessions per chain: 250 target pairs total, with up
  to 10 unsuccessful sessions of headroom for each chain.
- The full launcher is being hardened to require both ordered lifecycle proofs
  and retain their exact files and hashes.

```text
✓ Source validation
✓ One-chain lifecycle proof
✓ Diagnose first five-chain failures
✓ Shared method-contract hardening
✓ Shared Kimi checkpoint-retry hardening
✓ Resolve full-run budget: 5 × 50 successes, 60 sessions per chain
○ Validate and commit full-run organization
○ Synchronize exact source revision to HPC
○ Corrected five-chain topology rerun
○ Five-chain topology proof
○ Full five-chain launch
```

#### ⏭️ Next step

Validate and commit the organized source package. Then synchronize the exact
clean commit, reconfirm the model-role mapping, and rerun the five-chain canary.
Do not launch the 5×50 full experiment until the corrected topology proof passes.

<a id="run14-event-full-source-validated"></a>

### ✅ 19:09 PT — PASS: 5×50 source and proof-gating contract validated

> [!TIP]
> The organized full-run source now resolves five seeds, 50 successful pairs
> and 60 sessions per chain, and refuses a full launch without both correctly
> bound lifecycle proofs. This validation step launched no job; deployment of
> the final organized revision remains pending.

| Check                     | Result                   |
| ------------------------- | ------------------------ |
| Full YAML resolution      | PASS: `5 × 50`, max `60` |
| Focused Python tests      | PASS: 14                 |
| Bash syntax               | PASS                     |
| ShellCheck                | PASS                     |
| Python compilation        | PASS                     |
| Git whitespace validation | PASS                     |

```text
✓ Source validation
✓ One-chain lifecycle proof
✓ Shared failure hardening
✓ Full-run 5×50 budget contract
✓ Ordered proof validation and retention
○ Commit organized source
○ Synchronize exact source revision to HPC
○ Corrected five-chain topology rerun
○ Five-chain topology proof
○ Full five-chain launch
```

#### ⏭️ Next step

Commit this focused Run 14 source package, synchronize that exact commit, and
rerun the bounded five-chain topology gate after model-role reconfirmation.

<a id="run14-event-corrected-five-chain-launch"></a>

### ⏳ 21:50 PT — RUNNING: corrected five-chain canary bootstrap

> [!NOTE]
> The user confirmed the exact model roles. Preflight verified no active Run 14
> jobs, the exact one-chain proof, clean HPC source, and working endpoint/MCP
> access before submitting pipeline job `1810186` at 21:50:56 PDT.

```text
✓ Confirm exact model-role mapping
✓ Verify no active Run 14 jobs
✓ Validate exact one-chain prerequisite proof
✓ Verify clean HPC HEAD `e17b33468a15...`
✓ Endpoint and MCP preflight
⏳ Infrastructure bootstrap
○ Emit five research child job IDs
○ Five-chain method-to-finding lifecycles
○ Five-chain topology proof
○ Full five-chain launch
```

- Attempt:
  `/checkpoint/ram/aar/winnieyangwn/run14_native_generation/canary_attempts/20261011T045018Z-e17b33468a15`
- One-chain lifecycle-proof SHA-256:
  `f2c3e180ddb6f9fcd94c72d528ad89c57bcb358d18f75b4f2b93779548bd50ad`
- Source: clean HPC HEAD `e17b33468a1553a995eece4aa9fbefe8b0fabbc5`;
  Run 14 and shared paths are identical to `56b3c77`
- Child jobs: none emitted as of this launch update
- Decision: monitor bootstrap; do not report research chains as running until
  their distinct Slurm IDs are emitted

<a id="run14-event-corrected-five-chain-pass"></a>

### ✅ 22:39 PT — PASS: corrected five-chain topology gate

> [!TIP]
> All five chains completed their method, proposal, native-generation,
> real-GPU training, evaluation, and finding lifecycle. The final proof passed
> all 10 fail-closed booleans with AutoData disabled.

```text
✓ Exact one-chain prerequisite proof
✓ Five method contracts and approved proposals
✓ Five GPU smokes and adapter reload validations
✓ Five scores and five findings
✓ Evaluator and all research jobs completed `0:0`
✓ Five-chain topology proof
○ Full 5×50 launch
```

- Attempt:
  `/checkpoint/ram/aar/winnieyangwn/run14_native_generation/canary_attempts/20261011T045018Z-e17b33468a15`
- Source: `e17b33468a1553a995eece4aa9fbefe8b0fabbc5`
- Proof: `metadata/canary_passed.json`
- Proof SHA-256:
  `f78d83c592ea503307135cf1e5599df7a3a24dce78993c1fef9eae140abca4ef`
- Evaluator: `1810441`, `COMPLETED 0:0`
- AutoData: disabled with `AAR_AUTODATA=0`
- Decision: PASS; the retained proof authorizes the full launch

<a id="run14-event-full-five-chain-active"></a>

### ⏳ 22:43 PT — ACTIVE: full 5×50 experiment submitted

> [!NOTE]
> The user confirmed the exact model roles. Both ordered lifecycle proofs were
> validated and retained before pipeline `1810631` was submitted at 22:41:42
> PDT. Bootstrap completed successfully and emitted five evaluator/research
> pairs; all ten child jobs are currently queued in Slurm.

```text
✓ Confirm exact model-role mapping
✓ Validate and retain one-chain proof
✓ Validate and retain five-chain proof
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Emit five evaluator/research job pairs
⏳ Five chains target 50 successful score/finding pairs each
○ 250 total successful score/finding pairs
○ Full experiment completion
```

| Chain   | Evaluator | Research chain | State   |
| ------- | --------- | -------------- | ------- |
| Alpha   | 1810665   | 1810666        | PENDING |
| Beta    | 1810667   | 1810668        | PENDING |
| Gamma   | 1810669   | 1810670        | PENDING |
| Delta   | 1810671   | 1810672        | PENDING |
| Epsilon | 1810673   | 1810674        | PENDING |

#### Evidence

- Attempt:
  `/checkpoint/ram/aar/winnieyangwn/run14_native_generation/full_attempts/20261011T054113Z-8b83f841862c`
- Source commit: `8b83f841862c2381c714996b6467075805f342c3`
- Run 14 execution paths are unchanged from validated commit
  `e17b33468a1553a995eece4aa9fbefe8b0fabbc5`
- Pipeline: `1810631`, submitted at 22:41:42 PDT and `COMPLETED 0:0`
- Budget: five chains, 50 successful score/finding pairs per chain, maximum 60
  sessions per chain
- AutoData: disabled with `AAR_AUTODATA=0`
- Decision: monitor all five chain/evaluator pairs; count success only by
  atomic score/finding pairs

<a id="run14-event-full-five-chain-per-chain-snapshot-2341"></a>

### ⏳ 23:41 PT — RUNNING: per-chain lifecycle snapshot

> [!NOTE]
> All five research chains and evaluator workers remain running. Two complete
> score/finding pairs are durably joined by run ID: one from Delta and one from
> Epsilon. Training or score publication without the matching finding does not
> count toward the `250`-pair target.

#### Alpha — session 2/60, pairs 0/50

✓ Method authored and contract passed

✓ Proposal approved

✓ Training `1811063` completed

✓ Adapter submitted and merged

⏳ vLLM model loading and warmup

○ Benchmark evaluation

○ Score publication

○ Finding publication

Alpha successfully repaired the prior PEFT target-regex failure. Chain
`1810666` and evaluator `1810665` are running.

#### Beta — session 1/60, pairs 0/50

✓ Method authored and contract passed

✓ Proposal approved after code/paper corrections

⏳ Training `1810827`: approximately 79% complete

○ Adapter submission and merge

○ Evaluation

○ Score and finding publication

No runtime failure is present. Chain `1810668` and evaluator `1810667` are
running.

#### Gamma — session 3/60, pairs 0/50

✓ Method authored and contract passed

✓ Proposal approved

✓ Training `1811078` completed

✓ Adapter submitted and merged

⏳ vLLM model loading

○ Benchmark evaluation

○ Score and finding publication

Gamma recovered from both the generation-length failure and the unproductive
Session 1. Chain `1810670` and evaluator `1810669` are running.

#### Delta — session 2/60, pairs 1/50

✓ Previous iteration scored and finding published

✓ Current method and contract complete

✓ Current proposal approved

⏳ Current training `1811101`

○ Adapter merge

○ Evaluation

○ Next score/finding pair

Chain `1810672` and evaluator `1810671` are running. The current session has no
runtime failure.

#### Epsilon — session 3/60, pairs 1/50

✓ Helper-call failure repaired

✓ Previous training and evaluation completed

✓ Previous score and finding published

⏳ New method authoring

○ Contract check

○ Proposal review

○ Training and evaluation

Chain `1810674` and evaluator `1810673` are running. The new session has no
failure and is using the prior result through the leaderboard.

#### Evidence

- Snapshot: 2026-10-10 23:41:01 PDT
- Attempt:
  `/checkpoint/ram/aar/winnieyangwn/run14_native_generation/full_attempts/20261011T054113Z-8b83f841862c`
- Atomic progress: `2/250` total; Alpha `0/50`, Beta `0/50`, Gamma `0/50`,
  Delta `1/50`, Epsilon `1/50`

<a id="run14-event-full-five-chain-operator-pause-2359"></a>

### ⏸ 23:59 PT — PAUSED: source hardening and instrumented recovery

At the user's request, all five research chains, all five evaluator workers,
and Epsilon training job `1811135` were cancelled at 2026-10-10 23:59:51 PT.
All eleven jobs subsequently left the scheduler. The retained attempt and its
durable results were not deleted or overwritten.

#### Alpha — session 2/60, pairs 0/50

✓ Method authored, trained, and evaluated

✓ Score published

⏳ Finding publication to be recovered

○ Next score/finding pair

The completed score remains durable; it is not counted until its matching
finding is published.

#### Beta — session 1/60, pairs 0/50

✓ Method authored, trained, and evaluated

✓ Score published

⏳ Finding publication to be recovered

○ Next score/finding pair

The score completed approximately six seconds before the operator pause and
remains durable.

#### Gamma — session 3/60, pairs 0/50

✓ Method authored, contract passed, and training completed

✓ Adapter submitted and merged

⏳ Interrupted benchmark evaluation to be restarted

○ Score and finding publication

Five of thirteen benchmark phases had completed, but no score was published;
partial evaluator output will not be counted as a result.

#### Delta — session 2/60, pairs 1/50

✓ Previous score/finding pair remains durable

✓ Current method trained and adapter submitted

⏳ Interrupted benchmark evaluation to be restarted

○ Current score and finding publication

The existing pair remains counted. The interrupted current evaluation has no
published score.

#### Epsilon — session 3/60, pairs 1/50

✓ Previous score/finding pair remains durable

✓ Current method, contract, and proposal approved

⏳ Interrupted training to be resumed from the approved proposal

○ Adapter submission, evaluation, score, and finding

Training job `1811135` stopped after 12m29s without publishing an adapter.

#### Recovery scope

- Retained attempt:
  `/checkpoint/ram/aar/winnieyangwn/run14_native_generation/full_attempts/20261011T054113Z-8b83f841862c`
- Durable atomic progress: `2/250`
- Apply the shared target-generation and method-contract hardening.
- Enable vLLM runtime statistics through
  `evaluation.vllm_log_stats: true` and verify the live engine log markers.
- Resume from retained per-chain state with remaining session budgets Alpha
  `58`, Beta `59`, Gamma `57`, Delta `58`, and Epsilon `57`.

## 2026-10-11

<a id="run14-event-reviewed-five-chain-recovery-0106"></a>

### 🚀 01:06 PT — RUNNING: reviewed five-chain recovery reached 7/250 pairs

Run 14 resumed from the retained attempt at exact clean HPC commit
`b9bb6b201d19f45801df6c9bdf9aed2917b48592`. The focused recovery gate passed
with `72 passed`. A live plan-only proof validated all five exact remaining
session budgets and actionable proposal IDs without changing state before the
real launch.

#### Alpha — session 18/60, pairs 1/50

✓ Previous score and finding pair durable

✓ Current method authored and contract passed

✓ Current proposal approved

✓ Missing proposal run ID deterministically repaired and immutably bound

⏳ Trusted host-submitted training `1812309` pending resources

○ Adapter submission and merge

○ Benchmark evaluation

○ Score and finding publication

Alpha did not replay proposal authoring. The host submitted the exact approved
run before any Kimi turn.

#### Beta — session 20/60, pairs 1/50

✓ Previous score and finding pair durable

✓ Current method authored and contract passed

✓ Current proposal approved

✓ Missing proposal run ID deterministically repaired and immutably bound

⏳ Trusted host-submitted training `1812310` pending resources

○ Adapter submission and merge

○ Benchmark evaluation

○ Score and finding publication

Beta also entered score waiting directly, with no proposal replay or fabricated
identifier.

#### Gamma — session 6/60, pairs 1/50

✓ Retained training and evaluation score recovered

✓ Matching finding published without training or evaluation replay

⏳ Fresh next-iteration research and method authoring

○ Contract check

○ Proposal review

○ Training and evaluation

○ Next score and finding publication

#### Delta — session 5/60, pairs 2/50

✓ Previous pair retained

✓ Interrupted iteration's retained score recovered

✓ Matching finding published without training or evaluation replay

⏳ Fresh next-iteration research and method authoring

○ Contract check, proposal review, training, and evaluation

○ Next score and finding publication

#### Epsilon — session 6/60, pairs 2/50

✓ Previous pair retained

✓ Recovered training and evaluation score retained

✓ Matching finding published without training or evaluation replay

⏳ Fresh next-iteration research and method authoring

○ Contract check, proposal review, training, and evaluation

○ Next score and finding publication

#### Recovery diagnosis and reusable improvements

Two earlier recovery attempts exposed shared orchestration defects rather than
method failures:

- a persistent resume flag could replay a completed finding and consume another
  session; recovery is now one-shot and disables itself after the exact finding
  is durable;
- the recovery launcher omitted `AAR_NO_LOCAL_GPU=true`, so native decoupled
  approval produced no run ID. Kimi correctly refused to fabricate one. All
  decoupled execution signals now require approval-time IDs, and stopped legacy
  approvals can be deterministically repaired, immutably stamped, and audited;
- native recovery now owns training submission and score waiting before the
  first Kimi turn, while an existing score or submitted adapter prevents
  duplicate training even if a receipt is missing; and
- completed history is closed by its durable finding before current-method
  validation, so a later session's legitimate method edits cannot invalidate a
  prior pair.

The corrected recovery passed independent code review. Commits `dc2767d` and
`b9bb6b2` contain the reusable recovery hardening and this run's synchronized
documentation state. The earlier vLLM telemetry proof also confirmed live
periodic scheduler throughput and KV-cache statistics on all sampled replicas.

#### Active jobs and evidence

- Alpha evaluator/controller: `1812264` / `1812265`
- Beta evaluator/controller: `1812266` / `1812267`
- Gamma evaluator/controller: `1812268` / `1812269`
- Delta evaluator/controller: `1812270` / `1812271`
- Epsilon evaluator/controller: `1812272` / `1812273`
- Evaluators are scheduler-active and pending GPU resources; all five
  controllers are running.
- Atomic progress: Alpha `1/50`, Beta `1/50`, Gamma `1/50`, Delta `2/50`,
  Epsilon `2/50`; total `7/250`.
