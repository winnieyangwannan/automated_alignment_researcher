# Run 15 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Do not
record credentials, held-out examples, or partial held-out scores here.

## Visual key

| Symbol | Status      | Meaning                                      |
| ------ | ----------- | -------------------------------------------- |
| ✅     | PASS        | Completed successfully or verified correct  |
| 🔴     | FAIL / STOP | Failed gate or deliberate stop condition     |
| 🐛     | BUG         | A concrete implementation defect identified |
| 🔎     | OBSERVATION | Important experimental evidence              |
| 💡     | CONCLUSION  | Conclusion supported by current evidence     |
| 🛠️     | FIX         | Corrective change implemented                |
| ⏭️     | NEXT        | Next action or outstanding work              |
| ⏳     | RUNNING     | Work currently in progress                   |

## 2026-10-11

<a id="run15-event-created"></a>

### 🛠️ 01:43 PT — FIX: fresh Run 15 package created after Run 14 incidents

> [!IMPORTANT]
> **Not launched.** Run 15 starts from fresh experiment state and a new storage
> namespace. Run 14 artifacts remain retained and are not imported as Run 15
> sessions, proposals, adapters, scores, findings, or budget.

#### 🔎 Observation

- Run 14 reached only 7 durable score/finding pairs after 59 started sessions.
- Alpha at 18 sessions and Beta at 24 sessions could no longer reach 50 pairs
  within their respective 60-session ceilings, even under perfect future yield.
- Run 14 exposed reusable proposal-revision, approved-proposal recovery, and
  structured training-failure handoff defects.

#### 🛠️ Corrective change

- Commit `34ad5a5cc66e2c6f68161511abb8cca32f0d0bc8` permanently disarms a
  completed approved-proposal recovery, preserves a rejected proposal's exact
  revision identity, advances safe run-bound training/evaluation failures to a
  fresh research session, and fails closed on malformed failure feedback.
- The focused HPC suite passed: 86 tests.
- Run 15 uses `data_generation.backend: native`, five fresh chain namespaces,
  50 durable pairs per chain, and a 60-session ceiling per chain.

#### Lifecycle

```text
✓ Run 14 failure diagnosis
✓ Reusable recovery hardening committed and synchronized
⏳ Run 15 source/configuration review
○ Exact model-role confirmation
○ One-chain lifecycle proof
○ Five-chain topology proof
○ Full five-chain 5×50 launch
○ 250 durable score/finding pairs
```

<a id="run15-event-full-launch"></a>

### ⏳ 03:13 PT — RUNNING: full five-chain 5x50 attempt launched

- Attempt:
  `/checkpoint/ram/aar/winnieyangwn/run15_native_generation/full_attempts/20261011T101046Z-9748ae9bb6f8`
- Exact immutable source: `9748ae9bb6f870651c3a5ec545d31cff0addc89e`.
- Pipeline `1813941` completed successfully and retained five distinct
  evaluator/research-chain pairs.
- The detached source snapshot is clean and remote-free. The retained override
  is bound to that commit, the `full-five-chain-5x50` scope, and deployment
  `autodata2_8-kimi26`.
- `full-launch.env` records native generation, `autodata=0`, five chains, and
  50 target pairs per chain.

### Alpha — session 0/60, pairs 0/50

✓ Evaluator `1813981` launched
✓ Research chain `1813982` launched
⏳ Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication

### Beta — session 0/60, pairs 0/50

✓ Evaluator `1813983` launched
✓ Research chain `1813984` launched
⏳ Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication

### Gamma — session 0/60, pairs 0/50

✓ Evaluator `1813985` launched
✓ Research chain `1813986` launched
⏳ Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication

### Delta — session 0/60, pairs 0/50

✓ Evaluator `1813987` launched
✓ Research chain `1813988` launched
⏳ Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication

### Epsilon — session 0/60, pairs 0/50

✓ Evaluator `1813989` launched
✓ Research chain `1813990` launched
⏳ Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication

All ten child jobs were running at 03:13 PT. A session is not counted until its
durable session state appears; a pair is not counted until score and finding
records join on the same run ID.

### 🔎 03:14 PT — OBSERVATION: all chains entered session 1

### Alpha — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature and leaderboard context loaded
⏳ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

