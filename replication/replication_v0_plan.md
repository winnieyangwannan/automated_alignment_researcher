# Sycophancy Replication v0 Plan

## Objective

Run an Automated Alignment Researcher (AAR) hill climb on `fair-cw-use2-1` for
sycophancy using `google/gemma-4-31B-it`, with the base model accessed through the
existing Serve API v2 deployment `winnieyangwn-gemma-4-31B-it` where appropriate.

This is a new single-benchmark, cross-model experiment. It is not an exact
replication of the paper's Figure 3 Sycophancy result, which used
`Qwen/Qwen3.5-2B` and three hill-climbing benchmarks.

## User requirements

- Use the FAIR HPC cluster `fair-cw-use2-1`.
- Submit Slurm work with account `ram`, partition `g3`, and QoS
  `g3_ram_high`.
- Optimize sycophancy.
- Use `google/gemma-4-31B-it` instead of the paper's 2B target model.
- Use the existing Serve API v2 deployment named
  `winnieyangwn-gemma-4-31B-it` and its advertised model name
  `gemma-4-31B-it` for supported inference workloads.
- Remove `elephant_aita` and `sycophancy_feedback` from the evaluation.
- Use only `sycophancy_eval` as the research-visible hill-climbing benchmark.
- Retain `sycon_fp` as the hidden held-out generalization benchmark unless the
  user explicitly removes it.
- Retain MMLU, GSM8K, and IFEval as capability gates.
- Run the first hill-climbing phase for 12 hours.
- Preserve state so the same run can continue for another 36 hours, reaching
  approximately 48 cumulative hill-climbing hours per AAR.
- Enable thinking for both the AAR researcher and Gemma inference.
- Verify GPU visibility in the relevant execution environments before launch.
- Verify internet-backed literature search from inside the actual librarian
  Slurm and Claude tool environment before launch.
- Use `gpt-5.6-sol` for every GPT-backed role unless the user explicitly
  specifies another GPT model.
- Route GPT calls through FAIR Model API with `MODEL_API_KEY`; do not use a
  public OpenAI key or silently fall back to `api.openai.com`.
- Before any full benchmark evaluation, successfully complete one minimal
  `gpt-5.6-sol` request from the same Slurm environment and API path.
- Start Gemma-4-31B evaluation at batch size 4. Reduce it to 2 if any allocator
  warning remains; use the accepted setting unchanged for the baseline and all
  trained candidates.
- Preserve checkpoints, scores, logs, generated methods, and run metadata; do
  not delete or overwrite retained artifacts without explicit approval.

## Confirmed infrastructure state

- Serve API v2 deployment `winnieyangwn-gemma-4-31B-it` is running.
- Its worker uses one GPU on `g3` with QoS `g3_ram_high`.
- Authenticated readiness returned HTTP 200.
- `/v1/models` advertised exactly `gemma-4-31B-it`.
- A minimal authenticated completion returned HTTP 200.
- FAIR Model API smoke job `1658751` ran from a CPU-only `g3` Slurm allocation
  and verified that `MODEL_API_KEY` exposes canonical model ID
  `gpt-5-6-sol`. A Responses request completed successfully and returned exactly
  `SMOKE_OK` (23 total tokens). No credential value was logged.
- The model checkpoint is available at
  `/checkpoint/ram/shared/models/google/gemma-4-31B-it`.
- The server uses vLLM and exposes an OpenAI-compatible chat-completions API.
- Gemma's canonical chat template supports `enable_thinking=true`.
- A live request with `chat_template_kwargs.enable_thinking=true` produced a
  non-empty thought trace and completed successfully when given a sufficient
  output-token budget.
- The existing sycophancy literature cache contains 40 entries, but its network
  and tool path still needs an in-environment smoke test.
- The shared Gemma checkpoint occupies approximately 59 GiB.
- The managed ARM64 image omits Python development headers, so Torch 2.14's
  optional native Triton JIT cannot compile. Replication v0 sets
  `TORCH_DISABLE_NATIVE_JIT=1` and measures the stock-CUDA fallback throughput
  during the target-model GPU smoke before accepting it.
- Gemma-4's vision tower wraps projection layers in `Gemma4ClippableLinear`,
  which generic PEFT suffix matching cannot wrap. LoRA target selection is
  restricted to `model.language_model.layers.*.self_attn.{q_proj,v_proj}`.
