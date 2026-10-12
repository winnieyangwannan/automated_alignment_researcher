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

<a id="trial21-event-kimi-registry-locator"></a>

### 🔴 03:38 PT — FAIL: isolated Kimi worker lost cluster registry locator

> [!CAUTION]
> **Trial 21 failed closed during `clarify_design`.** The registration-race fix
> worked, but the isolated worker removed `SLURM_CLUSTER_NAME` from its bounded
> environment. `serve_api_v2` therefore could not resolve `aar_8-kimi26`, and
> Kimi was never invoked.

```text
✓ Endpoint and MCP preflight
✓ Infrastructure bootstrap
✓ Method authoring and proposal approval
✓ Workspace registration and clarify_design lease
✗ Isolated Kimi clarify_design worker startup
○ Meta-optimization
○ Production
○ Training smoke
```

- Source commit: `d64eb61b3bd65dfe302fdf886e95c01375f275cc`.
- Attempt: `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261012T102006Z-d64eb61b3bd6`.
- Jobs: launch `1835615` completed; research `1835734` failed with exit 70;
  controller `1835736` failed closed.
- No semantic outcome, native completion receipt, meta-optimization,
  production, training, evaluator, score, or finding was created.
- Corrective commit: `f786f21fe32239ffc61db8608a19d27845090434` preserves only the explicit
  deployment-registry locators. The full coordinator/supervisor suite passed
  (108 passed, 1 skipped), and a live isolated-worker call to `aar_8-kimi26`
  succeeded on HPC.
- Decision: preserve Trial 21 and launch fresh Trial 22; never resume it.
