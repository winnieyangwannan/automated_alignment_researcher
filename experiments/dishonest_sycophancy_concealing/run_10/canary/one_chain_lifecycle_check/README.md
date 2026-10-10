# Run 10 one-chain lifecycle check

- Status: planned; not launched
- Created: 2026-10-10 21:11 UTC
- Last updated: 2026-10-10 21:16 UTC
- Time standard: UTC

## Goal

Recorded: 2026-10-10 21:11 UTC

Prove the current Kimi-backed AAR lifecycle works end to end on the deployed
source revision before any five-chain Run 10 recovery is started. The canary
must be small enough to fail quickly while exercising every boundary that the
full run depends on:

```text
Kimi research
  → bounded file editing
  → proposal approval
  → protected submission validation
  → one-step GPU training
  → adapter validation
  → two-item evaluation
  → score receipt
  → share_finding completion
```

This is an infrastructure and orchestration proof, not a scientific-quality
measurement. Its score is not used to select a method or update the Run 10
frontier.

## Context

Recorded: 2026-10-10 21:16 UTC

The previous Run 10 execution spent substantial time failing before successful
evaluation. This canary checks the combined repairs before five long chains are
resumed. Full incident details remain in the linked, append-only Run 10
[`PROGRESS.md`](../../PROGRESS.md).

### What failed and what changed

Recorded: 2026-10-10 21:16 UTC

- [Kimi tool-selection stalls](../../PROGRESS.md#run10-event-kimi-tool-selection):
  Kimi sometimes narrated an action instead of issuing it. The adapter now uses
  bounded context, milestone-specific continuations, and required named tools at
  exact checkpoints, with a 30-minute whole-process-group turn timeout.
- [Generated-method and proposal replay failures](../../PROGRESS.md#run10-event-full-training-failures):
  incompatible Transformers/TRL, PEFT, data, and import code failed after
  approval, while stale proposal ownership replayed failed candidates. The CPU
  contract gate, source-bound approval, session-scoped ownership, Ruff checks,
  and one-step GPU adapter preflight now reject these defects earlier.
- [Incomplete failure feedback](../../PROGRESS.md#run10-event-failure-feedback),
  [missing terminal markers](../../PROGRESS.md#run10-event-slurm-timeout), and a
  [recovery environment mismatch](../../PROGRESS.md#run10-event-resume-invariant)
  caused retries or indefinite waits. Submission now uses atomic receipts;
  failures are structured and fed back safely; `sacct` reconciles terminated
  jobs; and initial launch and recovery share one validated environment.
- [Evaluator, storage, truncation, and turn limits](../../PROGRESS.md#run10-event-runtime-policy)
  were inconsistent. `config/run.yaml` now defaults durable state to
  `/checkpoint`, maximum evaluator-node memory, a 20% truncation ceiling,
  nonredundant checkpoint retention, and bounded Kimi turns.
- [Shared submission-wrapper corruption](../../PROGRESS.md#run10-event-wrapper-corruption)
  occurred when Kimi replaced `submit_train_job.sh` with `SCRIPT`, causing 14
  approved proposals to fail before training. Kimi `Write`/`Edit` is now confined
  to its ideas tree and memory file; protected files are checked against Git and
  `bash -n`; and wrapper failures publish a team-wide orchestration incident that
  stops further iteration consumption.

The lifecycle check verifies these defenses together, not merely as isolated
unit tests.

## Plan

Recorded: 2026-10-10 21:11 UTC

1. Verify the HPC worktree is on the intended committed `multi_kimi` revision,
   no Run 10 jobs are active, and the preserved full attempt is unchanged.
2. Run the existing zero-GPU gates, including the live Kimi tool protocol. Prove
   that `Write`/`Edit` succeeds inside the canary ideas directory and exact chain
   memory file, while an attempted write to a protected repository script is
   rejected without changing the file.
3. Start exactly one Kimi research chain with a one-session budget and no idle
   evaluator. Require one source-hash-bound proposal approval and one verified
   training receipt.
4. Run the generated method through the existing time-bounded, one-step GPU
   preflight. Require a reloadable PEFT adapter and retain the training receipt,
   method-contract proof, source hash, job ID, and terminal state.
5. Only after training succeeds, start one on-demand evaluator for the existing
   two-item lifecycle suite. Require one successful score file and no evaluator
   runtime failure.
6. Let the original Kimi session consume that score and call `share_finding`
   exactly once. Retain the finding joined to the same run ID.
7. Verify the complete evidence chain and issue a single go/no-go decision for
   selective Run 10 recovery.

## Pass criteria

Recorded: 2026-10-10 21:11 UTC

The canary passes only when all of the following are true:

- the protected script remains byte-identical to its committed Git blob;
- the Kimi write boundary allows both intended destinations and blocks the
  protected destination;
- exactly one research session, proposal, training submission, and training
  receipt are present;
- protected submission files pass their Git hash and shell-syntax checks;
- the GPU preflight produces a structurally valid, reloadable adapter;
- the on-demand evaluator produces one successful score for that adapter;
- one `share_finding` result references the same run ID;
- no `.orchestration_incident.json` is active for the deployed revision; and
- no canary job remains running after evidence collection.

## Stop criteria

Recorded: 2026-10-10 21:11 UTC

Stop without starting or resuming the five full chains if any shared lifecycle
stage fails. A protected-file mismatch, submission-wrapper failure, missing
receipt, or active orchestration incident is an infrastructure failure and must
pause the canary. A generated-method failure may be reported as method-specific,
but the one-session canary must still end as a no-go rather than opening another
research iteration.

## After a pass

Recorded: 2026-10-10 21:11 UTC

Use `../../recovery/resume_run_10.sh` to resume only incomplete seeds in the
preserved attempt. The recovery helper must retain existing methods, scores,
findings, chain memories, and consumed-session counts. Monitoring should report
successful scores, failed attempts, receipts, and per-seed sessions separately.

No canary or recovery job is launched merely by adding this specification.

Operational updates belong in the append-only [`PROGRESS.md`](PROGRESS.md), not
in this specification. Machine-readable evidence belongs in the durable canary
attempt directory under `/checkpoint`.
