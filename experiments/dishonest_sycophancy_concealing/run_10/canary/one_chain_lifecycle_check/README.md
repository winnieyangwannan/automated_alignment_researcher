# Run 10 one-chain lifecycle check

- Status: planned; not launched
- Created: 2026-10-10 21:11 UTC
- Last updated: 2026-10-10 21:14 UTC
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

Recorded: 2026-10-10 21:14 UTC

The previous Run 10 execution exposed failures at several lifecycle boundaries.
Most of the elapsed time was spent before a candidate reached successful
evaluation, so immediately resuming five long chains would risk repeating
expensive failures in parallel. The event-level source chronology remains in
the parent Run 10 [`PROGRESS.md`](../../PROGRESS.md).

### Failures observed

- Recorded: 2026-10-10 21:14 UTC
- Source-event window: 2026-10-09 00:36 UTC through 2026-10-10 20:53 UTC

- Generated methods passed proposal review but failed during training because
  they used incompatible Transformers/TRL APIs, invalid PEFT targets or data
  conversion, missing imports, and other code that was syntactically valid but
  incompatible with the locked runtime.
- A persistent approved-proposal marker made later sessions replay an already
  failed candidate instead of revising it. Some chains consequently consumed
  many research sessions without producing a new score.
- Training failures initially produced only generic process-exit information.
  Kimi could not see the concrete safe error, and a Slurm `TIMEOUT` could kill a
  job before its shell exit trap wrote any failure marker, leaving the chain
  waiting indefinitely.
- Recovery initially omitted the `AAR_NO_LOCAL_GPU=true` invariant. Approved
  proposals therefore failed to mint run IDs or training receipts, and five
  resumed chains exhausted continuation turns without reaching training.
- Evaluators inherited insufficient 64-GiB memory and stale truncation policy,
  while write-heavy state and redundant checkpoint copies accumulated under
  `/storage/home`.
- Kimi sometimes narrated future tool use instead of issuing a structured call,
  expanded discovery context excessively, or launched an unbounded filesystem
  scan. These behaviors delayed proposal completion and could hold a chain for
  a long time.
- Most recently, one Kimi `Write` call replaced the shared
  `scripts/submit_train_job.sh` with the six-byte text `SCRIPT`. Fourteen
  approved proposals then failed before training with `SCRIPT: command not
  found`. Because the wrapper failure was treated as an ordinary research
  failure, the shared corruption could consume additional sessions across
  chains rather than pausing the run.

### Changes made

Recorded: 2026-10-10 21:14 UTC

- The method-contract gate now imports and dry-runs candidates, checks the
  installed Transformers/TRL constructor contracts, rejects known incompatible
  trainer and PEFT patterns, runs target-environment Ruff undefined-name checks,
  and binds approval to the candidate source hash.
- Every full-run method must pass a time-bounded, one-step GPU preflight that
  saves and reload-validates its PEFT adapter before full training or evaluation.
- Proposal ownership is scoped to the session that submitted it. Deterministic
  adapter-controlled submission writes an atomic run-ID-to-Slurm-ID receipt and
  makes retries idempotent instead of relying on model-authored shell output.
- Training and evaluator failures are structured, secret-redacted, and
  held-out-safe. The next Kimi session receives the latest unscored method
  failure, while receipt reconciliation against `sacct` publishes a terminal
  marker when Slurm kills a job before the shell trap runs.
- Initial launch and selective recovery now source the same Run 10 environment.
  The reusable recovery helper refuses duplicate active chains, preserves state,
  subtracts already-started sessions, and replenishes only missing evaluators.
- `config/run.yaml` moves new durable state to `/checkpoint`, requests all
  evaluator-node memory, sets the explicit 20% truncation ceiling, removes
  redundant checkpoint retention, and bounds Kimi turns to 30 minutes with
  whole-process-group termination.
- Kimi uses bounded MCP responses, a system profile without competing goal or
  subagent tools, milestone-specific continuation prompts, and required named
  tool selection at exact checkpoints.
- A fail-closed Kimi hook now permits direct `Write`/`Edit` only inside
  `AAR_IDEAS_DIR` or the exact chain memory file. Immediately before submission,
  the adapter compares protected files with their committed Git blobs and runs
  `bash -n` on protected shell scripts.
- A protected-file mismatch, wrapper timeout or failure, or missing verified
  receipt now publishes `.orchestration_incident.json`. The detecting chain
  stops without retry backoff, and peer chains stop before another session or
  training submission instead of spending more research iterations.

This canary is intended to verify that these changes work together as one
complete lifecycle, rather than proving each fix only in isolation.

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
