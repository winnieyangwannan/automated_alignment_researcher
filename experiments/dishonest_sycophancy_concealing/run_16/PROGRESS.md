# Run 16 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Do not
record credentials, held-out examples, raw evaluator traces, or partial
held-out scores here.

## Visual key

| Symbol | Status      | Meaning                                      |
| ------ | ----------- | -------------------------------------------- |
| ✅     | PASS        | Completed successfully or verified correct   |
| 🔴     | FAIL / STOP | Failed gate or deliberate stop condition     |
| 🐛     | BUG         | A concrete implementation defect identified  |
| 🔎     | OBSERVATION | Important experimental evidence              |
| 💡     | CONCLUSION  | Conclusion supported by current evidence     |
| 🛠️     | FIX         | Corrective change implemented                |
| ⏭️     | NEXT        | Next action or outstanding work              |
| ⏳     | RUNNING     | Work currently in progress                   |

## 2026-10-11

<a id="run16-event-created"></a>

### 🛠️ 01:49 PT — FIX: Run 16 Claude package prepared from Run 15

> [!IMPORTANT]
> **Not launched.** Run 16 preserves Run 15's scientific and execution
> contract while changing only the AAR researcher to Claude Opus 4.8.

#### 🛠️ Corrective change

- Created a separate `run16_native_generation` storage namespace.
- Pinned the research backend to `claude` and model to
  `claude-opus-4-8` at maximum effort in launch, recovery, metadata, and
  documentation paths.
- Replaced Kimi endpoint assumptions with fail-closed Meta Claude CLI,
  secure-internet, bounded-search, and research-isolation checks.
- Preserved five chains, 50 durable pairs per chain, a 60-session ceiling,
  native data generation, ordered canaries, and the Run 15 evaluator stack.

#### Lifecycle

```text
✓ Run 16 source/configuration validation
○ Exact model-role confirmation
○ One-chain lifecycle proof
○ Five-chain topology proof
○ Full five-chain 5×50 launch
○ 250 durable score/finding pairs
```

#### ⏭️ Next step

Finish fail-closed source validation, commit and synchronize the exact source,
then obtain explicit confirmation of the documented model-role mapping before
any Run 16 model call or Slurm submission.

<a id="run16-event-source-validation"></a>

### ✅ 01:52 PT — PASS: source and operator contracts validated

> [!TIP]
> The Run 16 package passed its local fail-closed checks. No model call, Slurm
> submission, recovery action, or external-state mutation occurred.

| Check                           | Result        |
| ------------------------------- | ------------- |
| Full and canary YAML resolution | PASS          |
| Focused Python tests            | PASS: 5 tests |
| Bash syntax                     | PASS          |
| ShellCheck                      | PASS          |
| Python compilation              | PASS          |

```text
✓ Run 16 source/configuration validation
○ Exact model-role confirmation
○ Commit and HPC synchronization
○ One-chain lifecycle proof
○ Five-chain topology proof
○ Full five-chain 5×50 launch
○ 250 durable score/finding pairs
```

#### ⏭️ Next step

Review and commit the focused package, synchronize that exact commit to the
matching HPC worktree, and reconfirm the complete model-role mapping before
launching the one-chain gate.

<a id="run16-event-launch-requested"></a>

### ⏭️ 03:28 PT — NEXT: launch requested; model confirmation required

> [!IMPORTANT]
> The user authorized a Run 16 launch. No model call or Slurm submission has
> occurred because the exact model-role mapping must be explicitly confirmed
> against the committed configuration revision first.

- Intended first gate: one-chain lifecycle check.
- Source worktree: `/home/winnieyangwn/aar-worktrees/autodata`.
- Destination worktree: `/storage/home/winnieyangwn/aar-worktrees/autodata` on
  `fair-cw-use2-1`.
- Planned transfer: direct Git-over-SSH temporary ref followed by a verified
  fast-forward; GitHub is not part of this launch path.