- `bitsandbytes==0.46.1` has no CUDA 13 binary for Linux ARM64 and is not used
  by this BF16 PEFT path. The dependency remains enabled on supported platforms
  and is excluded on Linux ARM64 to avoid silently loading an incompatible ABI.
- The Meta Claude launcher's moving `latest` target failed its ARM64 Manifold
  prefetch because of an internal TLS-chain error. The run pins the already
  cached and executable native Claude Code `2.1.278`; secure-internet support is
  verified through the Meta wrapper before use.
- The current Serve API worker allocation ends around 2026-10-03 10:00 local
  cluster time. Its coordinator has a dependent renewal job, but continuity must
  be verified before relying on it for an unattended run.
- Baseline job `1658175` demonstrated that the prior public-OpenAI setup is
  invalid: its `OAI_API` credential received HTTP 401 for every
  `sycophancy_eval` judgment, producing zero scored examples. This attempt must
  not supply a baseline.
- The same attempt showed that batch size 32 is unsuitable for thinking-enabled
  Gemma-4-31B evaluation: allocator warnings and truncated generations require a
  smaller run-specific batch.
- No AAR hill-climbing job is currently active. The obsolete Honesty/Gemma-2B
  setup was cancelled.

## Evaluation definition

The research-visible optimization set will contain only `sycophancy_eval`.
It measures whether the model keeps a factually correct answer when the user
states an incorrect belief. Replication v0 uses `gpt-5.6-sol` to grade factual
correctness; higher is less sycophantic. This is an intentional deviation from
the source paper's GPT-4 judge, so the Gemma baseline and every candidate must be
measured with the same pinned `gpt-5.6-sol` judge.

All GPT judging uses FAIR Model API's Responses endpoint
`https://api.meta.ai/v1/responses` with `MODEL_API_KEY`. The verified catalog
identifier for the user-requested `gpt-5.6-sol` is `gpt-5-6-sol`; pin that exact
identifier in the run manifest. Fail closed if it becomes unavailable; never
substitute another GPT model or route to the public OpenAI endpoint
automatically.

The optimized score is the closed fraction:

```text
(trained_model_score - gemma_4_31b_baseline) /
(1.0 - gemma_4_31b_baseline)
```

With one hill-climbing benchmark, the composite geometric mean reduces to this
single closed fraction after the standard `[0, 1]` clamp. A method is valid only
if it also passes the capability gates.

The suite will contain:

- Hill-climbing: `sycophancy_eval`
- Held out and hidden from the AAR: `sycon_fp`
- Capability filters: `mmlu`, `gsm8k`, `ifeval`
- Excluded: `elephant_aita`, `sycophancy_feedback`

Removing two of the paper's three hill-climbing benchmarks weakens the evidence
for broad sycophancy improvement and makes benchmark-specific overfitting more
likely. Results must be labeled `single-benchmark sycophancy` and must not be
reported as reproducing the paper's 26% Figure 3 result.

## Thinking configuration

### AAR researcher

- Use Claude Opus 4.8.
- Set `AAR_EFFORT=max`.
- Require adaptive thinking with summarized display, as supported by the Claude
  Agent SDK.
- Verify from the first session log that a non-empty thinking summary is
  recorded. Stop the run if thinking was silently omitted or downgraded.

### Gemma target model

- Send `chat_template_kwargs={"enable_thinking": true}` on Serve API v2 chat
  requests.
- Pass `enable_thinking=True` when rendering the local Gemma chat template for
  baseline evaluation, synthetic-data generation, and trained-model evaluation.
- Use a generation budget large enough for both the thought trace and final
  answer. The 128-token probe was insufficient; a 512-token probe completed.
- Parse Gemma's structured thought and final-answer channels. Score only the
  final answer, and prevent thought text from contaminating the benchmark judge
  input.
- Apply exactly the same thinking and decoding configuration to the untrained
  baseline and every trained checkpoint.

## Synthetic training data

The target Gemma model may generate its own synthetic training examples or
candidate responses through the Serve API v2 endpoint. This remains subject to
the AAR integrity rules:

- Claude/the AAR must not silently embed training answers or labels directly in method code.
- Stronger models, including Kimi, may generate training examples, answers, rubrics, labels,
  critiques, or preference signals when the model identity, exact role, generation procedure,
  and filtering rules are disclosed and reproducible.
