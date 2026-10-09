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

The Kimi provider reserves up to 65,536 completion tokens. The initial 16,384-token setting was insufficient for the long AAR prompt after its first parallel MCP-tool batch and produced a thinking-only terminal response.

The endpoint's vLLM chat template enables reasoning by default and ignores Kimi Code's native `thinking: {type: "disabled"}` field. Run 10 therefore uses Kimi Code's dedicated `kimi` provider trait for native multi-turn tool-history encoding plus an opt-in loopback request-policy proxy that injects `chat_template_kwargs.enable_thinking=false`. This keeps tool execution within a turn reliable and also prevents the endpoint credential from entering the Kimi child process. Other Kimi configurations and the Claude path do not use this proxy.

Kimi Code may treat a textual statement of future intent as the end of a noninteractive prompt. The Kimi-only adapter therefore resumes the same CLI session until `share_finding` is called, with a bounded maximum of 24 continuation prompts. This does not alter the Claude SDK path.

## Monitoring and recovery

The durable attempts live under `/storage/home/winnieyangwn/aar-runs/run10_kimi/`. Monitoring checks Slurm state, `metadata/children.env`, session counts, score/finding pairs, evaluator fail-closed markers, merge manifests, and free space. A failed evaluator may be replaced against the same queue; research-chain history and retained results are never deleted or overwritten.
