# Run 10: Kimi research agents

Run 10 is the Run 7 five-chain experiment with `Kimi-K2.6` as the research agent. It deliberately preserves the existing Claude default: Kimi is selected only when `AAR_AGENT_BACKEND=kimi` is exported by this run's launcher.

## Topology

- Research: five CPU-only Kimi chains, seeds `alpha beta gamma delta epsilon`, at most 50 sessions per chain.
- Training: decoupled one-GPU jobs submitted by each chain.
- Evaluation: five independent four-GPU workers using vLLM 0.25.1, language-model-only mode, and atomically merged LoRA checkpoints.
- Endpoint: `serve_api_v2` deployment `steerability_8-kimi26`, served model `Kimi-K2.6`.
- Storage: new durable attempts default to `/checkpoint/ram/aar/$USER/run10_kimi/`; temporary merged checkpoints are node-local and removed after each evaluation. The existing Run 10 attempt remains at its original `/storage/home` path and is never moved implicitly.

## Directory layout

Run 10 follows the same responsibility-based layout as Run 12:

```text
run_10/
├── config/       # Validated operational YAML and shared environment
├── launch/       # Login-node submission entrypoint
├── slurm/        # Scheduled pipeline payload
├── canary/       # Endpoint, method-smoke, and lifecycle proof checks
├── recovery/     # Selective preserved-state resume entrypoint
├── runtime/      # Pinned Kimi installer and evaluator snapshotter
├── analysis/     # Status utility and retained frontier outputs
├── README.md
├── PLAN.md
└── PROGRESS.md
```

Shell files under `launch/`, `recovery/`, and `runtime/` are operator
entrypoints. The `slurm/` payload runs only after allocation. Configuration,
canary verification, and retained analysis outputs remain separate so the run
root contains only its three durable documents.

Each Kimi session dynamically runs `serve.sh generate-opencode-config steerability_8-kimi26`. Run 10 selects Kimi Code's dedicated `kimi` provider trait so multi-turn Kimi tool history uses its native encoding. A loopback request-policy proxy holds the current endpoint key in the AAR process and gives Kimi Code a non-secret local credential. The proxy adds `chat_template_kwargs.enable_thinking=false`, which is the control this vLLM deployment requires for reliable tool execution; it is enabled only for Run 10. `KIMI_AGENT_MODEL` remains unset because Kimi Code registers the environment-provided model under its own default alias.

The research prompt is installed as a Kimi agent profile, so its constraints are system-level rather than user-message text. That profile disables Kimi Code's separate goal/subagent tools and asks for one compact initial literature call; AAR remains the sole owner of iteration continuation and completion.

Kimi AAR sessions set Kimi Code's `defaultPermissionMode = "auto"` in the temporary session configuration because `--prompt` cannot be combined with the `--auto` CLI flag. This lets the checkpointed scaffold, edit, validation, and training commands execute without an unanswered approval prompt. It is opt-in for this backend and does not change the user's Kimi configuration, generic Kimi invocations, or Claude.

The same temporary Kimi configuration installs a fail-closed `PreToolUse` hook:
direct `Write` and `Edit` calls may target only `AAR_IDEAS_DIR` or the chain's
exact `AAR_AGENT_LOG_PATH`. Immediately before deterministic training submission,
the adapter hashes the shared submission scripts against the current Git commit
and runs `bash -n` on every protected shell file. Any mismatch, syntax failure,
wrapper timeout, nonzero wrapper exit, or missing verified receipt is a shared
orchestration incident—not a method iteration. The detecting chain writes
`.orchestration_incident.json`, exits without retry backoff, and peer chains stop
at their next boundary or before training submission. A repaired, newly deployed
commit makes the old revision-scoped marker inactive so selective recovery can
resume preserved state.

Run-10's Kimi-only request shim exposes one required function on exact continuation checkpoints and uses `tool_choice="required"`. Initial research and tool arguments remain model-selected; the shim only ensures that a checkpoint requiring `Read`, `Bash`, `Write`, or an AAR MCP function is emitted as a real structured call rather than narrated as prose.

Before proposal submission, Run 10 also requires a source-hash-bound method-contract proof with a no-GPU dry run. This catches import failures, unavailable BitsAndBytes use, invalid Gemma-4 PEFT targets, and missing `MethodConfig`, `run_experiment`, result fields, or timing phases that syntax compilation cannot detect. The training submitter repeats the proof independently and emits a terminal failure marker on any later training failure.

Failure markers are structured and held-out-safe. Training exceptions publish a sanitized exception type/message, stable error code, exit code, and the corresponding research-side Slurm log path. Evaluator failures publish a safe stage and category without raw evaluator traces or held-out details. The next Kimi session receives the latest unscored failure automatically; successful retry scores suppress stale failure feedback. This behavior is confined to the Kimi adapter, while the marker format remains backward compatible for shared infrastructure and Claude runs.

Run-10 training jobs request 128 GiB of host memory. Run-10 evaluators request
Slurm `--mem=0`, meaning all memory available on their allocated node; current
GB300 nodes advertise 900 GiB. This is also the shared evaluator default for
future Claude and Kimi runs; a run may explicitly request less through
`AAR_EVAL_MEM` or its operational YAML. Every approved Run-10 submission also writes an
atomic run-ID-to-Slurm-ID receipt. Repeating the same submission returns the
existing job ID instead of creating a duplicate, and Kimi advances to polling
only after that receipt exists.

