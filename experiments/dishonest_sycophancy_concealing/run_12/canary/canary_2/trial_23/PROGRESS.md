# Run 12 Canary 2 Trial 23 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Never
record generated rows, prompts, responses, credentials, held-out content, or
partial evaluator scores.

## 2026-10-12

<a id="trial23-event-staged"></a>

### ⏭️ 12:04 PT — NEXT: shared approval routing staged

> [!IMPORTANT]
> **Not launched.** Trial 22 evidence remains preserved. Trial 23 changes only
> the trigger for grounding and baseline approvals; proposal/bootstrap already
> use the exact shared Claude/Kimi implementation.

```text
✓ Proposal/bootstrap shared-path audit complete
✓ Grounding/baseline approval shared-path audit complete
✓ Focused coordinator implementation tested locally and committed
✓ Trial 22 evidence preserved
○ Exact-commit HPC synchronization and preflight
○ Operator confirmation of exact model-role mapping
○ Fresh Trial 23 attempt and jobs
```

- Source commit: the focused commit containing this record; resolve and verify
  its exact SHA before HPC synchronization.
- Attempt: not created.
- Jobs: none.
- Model mapping: recorded in `README.md`; confirmation pending.
- Decision: no launch until the focused commit and explicit mapping confirmation.
