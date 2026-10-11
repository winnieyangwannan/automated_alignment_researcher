# Run 17 plan

All timestamps and operator records use Pacific Time (`PT`).

## Ordered plan

1. Compile and validate the Run 17 YAML and Claude Model API runtime profile.
2. Commit the focused source changes and synchronize that exact commit to HPC.
3. Confirm the complete model-role mapping, target deployment, and synchronized
   source commit with the user before any Model API proof or Slurm submission.
4. Prove the exact Claude generator, Gemma target, Luna judge, broker image, and
   provider-usage contracts with a retained fail-closed broker canary.
5. Launch one alpha research session with at most one infrastructure retry.
6. Complete workspace authoring, baseline approval, and exactly three
   meta-optimization iterations over disjoint `64/32/32` partitions.
7. Produce 1,000 verified rows from 1,250 fixed source tasks at concurrency 32.
8. Verify the handoff, consume all 1,000 rows, execute one optimizer step, and
   validate the saved adapter.
9. Stop before evaluator allocation, scoring, result publication, or promotion.

## Invariants

- Only the Run 12 Kimi researcher and Kimi generator/teacher roles change.
- The generator uses `https://api.meta.ai/v1/responses` and authenticates only
  with the broker-injected `MODEL_API_KEY`.
- The researcher uses `claude-opus-4-8` at maximum effort.
- Target, judge, data contract, recipe, concurrency, budget ceiling, and
  training-smoke boundary match Run 12 Canary 2 Trial 12.
- Generated examples, prompts, target responses, credentials, and held-out
  information never enter Git documentation.
