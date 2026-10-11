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
