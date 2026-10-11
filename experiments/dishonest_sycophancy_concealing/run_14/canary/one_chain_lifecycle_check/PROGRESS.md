# Run 14 one-chain lifecycle progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Do not
record credentials, held-out examples, raw evaluator traces, or partial
held-out scores here.

Presentation standardized at 2026-10-10 18:09 PT. The reformat preserves the
chronology and operational facts of every existing event.

## Visual key

| Symbol | Status      | Meaning                                      |
| ------ | ----------- | -------------------------------------------- |
| ✅     | PASS        | Completed successfully or verified correct  |
| 🔴     | FAIL / STOP | Failed gate or deliberate stop condition     |
| 🛠️     | FIX         | Corrective change implemented                |
| 🔎     | OBSERVATION | Important experimental evidence              |
| ⏭️     | NEXT        | Next action or outstanding work              |
| ⏳     | RUNNING     | Work currently in progress                   |

## 2026-10-10

<a id="run14-one-chain-planned"></a>

### ⏭️ 17:02 PT — NEXT: one-chain lifecycle planned

> [!NOTE]
> **Not launched.** No attempt or job existed; only the source configuration
> had been prepared.

#### Evidence

- Source commit: not yet committed
- Attempt: not created
- Jobs: none
- Evidence: source configuration only

#### ⏭️ Next step

Validate the source before launch.

<a id="run14-one-chain-source-validation"></a>

### ✅ 17:05 PT — PASS: source validation completed

> [!TIP]
> **Source checks passed; lifecycle still unlaunched.**

#### Evidence

- Source commit: not yet committed
- Attempt: not created
- Jobs: none
- Validation: 39 tests plus 5 subtests, ShellCheck, Bash syntax, and Python
  compilation

#### ⏭️ Next step

Commit and synchronize the validated source before launching this canary.

<a id="run14-one-chain-handoff-fix"></a>

### 🛠️ 17:19 PT — FIX: smoke-to-evaluator handoff corrected

> [!IMPORTANT]
> The pre-launch audit found that the one-step training path deliberately did
> not stage its adapter. Run 14 now waits for the verified smoke proof, stages
> that exact adapter, and starts the evaluator on demand.

#### Evidence

- Source commit: pending
- Attempt: not created
- Jobs: none

#### ⏭️ Next step

Revalidate, commit, synchronize, and then launch.

<a id="run14-one-chain-gpu-preflight"></a>

### ✅ 17:24 PT — PASS: FAIR GB300 GPU and runtime preflight

> [!TIP]
> CUDA, BF16, target imports, and representative GPU execution passed.

| Stage                     | Result | Runtime |
| ------------------------- | ------ | ------- |
| GPU and runtime preflight | PASS   | 1m01s   |

#### Evidence

- Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
- Attempt: not yet created
- Jobs: preflight `1809164`, completed `0:0`

#### ⏭️ Next step

Launch the bounded one-chain lifecycle canary.

<a id="run14-one-chain-launched"></a>

### ⏳ 17:25 PT — RUNNING: native-generation canary launched

> [!NOTE]
> The bounded attempt started with native data generation and AutoData
> disabled.

```text
✓ Source validation
✓ GPU and runtime preflight
✓ Pipeline and research-chain submission
○ Method authoring and contract check
○ Proposal review and approval
○ Native example generation
○ Training smoke and adapter validation
○ Evaluation
○ Finding publication
○ One-chain lifecycle proof
```

#### Evidence

- Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
- Attempt:
  `/checkpoint/ram/aar/winnieyangwn/run14_native_generation/canary_attempts/20261011T002500Z-c8d5bc8da647`
- Jobs: pipeline `1809175`; research chain `1809185`
- Submission metadata: `research_model=Kimi-K2.6`,
  `data_generation_backend=native`, and `autodata=0`

#### ⏭️ Next step

Monitor the complete method-to-finding lifecycle.

<a id="run14-one-chain-training-passed"></a>

### ✅ 17:43 PT — PASS: method, proposal, data, and training smoke

> [!TIP]
> The method passed its contract and proposal review, generated eight native
> examples, completed one optimizer step, reloaded its adapter, and staged the
> exact verified adapter for evaluation.