### Beta — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature and leaderboard context loaded
⏳ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

### Gamma — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature and leaderboard context loaded
⏳ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

### Delta — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature and leaderboard context loaded
⏳ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

### Epsilon — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature and leaderboard context loaded
⏳ Method authoring and contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

Kimi output was coherent across all five chains. No strange output, failure
marker, or contract rejection had appeared. All evaluators were alive and idle,
awaiting their first submitted adapters.

### 🔴 03:15 PT — STOP: first full attempt preserved after conservative alert

- A monitor initially interpreted Gamma's references to exact Read/Bash calls
  as endpoint-preflight history contamination.
- All ten jobs were state-preservingly cancelled before any proposal, training
  job, adapter, score, or finding existed; total output was 0/250 pairs.
- Code and log tracing showed that the messages were normal production
  checkpoint prompts from `KimiAgent._continuation_prompt`, with exact
  attempt-local scaffold paths—not inherited endpoint-preflight history.
- The stopped attempt remains retained. A fresh replacement was chosen instead
  of resuming partially cancelled session state.

### ⏳ 03:22 PT — RUNNING: fresh replacement entered session 1

- Fresh attempt:
  `/checkpoint/ram/aar/winnieyangwn/run15_native_generation/full_attempts/20261011T101623Z-40bb8665e1c4`
- Source: `40bb8665e1c417062f8d633478f76a4f9ab08a3f`; pipeline `1814060`
  completed successfully.
- All five research jobs are running. All five evaluators exist but are pending
  GPU resources; no adapter is waiting for evaluation yet.

### Alpha — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature and leaderboard context loaded
✓ First method authored
⏳ Repairing method contract: Gemma target regex and TRL processing_class
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

Alpha's checkpoint retry recovered one malformed forced-Bash emission on retry
1/2. The two contract findings are actionable and non-terminal.

### Beta — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature and leaderboard context loaded
⏳ Method research and authoring
○ Method contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

No runtime failure.

### Gamma — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature and leaderboard context loaded
⏳ Method research and authoring
○ Method contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

The earlier context concern was disproven by tracing the production checkpoint
prompts. No contamination or runtime failure is present.

### Delta — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature context loaded
⏳ Method research and authoring
○ Method contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

No runtime failure.

### Epsilon — session 1/60, pairs 0/50

```text
✓ Infrastructure bootstrap
✓ Literature and leaderboard context loaded
⏳ Method research and authoring
○ Method contract check
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

No runtime failure.

Total: **0/250 completed atomic score/finding pairs**.

### ⏳ 03:25 PT — RUNNING: first methods reached contract validation

### Alpha — session 1/60, pairs 0/50

```text
✓ Method authored
✓ Initial Gemma regex and TRL contract errors repaired
✓ Method contract passed
⏳ Preparing proposal submission
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

Evaluator `1814094` is running. No proposal or training job exists yet.

### Beta — session 1/60, pairs 0/50

```text
✓ Method authored
✗ Contract found target-regex, DPO-stack, processing_class, and generation-bound issues
⏳ Revising the method
○ Contract pass and proposal review
○ Training and evaluation
○ Score and finding publication
```

Evaluator `1814096` is running. The contract failure is actionable and
non-terminal.

### Gamma — session 1/60, pairs 0/50

```text
✓ Method draft attempted
✗ Contract caught an unterminated triple-quoted string
⏳ Repairing method syntax
○ Contract pass and proposal review
○ Training and evaluation
○ Score and finding publication
```

One malformed forced-Bash emission recovered automatically. Evaluator
`1814098` is pending GPU resources.

### Delta — session 1/60, pairs 0/50

```text
✓ Method authored
✗ Contract found target-regex, undefined-name, and processing_class issues
⏳ Revising the method
○ Contract pass and proposal review
○ Training and evaluation
○ Score and finding publication
```

Evaluator `1814100` is pending GPU resources. The contract failure is
actionable and non-terminal.

### Epsilon — session 1/60, pairs 0/50

```text
✓ Method authored
✗ Contract rejected the Gemma target regex encoded as a list
⏳ Revising the method
○ Contract pass and proposal review
○ Training and evaluation
○ Score and finding publication
```

