# Run 17 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). This
log contains orchestration metadata only; never record generated rows, prompts,
responses, credentials, or held-out content.

## 2026-10-11

<a id="run17-event-canary2-setup"></a>

### ⏳ 15:20 PT — PREPARING: Canary 2 Claude role replacement

> [!NOTE]
> Setup and validation are in progress. No Run 17 job has been submitted.

The requested goal is the Run 12 Canary 2 production-to-training lifecycle with
both Kimi roles replaced: the researcher uses Claude Opus 4.8 through the
API-backed Meta Claude CLI, and the AutoData generator/teacher uses Claude Opus
4.8 through Meta Model API Responses.

```text
⏳ Source, configuration, and launcher corrections
○ Source commit and HPC synchronization
○ Explicit full model-role confirmation
○ Exact Claude/Gemma/Luna broker proof
○ Launcher and research allocation
○ Workspace authoring and freeze
○ Canonical baseline and meta iterations 1–3
○ Production and verified handoff
○ One-step training smoke
```

Jobs: none. Attempt: not created. Decision: continue setup; do not launch yet.

<a id="run17-event-local-validation"></a>

### ✅ 15:27 PT — PASSED: local configuration and launcher validation

The provider-neutral run configuration, pinned Model API Responses route,
source-pinned proof wrapper, and shared Run 12 lifecycle launcher passed focused
unit, static contract, shell syntax, and configuration-inspection checks.

Jobs: none. Attempt: not created. Decision: commit and synchronize the focused
change set, then request explicit model-role confirmation before any proof or
canary submission.

<a id="run17-event-sync-preflight"></a>

### ✅ 15:28 PT — PASSED: synchronization preflight

Requested destination: `/storage/home/winnieyangwn/aar-worktrees/autodata` on
`fair-cw-use2-1`. Source: `/home/winnieyangwn/aar-worktrees/autodata`. Both
worktrees are on branch `autodata`, represent the same repository, and began at
`15e90f46290bf550ee8a4efc5b828d0f65233cbf`; the HPC tracked worktree was clean.
No queued or running Slurm job with `run17` in its job name was present.

Planned transfer: commit only the focused Run 17 setup, push that exact commit
over direct Git-over-SSH to a unique temporary `refs/aar-sync/` ref, require an
ancestor-verified fast-forward, check every incoming path against preserved HPC
local state, verify the final branch and SHA, and delete only that temporary
ref. GitHub is not part of this transfer.

<a id="run17-event-proof-path-correction"></a>

### ⚠️ 15:31 PT — CORRECTED: pinned AutoData checkout materialized

The first proof command stopped before Slurm submission because its expected
AutoData worktree path did not exist on HPC. No attempt or job was created. The
exact clean AutoData commit `28a9c22125dc0cf101ebabc1b22408b4e974678a`
was transferred directly from its clean devserver worktree and materialized as
the detached HPC worktree
`/storage/home/winnieyangwn/autodata-worktrees/judge-repair-28a9c22`, restoring
the source-pinned path already enforced by the launch wrappers.

<a id="run17-event-canary2-launched"></a>

### 🚀 15:47 PT — RUNNING: Canary 2 research chain launched

The first retained broker-proof attempt at
`/checkpoint/ram/winnieyangwn/aar-runs/run17-adapter-target/20261011T223441Z-d5f4a29a367b`
failed closed after the Claude generator and Gemma target succeeded because the
GPT-5.6 Luna judge returned HTTP 429. Job `1820593` and its evidence remain
immutable.

The fresh proof root
`/checkpoint/ram/winnieyangwn/aar-runs/run17-adapter-target/20261011T224036Z-71fddb500dc4`
passed endpoint preflight job `1820609` and full Claude/Gemma/Luna broker-proof
job `1820614`. Later source changes through
`384a144bd495351c4abe92ba78b67dc6b5409402` did not change any proof-relevant
code or configuration and passed a clean focused validation snapshot.

Main attempt:
`/checkpoint/ram/winnieyangwn/aar-runs/run17-bootstrap-canary/20261011T224631Z-384a144bd495`.
Launcher job `1820659` emitted alpha research-chain job `1820679` and dependent
controller job `1820680`. No evaluator was submitted, as required by the
training-smoke boundary. The launcher froze immutable AAR and AutoData source
snapshots before submission.
