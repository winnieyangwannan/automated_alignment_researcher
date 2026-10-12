# Run 13 Canary Trial 2 progress

Append-only operational record. All timestamps use Pacific Time (`PT`).

## 2026-10-11

<a id="run13-trial2-protocol-recovery"></a>

### 🛠️ 23:20 PT — FIX: Trial 2 prepared after protocol-routing failure

> [!IMPORTANT]
> Trial 2 retains the confirmed Opus/Luna/Gemma contract and adds an explicit,
> fail-closed generator-transport boundary plus durable `trial2` identity.

```text
✓ Trial 1 failure retained
✓ Protocol-blind Kimi assumption identified
✓ Model API Responses route separated from Kimi proxy routing
○ Method authoring and contract check
○ Proposal review and approval
○ AutoData workspace registration and authoring
○ Meta-optimization
○ Production and verified export
○ Training smoke
```

- Preserved Trial 1 attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run13-bootstrap-canary/20261012T060647Z-67ab7629e12e`.
- Trial 1 jobs: launcher `1829625` completed; chain `1829639` failed `2:0`;
  controller `1829640` failed closed without retry; evaluator absent.
- Failure boundary: runtime-profile validation, before method authoring or any
  AutoData workspace, production, training, score, or finding.
- Trial 2 config identity: `run13-canary-trial2`.
- Trial 2 jobs: none yet.

#### ⏭️ Next step

Validate and synchronize the exact protocol-aware source commit, then launch
only through `trial_2/submit_canary.sh`.

<a id="run13-trial2-profile-registry-failure"></a>

### ❌ 23:32 PT — FAIL: Runtime rejected the strict Claude profile name

- Preserved attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run13-trial2-bootstrap-canary/20261012T062700Z-d4ce938d0ef7`.
- Launcher `1829776` completed; chain `1829799` failed `1:0`; controller
  `1829800` classified it permanent and failed closed; evaluator absent.
- The protocol-aware boundary passed. The next validator still used a
  hard-coded legacy profile-name registry and rejected
  `target-aware-model-api-claude-opus-4-8-c8-v1`.
- No method, proposal, workspace, provider generation, production, training,
  evaluator, score, or finding was created.

#### ➡️ Next step

Retain Trial 2 unchanged and use Trial 3 for the reviewed config-driven fix.