Evaluator `1814102` is pending GPU resources. The contract failure is
actionable and non-terminal.

No proposal, training job, adapter, score, or finding exists yet. Total:
**0/250 completed atomic score/finding pairs**.

### ⏳ 03:29 PT — RUNNING: two proposals reviewed; three contracts repairing

### Alpha — session 1/60, pairs 0/50

```text
✓ Method contract passed
✗ Proposal review 1 rejected for code/paper mismatch and missing reproducibility details
✓ Method revised from 44 to 32 examples and contract re-passed
⏳ Preparing proposal revision 2
○ Approval and training
○ Evaluation and score/finding publication
```

The data-policy review passed. The revision is adding exact templates,
shuffle/optimizer/masking details, and the corrected eight-step count.

### Beta — session 1/60, pairs 0/50

```text
✓ Method authored
✗ Contract found Gemma regex, DPO-stack, processing_class, and generation-bound issues
⏳ Revising the method
○ Contract pass and proposal review
○ Training and evaluation
○ Score and finding publication
```

No proposal or training job exists yet.

### Gamma — session 1/60, pairs 0/50

```text
✗ Initial Write produced corrupt/oversized content
✓ Method replaced with valid Python
✗ Latest contract has only the regex-as-list issue
⏳ Converting the target regex to a string and revalidating
○ Proposal review, training, evaluation, and publication
```

One malformed forced-Bash call recovered automatically; no terminal failure.

### Delta — session 1/60, pairs 0/50

```text
✓ Undefined-name and processing_class errors repaired
✗ Latest contract has only the regex-as-list issue
⏳ Revalidating the string-regex repair
○ Proposal review and approval
○ Training and evaluation
○ Score and finding publication
```

No proposal or training job exists yet.

### Epsilon — session 1/60, pairs 0/50

```text
✓ Method contract passed
✗ Proposal review 1 rejected for filter, count, and sampling-detail mismatches
⏳ Revising code and paper for exact reproducibility
○ Contract re-pass and proposal revision
○ Training and evaluation
○ Score and finding publication
```

The data-policy review passed. The revision is implementing a real type-specific
filter, exact counts, and explicit generation parameters.

All five research chains remain running. Alpha/Beta evaluators are running;
Gamma/Delta/Epsilon evaluators are pending GPU resources. There are no training
jobs, adapters, scores, or findings. Total: **0/250 completed atomic
score/finding pairs**.

### ⏳ 03:33 PT — RUNNING: first training failure handed to session 2

### Alpha — session 2/60, pairs 0/50

```text
✓ Session 1 method contract and proposal approved
✗ Training 1814237 failed after 1m11s with a structured TypeError
✓ Failure marker durably handed to a fresh session
⏳ Session 2 repairing a new candidate after a target-regex contract error
○ Contract and proposal review
○ Training and evaluation
○ Score and finding publication
```

The full path passed `None` where the training stack compares an integer. No
adapter or score was produced. This exposes a method-contract/smoke coverage
gap, but the orchestration recovery behaved correctly.

### Beta — session 1/60, pairs 0/50

```text
✓ Method authored
✓ DPO-stack, processing_class, generation-bound, and regex issues repaired
✓ Method contract passed
⏳ Authoring the first proposal
○ Proposal review, training, evaluation, and publication
```

No proposal or training job exists yet.

### Gamma — session 1/60, pairs 0/50

```text
✓ Corrupt initial draft repaired
✓ Method contract passed
✓ Proposal approved
⏳ Training 1814273 pending allocation
○ Adapter submission and merge
○ Evaluation and score/finding publication
```

No adapter or score exists yet.

### Delta — session 1/60, pairs 0/50

```text
✓ Undefined-name, processing_class, and regex issues repaired
✓ Method contract passed
⏳ Preparing the first proposal
○ Proposal review, training, evaluation, and publication
```

No proposal or training job exists yet.

### Epsilon — session 1/60, pairs 0/50

```text
✓ Method contract passed
✓ Proposal revision 2 approved
⏳ Approved-run training submission handoff
○ Training and adapter submission
○ Evaluation and score/finding publication
```

The corrected proposal passed data-policy and faithfulness/reproducibility
review. Its deterministic training job has not yet been emitted.

