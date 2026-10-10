# Run 12 progress

Last updated: 2026-10-09 16:10 PDT

## Fixed-bootstrap relaunch gate

Commit `6017b58ce4f6fa979ec835de2a7986430848ac1d` was fast-forwarded to the
clean HPC `autodata` worktree. ARM64 validation passed: Ruff reported no
issues and all 69 focused AutoData/Kimi/lifecycle tests passed.

The failed pre-fix attempt was then retired after a final audit still showed
zero durable score/result pairs and no workspace-bootstrap receipt. Its exact
remaining researchers, controllers, evaluators, and five base target
deployments were stopped; its logs, ledgers, and state remain retained.

The launcher now has a fail-closed `bootstrap-canary` mode. It permits exactly
one allowlisted chain seed and one target pair in a separate run/checkpoint
namespace. Canonical `full` mode still requires all five seeds and five target
pairs. The canary will be stopped as soon as it proves that proposal approval
created and registered the native workspace and reached a native AutoData
action; it is not intended to spend a full production data-generation budget.

The first canary submission then failed before GPU allocation at the Kimi MCP
preflight: the healthy shared deployment returned a direct completion quickly,
but the Kimi CLI round trip remained inside one unconstrained 65,536-token turn
for more than eleven minutes. The launcher now caps preflight completion at
4,096 tokens, bounds each scripted tool turn to 180 seconds, and has a 420-second
outer timeout. Production Kimi turns are capped at 16,384 output tokens while
retaining the full 262,144-token context window. This turns malformed or
non-terminating tool behavior into a prompt diagnostic instead of an unbounded
launcher stall.

The next canary reached distinct evaluator/research/controller jobs but the
research job failed in 15 seconds, before Kimi started, because Run 12 had not
exported the now-required trusted training-data contract. The launcher now
derives and validates a per-chain contract from each iteration's campaign
policy before submission. The chain controller atomically regenerates that
contract whenever it rotates the target binding, so generator, judge, and the
current `base + adapter` target provenance remain consistent across outer AAR
iterations.

The following canary's target endpoint became healthy, but its queued launcher
then failed its source-identity gate because a concurrent Run 13 commit advanced
the shared HPC `autodata` checkout between submission and Slurm start. The
checkout was clean; this was coordination drift, not a code failure. Subsequent
Run 12 jobs use a separate immutable checkout at the recorded commit. The next
bootstrap canary may reuse this already-verified base-only endpoint to avoid
another cold start; `full` mode explicitly forbids endpoint reuse and still
creates five isolated chain endpoints.

## Five-chain attempt: proposal bootstrap failure isolated

Attempt `20261009T170629Z-08f3d6a9be40` launched five Kimi researchers and five
healthy evaluator lanes, but produced zero durable score/result pairs. All five
chains remained on outer iteration 1. Kimi could obtain integrity approval,
then repeatedly emitted planning text or malformed tool calls while trying to
create the native AutoData workspace. No workspace, meta execution, production
generation, training, or candidate evaluation began. Beta and Delta exhausted
their eight-attempt controller budgets; Alpha, Gamma, and Epsilon were still
retrying when the failure was diagnosed.

The recovery removes this deterministic infrastructure transition from the
research-model conversation. The shared approval service now creates/resumes
and registers a proposal-bound workspace immediately after approval. The common
agent loop retries the same idempotent bootstrap before either Kimi or Claude
starts, and Kimi continuation prompts consume the retained workspace ID instead
of asking the model to load a skill and rediscover creation commands. Scientific
AutoData actions remain model-driven and all delegated approvals remain signed.

Focused validation: 69 tests passed, including both researcher backends,
idempotent recovery, proposal identity binding, secret non-persistence, Kimi
continuation behavior, native approval binding, lifecycle supervision, plugin
resolution, and recipe contracts.

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