```text
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Method authoring and contract check
✓ Proposal review and approval
✓ Native example generation
✓ Training smoke and adapter validation
✓ Exact adapter staging
○ Evaluation
○ Finding publication
○ One-chain lifecycle proof
```

| Stage          | Result | Runtime |
| -------------- | ------ | ------- |
| Pipeline       | PASS   | 17m29s  |
| Training smoke | PASS   | 1m53s   |

#### Evidence

- Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
- Attempt: unchanged
- Jobs: pipeline `1809175`, completed `0:0`; training `1809212`, completed
  `0:0`
- Kimi corrected two contract findings before approval.
- Method source SHA-256:
  `37359a7e8804d811c720f572c01fe599a06270b079ff42286b4afcd12933396d`
- Approved package SHA-256:
  `62813494c848efda7ed96b4b76a3e08cc2a72bac7e7a1744378167100e56d16e`

#### ⏭️ Next step

Evaluate the staged adapter; do not retrain.

<a id="run14-one-chain-evaluation-complete"></a>

### ✅ 17:52 PT — PASS: fail-closed vLLM evaluation completed

> [!TIP]
> The evaluator published an authoritative two-item workflow score using the
> exact merged adapter and removed the ephemeral merged checkpoint.

> [!NOTE]
> `verbalized_ece` scored `0.0` on two items versus baseline `0.3874`, so the
> regression gate failed. This bounded score is workflow evidence only, not a
> scientific conclusion.

```text
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Method authoring and contract check
✓ Proposal review and approval
✓ Native example generation
✓ Training smoke and adapter validation
✓ Exact adapter staging
✓ Evaluation and score publication
○ Finding publication
○ One-chain lifecycle proof
```

#### Evidence

- Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
- Attempt: unchanged
- Jobs: evaluator `1809218`, completed `0:0` in 8m15s
- Runtime: vLLM `0.25.1`, language-model-only mode, atomically merged adapter
- Retention: merge manifest retained; ephemeral checkpoint removed

#### ⏭️ Next step

Publish the matching finding for the scored run.

<a id="run14-one-chain-finding-publication-failed"></a>

### 🔴 17:59 PT — FAIL: final finding publication incomplete

> [!CAUTION]
> The research chain failed only at the final publication boundary. The method,
> adapter, evaluator proof, and authoritative score remain valid, but no forum
> finding exists and the required score/result pair is incomplete.

```text
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Method authoring and contract check
✓ Proposal review and approval
✓ Native example generation
✓ Training smoke and adapter validation
✓ Exact adapter staging
✓ Evaluation and score publication
✗ Finding publication
○ One-chain lifecycle proof
○ Five-chain topology gate
```

The cross marks the failed publication stage. No lifecycle proof or five-chain
work began.

#### 🔎 Observation

Kimi's first `share_finding` call omitted `results_writeup`; its second omitted
`run_id`; it then exhausted 24 continuations.

#### Evidence

- Source commit: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
- Attempt: unchanged
- Jobs: research chain `1809185`, failed `1:0` after 30m50s

#### ⏭️ Next step

Preserve all expensive artifacts and perform a finding-only recovery. Do not
repeat method authoring, training, or evaluation.

<a id="run14-one-chain-recovery-committed"></a>

### 🛠️ 18:04 PT — FIX: finding-only recovery committed

> [!IMPORTANT]
> The recovery requires the existing approved run ID and public score, keeps
> `AAR_AUTODATA=0`, forbids method edits, training, and evaluation, and requires
> one durable `share_finding` call.

#### Evidence

- Source commit: `d49bef0766eee1733bd1c58c9505151680841d21`
- Attempt: unchanged
- Jobs: no recovery job launched yet
- Change: commit `d49bef0` adds the scored-run-only finalizer

#### ⏭️ Next step

Synchronize the commit to HPC, publish the missing finding, create the
one-chain lifecycle proof, and then launch the five-chain canary.

<a id="run14-one-chain-recovery-synchronized"></a>

### ✅ 18:06 PT — PASS: exact source synchronized to FAIR HPC

> [!TIP]
> The matching HPC execution worktree is clean at the exact recovery revision.

#### Evidence

- Source commit: `fae1191f236f9aaca75a65005e402737fe391c73`
- Attempt: unchanged
- Jobs: no recovery job launched yet
- HPC revision: `fae1191f236f9aaca75a65005e402737fe391c73`