All five research-chain jobs remain running. Alpha/Beta evaluators are running;
Gamma/Delta/Epsilon evaluators are pending GPU resources. Total: **0/250
completed atomic score/finding pairs**.

### 🔴 11:06 PT — STOP/RUNNING: two chains terminal; three remain active

### Alpha — terminal after session 7/60, pairs 3/50

```text
✓ Three score/finding pairs durable
✓ Last scored result: 0.00%; filter and regression passed
✗ Session 7 exhausted 24/24 continuations
✗ Controller classified required_completion_missing as permanent_session_failure
○ No pending adapter or evaluation
```

Chain `1814095` exited with `Error: required successful AAR iterations did not
complete`. The replacement session spun on missing phase contexts after a
recurring `NoneType > int` training failure instead of advancing to session 8.

### Beta — session 12/60, pairs 6/50

```text
✓ Six score/finding pairs durable
✓ Current contract and proposal approved
⏳ Training 1817674 allocated but showing a startup-stall signature
○ Adapter submission and evaluation
○ Score and finding publication
```

The job has only recorded `train.queue_wait`; it has no preflight phase,
adapter, or substantive training output yet despite being allocated for about
22 minutes. Evaluator `1814096` is alive and idle.

### Gamma — session 16/60, pairs 6/50

```text
✓ Six score/finding pairs durable
✓ Previous training, evaluation, and finding completed
✓ Latest result: 22.33%; filter and regression failed
⏳ New method authoring, continuation 2/24
○ Contract, proposal, training, evaluation, and publication
```

Gamma recovered from the prior list/input-shape failure. Evaluator `1814098`
is alive and idle after publication.

### Delta — terminal after session 6/60, pairs 3/50

```text
✓ Three score/finding pairs durable
✗ Session 6 exhausted 24/24 continuations
✗ Controller classified required_completion_missing as permanent_session_failure
○ No pending adapter or evaluation
```

Chain `1814101` exited after the preceding training produced zero valid examples
and its recovery session exhausted continuations diagnosing the generation,
ORPOTrainer, and dataset-format path instead of advancing to session 7.

### Epsilon — session 4/60, pairs 3/50

```text
✓ Three score/finding pairs durable
✓ Current method contract passed
⏳ Proposal-submission checkpoint retry, continuation 5/24
○ Training and adapter submission
○ Evaluation and score/finding publication
```

The proposal checkpoint has stalled twice but remains within its configured
retry path. The earlier post-score Read stall and 5h34m first training both
self-recovered without intervention.

Active chain controllers: Beta, Gamma, and Epsilon. Alpha and Delta are
terminal. Total: **21/250 completed atomic score/finding pairs**.

#### ⏭️ Next step

Finish fail-closed source validation and obtain explicit confirmation of the
documented model-role mapping before any Run 15 model call or Slurm submission.

<a id="run15-event-model-confirmation"></a>

### ✅ 01:45 PT — PASS: exact model-role mapping confirmed

> [!TIP]
> The user confirmed the documented five-chain topology, native generation,
> model/deployment assignments, evaluator stack, and Run 14 stop handoff.

- Researcher/data author: Kimi-K2.6, `steerability_8-kimi26`.
- Target/training base: Gemma 4 31B IT; target calls require thinking.
- Proposal monitor: `claude-4-8-opus` through Meta Model API.
- Evaluator inference: atomically merged candidate plus Gemma 4 31B IT through
  vLLM 0.25.1, four GPUs per chain.
- Evaluator judge: `gpt-5-6-luna`; no AutoData row-judge role.
- Budget: five chains, 50 durable pairs per chain, 60 started sessions per
  chain; AutoData disabled.

Decision: finish source validation and ordered Run 15 lifecycle gates. Preserve
Run 14 artifacts and cancel its remaining jobs only after Run 15 is proven
launch-ready.

<a id="run15-event-generation-budget"></a>

### 🛠️ 01:53 PT — FIX: deterministic target-generation budget added

> [!IMPORTANT]
> Generated methods now fail their source contract before GPU submission when
> synchronous target-model generation is unbounded or exceeds 256 calls.

#### 🔎 Evidence

