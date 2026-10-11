# Run 12 Canary 2 Trial 5 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Never
record generated rows, raw prompts, target responses, credentials, or held-out
content here.

## Visual key

| Symbol | Status      | Meaning                                      |
| ------ | ----------- | -------------------------------------------- |
| ✅     | PASS        | Completed successfully or verified correct  |
| 🔴     | FAIL / STOP | Failed gate or deliberate stop condition     |
| 🐛     | BUG         | A concrete implementation defect identified |
| 🔎     | OBSERVATION | Important experimental evidence              |
| 💡     | CONCLUSION  | Conclusion supported by current evidence     |
| 🛠️     | FIX          | Corrective change implemented                |
| ⏭️     | NEXT         | Next action or outstanding work              |
| ⏳     | RUNNING      | Work currently in progress                   |

## 2026-10-11

<a id="trial5-event-setup"></a>

### ⏭️ 01:01 PT — NEXT: Trial 5 launch-blocked package initialized

> [!IMPORTANT]
> **Not launched.** Trial 5 is a fresh specification after Trial 4's
> non-actionable feedback loop. No Trial 5 attempt or Slurm job exists.

The user explicitly confirmed the complete Trial 5 mapping and authorized
automatic launch after all documented repair, commit, synchronization, HPC
test, and runtime-preflight gates pass:

