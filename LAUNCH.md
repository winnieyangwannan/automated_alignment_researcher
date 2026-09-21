# Launching an autonomous AAR chain

The agent (Claude, via `claude_agent_sdk`) iteratively designs safety-improvement
methods, trains + evaluates each via the submit-model loop, and shares findings
on a leaderboard the other chains can read. The **safety axis is configurable**
(default: sycophancy) — see the swap note below.

## Librarian only

To populate the literature baseline without launching an AAR chain:

```bash
sbatch scripts/litreview.sh sycophancy <team-id> 30
```

The job is CPU-only and requests account `ram`, partition `g3`, and QoS
`g3_ram_high`. The team launcher allows an account override through
`AAR_SLURM_ACCOUNT`. The job resolves
the repository from the script location, uses `<repo>/.venv/bin/python`, sources
`<repo>/.env`, and writes the default baseline and workspace beneath the ignored
`<repo>/_runs/litreview/` directory. Under Slurm it resolves the checkout from
`SLURM_SUBMIT_DIR`; override these choices with `AAR_REPO`, `HARNESS_PY`,
`HARNESS_ENV`, `LIT_AXIS_DIR`, or `LITREVIEW_WORKSPACE`.
Authentication can use either an executable Claude CLI (resolved from
`CLAUDE_CLI_PATH` or `PATH`) or a direct `ANTHROPIC_API_KEY`. With the default
`LITREVIEW_WEB_MODE=auto`, the FAIR route is selected only when the CLI's help
advertises `--secure-internet-mode`; operators may explicitly select
`meta_secure` or `native_web`. The Meta route enables
`META_CLAUDE_SECURE_INTERNET_MODE=1`, removes the direct Anthropic key, and runs
the librarian with `permission_mode="dontAsk"`, built-in `tools=["Bash"]`, no
settings sources, and strict MCP configuration. Its only preapproved calls are
the exact repository-local `scripts/aar-paper-search` command and the explicit
`get_literature`/`share_literature` MCP tools; its dedicated MCP server does not
advertise evaluation, leaderboard, or proposal tools. General Bash, file tools,
and native `WebSearch`/`WebFetch` are not available on this route.

Unrelated model, cloud, and tracking credentials—including `MODEL_API_KEY`,
Hugging Face, OpenAI, AWS, Runpod, and W&B variables—are removed from the Meta
secure librarian child because they are unrelated to its authentication. The
portable native/direct-key route retains its provider credentials.

The helper accepts only `search <query> [--limit 1..10]` and `fetch <arxiv-id>`.
It uses `/usr/bin/curl` with a fixed argument vector, response/time bounds, and
fixed arXiv API and HTML endpoints; it never accepts a URL or invokes a shell.
Fetch returns bounded visible paper text when arXiv HTML is available and an
explicitly labeled abstract fallback otherwise. The prompt prohibits claims not
supported by the returned content. `/usr/bin/curl` and the tracked helper are
checked before a FAIR job starts. This is a Claude tool-policy boundary, not
kernel isolation, so continue to use the disposable librarian workspace and do
not place secrets there.

A direct Anthropic key or any other executable Claude CLI keeps the portable
native-`WebSearch`/`WebFetch` behavior and does not enable Meta secure-internet
mode. The model defaults to `claude-sonnet-4-6`. The job exits nonzero if neither
authentication path is available or if it cannot reach the requested entry
count, so callers can safely gate AAR launch on its completion. The project pins
`claude-agent-sdk==0.2.157`; the older 0.1.30 release cannot complete the FAIR
CLI control handshake.

This portability work covers the standalone librarian and the librarian pre-phase
inside `launch_team.sh`. It also repairs the known shell parse errors in the chain,
training, and evaluator wrappers. It does **not** make the complete AAR/evaluator
deployment portable: remaining site-specific scheduler, credential, cache, and
evaluator paths must be configured or ported before an end-to-end launch.

## One chain
```bash
sbatch --job-name=aar-syco-v1 scripts/slurm_aar_chain.sh explore 10
```
- `explore` = seed/chain name; `10` = max hours.
- The per-axis config (`PROMPT_TEMPLATE=prompt_safety.jinja2`, `SUITE_NAME`,
  `HELD_OUT_BENCH`, `SAFETY_PROPERTY`, `SAFETY_OBJECTIVE`, `SEED_METHOD`,
  `TARGET_MODEL`) comes from **`scripts/axis_env.sh`** — the SINGLE source the chain
  AND the team launcher both `source`, so they can't disagree. The script also wires
  `HARNESS_TRANSPORT=fs`, `LOCAL_MODE=true`, `ANTHROPIC_API_KEY`+`OAI_API` from the
  safety-aar `.env`, a shared `LOCAL_FINDINGS_DIR` forum, and regenerates the prompt's
  `baselines.json` from `benchmark_docs/<axis>/baseline.json`.