- Run 14 Epsilon authored 400 prompts × 4 serial target responses: 1,600
  thinking-enabled requests.
- Its smoke executed 32 calls in 137.1 seconds; linear extrapolation is about
  114 minutes before tokenization or training.
- The Run 15 cap of 256 projects to about 18 minutes at that measured rate.

#### 🛠️ Corrective change

- `data_generation.max_sequential_target_generations: 256` resolves to
  `AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS=256`.
- The contract accepts locally bounded literal ranges/slices and bounded
  concurrency, but rejects dynamic sequential loops, `while` loops, and static
  nested products above the cap.
- The shared training submitter is regression-tested to invoke the contract
  before its first `sbatch` call.

#### Validation

- Focused source/config/recovery suite: 72 passed, plus 26 subtests.
- Python compilation, Bash syntax, ShellCheck, and Git whitespace checks passed.

#### ⏭️ Next step

Complete independent source review, commit the exact package, and test that
commit in an isolated HPC checkout without advancing the live Run 14 checkout.

<a id="run15-event-immutable-source-snapshot"></a>

### 🛠️ 02:04 PT — FIX: launch source pinned per attempt

> [!IMPORTANT]
> **Not launched.** The canary and full launch paths now create an independent,
> detached clone of the exact clean commit before endpoint preflight or Slurm
> submission. Later commits in the shared execution worktree cannot change the
> code used by an active attempt.

#### 🛠️ Corrective change

- The source clone lives at `<attempt>/runtime/aar-source`, has no Git remote or
  shared-object alternates, and supplies the scheduled pipeline, config,
  workspace, benchmark documentation, and Python import root.
- The pipeline rejects a non-attempt-local, attached, wrong-commit, remote-backed,
  shared-object, dirty, or externally configured source before child launch.
- Public benchmark sources and reused baseline inputs are copied and revalidated
  under the attempt runtime. `metadata/source-snapshots.json` and its SHA-256
  retain the code-snapshot provenance.
- The worktree-local Python environment remains the explicitly trusted external
  interpreter; imported AAR code remains pinned by `PYTHONPATH` to the snapshot.

#### Validation

- Run 15 setup and shared snapshot tests: 12 passed.
- Bash syntax, ShellCheck, Python compilation, and Git whitespace checks passed.
- Slurm jobs and model calls: none.

#### Lifecycle

```text
✓ Reusable recovery hardening
✓ Exact model-role confirmation
✓ Deterministic target-generation budget
✓ Immutable per-attempt source contract
○ Commit and synchronize exact Run 15 source
○ One-chain lifecycle proof
○ Five-chain topology proof
○ Full five-chain 5×50 launch
```

#### ⏭️ Next step

Commit and synchronize the reviewed source, then exercise the one-chain gate
from that exact revision. Any later model/config change requires reconfirmation.

<a id="run15-event-stopped-one-chain"></a>

### 🔴 02:29 PT — STOP: first one-chain attempt cancelled at user request

- Retained attempt:
  `/checkpoint/ram/aar/winnieyangwn/run15_native_generation/canary_attempts/20261011T091414Z-c6ddf73a6477`
- Pipeline job `1813100` and chain job `1813157` were cancelled.
- The attempt produced no training, evaluation, score/finding pair, or
  lifecycle proof. It remains retained as stopped evidence and is not a pass.

<a id="run15-event-endpoint-replacement"></a>

### ✅ 02:50 PT — PASS: replacement Kimi endpoint verified

- Serve API v2 deployment `autodata2_8-kimi26` reports served model
  `Kimi-K2.6` and passed endpoint health/generation checks.
- The exact AAR harness preflight passed with Kimi thinking disabled, a Bash
  tool roundtrip, MCP literature roundtrip, and forced-tool recovery.
- Claude 4.8 Opus proposal monitoring, GPT-5.6 Luna judging, thinking-enabled
  Gemma target generation, public sources, baseline, secrets, CUDA runtime,
  merge helper, storage, and prior merged-vLLM evidence were also verified.

### 🛠️ 03:07 PT — FIX: endpoint replacement and direct-full override authorized

> [!IMPORTANT]
> The user permanently replaced `steerability_8-kimi26` with
> `autodata2_8-kimi26` for every Run 15 gate and explicitly authorized the
> full five-chain 5x50 launch without either lifecycle proof.