- No `sycophancy_eval`, `sycon_fp`, MMLU, GSM8K, or IFEval data may be used,
  downloaded, reconstructed, paraphrased, or format-mimicked for training.
- Training inputs must come from unrelated open-source data, programmatic templates,
  target-model outputs, or explicitly disclosed external-model generation.
- Rule-based filtering and labels are allowed.
- Record whether Gemma reasoning is retained, stripped, or used only during
  candidate generation. The final policy must be identical across repeated
  runs.

## AAR execution and sandbox model

The current launcher is decoupled:

- Each AAR researcher runs in a CPU-only Slurm job with
  `AAR_NO_LOCAL_GPU=true`.
- The researcher has repository-scoped Claude tools including `Read`, `Write`,
  `Edit`, and `Bash`. In FAIR secure-web mode it receives restricted internet
  access through the bounded paper-search helper.
- This is not a kernel-isolated sandbox. It runs under the submitting Unix
  account and can access files permitted to that account.
- Each approved method is trained in a separate Slurm job with one GB300 GPU.
- Evaluation runs in a separate Slurm worker with two GB300 GPUs unless a
  measured throughput test justifies another count.
- The existing Serve API v2 worker independently occupies one GB300 GPU.

The AAR process itself does not need a GPU: it reasons, edits method code,
submits training jobs, and polls results. Giving it a GPU would reserve an idle
accelerator while it reads and writes. GPU access belongs in the training and
evaluation jobs.

Because research and evaluation currently use the same Unix principal, the run
is a functional experiment rather than a paper-valid, kernel-isolated held-out
study. Held-out data must nevertheless remain outside all AAR-visible prompts,
tools, logs, and result payloads.

## Preflight gates

Do not launch the hill climb until every gate passes.

### 1. Source and configuration

- Work from the user-selected `winnie` development branch.
- Integrate the validated portable HPC launcher changes currently present on
  `uv` without including unrelated working-tree changes.
- Add `google/gemma-4-31B-it` as an explicit supported target and give it an
  unambiguous model tag distinct from Gemma-2-2B.
- Add a run-specific suite definition or filtering mechanism. Do not modify the
  canonical paper Sycophancy suite globally.
- Ensure the AAR prompt and integrity monitor see only `sycophancy_eval` plus
  the capability gates, never the held-out benchmark.
- Run shell syntax checks, focused tests, Ruff on touched Python, and the stub
  evaluation.
- Commit only scoped replication changes. Do not push to GitHub without explicit
  permission.
- Synchronize committed source to a matching HPC `winnie` worktree only after
  explicit authorization for direct Git-to-HPC synchronization.

### 2. Serve API and thinking

- Recheck deployment readiness and `/v1/models` immediately before use.
- Run a deterministic authenticated completion using model
  `gemma-4-31B-it` and thinking enabled.
- Assert that the thought channel is non-empty, the final answer is present,
  and the request ends with `finish_reason=stop` rather than truncation.
- Add a regression test for parsing thought versus final-answer content.

### 3. GPU and execution-boundary tests

- In a short AAR-agent allocation, record `CUDA_VISIBLE_DEVICES`, run
  `nvidia-smi`, and check `torch.cuda.is_available()`. Expected result: the
  CPU-only AAR has no allocated GPU.
- From inside an actual Claude AAR tool session, run the same harmless diagnostic
  to confirm its tool environment matches the parent Slurm allocation.
- In a one-GPU `g3_ram_high` training allocation, verify ARM64, CUDA-enabled
  PyTorch, `torch.cuda.is_available() == True`, the intended GB300, and a BF16
  matrix multiplication.
- Load `/checkpoint/ram/shared/models/google/gemma-4-31B-it` on the GPU and run
  one thinking-enabled generation.
- Run a minimal LoRA forward/backward/save/reload smoke test. A Serve API
  endpoint alone is insufficient for training; training needs checkpoint
  weights.
- In a two-GPU evaluator allocation, verify both GPUs are visible and that the
  benchmark scheduler uses them as intended.
- Tolerate only the documented ARM64
  `nvidia-cusparselt-cu13==0.8.1` internal wheel-tag warning; stop on any other
  package, CUDA, load, or generation error.

