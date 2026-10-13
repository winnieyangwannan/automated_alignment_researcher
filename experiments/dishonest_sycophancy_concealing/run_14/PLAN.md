# Run 14 plan

Recorded: 2026-10-13 00:42 PT. Status: planned; no jobs submitted.

1. `config/run.yaml` uses the exact requested recipe path. Resolve the recorded
   recipe-identity caveat before interpreting an attempt as a v3 comparison.
2. Verify that only `run_id` and `recipe_root` differ, and validate through the
   strict AAR YAML loader and runtime-profile resolver.
3. Compile offline runtime artifacts and check recipe/host contracts. Report
   incompatible boundaries before launch; do not modify the in-progress v3
   recipe as part of run configuration.
4. Commit this focused setup on `autodata` and synchronize through direct
   Git-over-SSH after verifying the matching HPC worktree and preserving its
   local state. Do not advance a checkout used by an active attempt.
5. After separate launch authorization and explicit model-role confirmation,
   verify external recovery/provider prerequisites and create a fresh attempt.
6. Run all ten meta iterations; retain aggregate candidate outcomes and source
   identities. Finalize, produce 1,000 accepted rows, verify one Gemma training
   step, and stop at `training_smoke`.
7. Compare against actual Trial 14 v2 evidence using the definitions and
   limitations in `README.md`. Never count infrastructure failure as a
   scientific challenge result.

The ordered lifecycle is workspace registration → grounded pipeline approval →
meta-optimization → final test → production → training smoke. Preserve all
existing attempts and results. No larger topology or scored evaluation is
requested.