- The proof-gated launch remains the reusable default.
- The direct path requires the exact
  `--user-authorized-without-lifecycle-proofs` flag and writes a mode-400,
  commit-bound override record identifying the scope, endpoint, skipped
  proofs, and retained safety checks.
- The scheduled pipeline validates that record before launching children.

#### Lifecycle

```text
✓ Replacement Kimi endpoint and MCP preflight
✓ Non-Kimi launch dependencies
↷ One-chain lifecycle proof — explicitly bypassed; stopped attempt is not a pass
↷ Five-chain topology proof — explicitly bypassed; no proof claimed
⏳ Commit, exact HPC synchronization, and full submission
○ Five distinct research-chain jobs
○ Five distinct evaluator jobs
○ 250 durable score/finding pairs
```

<a id="run15-event-stopped-forum-alignment"></a>

### 🔴 17:27 PT — STOP: full attempt halted for paper-aligned forum correction

- Cancelled all five research chains, all five evaluators, and the remaining
  training job from attempt
  `/checkpoint/ram/aar/winnieyangwn/run15_native_generation/full_attempts/20261011T233758Z-88949395cbb1`.
- Slurm confirms that none of those eleven jobs remains active. Existing
  attempt artifacts were retained and not deleted.
- Diagnosis: the full-run launcher gave every chain a private forum. The paper's
  standard setting instead gives parallel AARs one shared finding forum and
  leaderboard; private forums correspond to the forum-removal ablation.
- Targeted correction: add validated YAML `research.forum_scope`, default it to
  `shared`, preserve `per_chain` as the explicit ablation, and bind both fresh
  launch and recovery to the same attempt-level forum.

<a id="run15-event-shared-forum-relaunch"></a>

### 🛠️ 17:32 PT — FIX: paper-aligned shared forum and fresh relaunch

#### Important forum conclusion

- The paper's default five-AAR design uses one shared finding forum and
  leaderboard. Each scored result is published before that researcher advances
  to its next proposal, and the published finding includes a method-code
  snapshot that peers can inspect and extend.
- Giving every chain a private forum prevents cross-chain learning and matches
  the paper's forum-removal ablation, not its standard experimental setting.
- Declarative runs now resolve omitted `research.forum_scope` to `shared`.
  `per_chain` remains available only as an explicit no-communication ablation.
- Run 15 explicitly sets `research.forum_scope: shared` and fails closed if the
  resolved setting differs. Fresh launch and recovery bind all five chains to
  the same attempt-level `forum/` directory while retaining separate training
  queues, score directories, evaluators, live method trees, and chain memories.
- Only public findings are shared. Held-out items, evaluator-private details,
  credentials, and unsanitized failure data remain outside the forum.

#### Cleanup and new submission

- Commit `41041df` implemented the forum policy; launch commit `c853678` is its
  synchronized descendant on both the devserver and HPC `autodata` worktrees.
- Deleted both stopped full attempts from HPC checkpoint storage, including
  `20261011T232739Z-88949395cbb1` and
  `20261011T233758Z-88949395cbb1` (1.4 GiB total). The deletion is not
  recoverable. Unrelated Run 12 jobs and outputs were not touched.
- Fresh attempt:
  `/checkpoint/ram/aar/winnieyangwn/run15_native_generation/full_attempts/20261012T003132Z-c853678bf5ce`
- Launch job: `1822364`; source commit: `c853678bf5ce3fc009d9671b5cb2a66947719bab`.
- Kimi endpoint, Bash tool, and MCP round-trip preflight passed. At 17:32 PT,
  the launch job was pending scheduler allocation; child evaluator and research
  job IDs had not yet been emitted, so the five chains were not yet reported
  active.

#### Lifecycle

```text
✓ Endpoint and MCP preflight
✓ Paper-aligned shared-forum configuration
✓ Old Run 15 checkpoint outputs removed
⏳ Infrastructure bootstrap and suite publication — launch job 1822364 pending
○ Five evaluator jobs
○ Five research-chain jobs
○ Method authoring and contract checks
○ Proposal review, training, and evaluation
○ 250 durable score/finding pairs
```