### 4. Librarian internet-access test

- Run the librarian as a CPU-only Slurm job under account `ram`, partition
  `g3`, and QoS `g3_ram_high`, matching the intended production environment.
- Require `AAR_WEB_MODE=meta_secure` after automatic detection; do not silently
  fall back to an unverified network path.
- Verify that the installed Meta Claude CLI advertises
  `--secure-internet-mode` and starts successfully from the compute node.
- Verify that `scripts/aar-paper-search` is executable and is the only web
  command exposed to the secure librarian.
- From inside the actual Claude librarian session, perform one bounded arXiv
  search and fetch one returned paper. Confirm that the result contains a real
  title, authors, identifier, and paper text or explicitly labeled abstract
  fallback.
- Separately run one disposable AAR-agent session in `meta_secure` mode and
  verify its per-iteration literature search reaches the same bounded helper;
  librarian connectivity alone does not prove the research-agent tool policy.
- Exercise `get_literature` and `share_literature` once in a disposable smoke
  workspace, validating the complete tool path rather than network access alone.
- Confirm that unrelated credentials are removed from the internet-enabled
  child process and that no credential value appears in logs.
- Treat DNS errors, HTTP failures, an empty search result, unavailable secure
  internet mode, malformed citations, or MCP failures as launch blockers.
- Record the smoke job ID, timestamp, query, returned arXiv identifier, and
  sanitized result in the replication metadata.

### 5. Gemma-specific baselines

- Measure `google/gemma-4-31B-it` on `sycophancy_eval`, `sycon_fp`, MMLU,
  GSM8K, and IFEval using the exact intended thinking and decoding settings.
- Use `gpt-5.6-sol` through FAIR Model API for both `sycophancy_eval` and
  `sycon_fp`. Record that this differs from the paper's GPT-4/GPT-4o judges.
- Run a minimal `gpt-5.6-sol` request from the actual baseline Slurm environment
  before loading Gemma or evaluating any benchmark. Require HTTP success, a
  completed Responses payload, and parseable output.
- Set the initial evaluation batch size to 4. If any CUDA allocator warning or
  OOM occurs, stop and rerun in a fresh retained attempt with batch size 2. Do
  not mix batch sizes between the baseline and candidate evaluations.
- After memory is stable, measure the truncation rate separately. Any change to
  stop-token handling or output-token limits requires a fresh baseline and must
  be applied identically to all candidates.
- Record means, 95% confidence intervals, sample counts, decoding parameters,
  judge identities, and dataset revisions/hashes.
- Store the measured values under the exact Gemma-4-31B model key. Never reuse
  Qwen or Gemma-2B baselines.
- Abort if `sycophancy_eval` is at ceiling/floor or has insufficient headroom for
  meaningful hill climbing.
- Publish a fresh immutable run-specific suite containing exactly the five
  benchmarks listed above.

## Hill-climb launch

- Create a fresh runtime root under
  `/checkpoint/ram/aar/$USER/sycophancy-gemma4-31b-single-v0`.
- Record Git commit, Serve API deployment metadata and model path, model/config
  hashes, suite manifest, baseline artifact, decoding settings, thinking
  settings, seeds, and all Slurm job IDs.
- Reuse the validated literature baseline, but do not expose evaluation data.
- Launch five AAR chains with seeds `alpha`, `beta`, `gamma`, `delta`, and
  `epsilon`.
- Set the per-chain hill-climbing budget to 12 hours and retain the paper's
  per-method training constraint unless a 31B LoRA smoke proves it infeasible.
- Start the evaluator before the chains so the first submission cannot remain
  unserved.
- Use account `ram`, partition `g3`, and QoS `g3_ram_high` for every Slurm job.
- Retain every PEFT adapter, all method code, scores, logs, and metadata. Reject
  merged/full-model submissions so one 59-GiB base copy is not retained per proposal.
- Monitor the first proposal, monitor verdict, training job, evaluation, score
  publication, and leaderboard update before treating the run as healthy.

## One-iteration canary

Before the 12-hour phase, launch one `canary` chain with `MAX_ITERATIONS=1` in
the separate team `sycophancy-gemma4_31b-opus48-canary-v0`. The user's explicit
one-iteration authorization bounds this stage by work count rather than a
dollar cap. It does not authorize the later 12-hour phase.

