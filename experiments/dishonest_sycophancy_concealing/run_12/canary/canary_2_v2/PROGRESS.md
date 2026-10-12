# Run 12 Canary 2 v2 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). This
log contains orchestration metadata only; never record generated rows, prompts,
responses, credentials, held-out content, or partial evaluator scores.

## 2026-10-11

<a id="canary2-v2-event-planned"></a>

### ⏭️ 19:33 PT — NEXT: held-out-valid successor gate documented

> [!IMPORTANT]
> **Planned and not launchable.** No config, launcher, attempt, or Slurm job
> exists for Canary 2 v2.

Trial 15 was intentionally stopped at 19:19 PT after production accepted only
1 of 319 processed tasks. Meta-optimization had completed, but both baseline
and final selected-winner evidence reported `constraints.valid=false`; trusted
orchestration incorrectly crossed the production boundary.

The successor gate will use
`aar/autodata_recipes/dishonest_sycophancy_concealing_v2`, require a verified
held-out-valid final winner before production, monitor accepted-row yield
against the 1,250→1,000 contract, and stop after a verified one-step real-GPU
training smoke. Meta policy is minimum 3, maximum 10, and early-stop patience 3
consecutive rounds without meaningful accepted improvement. If early stopping
leaves no held-out-valid winner, the run must fail closed before production.

```text
○ Combined v2 recipe and held-out constraint validation
○ Trusted pre-production held-out-validity gate
○ Accepted-row yield and attainable-row monitoring
○ Exact meta policy: minimum 3, maximum 10, patience 3
○ Config, thin launcher, source snapshots, and role reconfirmation
○ Endpoint and infrastructure preflight
○ Method authoring and baseline verification
○ Meta-optimization and held-out-valid final-winner proof
○ Production: 1,250 tasks → exactly 1,000 accepted rows
○ Verified training handoff
○ One-step real-GPU training smoke
○ STOP; evaluator remains disabled
```

Planned roles are researcher `aar_8-kimi26`, generator
`autodata_8-kimi26`, one fixed Gemma 4 31B target, and Luna row judge
`gpt-5-6-luna`; they require user reconfirmation against the future config.

- Source commit at documentation time:
  `a23b2e621bf982f69e4fe815e9df5487287fb1b3`.
- Configuration: not created.
- Launcher: not created.
- Attempt: not created.
- Jobs: none.
- Decision: no-go until implementation, configuration, validation, and role
  reconfirmation are complete.

<a id="canary2-v2-event-role-confirmation"></a>

### ✅ 19:38 PT — COMPLETE: model roles and lifecycle contract confirmed

> [!IMPORTANT]
> **Confirmation recorded; no launch occurred.** Any later change to these
> assignments or settings requires new user confirmation.

The user confirmed researcher Kimi-K2.6 through `aar_8-kimi26`, generator
Kimi-K2.6 through `autodata_8-kimi26`, fixed Gemma 4 31B target and training
base `winnieyangwn-r12-alpha-i1-c0dab4f7`, and Luna `gpt-5-6-luna` as row
judge. Evaluator inference and evaluator judging remain disabled.

The confirmed execution contract is one chain at concurrency 8, the combined
v2 recipe, meta minimum 3 and maximum 10 with patience 3 consecutive rounds,
production 1,250→1,000 accepted rows, and one real-GPU optimizer-step training
smoke. A meaningful accepted improvement is a durable candidate promotion with
paired improvement at least `0.01` and passing `valid`, `quality`, and
`challenge` constraints. An invalid final winner must stop before production.

- Configuration: not created; it must exactly encode this confirmed contract.
- Launcher: not created.
- Attempt: not created.
- Jobs: none.
- Decision: confirmation satisfied; implementation and validation remain
  required before launch.

<a id="canary2-v2-event-config-prepared"></a>

### ⏭️ 19:40 PT — NEXT: strict config and launcher prepared

> [!IMPORTANT]
> **Prepared but not launched.** `autodata_run.yaml` and the fail-closed thin
> `submit_canary.sh` now encode the confirmed roles and lifecycle boundary.

