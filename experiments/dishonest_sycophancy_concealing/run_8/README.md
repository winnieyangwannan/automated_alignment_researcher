# Run 8: AAR-driven Autodata generation

Run 8 will make Autodata a real data-generation tool inside the AAR research
loop for the dishonest/sycophancy/concealing workflow. AAR chooses and approves
the method; Autodata executes the approved generation plan, records provenance,
and returns a verified dataset; the AAR training job consumes that dataset
before the validated vLLM evaluation path.

The unattended deterministic integration and the production launcher are
implemented. The launcher resolves the qualified `winnieyangwn-kimi26`
deployment, starts the canonical AutoData broker and live AAR adapter in a
separate CPU Slurm job, then starts one sequential two-iteration chain and one
four-GPU vLLM 0.25.1 evaluator. It is intentionally not submitted by the
implementation change. The detailed architecture, validation sequence, and
launch gates are in
[autodata_plan.md](autodata_plan.md); retained test evidence is in
[progress.md](progress.md).

## Production submission

Run only from the synchronized, clean HPC `autodata` worktree after installing
the authorized Firecracker Runner bearer at
`/storage/home/winnieyangwn/aar-worktrees/autodata/.sandoq-firecracker-token`
as an owner-owned mode-0600 file. The profile freezes 64 retained SFT rows per
iteration, concurrency 4, and one $100 campaign cap across both iterations.
The conservative accounting defaults are $1/M input tokens and $4/M output
tokens for both Kimi and Luna. The launcher derives the maximum task
reservation from the frozen input/output token ceilings, those rates, and the
three-attempt request limit; it is not a separately configurable flat fee. The
current controls derive a $0.049152 ceiling. Providers return token usage but no
billable cost. The submitter verifies that the cap covers two worst-case
reservations (898 task attempts per iteration at the frozen row target).

```bash
cd /storage/home/winnieyangwn/aar-worktrees/autodata
bash experiments/dishonest_sycophancy_concealing/run_8/submit_run_8.sh
```

Secrets remain in mode-0600 files. Only their paths and non-secret run controls
enter Slurm submission metadata. The adapter token and broker token are minted
under the retained attempt directory, and both iteration run IDs debit the same
attempt-scoped budget ledger. Static checks are available with:

```bash
pytest tests/test_run8_launcher.py
```

Every newly generated Run 8 artifact is confined to the submitting user's HPC
storage tree, never `/checkpoint/ram`:

```text
/storage/home/$USER/aar-runs/
  honesty-sycophancy-concealing-gemma4-31b-vllm-v0/
    run8_attempts/<UTC timestamp>-<Git commit>/
```

The submitter resolves the root and fails unless it is inside
`/storage/home/$USER/aar-runs`; symlinked artifact parents are rejected. Existing
baseline, model, literature, and evaluator-program files may be read from shared
checkpoint paths, but Run 8 treats them as immutable and does not write its
attempt, AutoData, model, evaluation, log, temporary, or metadata outputs there.

## Required architecture

```text
AAR method + AUTODATA_SPEC
  -> integrity-monitor approval and immutable run_id
  -> AAR Autodata MCP tools
  -> operator-owned AAR-Autodata adapter
  -> Autodata main ExecutionEngine
  -> native autodata-broker / SandoQ Firecracker execution
  -> verified AAR dataset
  -> AAR training and evaluation
```

Autodata does not choose the domain. Run 8 must use an AAR-owned generation
recipe for the configured safety axis. It must not use legal documents, the
historical `legal-os/paper-baseline` recipe, the old `sandoq_fleet` director, or
the deterministic `programmatic_contract_smoke` generator as scientific data.

## Framework pin

The canonical Autodata checkout is on `main` at
`9e623eb25bab4c4ba50642f72ca338f887772e27` in both locations:

- `/home/winnieyangwn/autodata_pipelines`;
- `/storage/home/winnieyangwn/autodata_pipelines`.

Both were clean when the plan was written. GitHub was bypassed for the HPC sync.
The local `origin/main` points to this commit, but a fresh GitHub fetch was
blocked by the development environment's destination filter. Production must
either refresh upstream through an approved path or explicitly retain this
reviewed commit.

## Integration status

The AAR research agent now has `autodata_generate`, `autodata_step`,
`autodata_status`, `autodata_action_begin`, `autodata_action_complete`,
`autodata_action_fail`, and `autodata_fetch`. The durable AAR-facing adapter
binds requests to the approved method, proposal `run_id`, framework revision,
resource profile, retained-row requirement, and campaign budget scope.

The deterministic adapter backend has completed the canonical native workspace
workflow, `meta_optimize`, production, strict fetch, and dataset-consumption
receipt through one real `AutonomousAgentLoop` session without a human pause.
This is orchestration evidence, not scientific training data.

