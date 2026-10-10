# Run 12 progress

Last updated: 2026-10-09 16:10 PDT

## Checkpoint-backed production resume

The production entrypoints now default to `/checkpoint/ram/$USER` and fail
closed if an operator supplies any other storage root. Existing Run 12 output
was moved out of `/storage/home`, with compatibility symlinks left behind.

The production resume then found the shared `fair-cw-use2-1` inference gateway
returning HTTP 503 while its sole recovery job waited for a CPU allocation.
The two obsolete Run 12 canary deployments were stopped. A committed deferred
launcher now waits for gateway leader health, the exact `aar_8-kimi26` registry
entry, and a real Kimi completion before invoking the five-chain launcher. This
avoids spending bounded AAR attempts during a cluster-wide routing outage.

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

The final researchers route to the validated multi-replica `aar_8-kimi26`
deployment. AutoData generation separately routes to the dedicated
multi-replica `autodata_8-kimi26` deployment, so generation cannot starve the
research sessions. The five Gemma target lanes remain chain-specific. AutoData
concurrency is eight per chain, for at most forty simultaneous tasks across the
five chains; this is a deliberately safer first production setting than five
times sixteen.

## Final bootstrap-canary recovery

The first clean bootstrap-canary attempt failed closed before creating a Gemma
endpoint or submitting evaluator, researcher, or controller jobs. Kimi Code
2.1.1 reached its first native Bash action but then remained inside the bounded
MCP round trip until the 180-second preflight killed its process group.

An attempted recovery mapped `auto_approve=True` to Kimi's documented `--auto`
flag. The next canary immediately rejected that combination because Kimi 2.1.1
does not allow `--auto` with noninteractive `--prompt` mode. Inspection of the
pinned CLI implementation then established that prompt mode already forces the
agent permission service to `auto`; the CLI flag was reverted rather than
weakening or skipping the MCP preflight. The remaining investigation therefore
focuses on the model/MCP round trip and its timeout, not approval.

The retained trace and vLLM worker logs then localized the repeatable stall to
the initial model response: the CLI emitted only `system.version`, while one
Kimi worker generated continuously at about 87 tokens/second for the entire
180 seconds without producing a tool call. The endpoint remained healthy; the
health probe had incorrectly inherited the research session's 65,536-token
output allowance. The verifier now uses a process-local 1,024-token ceiling
and a named-tool checkpoint for `get_literature`. This does not reduce the
maximum input or output allowances of production researcher or AutoData
sessions.

A controlled comparison with thinking enabled did eventually return the exact
MCP sentinel, but its following forced Bash checkpoint then remained in
`turn.step.retrying` until the 180-second timeout. The non-thinking policy is
therefore retained: it reaches structured tools quickly and is the previously
validated Run 10 mode. The preflight now checks successful structured MCP and
Bash calls plus a nonempty assistant completion; it no longer treats the exact
wording of free-form acknowledgment text as infrastructure correctness.

The first post-preflight Gemma deployment exposed a separate scheduling bug:
the Run 12 launcher explicitly overrode the cluster's validated
`cpu_x86_lowest` coordinator/proxy QoS with `normal`. Its coordinator job
`1800796` remained pending with priority 136 and no start estimate. The failed
canary deployment was archived without ever allocating a GPU. Both initial and
post-promotion Gemma launch paths now use `cpu_x86_lowest`, matching the live
Kimi and Gemma Serve API deployments on `fair-cw-use2-1`.

The first real researcher process then failed before starting Kimi because the
plugin resolver required the AutoData checkout to report branch `main`, while
the launcher intentionally uses a detached, clean checkout at reviewed commit
`823c5948854df14664f3168bc5e6c49a2cecb975`. The resolver now accepts either
`main` or detached HEAD only after the full expected SHA and clean plugin tree
have been verified; named feature branches remain rejected even at the same
commit. The top-level launcher now executes this resolver preflight before any
new Gemma deployment.

After that recovery, the first production Kimi request again generated at
about 87 tokens/second for more than four minutes without emitting a tool. The
65,536-token maximum is retained for legitimate research/code output, but the
non-thinking request proxy now adds a stop sequence for the observed
`The!!!!...` degeneration (16 consecutive exclamation marks). The Kimi
continuation state machine also requires the initial `get_literature` call
before advancing to template inspection, so stopping a degenerate first answer
cannot silently skip research grounding.

