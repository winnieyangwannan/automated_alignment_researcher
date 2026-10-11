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
