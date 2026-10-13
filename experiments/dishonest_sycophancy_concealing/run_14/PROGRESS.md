# Run 14 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Do not
record credentials, hidden examples, evaluator-private traces, or partial
held-out scores.

## Visual key

| Symbol | Status      | Meaning                                      |
| ------ | ----------- | -------------------------------------------- |
| ✅     | PASS        | Completed successfully or verified correct  |
| 🔴     | FAIL / STOP | Failed gate or deliberate stop condition     |
| 🔎     | OBSERVATION | Important experimental evidence              |
| 🛠️     | FIX         | Corrective change implemented                |
| ⏭️     | NEXT        | Next action or outstanding work              |

## 2026-10-12

<a id="run14-event-opus5-canary-prepared"></a>

### 🛠️ 23:46 PT — FIX: Opus 5 comparison package prepared

> [!IMPORTANT]
> **PREPARED, NOT LAUNCHABLE, NOT LAUNCHED.** The declarative Run 14 canary
> preserves the Run 13 Trial 14 AutoData loop and changes the two requested
> model roles to Opus 5. Existing Run 13-only launch guards remain intact.

```text
✓ Reference configuration inventoried
✓ Opus 5 Model API catalog identity discovered
✓ Run 14 declarative configuration prepared
✓ Configuration-parity contract added
○ Run 14 runtime launcher and recovery fences
○ Exact Claude CLI Opus 5 preflight
○ Explicit model-role confirmation
○ Canary submission
○ Meta-optimization
○ Production
○ Training smoke
```

- Reference source commit: `cf801547196f52a92a139434e52cc0377e02ceaa`.
- Researcher intent: `claude-opus-5` through
  `meta-claude-cli-opus-5`, maximum effort.
- Generator identity discovered in the live Model API catalog:
  `claude-5-opus`; logical deployment `meta-model-api-claude-5-opus`.
- Unchanged row judge: `gpt-5-6-luna`.
- Unchanged target/training base: `gemma-4-31B-it`.
- Jobs: none.
- Attempt: none.
- Decision: no-go until runtime enablement, preflight, and explicit role
  confirmation are complete.

<a id="run14-event-opus5-launch-path-validated"></a>

### ✅ 23:55 PT — PASS: source launch path validated

> [!TIP]
> **SOURCE READY; NOT LAUNCHED.** Run 14 now has a thin operator wrapper,
> source-pinning host launcher, scheduled pipeline, and chain controller. The
> shared recovery and authoring coordinators explicitly allow only the exact
> Run 14 Opus 5 identity while retaining existing Run 13 behavior.

```text
✓ Declarative configuration parity
✓ Run 14 recovery-manifest validation path
✓ Run 14 host launcher and immutable source snapshots
✓ Run 14 Slurm pipeline and chain controller
✓ Claude tool-ownership and lifecycle-supervisor allowlists
✓ Exact Claude CLI model identity present locally
○ External Opus 5 provider/target proof
○ External Run 14 recovery manifest
○ Explicit model-role and source-revision confirmation
○ Canary submission
○ Meta-optimization
○ Production
○ Training smoke
```

- Jobs: none.
- Attempt: none.
- Model calls: none.
- Decision: source implementation passes focused validation; remain no-go until
  the external proof/manifest are prepared and the exact launch mapping and
  source revision are explicitly confirmed.

<a id="run14-event-hpc-sync-deferred"></a>

### 🔴 23:58 PT — STOP: HPC worktree synchronization deferred

> [!WARNING]
> The matching HPC `autodata` worktree is an active execution checkout. It was
> not advanced while jobs were using it.

- Request: synchronize the committed Run 14 launch package from
  `/home/winnieyangwn/aar-worktrees/autodata` to
  `/storage/home/winnieyangwn/aar-worktrees/autodata` on `fair-cw-use2-1`.
- Branch: `autodata` in both worktrees.
- Devserver pre-change HEAD: `655e2ee011deee369163a6b46a09c8f97ba5852b`.
- HPC pre-transfer HEAD: `9fefddeb81367b3f5a8c63ad5c2717322422e9cd`.
- Intended transfer: exact commit through a unique temporary `refs/aar-sync/`
  ref over direct Git-over-SSH, followed by collision checks and `--ff-only`.
- HPC-local untracked state preserved: `.aar-method-contract.json`.
- Result: no transfer attempted because active Slurm jobs reference the HPC
  worktree directly. Re-run the synchronization preflight after it is idle.

## 2026-10-13

<a id="run14-event-launch-authorized"></a>

### 🔎 00:04 PT — OBSERVATION: launch authorized and preflight resumed

> [!IMPORTANT]
> The user authorized launch and monitoring after the complete role mapping was
> restated: Claude Opus 5 researcher/monitor, Claude Opus 5 AutoData semantic
> optimizer and generator/challenger, GPT-5.6 Luna row judge, and Gemma 4 31B
> IT target/training base.

- The canonical HPC `autodata` checkout remains active and will not be
  advanced under running jobs.
- Plan: transfer the exact committed source to an isolated clean HPC checkout
  on branch `autodata`, create its ARM64 environment on a GPU node, and launch
  from that source-pinned checkout.
- Healthy reusable target: `winnieyangwn-r12-alpha-i1-c0dab4f7`; gateway
  registration and direct `serve.sh test` passed.
- Added a narrow Run 14 provider-proof wrapper for the exact Opus 5/Gemma/Luna
  configuration. Focused proof and Run 14 tests: `16 passed`.
- No Run 14 job or model call had been submitted at this checkpoint.

<a id="run14-event-launch-blocked-model-api-spend"></a>

### 🔴 00:14 PT — STOP: Opus 5 Model API spend limit blocked launch

> [!WARNING]
> **NOT LAUNCHED.** The retained provider proof failed closed before the main
> Run 14 submission because the configured Model API key has exhausted its
> `claude-5-opus` spend limit.

- Source commit: `d103a569ce7d8fca6cb348fa43b636b2dea0572a`.
- Isolated HPC checkout:
  `/storage/home/winnieyangwn/aar-worktrees/run14-autodata-d103a56` on branch
  `autodata`; the active canonical checkout was not changed.
- ARM64 environment job `1865734`: `COMPLETED`; NVIDIA GB300 visible, PyTorch
  CUDA enabled, CUDA matrix multiplication passed, and focused HPC tests
  reported `142 passed, 2 subtests passed`.
- Reused target `winnieyangwn-r12-alpha-i1-c0dab4f7`: gateway registration,
  direct service smoke test, and proof preflight job `1865742` passed.
- Provider proof root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run14-adapter-target/20261013T070855Z-d103a569ce7d`.
- Provider proof job `1865765`: `FAILED` after five configured generator
  attempts, all HTTP 429 with `reason_code=provider_http_429`.
- A minimal direct Model API diagnostic confirmed `claude-5-opus` is present
  in the key catalog and returned `rate_limit_exceeded`: `Spend limit exceeded
  for this model.`
- Verified external recovery manifest:
  `/storage/home/winnieyangwn/aar-recovery/run14_20261013T070840Z-d103a56/preautodata-recovery-manifest.json`.
- Jobs remaining for Run 14: none. Main canary attempt: none.
- Recovery: raise/reset the configured key's `claude-5-opus` spend limit or
  provide another authorized `MODEL_API_KEY` with access and budget, then
  regenerate the provider proof before launching. Do not switch protocol or
  gateway without treating it as an experimental change.
