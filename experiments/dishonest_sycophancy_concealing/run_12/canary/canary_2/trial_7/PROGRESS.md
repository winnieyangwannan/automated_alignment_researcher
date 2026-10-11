# Run 12 Canary 2 Trial 7 progress

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
| 🛠️     | FIX         | Corrective change implemented                |
| ⏭️     | NEXT        | Next action or outstanding work              |
| ⏳     | RUNNING     | Work currently in progress                   |

## 2026-10-11

<a id="trial7-event-setup"></a>

### ⏭️ 02:30 PT — NEXT: same-configuration replacement prepared

> [!IMPORTANT]
> **Authorized but not launched.** Trial 7 preserves the exact user-confirmed
> Trial 6 contract under fresh run ID `run12-canary2-trial7`. Launch remains
> blocked on the focused adapter repair commit, exact HPC synchronization,
> complete regression gate, and live preflight.

Trial 6 proved launch, authoring, dry-run, approval, and freeze, then failed
before canonical intent publication because AAR rejected native-valid freeze
fields. The repair accepts the native shape but derives all authoritative
values from trusted operator configuration.

```text
✓ Trial 6 terminal evidence preserved
✓ Native/AAR adapter mismatch identified
✓ Focused code and regression repair implemented locally
○ Focused commit and exact HPC synchronization
○ Complete HPC regression gate and live preflight
○ Trial 7 immutable-source launch
○ Workspace freeze and canonical execution registration
○ Three-iteration meta-optimization
○ Production
○ Training smoke
○ Evaluator (intentionally disabled)
```

#### Evidence

- Trial 6 launcher: `1812990`, `COMPLETED 0:0`
- Trial 6 research: `1813007`, `FAILED 70:0`
- Trial 6 controller: `1813008`, `FAILED 1:0`
- Trial 7 attempt: not created
- Trial 7 jobs: none

#### ⏭️ Next step

Finish validation, commit only the scoped repair and Trial 6/7 records,
synchronize and validate the exact revision, then launch automatically.

<a id="trial7-event-prelaunch-integration-audit"></a>

### 🛠️ 02:49 PT — FIX: comprehensive integration-boundary audit completed

> [!IMPORTANT]
> **Trial 7 remains unlaunched.** The prelaunch hold exposed several defects
> that would otherwise have caused a late failure or an ambiguous multi-hour
> wait. No research, native execution, training, or evaluation job was started.

The Trial 6 defect was one AAR/native serialization mismatch, not an isolated
typo. A systematic audit found and repaired the same broader failure pattern:
duplicated assumptions at the recipe, native engine, supervisor, handoff, and
training boundaries.

```text
✓ Accept native freeze serialization while rebuilding trusted values
✓ Pin the complete operator pipeline and reject added checks before native CLI
✓ Split meta/test dry-run IDs with their actual disjoint partitions
✓ Account for 608 evaluations + 3 checks = 611 deterministic native attempts
✓ Retain 88 bounded recovery attempts inside the unchanged $5,500 ceiling
✓ Accept and meter retry-aware G/T/J provenance across handoff and loader
✓ Keep training submission stdout to the normalized numeric Slurm job ID
✓ Publish one digest-bound verified marker for original and reuse handoffs
✓ Fail on corrupt/partial handoffs instead of treating them as pending forever
✓ Fail on SQLite/action-state errors instead of converting them to no action
✓ Fail when Slurm completes without a smoke marker after a bounded grace
✓ Require a fresh supervisor heartbeat while no host action is visible
✓ Retain subprocess stdout/stderr only in private mode-0600 operator evidence
✓ Round-trip exact native meta and production serializers through AAR
✓ Pinned native engine regression: 19 tests passed
✓ Focused local regression: 147 tests passed
○ Focused repair commit and exact HPC synchronization
○ Exact-commit HPC regression and live preflight
○ Immutable Trial 7 launch
```

The pinned native adapter gate passes with `3/3/3`, disjoint `64/32/32`, 1,250
production tasks, 1,000 required rows, 699 configured native meta attempts, and
88 bounded recovery attempts. The gate runs before child job submission.

#### ⏭️ Next step

Finish the full local gate, commit only scoped integration changes and Trial 7
records, synchronize the exact commit to HPC, rerun the gate there against the
pinned native snapshot, then launch under the standing authorization.
