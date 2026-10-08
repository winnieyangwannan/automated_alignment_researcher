# Run 10 plan

Run 10 changes only the research-agent backend from Claude to Kimi-K2.6. The Gemma 4 target, multidimensional suite, retained baseline, training protocol, and merged-checkpoint vLLM 0.25.1 evaluator remain equivalent to Run 7.

## Gates

1. Validate `steerability_8-kimi26` is serving `Kimi-K2.6` and resolves dynamically through `serve_api_v2`.
2. Install the pinned ARM64 Node 22.22.0 and Kimi Code 2.1.1 runtime on HPC; verify `node-pty`.
3. Synchronize a clean, committed `multi_kimi` checkout and build its own ARM64 `.venv` on a GPU compute node.
4. Prove a complete Kimi → AAR MCP tool → Kimi round trip without printing or persisting the endpoint key.
5. Run one fresh chain for one iteration with one four-GPU evaluator. Require a score/finding pair, vLLM 0.25.1 language-model-only markers, merged-checkpoint provenance, retained merge manifest, and deletion of the ephemeral merged checkpoint.
6. Only after the canary proof passes, launch five fresh chains (`alpha` through `epsilon`) for 50 sessions each and five distinct four-GPU evaluators.

Fifty iterations means 50 research sessions started per chain. A session that fails before scoring still consumes an iteration, so completion is reported with both started-session and successful score/result counts.

## Monitoring and recovery

The durable attempts live under `/storage/home/winnieyangwn/aar-runs/run10_kimi/`. Monitoring checks Slurm state, `metadata/children.env`, session counts, score/finding pairs, evaluator fail-closed markers, merge manifests, and free space. A failed evaluator may be replaced against the same queue; research-chain history and retained results are never deleted or overwritten.
