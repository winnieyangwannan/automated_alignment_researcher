# Run 12 Canary 2 Trial 24 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Never
record generated rows, prompts, responses, credentials, held-out content, or
partial evaluator scores.

## 2026-10-12

<a id="trial24-event-staged"></a>

### ⏭️ 12:48 PT — NEXT: fresh ownership-correction trial staged

> [!IMPORTANT]
> **Not launched.** Trial 23 evidence remains preserved. Trial 24 keeps the
> exact Trial 23 model and lifecycle settings and changes only the run ID and
> trial identity.

```text
✓ Trial 23 failure reconciled and evidence preserved
✓ Fresh Trial 24 configuration and launcher staged
✓ Trial 23 settings retained exactly
✓ Focused ownership correction committed and tested (`f210df8`)
○ Exact-commit HPC synchronization and preflight
✓ Exact model-role mapping covered by standing operator approval
○ Fresh Trial 24 attempt and jobs
```

- Repair commit: `f210df8`; capture the final documentation/launch commit before
  HPC synchronization.
- Attempt: not created.
- Jobs: none.
- Model mapping: recorded in `README.md` and confirmed by standing operator
  approval for unchanged settings.
- Decision: launch only after exact-commit sync and validation complete.