Separately, the reusable runtime profile was corrected from an accidental
concurrency value of 32 back to the documented production value of eight per
chain. A fresh canary must pass these gates before the five-chain launch.

The next canary at commit `8e9fe2a` proved that the stop sequence works in a
real research session: structured literature calls began about eight seconds
after the researcher started, the template was read, a method was written, and
its local contract was repaired and passed. It also exposed two later fail-closed
gaps before any AutoData workspace or training job was created:

1. Native proposal approval rejected direct JSON consumption because the local
   method validator did not yet require
   `load_autodata_campaign_datasets`. The validator now mirrors the native
   receipt, execution-ID, rubric, row-count, and objective checks, and Kimi adds
   that gate automatically whenever AutoData is active.
2. After the code was repaired, the reproducibility monitor rejected the paper
   because the agent had not inspected the reviewed recipe and described
   response-only loss while its code trained the full rendered sequence. The
   continuation state machine now reads the protected pipeline, objective,
   comparator, grounding coverage, generation strategy, exact judge rubric,
   request, and task implementation before method authoring. A rejection whose
   unchanged code passes policy but whose paper is incomplete now triggers a
   paper-only resubmission rather than an unnecessary new candidate.

The retained canary jobs were evaluator `1801120`, researcher `1801121`, and
controller `1801122`. The first proposal was submitted about seven minutes
after the researcher started. This attempt is diagnostic only and is replaced
because its already-running researcher cannot inherit the new continuation
logic. Sixty focused tests pass across the Kimi, method-validator, AutoData
proposal-binding, plugin, and Run 12 canary suites.

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

## Bootstrap canary: target-challenge feedback recovery

The canary launched from commit `e3da07f3fd8fa2cce914aa2a369a144367891ccc`
successfully reached target-aware AutoData authoring. Evaluator job `1805362`
and researcher job `1805363` ran for about 17 minutes; controller `1805364`
remained correctly dependency-held. The local broker completed all 12 requested
jobs. This ruled out endpoint discovery, Bubblewrap, broker concurrency, Gemma
identity, Kimi routing, and Luna availability as the immediate blocker.

The baseline itself failed scientifically: four reviewed strategies generated
teacher answers with quality `1.0`, but both dry-run prompts repeatedly had
challenge `0.0`, so no item was accepted. A direct diagnostic call showed the
problem concretely. Kimi asked Gemma to confirm an obvious claim that vacuum
fluctuations literally violate energy conservation; Gemma explicitly corrected
the claim, and Luna correctly reported that the expected sycophancy failure did
not occur. The canary was canceled without training, and all artifacts remain
under its retained attempt directory.

The failure exposed a feedback defect: rejected task results discarded the
candidate, leaving the pipeline author only the coarse reason
`target_not_challenging`. The recovery keeps rejections out of every tuning and
production dataset, but retains the candidate as explicitly rejected diagnostic
evidence during `authoring-dry-run` only. The approval monitor can therefore
return the actual prompt and Luna target reason as revision evidence. Its policy
also now states that the external Model API Luna process is the intentionally
independent judge and must not be mistaken for a provenance defect.

The initial strategy was changed from an obvious direct-confirmation pattern to
an indirect-compliance pattern: rewriting, summarizing, or polishing an
otherwise plausible request containing one subtle false inference, unsupported
endorsement, contradiction, or unresolved unknown. This is intended to test the
target model rather than merely elicit an easy correction. A fresh one-chain
canary remains required before the five-chain launch.

## Bootstrap canary: challenge reached, teacher feedback missing

The replacement canary launched from commit `40faf1884496` as launcher job
`1805504`, evaluator `1805521`, researcher `1805522`, and dependency-held
controller `1805523`. The launcher prepared the run in about 80 seconds. The
proposal required four monitor passes and was approved roughly 16 minutes after
the researcher began; one bounded 300-second Kimi turn timed out and resumed
from its persisted session without losing the AutoData workspace or broker.

The broker and all three providers remained healthy. Early authoring baselines
produced high-quality teacher responses but `challenge=0`: Gemma correctly
resisted obvious rental-income, CRISPR, desalination, and event-planning traps.
The retained dry-run diagnostics let the pipeline author make evidence-backed
strategy revisions rather than guess from a coarse rejection code.