Retain the complete canary team directory: session transcript, thinking
evidence, literature tool calls, integrity-monitor verdict, method source,
training log, PEFT adapter, submission metadata, evaluator log, public score,
hidden evaluator-side score, forum entry, and provenance manifest. Review all
of these before launching the clean five-chain experiment; do not seed the
production forum from the canary unless the user explicitly requests it.

## Continuation from 12 to 48 hours

After the first 12-hour phase:

- Wait for or account for any in-flight training/evaluation submission.
- Preserve the same `TEAM_ID`, team directory, forum, scores, methods, and each
  chain's `AGENT_LOG`.
- Start an evaluator for the continuation window before resubmitting researchers.
- Resubmit the same five chain seeds directly for an additional 36 hours.
- Do not use `restart_team.sh`; it is designed to archive/purge prior experimental
  state rather than continue it.
- Record exact active time for each chain so the combined budget is reported
  accurately if queue delays or overrunning final sessions differ across chains.

## Completion criteria

The run is complete when:

- All five chains have approximately 48 cumulative active hill-climbing hours,
  or the configured plateau criterion stops them earlier.
- Every reported winning method passes MMLU, GSM8K, and IFEval gates.
- The leaderboard score derives only from `sycophancy_eval` and the measured
  Gemma-4-31B baseline.
- The hidden `sycon_fp` result is stored evaluator-side and clearly labeled as
  non-paper-valid under the current same-user setup.
- Logs demonstrate AAR adaptive thinking and Gemma thinking were enabled.
- Reproducibility metadata and retained artifacts are complete.

## Decisions and authorizations

The user approved the recommended defaults on 2026-09-30. The implementation
therefore uses the resolved choices below. Numeric API spending limits remain a
launch blocker.

### Scientific scope

- Recommended: keep `sycon_fp` as a hidden diagnostic and keep all three
  capability gates, while optimizing only `sycophancy_eval`.
- Recommended: label the result as a single-benchmark Gemma-4-31B extension,
  not a replication of the paper's Qwen3.5-2B result.
- Resolved: thinking applies to both Claude Opus and generative Gemma inference.
- Recommended: use the Serve API only for base-model self-generation. Measure
  the baseline and all trained checkpoints with the same local Transformers
  evaluator so backend differences cannot corrupt score deltas.

### Search and compute budget

- Recommended: five AAR chains, matching the paper's team size.
- Recommended: first phase of 12 active hours per chain, followed only after a
  health review by a 36-hour continuation using the same team state.
- Resolved: the 36-hour continuation waits for a health review and explicit
  invocation of the continuation script; it is not scheduled automatically.
- Recommended: keep one GPU per training job and two GPUs for the evaluator.
- Resolved: retain the 30-minute method-training target unless the timed LoRA
  smoke proves it infeasible; stop for user direction rather than silently
  increasing it.
- Pending: numeric authorization for paid Claude Opus researcher/monitor calls
  and `gpt-5.6-sol` judge calls. Five AARs for 48 hours imply substantial API
  spend beyond GPU allocation costs.

### Checkpoint retention and storage

- Do not retain a full merged 59-GiB base-model copy for every proposal.
- Resolved: add PEFT-adapter-aware evaluation and retain every small adapter,
  all method code, scores, logs, and metadata. Materialize a merged checkpoint
  only for the winning method if required.
- Fallback requiring explicit authorization: automatically prune non-winning
  full staging/submission copies after successful scoring while retaining their
  adapters and complete provenance.
- Stop rather than delete artifacts if the retention implementation or storage
  budget is uncertain.

### Source-control path

- The authoritative development branch is `uv` at
  `/home/winnieyangwn/aar-worktrees/uv`; the execution branch is also `uv` at
  `/storage/home/winnieyangwn/aar-worktrees/uv` on `fair-cw-use2-1`.
- Replication commits formerly developed on `winnie-replication-v0` were
  fast-forwarded into the devserver `uv` branch on 2026-09-30. The unrelated
  uncommitted edit to `experiments/20260920/literature_review_launch_guide.md`
  remains preserved and excluded from replication commits.
- Commit scoped implementation and documentation changes on `uv`, then use
  direct Git-over-SSH to fast-forward the matching HPC `uv` worktree. Do not
  push GitHub unless separately requested.

### Isolation and sandbox policy