- Full config SHA-256:
  `cc172ce419a1ca7fccf2b200acd49eafb2e6ce2b5c4a1275dd3a5eac8eef113d`.
- One-chain config SHA-256:
  `c003f792f50f26faa0a492510c457132bbbf99b515bcc08dbe429bcdd89a493a`.

#### ⏭️ Next step

Commit and synchronize this exact source, then present the complete role
mapping for explicit confirmation before submitting the one-chain job.

<a id="run16-event-one-chain-startup-failure"></a>

### 🔴 03:37 PT — FAIL / STOP: first one-chain attempt stopped before research

> [!WARNING]
> Pipeline job `1814269` and research-chain job `1814308` are terminal
> `FAILED`. No Claude research session, training job, evaluator job, or score
> was produced. The failed attempt remains retained at
> `/checkpoint/ram/aar/winnieyangwn/run16_native_generation/canary_attempts/20261011T103159Z-ed9053944475`.

- The pipeline published exactly two `verbalized_ece` lifecycle items and
  submitted the one research chain.
- The chain stopped during startup before the research-process marker.
- The pipeline then failed closed because the terminal chain had no matching
  training receipt.

#### 🐛 Root cause

The Claude mount-namespace helper's `add_hidden_mountpoint` function used a
bare `return` when a writable run root was outside the hidden home tree. The
preceding test was false, so Bash propagated status 1; `set -e` terminated the
wrapper silently before `bwrap` started.

<a id="run16-event-sandbox-return-fix"></a>

### 🛠️ 03:46 PT — FIX: sandbox helper accepts external run roots

- Changed the no-mountpoint branch to `return 0` explicitly.
- Added a regression assertion to the sandbox contract tests.
- The next launch must use a fresh attempt directory and must pass the
  compute-node sandbox and real-Claude-launcher probes before research starts.

#### ⏭️ Next step

Validate, commit, synchronize the focused fix, then rerun the one-chain
lifecycle check. Do not advance to the five-chain topology gate until the new
attempt retains the required lifecycle proof.

<a id="run16-event-one-chain-functional-pass-source-drift"></a>

### 🔴 04:45 PT — FAIL / STOP: functional pass rejected for mixed source commits

The fresh one-chain attempt completed its full functional lifecycle with all
jobs at exit code zero:

- pipeline `1814581`;
- Claude Opus 4.8 research chain `1814586`;
- one-step GPU training job `1814698`;
- on-demand vLLM evaluator `1814708`;
- one durable score/finding pair for one started session.

The evaluator proved vLLM `0.25.1`, `language_model_only=True`, and
`lora_strategy=merged_checkpoint`; it retained the merge manifest and removed
the ephemeral merged checkpoint.

This attempt is not eligible as the canonical lifecycle proof. Submission
recorded source commit `7f364115984290c9046684d64085933b67eb2a5f`, while the
later GPU smoke recorded `08011928cada9a9729994f85ed7cede63b5b868a` after the
shared HPC worktree advanced concurrently. The artifacts remain retained at
`/checkpoint/ram/aar/winnieyangwn/run16_native_generation/canary_attempts/20261011T104634Z-7f3641159842`.

<a id="run16-event-immutable-source-recovery"></a>

### 🛠️ 11:33 PT — FIX: immutable-source recovery authorized

The user directed the operator to perform what is necessary to start the
five-chain gate. The recovery adds an attempt-local detached, remote-free,
independent Git snapshot; source-pins the run configuration and reproducible
input copies; and rejects any mismatch between submission and training source
commits. The required sequence remains:

```text
○ Validate and synchronize immutable-source fix
○ Fresh one-chain lifecycle proof
○ Five-chain topology launch
```

<a id="run16-event-model-role-confirmation"></a>

### ✅ 15:02 PT — PASS: model-role mapping explicitly confirmed

> [!TIP]
> The user explicitly confirmed the Run 16 one-chain and five-chain gate
> model-role mapping for one-chain config SHA-256
> `3bf9829363aef17fa5c37aa537bfb612998a35b180a3ac4f7ce32e83497e16ce`.

