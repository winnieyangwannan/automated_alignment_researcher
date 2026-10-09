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

Continuation prompts are single-action checkpoints rather than identical task replays. They advance only after the recorded tool arguments prove the previous action: exact template read, scaffold copy, method write, syntax/phase validation, idea proposal, one training submission, foreground score polling, score read, and finding publication. Each recovery prompt requires exactly one native structured tool call and forbids prose/XML representations of proposed calls. The no-local-GPU workflow consumes the score produced by the asynchronous training/evaluator path and never calls `evaluate_model` redundantly.

For these fail-closed continuation checkpoints only, the Kimi request proxy exposes the single required function and requests `tool_choice="required"`. This prevents Kimi-K2.6 from narrating or inventing Claude/XML syntax instead of selecting the available function, while routing through vLLM's automatic Kimi tool parser. The model still supplies all tool arguments and research content, and normal research turns retain automatic tool choice.

Candidate validation imports the generated module and proves the complete training interface: `MethodConfig(output_dir=..., dry_run=True)`, a successful no-GPU `run_experiment(config)` result, all required phase contexts, available quantization dependencies, and the required language-tower-only Gemma-4 PEFT target regex. The proof records the candidate source hash; a later edit invalidates it automatically. A failed proof sends Kimi back to a forced `Write` checkpoint with the concrete errors instead of allowing proposal or training. The submission wrapper independently repeats this gate, and Run-10 training failures publish a terminal failure marker so neither the research chain nor evaluator waits indefinitely.

Training submission is receipt-driven rather than inferred from Kimi's Bash text. The Run-10-only receipt binds the approved run ID to a numeric Slurm job ID under the team directory, serializes retries, and makes repeated submission idempotent. Run 10 overrides training host memory to 128 GiB after the 64 GiB canary crossed its cgroup limit during Gemma training; the shared 64 GiB default and Claude path are unchanged.

The AAR Kimi session uses Kimi Code's documented `defaultPermissionMode = "auto"` (Never Ask) configuration. This is required because Kimi Code forbids the `--auto` flag with noninteractive `--prompt`, while the Slurm research chain cannot answer permission prompts for scaffold writes or training commands. The setting is written only into the session's temporary Kimi home; the generic Kimi adapter default, user configuration, and Claude SDK path remain unchanged.

The AAR session uses a Kimi agent profile with actual system-level instructions. Kimi Code's internal goal, subagent, and to-do tools are disabled for this profile so its separate goal-continuation runtime cannot compete with AAR's session loop. Initial literature discovery is one compact unfiltered call, with at most one focused follow-up, to avoid filling the context with multiple redundant full-detail surveys.

Kimi MCP text responses are bounded to 16,000 characters. Oversized literature results remain valid JSON and include as many complete summary entries as fit plus explicit truncation metadata. This prevents Kimi Code from replacing an 80,000-character discovery result with a spill-file reference that the model then fails to read.

## Monitoring and recovery

The durable attempts live under `/storage/home/winnieyangwn/aar-runs/run10_kimi/`. Monitoring checks Slurm state, `metadata/children.env`, session counts, score/finding pairs, evaluator fail-closed markers, merge manifests, and free space. A failed evaluator may be replaced against the same queue; research-chain history and retained results are never deleted or overwritten.
