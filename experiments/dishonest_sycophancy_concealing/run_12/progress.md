# Run 12 progress

Last updated: 2026-10-09 10:05 PDT

## Full-run launch gate: failed fast and fixed

Attempt `20261009T161919Z-1ae4a3ed13bb` successfully launched five Kimi
research jobs, five isolated local-Bubblewrap brokers, and five four-GPU vLLM
0.25.1 evaluator lanes. All five researchers reached Session 0. Epsilon was the
first to obtain an approved proposal, after 711 seconds.

That approval exposed a deterministic ordering bug. The Kimi wrapper called
`submit_train_job.sh` immediately when `submit_idea_proposal` returned approved.
AutoData policy deliberately forbids creating a workspace before proposal
approval, so the required production handoff could not yet exist. The training
preflight therefore failed closed with `run-scoped AutoData directory is
missing or unsafe`. The controller correctly retried outer iteration 1, but the
retry minted a new proposal identity and restarted literature review instead of
resuming the approved AutoData run.

The relaunch fix now:

- defers deterministic training submission until
  `$TEAM_DIR/autodata/<run_id>/training-handoff.json` exists;
- drives Kimi into the native AutoData workflow immediately after approval;
- keeps a stable proposal identity across retries of the same outer iteration;
- injects explicit resume context for an approved but incomplete AutoData run;
- starts a new proposal identity only after a durable score/result pair advances
  the outer iteration; and
- includes the exact statically verifiable AutoData loader signature in the
  researcher prompt, avoiding repeated contract-discovery rejections.

The faulty attempt is retained for diagnosis but will not be counted as a Run
12 result. Focused devserver validation after the fix: 48 tests passed; shell
syntax and diff checks passed. HPC validation and a clean relaunch follow.

## Adapter-routing proof: passed

Run 12 proved the complete iteration-2 route with a newly produced Run 12
adapter, not the older Run 7 stand-in:

- candidate run ID: `gemma4_31b-explore-canary-1791553866-gemma4_31b_explore_canary__kimi_candidate-1791555168973`;
- adapter SHA-256: `acbefeb10076fa7136c96d4fd09857e7e82214694980c175c74c6cbeda73c112`;
- score: headline `0.45`, `passes_filter=true`, `passes_regression=true`;
- merged checkpoint: 13 shards and `62,546,336,448` weight bytes;
- research deployment: `winnieyangwn-run12-canary-iter2`;
- binding checkpoint identity: `sha256:17e55ba9e4164c586a80ba46c492031c0d7c9d2ceef709fafbcecaf1106aae06`.

Endpoint preflight job `1788027` succeeded in 5.075 seconds, including a
4.71-second deterministic generation. Native AutoData canary job `1788068`
then completed exactly three model calls in order: Kimi generator, promoted
Gemma target, and Luna judge. The target call recorded the expected deployment,
checkpoint identity, incumbent run ID, and AAR iteration 2.

The single row was rejected as `target_not_challenging` with quality `1`,
challenge `0`, and valid `0`. That is a useful data-quality outcome, not an
infrastructure failure: the exact promoted adapter was attached and invoked.

## Failure caught during the canary

The canary candidate's own method initially called the Serve API helper with an
invalid positional signature, swallowed the resulting exception, and trained
on two canned fallback rows. The candidate still passed the small evaluator,
so this was a real fail-open risk. The production contract now:

- permits only positional `messages` plus supported keyword arguments;
- forbids Python `chat_template_kwargs` and unsupported decoding arguments;
- rejects broad exception handling around target generation; and
- requires target-generation errors to propagate rather than silently using
  fallback training data.

The canary proves attachment and routing. It does not validate that candidate's
proposed data-generation method.

## Final five-by-five implementation

The production launcher now implements five independent Kimi research chains,
each targeting five durable score/result pairs. Each chain owns:

- a separate team directory and persistent `AGENT_LOG`;
- an isolated AutoData broker ledger, native state, workspaces, and proposal bindings;
- one evaluator lane;
- a retained merged-candidate directory; and
- its own versioned Gemma research deployment and binding history.

Every outer iteration is one bounded research job. After it produces a durable
score/result pair, a trusted chain controller selects the best valid adapter,
uses the evaluator's retained atomic `base + adapter` merge, launches and tests
a new immutable endpoint, creates the next iteration binding, rewrites the
broker campaign policy atomically, retires the previous backend, and only then
starts the next research job. If no candidate passes the promotion gates, the
controller correctly retains the previous verified parent.

The final researcher and AutoData generator both route to the validated
multi-replica `aar_8-kimi26` deployment. The five Gemma target lanes remain
chain-specific. AutoData concurrency is eight per chain, for at most forty
simultaneous tasks across the five chains; this is a deliberately safer first
production setting than five times sixteen.

## Validation

- Devserver focused tests: 23 passed plus 5 parameterized subtests.
- Shell syntax checks: passed.
- HPC ARM64 tests and Ruff: pending synchronization of the final launcher commit.
- Full launch: pending the final HPC validation gate.

## Timing and bottleneck tracking

Each chain writes controller events, research phase timings, AutoData state,
broker logs, evaluator timings, endpoint identities, and Slurm job IDs beneath
`chains/<seed>/` and its team directory. This allows the final report to split:

- research reasoning;
- AutoData approvals;
- meta-optimization;
- production generation;
- training queue and training;
- evaluator queue, adapter merge, model startup, and scoring; and
- promoted-endpoint startup.

The previous Run 9 measurements showed the broker tasks themselves were fast
but the host controller left the broker idle for most of the generation span.
The final run preserves the SQLite write fix and local Bubblewrap execution;
the retained timing data will show whether remaining time is provider latency,
AutoData scheduling gaps, acceptance-rate expansion, or evaluator/model startup.
