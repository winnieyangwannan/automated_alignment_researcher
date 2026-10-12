# Run 16 five-chain native-generation lifecycle check

- Status: authorized for topology-only launch with functional-prerequisite waiver
- Created: 2026-10-11 01:49 PT
- Last updated: 2026-10-11 19:05 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 01:49 PT

Prove five parallel Claude Opus 4.8 research chains and their shared training/evaluation
queues with the same bounded native-generation lifecycle used by the one-chain
gate. This is a topology proof, not a scientific result.

## Context

Recorded: 2026-10-11 01:49 PT

This is the ordered gate between the one-chain lifecycle check and the full
Run 16 experiment. It consumes and retains the exact passed one-chain proof;
its own proof records the prerequisite file's SHA-256.

No eligible Run 16 prerequisite proof exists yet. The retained recovery attempt
completed training, evaluation, score publication, finding publication, and
ephemeral-checkpoint cleanup, but its fail-closed proof correctly rejected a
mixed source commit: research began at `384ce75`, while recovered training used
the Serve proxy fix at `6436be8`. It remains functional evidence, not the
prerequisite for this gate.

The shared execution path now includes the operational safeguards established
by the one-chain work: the AAR Bubblewrap wrapper is removed, the current Serve
hostname is added centrally to `no_proxy`/`NO_PROXY`, the advertised method
budget and Slurm training limit are both 15 minutes, and terminal evaluator
failures are not automatically retried with an unchanged adapter.

On 2026-10-11 at 19:08 PT, the user explicitly authorized this topology check
to proceed using the functionally complete mixed-source prerequisite. The
launcher permits that single known failed field only when
`AAR_RUN16_ALLOW_MIXED_SOURCE_PREREQUISITE=1` is supplied, requires every other
one-chain proof field to be true, and retains a machine-readable waiver. This
waiver is scoped to the five-chain topology check and cannot authorize the full
scientific run.

## Launch

Recorded: 2026-10-11 01:49 PT

After synchronizing the final clean source revision and obtaining a fresh
Run 16 one-chain proof from that same revision, launch from the HPC
`autodata` worktree with that exact proof:

```bash
experiments/dishonest_sycophancy_concealing/run_16/canary/five_chain_lifecycle_check/launch/launch.sh \
  <one-chain-attempt>/metadata/canary_passed.json
```

For the user-authorized functional-prerequisite waiver, use the same committed
launcher with the explicit flag:

```bash
AAR_RUN16_ALLOW_MIXED_SOURCE_PREREQUISITE=1 \
  experiments/dishonest_sycophancy_concealing/run_16/canary/five_chain_lifecycle_check/launch/launch.sh \
  <one-chain-attempt>/metadata/canary_passed.json
```

After all five lifecycles finish, create the fail-closed proof:

```bash
python experiments/dishonest_sycophancy_concealing/run_16/canary/verify_run_16_canary.py \
  <five-chain-attempt>
```

## Plan

Recorded: 2026-10-11 01:49 PT

1. Validate the supplied one-chain proof and source ancestry.
2. Start `alpha`, `beta`, `gamma`, `delta`, and `epsilon` together in one
   isolated team, with one research session per chain. All five chains use the
   attempt-level shared forum, while methods, run IDs, receipts, scores, and
   transcripts remain chain-namespaced.
3. Require five proposal-approved, source-bound, real-GPU one-step adapters.
4. Stage all five verified adapters, then start the same single one-GPU
   evaluator used by the one-chain gate to drain the shared queue.
5. Require five two-item `verbalized_ece` scores and five matching findings.
6. Emit a five-chain proof bound to the exact one-chain proof.

## Model and execution roles

Recorded: 2026-10-11 01:49 PT

The role mapping is identical to the one-chain gate: Claude Opus 4.8 model
`claude-opus-4-8` at maximum effort authors the methods and native training data;
`claude-4-8-opus` through Meta Model API reviews proposals; Gemma 4 31B IT is
the fixed training base and the vLLM evaluator base plus each promoted adapter.
`verbalized_ece` is rule-scored, so no evaluator-judge model is used. AutoData
has no generator, probe, judge, broker, workspace, comparator, or export role.
The user previously confirmed this unchanged mapping for both lifecycle gates;
the operational safeguards above do not alter any model role.

## Pass criteria

Recorded: 2026-10-11 01:49 PT

- Normally, the prerequisite is a passed one-chain proof from an ancestor
  commit. The explicitly authorized topology-only waiver may accept a failed
  proof only when `source_commit_consistent=false` and every functional field
  is true.
- The prerequisite and this gate each use one internally consistent immutable
  source revision; mixed-commit recovery evidence is ineligible.
- Exactly five distinct research-chain jobs and five real-GPU smoke proofs
  exist for the five configured seeds.
- The verifier joins findings from the configured attempt-level shared forum to
  scores by exact run ID; it does not rely on aggregate file counts.
- All five exact adapters produce a two-item score and one matching finding.
- The evaluator records the required vLLM 0.25.1, language-model-only, and
  merged-checkpoint markers for every candidate.
- The final proof binds the prerequisite SHA-256 and confirms
  `data_generation.backend=native` / `AAR_AUTODATA=0`.

## Stop criteria

Recorded: 2026-10-11 01:49 PT

Stop on a missing or stale prerequisite proof, any AutoData initialization,
wrong child count, proposal or smoke failure, adapter mismatch, evaluator
failure, or missing score/finding pair.

## Monitoring goals

Recorded: 2026-10-11 19:09 PT

Every operator status report must show all five chains separately, including
started sessions, completed score/finding pairs, completed lifecycle stages,
the current stage, and relevant job IDs. It must also report:

- research concurrency: five distinct chain jobs, their Slurm states, and any
  chain making no substantive transcript or artifact progress;
- training concurrency: queued/running training jobs and proof that no more
  than the configured single training job runs at once;
- evaluator concurrency: zero evaluators before all five GPU smoke proofs and
  exactly one shared one-GPU evaluator afterward;
- rate-limit and connectivity signals: HTTP 403/429 responses, Claude 529
  overloads, Serve/API timeouts, sequential generation-budget exhaustion, and
  any repeated identical request pattern;
- retry health: Slurm restarts, agent-session retries, training resubmissions,
  evaluator retries, and confirmation that a terminally failed adapter is not
  automatically reevaluated;
- code-health signals: exceptions, malformed tool calls, contract failures,
  stale receipts, duplicate run IDs, cross-chain artifact mixing, missing
  failure feedback, or a process that is alive without meaningful progress;
- durable progress: per-chain method, receipt, smoke, score, and finding counts,
  plus the total exact score/finding-pair count out of five.

A status report must distinguish healthy queueing from a hang and bounded
backoff from a retry loop. A failure report must state whether its feedback is
specific enough to guide a correction without exposing evaluator-private data.

## After a pass

Recorded: 2026-10-11 01:49 PT

Review and retain the held-out-safe proof. Only then may the full five-chain
Run 16 launcher be authorized; neither canary score is a scientific result.