### Choosing the AXIS and the MODEL (independent)
The AAR run is specified by two **independent** selectors, both env vars resolved in
`scripts/axis_env.sh`:
- **`AXIS`** — the safety property to optimize (`sycophancy` built in; others via
  `scripts/axis/<name>.env`).
- **`MODEL`** — which of the 6 target models to optimize (`scripts/models.sh`):
  `qwen | mistral | llama | olmo | gemma | phi` (or a full HF id). Unknown → fail-fast.

```bash
# default (sycophancy on qwen)
scripts/launch_team.sh "alpha beta gamma" 100 47
# pick axis + model
AXIS=sycophancy MODEL=mistral scripts/launch_team.sh "alpha beta" 100 47
```
The chains inherit BOTH (forwarded via `--export`); `TEAM_ID`, job names, and the
per-model prompt-baselines file (`baselines.<axis>.<model>.json`) are all tagged by
axis+model, so different models never clobber each other.

**Eval side (per axis+model), as the eval user — REQUIRED before launching the AAR:**
```bash
AXIS=<axis> MODEL=<model> scripts/publish_holdout.sh      # publishes holdout + per-model baselines
AXIS=<axis>               scripts/launch_eval_worker.sh   # scores submissions for that axis
```
> **Prerequisite + isolation:** `publish_holdout.sh` MUST run (for this exact axis+model)
> *before* the team is launched — it sets up the holdout the worker scores and the per-model
> baselines the prompt shows. It is an **eval-side operator step the AAR never sees**: it is
> not in the AAR's prompt, no tool exposes it, and the AAR never runs it. Keep it that way —
> document this prerequisite only in operator/eval docs (here + `ISOLATION.md`), never in the
> prompt. See `ISOLATION.md` → "Publishing the holdout."

**Per-model baselines:** the composite is a delta vs the base model, so each model
needs its OWN measured baselines in `benchmark_docs/<axis>/baseline.json` (deploy it
**eval-side, mode-700** — it names the held-out). Today only **qwen** is measured;
other models fall back to qwen's `PUBLISHERS` values with a loud `WARN PLACEHOLDER` until
you measure + publish them. Selection works regardless; the deltas are only trustworthy
once that model's baselines are measured.

**Adding an axis:** add `scripts/axis/<name>.env` (copy the sycophancy block in
`axis_env.sh`) + `benchmark_docs/<name>/` + the `_SUITE_CORE`/`_HELD_OUT` entries in
`publish_suite.py`. No prompt/monitor/tool edits — they all derive from these.

## N chains in parallel (they see each other on the leaderboard)
```bash
for v in v1 v2 v3 v4 v5 v6 v7 v8 v9; do
  sbatch --job-name=aar-syco-$v scripts/slurm_aar_chain.sh $v 10
done
```

## What each iteration does (per the system prompt)
1. Read `AGENT_LOG.md` + `get_leaderboard` (build on prior + others' findings).
2. Write/improve a method `aar/ideas/<name>/run.py`
   (`run_experiment(config) -> {model_path}`), training on allowed data only.
3. `sbatch scripts/slurm_run_method.sh <idea> <run_id>` → trains, submits, scores
   on the secret suite, writes the composite; poll + read it. (Or the
   `evaluate_model` tool on a trained dir.)
4. `share_finding` the composite; log the result.

Counts toward best-so-far only if it passes the capability filter AND beats the
prior best headline.

## Status — what's validated vs what a first run will shake out

**Validated end-to-end already:**
- The eval path: model dir → `slurm_eval.sh`/entrypoint → score → composite (integration test, headline≈0 baseline-vs-itself).
- The method path: `slurm_run_method.sh antisyc_sft` trained + submitted + scored; the capability tripwire correctly disqualified it (wei 0.997→0.82 < floor).
- The forum composite wiring (model round-trip + leaderboard sort).
- Prompt renders; `claude_agent_sdk` + Anthropic key present.

**Needs the first live run to confirm (burns API budget):**
- The `AutonomousAgentLoop` wrapper still carries some W2S-flow assumptions
  (it was built for the predictions/PGR flow). `LOCAL_MODE=true` skips S3/RunPod,
  but the **first launch is effectively a smoke test** — expect to fix 1–2 rough
  edges in the loop's local-mode path (e.g. findings-sync wiring) before a clean
  multi-iteration run. Start with ONE chain, watch the first iteration's
  trajectory log under `aar/research_loop/logs/`, then scale to N.

## Isolation note
Until the `eval-user` user exists, the holdout is honor-system (the chain
runs as you). The submit-model contract still means the agent only ever receives
aggregate scores — it never sees test items through the intended path. See
ISOLATION.md.
