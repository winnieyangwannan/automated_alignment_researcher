# Run 14 progress

Append-only operational record. All timestamps use Pacific Time (`PT`).
No credentials or hidden item-level evaluation content belongs here.

## 2026-10-13

<a id="run14-recipe-setup-started"></a>

### 🔎 00:42 PT — OBSERVATION: recipe comparison setup requested

> [!NOTE]
> Preparing the Trial 14 configuration with unchanged Opus 4.8 roles and an
> isolated Run 14 recipe treatment. Recipe-directory clarification is pending.

- Source branch: `autodata`.
- Setup source: `e17ab31781fc67edfaa8d19b160296340378cd13`.
- Existing v3 edits, unrelated figures and papers remain user-owned.
- Jobs/model calls: none. Attempt: none.

```text
○ Recipe selection and offline configuration verification
○ Endpoint/MCP and recovery preflight
○ Fresh workspace registration and pipeline approval
○ Ten native meta iterations and final test
○ Production: 1,000 accepted rows
○ Verified Gemma training smoke
```

This is configuration preparation; no Run 14 lifecycle stage has started.

<a id="run14-config-validated"></a>

### ✅ 00:44 PT — PASS: requested-path YAML and host contracts validated

> [!TIP]
> The YAML differs from Run 13 Trial 14 only in `run_id` and `recipe_root`.
> Strict YAML inspection, offline compilation/artifact validation, and native
> recipe staging passed. No model calls or jobs were made for Run 14.

- Config: `canary/v3_recipe_comparison/config/run.yaml` (from the run root).
- Exact requested recipe: `aar/autodata_recipes/dishonest_sycophancy_concealing`.
- Rubric: `run9-axis-conditioned-v4`,
  `sha256:e7d0cfd17f9095675c9b2a65e75244faa0504190d4d2c89f42c143a626de1938`.
- Model mapping: unchanged Trial 14 Opus 4.8 researcher/monitor/optimizer/
  generator, GPT-5.6 Luna row judge, fixed Gemma 4 31B IT probe/training base.
- Validation: 14 focused pytest tests passed; shell syntax and ShellCheck error
  checks passed for all six affected shell/payload files; Ruff passed for the
  new verifier and updated Run 14 contract tests.
- Verifier: `launch/verify_config.py` in the gate; offline target-binding
  fixtures live only in a temporary directory and make no inference calls.

```text
✓ YAML parity, strict loading and offline runtime/recipe staging
○ Resolve recipe identity for the intended v3 comparison
○ Endpoint/MCP and recovery preflight
○ Fresh workspace registration and pipeline approval
○ Ten native meta iterations and final test
○ Production: 1,000 accepted rows
○ Verified Gemma training smoke
```

Run 14 has no attempt, jobs, exports, receipts or adapter. The supplied path
currently holds the older synthetic recipe; the paper-grounded work is in
`v3_grounding` and has documented host/pipeline incompatibilities. The pending
path clarification does not authorize a recipe rewrite or a launch.

### ⏭️ 00:44 PT — NEXT: HPC synchronization deferred for active checkout users

> [!IMPORTANT]
> The `organize-aar-experiment` skill forbids advancing a checkout underneath
> an active attempt. Jobs `1865857` and `1865841` execute training scripts from
> `/storage/home/winnieyangwn/aar-worktrees/autodata` and use it as `WorkDir`.
> Keep this change source-only until the checkout is safe to advance.

- Destination preflight: `fair-cw-use2-1`, branch `autodata`, HEAD
  `9fefddeb81367b3f5a8c63ad5c2717322422e9cd`.
- HPC untracked `.aar-method-contract.json` and `output/` are preserved.
- Existing Trial 14 chain `1865399` uses its immutable attempt snapshot; its
  controller `1865400` also points to that snapshot. Neither is altered.
- Future sync: direct Git-over-SSH with `git-sync-from-dev-to-hpc`, require
  matching branch and fast-forward, collision-check incoming paths, preserve
  ignored state and use `with-proxy` for the temporary-ref push.
- No transfer, temporary ref, HPC merge or GitHub push was performed.
