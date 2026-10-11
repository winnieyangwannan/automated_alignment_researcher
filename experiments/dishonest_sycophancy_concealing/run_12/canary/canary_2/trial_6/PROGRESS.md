# Run 12 Canary 2 Trial 6 progress

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
| 🛠️     | FIX         | Corrective change implemented                |
| ⏭️     | NEXT        | Next action or outstanding work              |
| ⏳     | RUNNING     | Work currently in progress                   |

## 2026-10-11

<a id="trial6-event-setup"></a>

### ⏭️ 01:59 PT — NEXT: Trial 6 replacement package prepared

> [!IMPORTANT]
> **Authorized but not launched.** Trial 6 preserves the exact user-confirmed
> Trial 5 contract under fresh run ID `run12-canary2-trial6`. Launch remains
> blocked on the `HARNESS_PY` repair, focused commit, exact HPC synchronization,
> regression gates, and final runtime preflight.

The confirmed contract remains:

- researcher/host: Kimi-K2.6, `aar_8-kimi26`;
- generator/teacher: Kimi-K2.6, `autodata_8-kimi26`;
- proposal/semantic monitor: Claude Opus 4.8 via FAIR Model API;
- baseline approval: deterministic trusted AAR policy;
- target/training base: fixed `gemma-4-31B-it`, retained deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`, vLLM 0.25.1 language-model-only;
- row judge: `gpt-5-6-luna`;
- exact `3/3/3`, `64/32/32`, c32, production `1250` to `1000`;
- `$5,500` hard campaign ceiling; and
- no evaluator; stop after verified training smoke.

#### Trial 5 pre-child failures carried forward

| Attempt boundary                 | Launcher  | Result              | Later work |
| -------------------------------- | --------- | ------------------- | ---------- |
| Shared-checkout integrity gate   | `1812591` | FAIL, exit `2:0`    | None       |
| Immutable-snapshot runtime entry | `1812713` | FAIL, exit `127:0`  | None       |

Launcher `1812591` failed closed at 01:40 PT because a synchronization advanced
the shared HPC checkout while the job waited in Slurm. No child job began.

The corrective immutable-source design succeeded before launcher `1812713`
failed: both detached source snapshots matched their exact revisions, retained
no remote or shared-object alternate, were clean, and matched source-manifest
digest
`sha256:c03b99b063e95507f9cf0214222bbcf7fba458daaaaeda4e870d2a7e4f63d2f3`.
This proves the mutable-checkout race was removed from the queued execution.

Launcher `1812713` was submitted at 01:55:10 PT, ran from 01:56:45 through
01:57:00 PT, and failed after 15 seconds with exit `127:0`. It created no
`children.tsv` entries and no research, controller, AutoData, training, or
evaluator job. The bounded diagnostic identified a missing interpreter at the
attempt-local source path; it contained no prompt, row, response, held-out
content, or secret.

#### 🐛 Identified bug

`submit_full.sh` correctly exported the shared architecture-compatible runtime
as `HARNESS_PY`. During scheduled execution, `pipeline.sbatch` sourced
`replication/env_multidimensional.sh`, which unconditionally reset
`HARNESS_PY` to `${AAR_REPO}/.venv/bin/python`. Because `AAR_REPO` is now the
intentionally environment-free immutable source snapshot,
`aar_runtime_env.sh` preserved a nonexistent path and baseline validation could
not start.

The failure is an environment ownership bug, independent of the source-snapshot
integrity repair. The fix is in progress and is neither validated nor committed
at this event.

#### Lifecycle snapshot

```text
✓ Both Trial 5 pre-child failures preserved
✓ Immutable attempt-local source isolation proved
✗ Shared-interpreter handoff repair not yet validated
○ Focused repair commit and exact HPC synchronization
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

- Trial 5 shared-checkout attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T083852Z-4e57c7fe07ac`
- Trial 5 immutable-source attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T085409Z-2dde96057ffa`
- Immutable AAR snapshot: `2dde96057ffa8d3ba6a6a35f0225583b074df08a`
- Immutable native snapshot: `d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc`
- Trial 6 attempt: not created
- Trial 6 jobs: none

#### ⏭️ Next step

Complete the environment-handoff repair and all mandatory gates. Only then may
the already-authorized Trial 6 wrapper launch automatically.