Operational policy is declared in `config/run.yaml`, separately from the
evaluator-private benchmark suite YAML. It controls the durable storage root,
checkpoint retention policy, evaluator memory, truncation ceiling, research
backend, and Kimi turn timeout. The shared loader validates every supported key
and rejects unknown or malformed values before Slurm submission. Full runs
prune the redundant `_train` staging copy after an adapter enters the submission
queue while retaining one evaluated adapter for later champion selection.

The Kimi MCP bridge bounds text responses at 16,000 characters. Large literature lists are reduced at complete-entry boundaries and carry truncation metadata, keeping discovery context directly usable instead of triggering Kimi Code's external tool-result spill file.

## Launch sequence

From the isolated HPC `multi_kimi` checkout:

```bash
experiments/dishonest_sycophancy_concealing/run_10/runtime/install_kimi_runtime.sh
experiments/dishonest_sycophancy_concealing/run_10/launch/submit_run_10.sh smoke
```

The smoke mode first runs the CPU replay and live Kimi protocol gates. It then starts one CPU-only Kimi chain with no evaluator. Once Kimi produces an approved method, a time-bounded one-GPU job loads the real Gemma model, runs the method's real CUDA/PEFT path for one optimizer step, saves and reload-validates the adapter, and exits. Only after that proof passes does the launcher publish the holdout, stage that exact adapter, and start one four-GPU evaluator on demand. The original Kimi chain remains alive to consume the score and publish the finding.

After the on-demand evaluator produces a score/result pair:

```bash
python experiments/dishonest_sycophancy_concealing/run_10/canary/verify_run_10_canary.py <smoke-attempt>
experiments/dishonest_sycophancy_concealing/run_10/launch/submit_run_10.sh full <smoke-attempt>/metadata/canary_passed.json
```

The full run is active only after `metadata/children.env` records five distinct evaluator IDs and five distinct research-chain IDs.

## Monitoring

```bash
python experiments/dishonest_sycophancy_concealing/run_10/analysis/status_run_10.py <attempt>
squeue -j <launch-and-child-job-ids> -o '%.18i %.30j %.10T %.10M %R'
```

The Run-7-style frontier plot is generated from durable score and session
artifacts rather than a run-specific hard-coded point list:

```bash
python scripts/plot_aar_frontier.py <attempt-or-team-dir> \
  --output-stem <output-dir>/aar_frontier \
  --title 'AAR Run 10 · Kimi 5×50'
```

The reusable plotter discovers the single team when given an attempt, joins
score creation timestamps to chronological per-chain session logs across
restarts, treats a point as frontier-valid only when both the capability and
regression gates pass, and writes PNG, SVG, and a JSON provenance snapshot.
The committed 2026-10-10 snapshot is
[`aar_5x50_frontier_style.svg`](analysis/aar_5x50_frontier_style.svg), with the matching
PNG and provenance JSON beside it.

After confirming a chain is terminal or genuinely hung, resume only the affected
seed in the same preserved attempt:

```bash
experiments/dishonest_sycophancy_concealing/run_10/recovery/resume_run_10.sh \
  /storage/home/winnieyangwn/aar-runs/run10_kimi/full_attempts/<attempt> beta
```

The Run 10 wrapper configures its endpoint and experiment policy, then delegates
to the reusable `scripts/resume_aar_team.sh` recovery engine. The engine refuses
duplicate active jobs, replenishes missing evaluators, and subtracts
already-started sessions from the seed's original 50-session budget.
Pass multiple space-separated seeds as one quoted argument when needed. Recovery
job IDs, remaining budgets, timestamps, and the recovery source commit are appended
to `metadata/recovery_jobs.tsv`; existing results are never reset.

Future experiments can build a thin wrapper around the same engine by sourcing
their normal runtime configuration and exporting `AAR_RESUME_DEFAULT_SEEDS`,
`AAR_RESUME_EVALUATOR_COUNT`, and `AAR_RESUME_HOURS`. An optional
`AAR_RESUME_ALLOWED_SEEDS` allowlist and expected branch/mode guards keep
experiment-specific policy outside the shared recovery mechanics.

## Exporting the champion

After all research-chain jobs have reached a terminal state and their final scores have landed, run:

```bash
python scripts/export_aar_champion.py \
  --attempt-dir /checkpoint/ram/aar/$USER/run10_kimi/full_attempts/<attempt> \
  --output-dir /checkpoint/ram/aar/$USER/run10_kimi/full_attempts/<attempt>/champion \
  --suite honesty_sycophancy_concealing_uncertainty \
  --inference-backend vllm \
  --require-artifact-type adapter \
  --base-model google/gemma-4-31B-it
```

Run 10 retains the exact submitted PEFT adapters. The merged vLLM checkpoints are intentionally
ephemeral, so the champion package contains the evaluated adapter and records the frozen base model.
Use `scripts/merge_peft_adapter.py` afterward only if the receiving system requires a full merged
checkpoint.

The scored smoke/canary is fail-closed on the research backend and evaluator protocol. Its `metadata/canary_passed.json` must prove the Kimi MCP round trip, real-GPU generated-method smoke, adapter reload, on-demand evaluator launch, one score/finding pair, vLLM 0.25.1 language-model-only execution, merged-checkpoint strategy, retained merge manifest, and ephemeral checkpoint cleanup.

## Isolation and provenance

The run starts with a fresh forum and fresh chain memories; it does not reconstruct Run 7's Claude history. It reuses Run 7's validated baseline and public-source bundle because the evaluator model and protocol are unchanged. The attempt records the exact Git commit, baseline provenance, endpoint deployment/model, pinned Kimi runtime, child Slurm IDs, and evaluator-runtime snapshot. Held-out data stays evaluator-only; research-readable outputs contain scores and public findings, never held-out items.