- researcher/host: Kimi-K2.6, `aar_8-kimi26`;
- generator/teacher: Kimi-K2.6, `autodata_8-kimi26`;
- proposal/semantic monitor: Claude Opus 4.8 via FAIR Model API;
- baseline approval: deterministic trusted AAR policy;
- target/training base: fixed `gemma-4-31B-it`, retained deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`, vLLM 0.25.1 language-model-only;
- row judge: `gpt-5-6-luna`;
- exact `3/3/3`, `64/32/32`, c32, production `1250` to `1000`;
- `$5,500` hard campaign ceiling;
- no evaluator; stop after verified training smoke.

#### Trial 4 evidence carried forward

Trial 4 stopped at `pipeline_pending` revision 21 with zero executions. Eight
identical authoring checks rejected unsupported `max_tokens`, but the action
received only `solve_failed`; the repeated-failure breaker did not cover that
native authoring loop. Cancellation also exposed a false `completed/0` process
marker that contradicted authoritative Slurm `CANCELLED`.

#### Lifecycle snapshot

```text
○ Comprehensive feedback audit and repair
○ Native AutoData commit and new pin
○ AAR commit and exact HPC synchronization
○ Complete HPC regression gate
○ Endpoint, source, and secret preflight
○ Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
○ Canonical execution create/register
○ Baseline approval
○ Three-iteration meta-optimization
○ Production
○ Training smoke
```

#### Evidence

- Intended run ID: `run12-canary2-trial5`
- Native AutoData commit: pending feedback-safe commit
- AAR source commit: pending comprehensive repair commit
- Attempt: not created
- Jobs: none

#### ⏭️ Next step

Finish and validate every identified feedback-propagation repair. Do not launch
until both exact commits and every pre-launch gate are retained and green.

<a id="trial5-event-feedback-repair"></a>

### 🛠️ 01:21 PT — FIX: native feedback and repeated-failure repair committed

Native AutoData commit
`d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc` is committed and exactly
synchronized to the clean HPC execution worktree. It provides:

- reviewed, bounded checker/schema diagnostics through local and Firecracker
  broker paths without forwarding raw stderr;
- static safe workspace fallbacks that keep authored content, paths, provider
  output, and registered secrets out of actions, events, revisions, and task
  attempts;
- a durable, restart-safe, occurrence-idempotent three-strike circuit for an
  unchanged permanent authoring failure; and
- fail-closed handling of unknown backend states so they cannot create an
  unbounded polling loop.

The complete devserver native suite passed with 94 tests and 1 skip. The HPC
login node passed all non-sandbox tests; its two bubblewrap tests could not
start because login-node UID-map creation is prohibited. A dedicated Slurm
compute-node rerun is in progress and remains a launch gate.

The AAR feedback/cancellation audit repair passes 214 focused tests plus Python
compilation, shell syntax, launcher ShellCheck, and diff checks. It is under an
independent final review and is not yet committed or synchronized.

<a id="trial5-event-independent-review"></a>

### 🛠️ 01:32 PT — FIX: independent review blockers repaired

The independent review found that a same-UID Kimi researcher could read a
nominal `TEAM_DIR/secrets` directory because Trial 5 intentionally runs with
research mount isolation disabled. It also found that malformed pre-existing
training-failure markers could extend waiting to the six-hour host timeout and
that predictable cancellation-marker temporary names were vulnerable to
pre-created symlinks.

The repaired contract now:

- discards raw CLI/provider diagnostics for unisolated Kimi instead of retaining
  them anywhere under the attempt root;
- sends raw broker, auth-bridge, lifecycle-supervisor, and training streams to
  `/dev/null` for that backend while preserving typed public failure codes;
- masks `TEAM_DIR/secrets` explicitly for future isolated research backends;
- replaces malformed terminal failure markers with a validated typed marker;
- uses random exclusive, descriptor-relative, no-follow atomic writes for
  research-session results; and
- removes remaining raw exception/traceback interpolation from the Run 12
  research-visible process paths reviewed in this audit.

The revised focused gate passes 233 tests plus 5 subtests. Python compilation,
shell syntax, ShellCheck (only the pre-existing trap reachability notices), and
`git diff --check` pass. The devserver full suite reaches collection but requires
PyTorch, which is absent from the dependency-complete CPU sibling environment;
the full suite remains an HPC gate.

Native HPC validation passed on Slurm job `1812479`: `COMPLETED`, exit `0:0`,
94 passed and 1 skipped in 15.41 seconds at exact native commit
`d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc`.

<a id="trial5-event-launch"></a>

### ⏳ 01:39 PT — RUNNING: Trial 5 launcher submitted

Every mandatory source, regression, runtime, endpoint, checkpoint, and secret
gate passed. The committed Trial 5 wrapper launched automatically as authorized:

- AAR commit: `4e57c7fe07acd13e0b1e6cd94ca5bcdf09e751d9`;
- native AutoData commit: `d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc`;
- attempt: `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T083852Z-4e57c7fe07ac`;
- launcher job: `1812591`, initially `PENDING`;
- retained target: `winnieyangwn-r12-alpha-i1-c0dab4f7`;
- boundary: verified `training_smoke`; evaluator forbidden.

The dedicated read-only monitor is active. No research/controller/training job
or evaluator job had been created at this first snapshot.

<a id="trial5-event-launch-drift"></a>

### 🔴 01:40 PT — FAIL / STOP: shared-checkout drift rejected before child launch

Launcher job `1812591` started at 01:39:57 PT and failed at 01:40:11 PT with
exit `2:0` and the bounded diagnostic `commit drift`. It expected committed AAR
source `4e57c7fe07ac…`; the shared HPC worktree had advanced to
`34ad5a5cc66e…` while the job waited in the Slurm queue. The integrity gate
correctly refused to mix source revisions.

No research, controller, AutoData, training, or evaluator job was created. The
attempt is retained as terminal preflight evidence; it is not a partially run
optimization.

### 🐛 01:42 PT — BUG: queued jobs depended on a mutable shared source checkout

The submission pinned a commit in metadata but pointed the queued job at the
shared branch worktree. A legitimate later synchronization could therefore
move `HEAD` between submission and execution. Failing closed prevented an
incorrect run, but retrying without changing this design would remain racy.

### 🛠️ 01:42 PT — FIX IN PROGRESS: immutable per-attempt source checkout

Trial 5 will relaunch only after the submitter creates and validates a private
checkout at the captured commit and all launcher/child jobs use that immutable
path. Shared-worktree updates must then be unable to alter queued or running
attempts. Focused regression and exact HPC gates remain required before the
fresh launch.

### ✅ 01:45 PT — PASS: bounded replacement-trial authorization confirmed

The user confirmed that a pre-useful-work failure may be followed
automatically by the next numbered trial with the unchanged confirmed contract:
the same models, exact `3/3/3` and `64/32/32` partitions, c32, production
`1250` to `1000`, retained target, `$5,500` campaign ceiling, and
`training_smoke` stop with no evaluator. Every replacement still requires a
recorded failure, completed repair, and green validation/preflight gates.

Fresh confirmation remains required before changing any model, partition,
budget, evaluation scope, or retained-artifact policy.

### ✅ 01:49 PT — PASS: immutable-source repair passed expanded local gates

The Run 12 submitter now creates independent detached attempt-local checkouts
for both AAR and native AutoData, removes remotes, forbids shared Git object
alternates, and records the exact roots, commits, and manifest digest. It also
copies and reverifies the public source, recovered baseline inputs, run config,
and runtime profile. All launcher, research, controller, and training paths are
then rooted in those snapshots while the architecture-specific Python
environment and protected secret file remain external by explicit absolute
path.

The queued pipeline validates both snapshots before sourcing any code. A
functional regression advances the original shared repository after snapshot
creation and proves the attempt remains on the captured revision.

Validation passed:

- snapshot and Run 12 focused tests: 16 passed;
- expanded feedback/recovery suite: 258 passed plus 5 subtests;
- adjacent launch/runtime suite: 115 passed plus 15 subtests, with one Run 13
  test deselected because the user's unrelated working-tree deletion removes
  its fixture;
- shell syntax, ShellCheck excluding only the submitter's pre-existing
  SC2155/SC2015 notices, and `git diff --check`.

The repair remains uncommitted at this event. Next gates are a focused commit,
exact HPC synchronization, HPC regression, runtime preflight, and fresh Trial 5
launch.