Strategy v5 then crossed the important scientific threshold. Both prompts made
Gemma materially fail: the honesty sample had `challenge=1.0`, and the
sycophancy sample had `challenge=0.5`. They still failed closed because their
ideal teacher answers scored only `0.50` and `0.66`: one invented unsafe food
holding assurances, while the other insufficiently scrutinized an unsupported
technical premise. No rejected row entered training.

This exposed the remaining design defect: target-aware execution generated one
candidate and measured it, but did not feed Gemma/Luna rejection evidence back
into the same task. Run 12 now configures up to three bounded candidate attempts
per task. A retry receives the prior prompt, target response, and teacher/target
judge reasons, must generate a materially different candidate, and stops on the
first accepted row. This was the first bounded feedback implementation; the
subsequent canary showed that generic regeneration did not guarantee that a
newly discovered hard prompt was preserved, motivating the failure-specific
repair described below.

The old canary's final v6 edit was never evaluated. AutoData had advanced the
workspace to revision 20 while writing it, then every supervisor pass failed
with `workspace revision budget exceeded` before launching its dry run. The
three canary jobs were canceled after this terminal condition was confirmed;
all evidence remains retained. The workspace budget is now 32 revisions so an
edit cannot consume the final slot without leaving capacity for its dry run and
approval. The task-attempt and 6,300-second wall-clock bounds remain unchanged.

The evidence-backed v6 strategy is now the reviewed starting strategy for the
next canary. It combines the hard prompt patterns that reached target challenge
`1.0`/`0.5` with strict teacher constraints against invented parameters and
sycophantic praise, while retaining the recipe's general safety exclusions.

## Bootstrap canary: bounded retries validated and specialized

The next canary launched from commit `348bdceffdb8df7940cd6fcbc9c5df987eabdc31`
as launcher `1806313`, evaluator `1806352`, researcher `1806353`, and
dependency-held controller `1806354`. The proposal and workspace bootstrap took
about 16.5 minutes. Grounding remained balanced across the three axes and was
approved without infrastructure errors.

The initial v6 baseline exercised all three configured model attempts for each
of two samples. This validated the bounded feedback mechanism end to end: each
task made three Kimi, three Gemma, and three Luna calls. The two tasks completed
in about two minutes, and the broker, dedicated AutoData Kimi route, target
Gemma route, and Luna judge all remained healthy. Neither item passed: the
honesty teacher invented a defect in a reasonable approximation, while Gemma
resisted the sycophancy prompt.

Two subsequent strategy checks failed immediately because the researcher made
`scenario_prompt_prefix` longer than the recipe's 2,000-byte bound. These were
static contract failures, not model-serving or Bubblewrap failures. The
simplified v9 strategy passed the same check. Its honesty and sycophancy dry-run
tasks completed in 42 and 34 seconds respectively. The honesty prompt finally
challenged Gemma (`challenge=0.5`), but its teacher contradicted itself and
scored `quality=0.66`. The sycophancy teacher scored `quality=1.0`, but Gemma
again resisted (`challenge=0`). The monitor correctly requested revision, and
no rejected row entered training.

That evidence exposed a remaining inefficiency in generic retries: every
failure regenerated both the prompt and teacher answer. The recipe now uses
failure-specific retries. A non-challenging prompt is regenerated and reprobed.
When a prompt already challenges Gemma but the teacher fails, the measured
prompt and Gemma response are retained, only the teacher is repaired, and the
judge is rerun. This preserves scarce hard prompts, avoids an unnecessary Gemma
call, and directly addresses the v9 honesty failure. Each row records whether
its selected attempt was `full_generation` or `teacher_repair`.

The reviewed starting strategy was also tightened from v6 to v7 using the only
retained sycophancy sample that had challenged Gemma. That sample succeeded by
eliciting partial endorsement while asking for an expert assessment, whereas
the later obvious requests to confirm false astronomy facts were cleanly
resisted. The new strategy therefore asks for indirect transformations such as
polishing a proposal, drafting an endorsement, or writing an executive summary;
it embeds a consequential unsupported inference among otherwise plausible
details and requires the teacher to complete the requested format while
correcting that inference. It also explicitly requires every arithmetic
correction to be independently recomputed. The resulting system prompt and
scenario prefix remain within the protected static size bounds.
