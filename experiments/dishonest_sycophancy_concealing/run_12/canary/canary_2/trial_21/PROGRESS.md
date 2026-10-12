# Run 12 Canary 2 Trial 21 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Never
record generated rows, prompts, responses, credentials, held-out content, or
partial evaluator scores.

## 2026-10-12

<a id="trial21-event-staged"></a>

### ⏭️ 03:17 PT — NEXT: registration-race repair staged

> [!IMPORTANT]
> **Launch approved; preflight pending.** Trial 21 changes only the AAR source
> revision containing the pre-registration wait fix.

```text
✓ Trial 20 evidence preserved
✓ Registration-race fix tested and committed
○ Exact-commit HPC synchronization
○ Endpoint and infrastructure preflight
○ Research and proposal approval
○ Coordinated clarify_design
○ Meta-optimization
○ Production
○ Training smoke
```

- Source fix: `23023b1a066362695cda624d0ab7f65f88d7efb6`.
- Attempt: not created.
- Jobs: none.
- Model mapping: unchanged from the operator-confirmed Trial 20 mapping.
- Decision: launch after synchronization and HPC validation succeed.
