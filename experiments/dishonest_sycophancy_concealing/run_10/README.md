# Run 10: Kimi research agents

Run 10 is the Run 7 five-chain experiment with `Kimi-K2.6` as the research agent. It deliberately preserves the existing Claude default: Kimi is selected only when `AAR_AGENT_BACKEND=kimi` is exported by this run's launcher.

## Topology

- Research: five CPU-only Kimi chains, seeds `alpha beta gamma delta epsilon`, at most 50 sessions per chain.
- Training: decoupled one-GPU jobs submitted by each chain.
- Evaluation: five independent four-GPU workers using vLLM 0.25.1, language-model-only mode, and atomically merged LoRA checkpoints.
- Endpoint: `serve_api_v2` deployment `steerability_8-kimi26`, served model `Kimi-K2.6`.
- Storage: durable attempts at `/storage/home/winnieyangwn/aar-runs/run10_kimi/`; temporary merged checkpoints are node-local and removed after each evaluation.

Each Kimi session dynamically runs `serve.sh generate-opencode-config steerability_8-kimi26`. Run 10 selects Kimi Code's dedicated `kimi` provider trait so multi-turn Kimi tool history uses its native encoding. A loopback request-policy proxy holds the current endpoint key in the AAR process and gives Kimi Code a non-secret local credential. The proxy adds `chat_template_kwargs.enable_thinking=false`, which is the control this vLLM deployment requires for reliable tool execution; it is enabled only for Run 10. `KIMI_AGENT_MODEL` remains unset because Kimi Code registers the environment-provided model under its own default alias.

The research prompt is installed as a Kimi agent profile, so its constraints are system-level rather than user-message text. That profile disables Kimi Code's separate goal/subagent tools and asks for one compact initial literature call; AAR remains the sole owner of iteration continuation and completion.

Kimi AAR sessions use Kimi Code's `--auto` permission mode because the Slurm research process is noninteractive. This lets the checkpointed scaffold, edit, validation, and training commands execute without an unanswered approval prompt. It is opt-in for this backend and does not change generic Kimi invocations or Claude.

The Kimi MCP bridge bounds text responses at 16,000 characters. Large literature lists are reduced at complete-entry boundaries and carry truncation metadata, keeping discovery context directly usable instead of triggering Kimi Code's external tool-result spill file.

## Launch sequence

From the isolated HPC `multi_kimi` checkout:

```bash
experiments/dishonest_sycophancy_concealing/run_10/install_kimi_runtime.sh
experiments/dishonest_sycophancy_concealing/run_10/submit_run_10.sh canary
```

After the canary chain finishes and its evaluator produces a score/result pair:

```bash
python experiments/dishonest_sycophancy_concealing/run_10/verify_run_10_canary.py <canary-attempt>
experiments/dishonest_sycophancy_concealing/run_10/submit_run_10.sh full <canary-attempt>/metadata/canary_passed.json
```

The full run is active only after `metadata/children.env` records five distinct evaluator IDs and five distinct research-chain IDs.

## Monitoring

```bash
python experiments/dishonest_sycophancy_concealing/run_10/status_run_10.py <attempt>
squeue -j <launch-and-child-job-ids> -o '%.18i %.30j %.10T %.10M %R'
```

The scored canary is fail-closed on the research backend and evaluator protocol. Its `metadata/canary_passed.json` must prove the Kimi MCP round trip, one score/finding pair, vLLM 0.25.1 language-model-only execution, merged-checkpoint strategy, retained merge manifest, and ephemeral checkpoint cleanup.

## Isolation and provenance

The run starts with a fresh forum and fresh chain memories; it does not reconstruct Run 7's Claude history. It reuses Run 7's validated baseline and public-source bundle because the evaluator model and protocol are unchanged. The attempt records the exact Git commit, baseline provenance, endpoint deployment/model, pinned Kimi runtime, child Slurm IDs, and evaluator-runtime snapshot. Held-out data stays evaluator-only; research-readable outputs contain scores and public findings, never held-out items.
