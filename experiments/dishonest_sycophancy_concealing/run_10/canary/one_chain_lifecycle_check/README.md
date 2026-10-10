# Run 10 one-chain lifecycle check

## Goal

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

## Plan

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

Stop without starting or resuming the five full chains if any shared lifecycle
stage fails. A protected-file mismatch, submission-wrapper failure, missing
receipt, or active orchestration incident is an infrastructure failure and must
pause the canary. A generated-method failure may be reported as method-specific,
but the one-session canary must still end as a no-go rather than opening another
research iteration.

## After a pass

Use `../../recovery/resume_run_10.sh` to resume only incomplete seeds in the
preserved attempt. The recovery helper must retain existing methods, scores,
findings, chain memories, and consumed-session counts. Monitoring should report
successful scores, failed attempts, receipts, and per-seed sessions separately.

No canary or recovery job is launched merely by adding this specification.