#### ⏭️ Next step

Use this synchronized revision as the recovery starting point.

<a id="run14-one-chain-model-roles-confirmed"></a>

### ✅ 18:07 PT — PASS: user confirmed the model-role mapping

> [!TIP]
> The exact presented model roles were explicitly confirmed for the
> finding-only recovery at this configuration revision.

#### Evidence

- Source commit: `fae1191f236f9aaca75a65005e402737fe391c73`
- Attempt: unchanged
- Jobs: no recovery job launched yet
- Research and native generation: Kimi-K2.6, deployment
  `steerability_8-kimi26`
- Proposal monitor: `claude-4-8-opus`
- Training target: fixed Gemma 4 31B IT base
- Evaluator inference: Gemma 4 plus merged adapter through vLLM `0.25.1` in
  language-model-only mode
- Unused roles: evaluator judge, AutoData teacher, row judge, and broker

#### ⏭️ Next step

Proceed only with the confirmed finding-only recovery configuration.

<a id="run14-one-chain-final-finding-hardening"></a>

### ⏳ 18:08 PT — RUNNING: shared final-finding hardening

> [!NOTE]
> Implementation and focused validation are proceeding in a separate work
> thread so the one-chain recovery and later five-chain experiment share the
> same guarded final-finding behavior. No recovery job has launched.

```text
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Method authoring and contract check
✓ Proposal review and approval
✓ Native example generation
✓ Training smoke and adapter validation
✓ Exact adapter staging
✓ Evaluation and score publication
✗ Finding publication (recovery pending)
○ One-chain lifecycle proof
○ Five-chain topology gate
```

The cross remains on the failed publication boundary. The recovery, lifecycle
proof, and five-chain gate have not begun.

#### Evidence

- Source commit: `fae1191f236f9aaca75a65005e402737fe391c73`
- Attempt: unchanged
- Jobs: no recovery job launched yet
- State: shared Kimi final-finding hardening in progress

#### ⏭️ Next step

Wait for the shared hardening to be committed and synchronized before
finding-only recovery. No lifecycle proof has passed yet.

<a id="run14-one-chain-finding-recovery-passed"></a>

### ✅ 18:11 PT — PASS: finding-only recovery and lifecycle proof

> [!TIP]
> Recovery completed from 18:10:48 to 18:11:30 PDT with `RC=0`. The retained
> score now has its finding, and the fail-closed one-chain proof passed.

```text
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Method authoring and contract check
✓ Proposal review and approval
✓ Native example generation
✓ Training smoke and adapter validation
✓ Exact adapter staging
✓ Evaluation and score publication
✓ Finding publication
✓ One-chain lifecycle proof
○ Five-chain topology gate
```

#### Evidence

- Recovery source: clean HPC commit
  `766e7f1a0844bae66b1330a46e9b9b8c5705425f`
- Retained attempt source: `c8d5bc8da647bdea5f863db3c2292607282c28b0`
- Attempt: unchanged
- Run ID:
  `gemma4_31b-explore-canary-1791678522-gemma4_31b_explore_canary__kimi_candidate-1791679190905`
- Finding SHA-256:
  `1296ffcd96596829ba7f9a59fcdb4bed5c8be841138badcd603d3ca6657c8fef`
- Evaluation-contract SHA-256:
  `2529aa934f3f2e2bf9a42a734ccaf8de063bc55b9bc6d5232c77c5c309b3986b`
- Lifecycle-proof SHA-256:
  `f2c3e180ddb6f9fcd94c72d528ad89c57bcb358d18f75b4f2b93779548bd50ad`
- All ten proof booleans are true: adapter reload validation, AutoData
  disabled, ephemeral merge removed, evaluation item contract, fail-closed
  markers, Kimi MCP tool roundtrip, merge manifest retained, method GPU smoke,
  on-demand evaluator, and score/result pair
- Jobs: no Slurm, training, or evaluation work was submitted during recovery
- Repository: clean after recovery

#### 🔎 Audit caveat

Kimi called `get_literature` and `Read`, but created zero literature-review
files and touched no method files. AutoData remained disabled.

#### ⏭️ Next step

The one-chain lifecycle gate passed and authorizes the five-chain canary.
