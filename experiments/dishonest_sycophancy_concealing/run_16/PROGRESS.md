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
