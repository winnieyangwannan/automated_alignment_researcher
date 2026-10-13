# Run 12 Canary 2 Trial 29 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Never
record generated rows, prompts, responses, credentials, held-out content, or
partial evaluator scores.

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

## 2026-10-12

<a id="trial29-event-staged"></a>

### ⏭️ 21:55 PT — NEXT: automatic campaign-cap lifecycle proof staged

> [!IMPORTANT]
> **Not launched.** Trial 29 replaces Trial 28's copied numeric cap with trusted
> compile-time derivation. All model, retry, task, concurrency, coordinator,
> production, and training-smoke settings remain unchanged.

```text
✓ Trial 28 terminal evidence preserved
△ General max_cost_usd: auto implementation
△ Exact $64,523.1552 / 21,630-round compiler regression
○ Focused validation and commit
○ Exact-commit HPC synchronization
○ Fresh Trial 29 launch
```

- Source commit: pending focused validation and commit.
- Attempt: not created.
- Jobs: none.
- Decision: launch only after the source sentinel compiles to a numeric cap in
  every runtime artifact and the unchanged runtime validator independently
  reproduces the same requirement.

<a id="trial29-event-auto-cap-validated"></a>

### ✅ 21:58 PT — PASS: automatic cap implementation validated locally

> [!TIP]
> The source sentinel compiles to numeric `$64,523.1552` in both the resolved
> configuration and campaign policy. Runtime validation independently derives
> the same `21,630` reservations and accepts the compiled cap.

```text
✓ Canonical capacity formula factored without changing accounting
✓ Numeric historical caps retain existing behavior
✓ Unknown symbolic cap values fail closed
✓ Trial 29 differs from Trial 28 only by run ID and automatic cap source
○ Focused commit and exact-commit HPC synchronization
○ Fresh Trial 29 launch
```

- Validation: 50 focused tests passed; 95 of 96 broader tests passed. The only
  broader failure is an unrelated pre-existing missing Run 13 launcher fixture.
- Static checks: Ruff, Bash syntax, ShellCheck, and diff whitespace passed.
- Independent read-only reviews: implementation and Trial 29 runtime envelope
  found no code/config blocker; documentation findings were corrected.
- Decision: proceed to focused commit and HPC validation.
