# Run 12 Canary 2 Trial 26 progress

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

<a id="trial26-event-staged"></a>

### ⏭️ 16:54 PT — NEXT: shared Kimi semantic-action parity trial staged

> [!IMPORTANT]
> **Not launched.** Trial 25 evidence remains preserved. Trial 26 keeps its
> exact model, budget, task, and retry settings while additionally enabling the shared
> `author_grounding`, `author_pipeline`, `analyze_results`, and
> `mutate_candidate` coordinators with the Kimi worker. Its host-only wait is
> extended from three to eight hours because prior production took about 4.5
> hours.

```text
✓ Trial 25 terminal evidence preserved
✓ Fresh Trial 26 configuration and launcher staged
✓ Trial 25 model, deployment, budget, task, and retry settings retained
△ Shared Kimi ownership integration under implementation and focused testing
○ Exact-commit HPC synchronization and preflight
○ Fresh Trial 26 attempt and jobs
```

- Source commit: pending the focused implementation and trial-record commit.
- Attempt: not created.
- Jobs: none.
- Model mapping: identical to Trial 25, recorded in `README.md`, and covered by
  standing operator approval for unchanged settings.
- Decision: launch only after the shared action-owner integration passes
  focused tests and the exact commit is synchronized to HPC.

<a id="trial26-event-shared-actions-validated"></a>

### 🛠️ 17:04 PT — FIX: shared Kimi action ownership validated

> [!IMPORTANT]
> Outer Kimi now yields every enabled semantic action to the shared supervisor.
> The legacy result-file bridge cannot consume a coordinator-owned action, and
> the existing Run 13 Claude scope remains fail-closed.

```text
✓ Shared grounding/pipeline scope permits only the validated Run 12 Kimi envelope
✓ Shared analysis/mutation use the existing backend-neutral reconcilers
✓ Outer Kimi waits without model, lease, begin, complete, or result-file authority
✓ Unchanged mutation documents remain deterministically rejected
✓ Trial-local host wait raised to 28,800 seconds for the known production runtime
○ Focused commit and exact-commit HPC synchronization
○ Fresh Trial 26 attempt and jobs
```

- Validation: coordinator/supervisor `122 passed, 1 skipped`; Kimi and Claude
  compatibility `106 passed` plus `15` subtests; launch/config `17 passed`;
  Ruff, Bash syntax, ShellCheck, YAML equivalence, and whitespace checks passed.
- Model mapping: unchanged from Trial 25 and covered by the operator's standing
  and current approval—Kimi-K2.6 researcher/semantic worker, Kimi-K2.6
  generator, fixed Gemma 4 31B target, Claude Opus proposal/grounding monitor,
  and Luna row judge; evaluator roles remain disabled.
- Source commit: pending this focused commit.
- Attempt: not created.
- Jobs: none.
- Decision: commit only these changes, synchronize that exact commit, then
  launch the committed Trial 26 entrypoint.