The resolved static configuration selects `alpha`, target pair count 1,
`training_smoke`, concurrency 8, three model transport attempts, exact
`64/32/32`, meta minimum 3 / maximum 10 / patience 3, target feedback 5, two
strict JSON-schema judge-format attempts, production 1,250→1,000 with minimum
successful-task fraction 0.95, and the combined v2 recipe. The wrapper binds
the fixed target deployment `winnieyangwn-r12-alpha-i1-c0dab4f7` and delegates
to the shared Run 12 submitter.

Trusted worst-case accounting for the 10-iteration ceiling requires 4,100 task
attempts, 14,900 semantic model rounds, and `$44,447.296`. Trial 15's
`$41,775` cap fails closed; the prepared config uses the smallest whole-dollar
ceiling, `$44,448`. Approval of that increase is required before launch.

- Configuration: prepared; local validation in progress.
- Launcher: prepared; no invocation performed.
- Attempt: not created.
- Jobs: none.
- Decision: no-go pending implementation tests, immutable commit/sync, HPC
  validation, and approval of the `$44,448` campaign ceiling.

<a id="canary2-v2-event-local-validation"></a>

### 🔴 19:43 PT — STOP: local package valid; shared test blocker remains

> [!CAUTION]
> **No launch occurred.** The prepared config and launcher pass their direct
> checks, but the shared focused suite is not fully green.

The config compiler and compiled-artifact validator accepted run ID
`run12-canary2-v2`, chain `alpha`, concurrency 8, three transport attempts,
exact `64/32/32`, meta `3/10/3`, the v2 recipe, and fixed target deployment
`winnieyangwn-r12-alpha-i1-c0dab4f7`. Trusted execution accounting confirmed
4,100 task attempts, 14,900 semantic rounds, and required cost `$44,447.296`;
it rejected the old `$41,775` cap.

Shell syntax and ShellCheck passed. Explicit negative tests rejected a wrong
experiment ID, full mode, conflicting config, and wrong reused target with exit
status 2. No submitter path was invoked.

The focused Python run initially reported 108 passed, two failed, and one
unrelated Run 17 test deselected because that run's files are absent in the
existing dirty worktree. A targeted rerun after concurrent shared-code updates
reported one pass and one remaining failure:
`test_long_native_step_refreshes_supervisor_heartbeat` lacks the live native
state now required by the supervisor's `_step` path.

This event supersedes the initial event's historical “config not created”
state: config and launcher now exist, but no attempt or job exists.

- Configuration: compiled and artifact-validated locally.
- Launcher: `bash -n`, ShellCheck, and four fail-closed negative gates passed.
- Attempt: not created.
- Jobs: none.
- Decision: no-go pending the remaining focused test repair, full local and HPC
  validation, immutable commit/sync, and campaign-ceiling approval.

<a id="canary2-v2-event-local-ready"></a>

### ✅ 19:45 PT — COMPLETE: blockers repaired; budget ceiling approved

> [!IMPORTANT]
> **Local launch gates pass; no launch occurred.** The user approved the
> `$44,448` maximum campaign ceiling at 19:44 PT.

The trusted lifecycle supervisor now requires final held-out evidence for the
same selected winner with `constraints.valid` exactly `true` before winner
export or production creation. During production, it counts accepted source
IDs and conservatively retains all unfinished, in-flight, and native-retryable
source IDs as still possible. It stops only when accepted plus still-possible
unique source IDs is strictly less than 1,000; equality continues.

The integrated relevant suite reports 198 passed and one deselected. The
deselected Run 17 config test depends on Run 17 files already deleted in the
user's dirty worktree and is outside this change. Ruff, recipe checks, shell
syntax, ShellCheck, config compilation, compiled-artifact validation, cost
accounting, and fail-closed launcher negative gates pass.

- Configuration: locally validated at the approved `$44,448` ceiling.
- Launcher: locally validated; no invocation performed.
- Attempt: not created.
- Jobs: none.
- Decision: go for focused commit, exact-commit HPC synchronization, and HPC
  preflight; submission remains prohibited until those gates pass.