| Role                         | Confirmed model or execution path                                      |
| ---------------------------- | ---------------------------------------------------------------------- |
| Researcher/data author       | `claude-opus-4-8`, maximum effort, secure Meta Claude CLI              |
| Proposal monitor             | `claude-4-8-opus` through Meta Model API                               |
| Optional target probe        | Gemma 4 31B IT, deployment `winnieyangwn-gemma-4-31B-it`               |
| Training model               | Fixed Gemma 4 31B IT checkpoint plus a new PEFT adapter                |
| Evaluator inference          | Atomically merged candidate through vLLM 0.25.1, language-model-only   |
| Canary evaluator judge       | None; `verbalized_ece` is rule-scored                                  |
| AutoData generator/row judge | Not used; native generation is required and AutoData remains disabled  |
| Trusted orchestration        | Deterministic AAR policy, transport, isolation, and proof-verification |

The authorization covers a fresh one-chain lifecycle attempt and, only after
its fail-closed proof passes, the five-chain topology gate. It does not
authorize the full 5×50 scientific run.

```text
✓ Immutable-source fix
✓ Exact model-role confirmation
○ Fresh one-chain lifecycle attempt
○ One-chain fail-closed proof
○ Five-chain topology gate
```

<a id="run16-event-canary-retry-budget-hardening"></a>

### 🛠️ 15:22 PT — FIX: canary budget and terminal-retry contracts hardened

Live monitoring of the fresh one-chain attempt found two operational contract
risks before its evaluator started:

- the canary training jobs have a 15-minute hard Slurm limit, while the
  researcher prompt inherited a 30-minute method-training budget;
- Run 16 enabled evaluation retries even though a failed candidate is published
  as terminal, its claim is removed, and its retained adapter remains eligible,
  which could repeatedly evaluate the same unchanged failure.

The descendant revision now gives both lifecycle canaries an explicit
15-minute method budget and exports it as `AAR_METHOD_TRAIN_MINUTES=15`. It also
sets `AAR_EVAL_RETRY_FAILED=0`, preserving terminal failure evidence for
diagnosis without an automatic GPU retry loop. These changes do not alter the
confirmed model-role mapping or scientific objective.

The active one-chain attempt remains immutable at commit
`26683f62b1ac89185afbb6e0339c58311e70d7bf`. Its jobs were not modified. The
five-chain gate must launch from this hardened descendant revision after the
one-chain proof passes.

Validation at 15:22 PT:

```text
✓ tests/test_run16_setup.py: 7 passed
✓ one-chain config exports AAR_METHOD_TRAIN_MINUTES=15
✓ five-chain config exports AAR_METHOD_TRAIN_MINUTES=15
⚠ broader config test file: 15 passed, 8 unrelated failures because the
  user-approved Run 14 repository experiment deletion is present in the worktree
```

<a id="run16-event-claude-progress-watchdog"></a>

### 🛠️ 15:37 PT — FIX: Claude heartbeat-only stalls bounded

The immutable one-chain attempt at
`/checkpoint/ram/aar/winnieyangwn/run16_native_generation/canary_attempts/20261011T220338Z-26683f62b1ac`
stopped making substantive progress after reading
`scripts/validate_method_contract.py`. From 15:16 PT onward its transcript
contained only blank Claude SDK `SystemMessage` heartbeats: it created no method,
training job, adapter, submission, score, or finding. At the user's direction,
pipeline job `1820191` and research job `1820223` were cancelled; neither a
training job nor evaluator had started.

The descendant source adds a Claude inactivity watchdog. The configured
`agent.turn_timeout_seconds` now exports the generic
`AAR_AGENT_TURN_TIMEOUT_SECONDS`; Claude resets the 20-minute watchdog on real
SDK/tool progress but not on `SystemMessage` heartbeats. A timeout closes the SDK
client and emits the terminal, non-retryable `claude_progress_timeout` failure.
This bounds the observed failure mode without imposing a total duration limit
on an otherwise active research lifecycle.