The AAR-owned live recipe, native `SandoQFirecrackerExecutor` and
`autodata-broker` wiring, and qualified Kimi route are implemented. Production
submission still requires the authorized Firecracker Runner token at the
mode-0600 path above. The launcher then fails closed unless the canonical
broker's native image/lease canary passes before the adapter or AAR chain
starts. A second pre-chain canary then runs one real qualified Kimi generation
and Luna judgment inside the Firecracker workload and retains only safe usage
and provenance. The retained evidence still does not
claim a complete live Kimi/Luna generation, training, or isolated evaluation
iteration; those are outcomes of the unlaunched production chain.

The adapter's live backend fails closed when routes, credential references,
metered usage, or the shared campaign budget are incomplete. Required mode also
blocks training without verified artifacts and blocks submission when the method
did not create a matching dataset-consumption receipt.

The preconfigured Run 8 resource profile fixes `Kimi-K2.6` as generator and
`gpt-5.6-luna` as judge. The operator authorizes one campaign-wide
`max_cost_usd` before any loop starts; it covers every parallel AAR chain and
all of their iterations and does not reset for each chain, proposal, or dataset.
Every Autodata Kimi and Luna request is charged to the same AAR ledger and
tagged with its chain and per-iteration `run_id`. Unused iteration reservations
return to the campaign balance. Low-level aggregate call, token, and
task-attempt ceilings are derived or retained as fallback guardrails instead of
being separate budgets the operator must tune manually.
Credentials, routes, and secret values remain outside the agent.

Run 8 also uses two non-financial controls with different meanings:

- `max_concurrency: 4` permits at most four Autodata source-task attempts to run
  at once. It is not the number of AAR iterations or a training batch size.
- `required_retained_rows` is the minimum number of final accepted, validated
  training examples for a particular execution. It is an output requirement,
  not a native Autodata budget or the `meta_optimize` batch size. Run 8 uses
  production mode; model-training minibatches are configured separately.

Earlier two-row and 16-row designs were test-only proposals and are not launch
gates for Run 8. The mandatory pre-chain model canary performs exactly one Kimi
generation and one Luna judgment without publishing training rows. Each real
AAR iteration then requires 64 accepted SFT rows; the agent cannot lower that
frozen target to claim that a shorter generation succeeded.

The profile retains a wall-clock deadline and per-call output-token ceiling so
a stalled task or one malformed response cannot run indefinitely even when
money remains. The research agent cannot replace either model or expand these
limits.

## Validation order

Validation progresses in this order:

1. unit contract and security tests — passed;
2. deterministic local AutoData engine and live AAR-agent integration — passed;
3. one real Kimi generation plus `gpt-5.6-luna` judgment inside native SandoQ,
   wired as a mandatory pre-chain gate;
4. first 64-row production generation through the AAR MCP tools and one
   complete AAR proposal-to-evaluation iteration;
5. a second sequential 64-row iteration with a distinct proposal run ID.

Run 8 is not considered successful merely because Autodata independently emits
rows. The accepted evidence is an AAR iteration that calls Autodata after method
approval, fetches a run-bound verified dataset, records that the training job
consumed its digest, and produces the normal AAR score/result pair.

## Current operational state

The retained final smoke used a real bounded `AutonomousAgentLoop` session to
initiate workspace creation and call the normal AutoData MCP tools. It completed
native meta-optimization followed by production, fetched 10 deterministic SFT
rows, and loaded them through the method API with a matching consumption
receipt. The focused AAR integration suite has 25 passing tests; the canonical
AutoData suite has 57 passing tests and one skip. After the production driver,
completion verifier, secret boundary, and storage hardening were integrated,
the focused production suite passed 63 tests and the complete AAR `tests/`
suite passed 269 tests plus 35 subtests.

The exact `gpt-5-6-luna` route passed a real API preflight. The exact
`winnieyangwn-kimi26` deployment serves `Kimi-K2.6` and passed a qualified
host-side completion through the FAIR gateway; friendly unqualified model
aliases remain invalid. A native broker canary reached the Firecracker
execsidecar and correctly failed on the placeholder runner bearer, motivating
the launcher's strict external token-file gate. No live Kimi/Luna SandoQ
production dataset or legal data was generated. See [progress.md](progress.md)
for exact IDs, digests, commands, and limitations.

The evaluator is the validated four-GPU vLLM 0.25.1 merged-checkpoint path, but
this launcher uses the existing same-user functional-evaluation mode. It is
real scoring and produces score/result pairs; it is not kernel-enforced
research/evaluator principal isolation and must not be presented as such.
