# Run 12 Canary 2 Trial 12 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). This
log contains orchestration metadata only; never record generated rows, prompts,
responses, credentials, or held-out content.

### ⏳ 06:24 PT — PREPARING: repaired budget and broker contracts

Trial 11 is terminal and preserved. Native repair
`da9e12a43710ced9d407822e55c6e7c541e57a27` and AAR repair
`b8629a8fa3374111a1b55e40b1a9d114c7e5650d` are committed, synchronized, and
validated locally and on HPC. The old native detached worktree remains
untouched; a new immutable HPC worktree is pinned to `da9e12a`.

```text
✓ Trial 11 terminal evidence preserved
✓ Native atomic budget and broker-cost repair committed
✓ AAR campaign derivation and typed feedback repair committed
✓ Local and HPC focused regression gates
⏳ Explicit model/config confirmation
○ Trial 12 record commit and synchronization
○ Launcher and research allocation
○ Workspace authoring and freeze
○ Canonical baseline and meta iterations 1–3
○ Production and verified handoff
○ One-step training smoke
```

The proposed mapping is Kimi-K2.6 researcher `aar_8-kimi26`, Kimi-K2.6
generator `autodata_8-kimi26`, Claude Opus 4.8 monitor, fixed Gemma 4 31B
target/training checkpoint with retained deployment
`winnieyangwn-r12-alpha-i1-c0dab4f7`, and `gpt-5-6-luna` row judge. Evaluator
roles remain disabled.

The run contract is exact `3/3/3`, disjoint `64/32/32`, concurrency 32,
1,250→1,000 production, five final feedback rounds, one HTTP transport attempt,
707 native attempts, and a `$24,100` hard safety ceiling. The derived worst-case
requirement is `$24,099.427584`; expected spend is lower. No Trial 12 job or
attempt root exists yet.
