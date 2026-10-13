# Run 14 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Do not
record credentials, hidden examples, evaluator-private traces, or partial
held-out scores.

## Visual key

| Symbol | Status      | Meaning                                      |
| ------ | ----------- | -------------------------------------------- |
| ✅     | PASS        | Completed successfully or verified correct  |
| 🔴     | FAIL / STOP | Failed gate or deliberate stop condition     |
| 🔎     | OBSERVATION | Important experimental evidence              |
| 🛠️     | FIX         | Corrective change implemented                |
| ⏭️     | NEXT        | Next action or outstanding work              |

## 2026-10-12

<a id="run14-event-opus5-canary-prepared"></a>

### 🛠️ 23:46 PT — FIX: Opus 5 comparison package prepared

> [!IMPORTANT]
> **PREPARED, NOT LAUNCHABLE, NOT LAUNCHED.** The declarative Run 14 canary
> preserves the Run 13 Trial 14 AutoData loop and changes the two requested
> model roles to Opus 5. Existing Run 13-only launch guards remain intact.

```text
✓ Reference configuration inventoried
✓ Opus 5 Model API catalog identity discovered
✓ Run 14 declarative configuration prepared
✓ Configuration-parity contract added
○ Run 14 runtime launcher and recovery fences
○ Exact Claude CLI Opus 5 preflight
○ Explicit model-role confirmation
○ Canary submission
○ Meta-optimization
○ Production
○ Training smoke
```

- Reference source commit: `cf801547196f52a92a139434e52cc0377e02ceaa`.
- Researcher intent: `claude-opus-5` through
  `meta-claude-cli-opus-5`, maximum effort.
- Generator identity discovered in the live Model API catalog:
  `claude-5-opus`; logical deployment `meta-model-api-claude-5-opus`.
- Unchanged row judge: `gpt-5-6-luna`.
- Unchanged target/training base: `gemma-4-31B-it`.
- Jobs: none.
- Attempt: none.
- Decision: no-go until runtime enablement, preflight, and explicit role
  confirmation are complete.
