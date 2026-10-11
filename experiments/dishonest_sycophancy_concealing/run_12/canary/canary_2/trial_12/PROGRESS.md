# Run 12 Canary 2 Trial 12 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). This
log contains orchestration metadata only; never record generated rows, prompts,
responses, credentials, or held-out content.

### ⏳ 06:24 PT — PREPARING: repaired budget and broker contracts

Trial 11 is terminal and preserved. Native repair
`da9e12a43710ced9d407822e55c6e7c541e57a27` and AAR repair
`b8629a8fa3374111a1b55e40b1a9d114c7e5650d` are committed, synchronized, and
validated locally and on HPC. The old native detached worktree remains
untouched; a new immutable HPC worktree is pinned to `da9e12a`.

```text
✓ Trial 11 terminal evidence preserved
✓ Native atomic budget and broker-cost repair committed
✓ AAR campaign derivation and typed feedback repair committed
✓ Local and HPC focused regression gates
⏳ Explicit model/config confirmation
○ Trial 12 record commit and synchronization
○ Launcher and research allocation
○ Workspace authoring and freeze
○ Canonical baseline and meta iterations 1–3
○ Production and verified handoff
○ One-step training smoke
```

The proposed mapping is Kimi-K2.6 researcher `aar_8-kimi26`, Kimi-K2.6
generator `autodata_8-kimi26`, Claude Opus 4.8 monitor, fixed Gemma 4 31B
target/training checkpoint with retained deployment
`winnieyangwn-r12-alpha-i1-c0dab4f7`, and `gpt-5-6-luna` row judge. Evaluator
roles remain disabled.

The run contract is exact `3/3/3`, disjoint `64/32/32`, concurrency 32,
1,250→1,000 production, five final feedback rounds, one HTTP transport attempt,
707 native attempts, and a `$24,100` hard safety ceiling. The derived worst-case
requirement is `$24,099.427584`; expected spend is lower. No Trial 12 job or
attempt root exists yet.

### ⏳ 12:14 PT — REPAIRED: Luna wire contract and retry accounting

The Trial 11 failure audit supersedes the earlier `$24,100` plan. The repaired
contract requires only the six anchored dimension scores, a teacher reason,
and target score/failure modes/reason. Trusted code derives the redundant
`accept`, per-dimension `pass`, and target `challenging` booleans without
changing any scientific acceptance threshold.

Malformed Luna content now receives one bounded Luna-only repair request with
the safe validation code. The raw malformed response is neither retained nor
sent to Kimi, and the already-completed Kimi generation and Gemma probe are not
repeated. Both Luna calls' usage records are retained. If the second response
is still malformed, the task fails precisely as `judge_contract_exhausted` and
native finalization does not rerun its upstream providers.

The campaign now reserves one generator call, one target call, and up to two
judge calls per semantic round. The exact worst-case requirement is
`$41,774.49216`; Trial 12 is pinned to a `$41,775` hard ceiling. This represents
14,004 generator calls, 14,004 target calls, and at most 28,008 judge calls.
The protected task timeout is raised from 600 to 2,100 seconds to cover five
sequential final rounds with one possible judge repair in each.

The systematic audit also repaired two transferable issues in the original
non-v1 recipe: feedback rounds are now finalization-only, matching broker
reservations, and raw Gemma responses are no longer included in Kimi repair
feedback. FAIR native JSON-schema output support is not documented for this
Luna route, so Trial 12 fails closed on the operator-pinned `prompt_json` mode;
no unsupported API field is guessed.

Local evidence at this point: 85 focused AAR tests and 49 native broker/engine
tests pass. No Trial 12 model call, job, or attempt root has been created.

### ⏳ 14:40 PT — CONFIRMED: exact Trial 12 launch contract

The user explicitly confirmed the exact repaired mapping and configuration:
Kimi-K2.6 researcher `aar_8-kimi26`, Kimi-K2.6 generator
`autodata_8-kimi26`, fixed Gemma 4 31B target/training deployment
`winnieyangwn-r12-alpha-i1-c0dab4f7`, `gpt-5-6-luna` row judge, and Claude
Opus 4.8 semantic/proposal monitor. Evaluator roles remain disabled.

The confirmed execution is exact `3/3/3` over disjoint `64/32/32`, concurrency
32, 1,250→1,000 production, five final feedback rounds, two total judge-format
attempts per semantic round, one HTTP transport attempt, 707 native attempts,
a `$41,775` hard campaign ceiling, and a stop after verified training smoke.
Submission is authorized from the committed immutable AAR/native snapshots.

### ⏳ 14:58 PT — PREPARING: fresh base-target proof and attempt

The formerly missing three-provider proof was found intact in seven immutable
`/checkpoint/ram` snapshots. The live attempt path had disappeared, but the
snapshot copies contain identical nonempty preflight, target-binding, and
canary-report receipts. No Trial 12 work had started.

Because the user requested a fresh Trial 12 start, submission will not depend
on the historical adapter-target binding. The canary path now accepts the same
base-target manifest used by Trial 12, resolves its target environment through
the shared campaign policy, and permits the bounded second Luna usage record
introduced by the judge-format repair. Focused validation passes: 62 Python
tests, shell syntax checks, and whitespace checks. A new current-target proof
will be generated before creating a fresh Trial 12 attempt.

### ⏳ 15:09 PT — REPAIRED: provider proof identity contract

Fresh endpoint preflight job `1819999` passed against retained deployment
`winnieyangwn-r12-alpha-i1-c0dab4f7`. Provider canary job `1820087` then made
successful Kimi, Gemma, and Luna calls but failed closed before Trial 12 launch:
the proof validator incorrectly rejected the generator's required
`deployment_id` as an extra field. The failed proof attempt is retained under
`/checkpoint/ram/winnieyangwn/aar-runs/run12-adapter-target/20261011T215928Z-dabb748ef749`.

The shared validator now uses role-specific usage contracts and verifies the
current compiled generator and judge identities. The systematic audit also
fixed both recipe variants so token-ceiling failures retain generator/target
routing provenance, and replaced the weak launch-time role-only proof check
with full cross-file validation of call count, unique request IDs, generator
deployment, target model/deployment/checkpoint, judge model, and the requested
reused deployment. Validation passes 154 focused tests plus shell, bytecode,
and whitespace checks. No Trial 12 attempt has yet been created.

### ❌ 15:35 PT — TERMINAL: corrected action result lost to stall ordering

Trial 12 attempt `20261011T221840Z-b6db78771f9c` launched successfully. The
fresh provider proof passed, pipeline job `1820488` completed, and research job
`1820501` created and registered workspace
`ws_098e3f3c53544a01b3d94adc3cbb9d18`. Kimi authored a contract-valid method
and reached the first native `clarify_design` action.

The action result was initially malformed twice. Kimi's next correction was a
valid `autodata.action-result/v1` envelope with the required `summary` string
and `decisions` array, but the generic unchanged-lifecycle detector ran before
the host FSM re-entered to consume the corrected file. The research job failed
as `research_session_stalled` after 5m24s; controller `1820502` failed closed as
`training_smoke_session_failed`. No native execution, baseline, meta iteration,
production task, or training job started.

The transferable repair consumes action results immediately after every model
tool turn, fingerprints action/result/feedback/strategy and both training
handoff receipts as durable progress, resets stale method-contract counters on
real lifecycle progress, excludes unowned stale proposal markers, and preserves
host-resume semantics even when an action completes during the first process
turn. Trial 12 is retained and will not be resumed; the next launch is Trial 13.