The user explicitly authorized deleting only the stopped attempt above and
launching a fresh one-chain canary after this fix is committed, synchronized,
and validated. The deletion and new launch remain operational steps to perform
after synchronization.

Validation at 15:37 PT:

```text
✓ Ruff: all edited Python files passed
✓ 24 focused agent, SDK-compatibility, and Run 16 tests passed
✓ SystemMessage-only regression test proves cleanup and terminal timeout
```

<a id="run16-event-prompt-budget-single-source"></a>

### 🛠️ 15:44 PT — FIX: remove residual hard-coded prompt budget

The first watchdog-enabled one-chain attempt was stopped before method creation
after its resolved prompt exposed a second training-budget statement. The main
contract correctly rendered the configured 15-minute budget, but a later general
guideline still said "30-minute training budget." Pipeline job `1820606` and
research job `1820612` were cancelled after 3 minutes and 1 minute respectively;
no training or evaluator job had started.

The later guideline now renders `method_train_minutes` from the same validated
configuration as the main contract. A source contract test rejects the stale
literal and requires the parameterized statement. The stopped attempt remains
scheduled for the user-authorized deletion after this descendant revision is
synchronized, followed by another fresh one-chain launch.

Validation at 15:44 PT:

```text
✓ 25 focused agent, SDK-compatibility, and Run 16 tests passed
✓ edited Python test file passed Ruff
✓ prompt source contains no hard-coded 30-minute training statement
```

<a id="run16-event-lifecycle-health-monitoring-contract"></a>

### 👀 16:01 PT — MONITOR: lifecycle-health criteria made explicit

The Run 16 README now requires monitoring for code-health signals, genuine
hangs, bounded retries, and actionable held-out-safe failure feedback. Process
liveness alone is insufficient: monitoring must follow substantive transcript
events and lifecycle artifacts through method, smoke, training, proposal,
evaluation, score, and finding.

At this checkpoint, fresh one-chain pipeline job `1820641` and research job
`1820681` are both running with zero Slurm restarts. The Claude researcher is
making substantive tool-driven progress through literature, scoring mechanics,
runtime contracts, and evaluation-format inspection. It has not yet created a
method, training job, adapter, submission, score, or finding. No retry loop or
terminal failure exists. Two jail telemetry-counter connection warnings are
non-fatal and did not prevent the Claude session from progressing.

The five-chain gate remains closed until this one-chain attempt reaches a
terminal state and the fail-closed verifier produces a passing proof.

<a id="run16-event-trusted-python-sandbox-bind"></a>

### 🛠️ 16:40 PT — FIX: expose the trusted runtime inside research isolation

The fresh one-chain attempt reached an approved method but failed before
training submission. The immutable source snapshot correctly used an external
ARM64 virtual environment as `HARNESS_PY`; Claude's mount namespace hid the
entire storage home and did not restore that validated environment. Therefore
`submit_train_job.sh` failed its trusted-Python check before `sbatch` and no GPU
job started. Pipeline `1820641` and research job `1820681` were cancelled with
their method, approved proposal, transcript, and failure evidence initially
preserved. At the user's explicit direction, the stopped 229 MB attempt was
then deleted at 16:41 PT; it is not recoverable from the checkpoint filesystem.

The focused repair restores only the validated virtual-environment root as a
read-only sandbox bind. It does not expose the rest of the storage home or
change prompts, methods, training, evaluation, retry, or scientific policy.
The direct namespace test proves that the interpreter is executable, the
environment remains read-only, run artifacts remain writable, and an unrelated
neighboring home path remains hidden.

Validation at 16:40 PT:

```text
✓ 20 focused sandbox, immutable-snapshot, and Run 16 tests passed
✓ edited Python test passed Ruff
✓ shell syntax and whitespace checks passed
✓ direct Bubblewrap visibility/read-only/isolation proof passed
```