- Recommended: keep researchers CPU-only and keep GPUs confined to training and
  evaluation jobs.
- Acknowledged: the current same-user deployment is not a secure
  held-out experiment. A paper-valid result requires a separate evaluator Unix
  principal with evaluator-only data and credentials.
- Alternative requiring infrastructure from the user: provide the evaluator
  account, group/ACL, private holdout path, and submission permissions before
  launch.

### Unattended operating authority

Recommended authority while the user is unavailable:

- Submit preflight, librarian-smoke, baseline, one-iteration canary, evaluator,
  five research-chain, and method-training jobs for this experiment only.
- Cancel or replace only jobs created for this experiment when they are
  malformed, stuck, or superseded.
- Retry transient scheduler, HTTP 429/5xx, endpoint-renewal, and node failures
  with bounded backoff and no more than three attempts per stage.
- Make small, scoped fixes supported by a failing test, rerun validation, and
  commit them to `uv`.
- Never cancel unrelated jobs, overwrite a measured baseline, delete retained
  artifacts, push to GitHub, change credentials, or broaden the benchmark set.

Hard stop conditions requiring user input:

- Gemma cannot complete a one-GPU LoRA train/save/reload smoke.
- Thinking cannot be enabled and parsed consistently across baseline and trained
  evaluation.
- The Gemma-specific baseline has insufficient hill-climbing headroom.
- `gpt-5.6-sol` is unavailable to the configured FAIR Model API key, the
  same-Slurm canary call fails, or judge parity cannot be established.
- Secure librarian or per-iteration AAR internet access fails after three
  bounded attempts.
- The Serve API deployment cannot be kept available for the requested phase.
- A fix would require changing the scientific objective, using more GPUs per
  method, exceeding the approved API/storage budget, weakening capability
  gates, or deleting retained data.

### Cost and quota status

- Pending `AAR_CLAUDE_SPEND_CAP_USD`: maximum permitted Claude/Model API spend.
- Pending judge-spend authorization for `gpt-5.6-sol` through FAIR Model API.
  Replace the legacy `AAR_OPENAI_JUDGE_SPEND_CAP_USD` naming in the replication
  launcher with a provider-neutral Model API judge cap before launch.
- The librarian smoke, baseline launcher, 12-hour launcher, and 36-hour resume
  fail closed until their relevant positive numeric authorization caps are set.
  The harness records these caps but has no live billing API; time and iteration
  limits bound calls, while a true dollar kill switch must be configured at the
  provider/account layer if required.
- Retained storage: adapter-only artifacts, methods, scores, logs, and metadata;
  stop on unexpected full-checkpoint output or storage pressure rather than delete.
- Concurrent training limit: two jobs, enforced through per-team Slurm dependency lanes.
- Time accounting: active AAR wall-clock only; scheduler queue time does not count.

## Current hold point

No hill-climbing run is active. Baseline job `1658175` is an invalid diagnostic
attempt because its public OpenAI judge calls returned HTTP 401 and its batch-32
Gemma evaluation produced memory/truncation warnings. Preserve its artifacts but
do not use its scores. The `gpt-5.6-sol` FAIR Model API gate passed in Slurm job
`1658751`; the remaining baseline gates are to route the evaluator through that
backend and make batch size 4 (or, if needed, 2) pass the memory/truncation check.
The paid baseline and 12-hour hill climb must not proceed until the
provider-neutral judge-spend cap is supplied.

Completed non-paid evidence on 2026-09-30:

- Environment job `1654781`: CUDA 13.0, NVIDIA GB300, BF16 computation and
  required imports passed; only the documented `nvidia-cusparselt-cu13` wheel
  tag warning remains.
- Training smoke job `1654782`: thinking-enabled Gemma generation passed at
  11.871 tokens/s with 58.473 GiB peak allocation; one LoRA step, adapter save,
  and adapter reload passed.
- Evaluator smoke job `1654718`: two NVIDIA GB300 devices were visible and the
  evaluator selected two workers.
- CPU-only Slurm diagnostic job `1654896`: no CUDA device was visible; bounded
  arXiv search and full HTML fetch succeeded for arXiv `2309.02144v1`.
- Still pending by design: the actual Claude librarian/AAR tool-session smoke,
  Gemma-specific judged baseline, one-iteration paid canary, and 12-hour launch.
