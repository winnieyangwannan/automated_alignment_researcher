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
- Preserve checkpoints, scores, logs, generated methods, and run metadata; do
  not delete or overwrite retained artifacts without explicit approval.

## Confirmed infrastructure state

- Serve API v2 deployment `winnieyangwn-gemma-4-31B-it` is running.
- Its worker uses one GPU on `g3` with QoS `g3_ram_high`.
- Authenticated readiness returned HTTP 200.
- `/v1/models` advertised exactly `gemma-4-31B-it`.
- A minimal authenticated completion returned HTTP 200.
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
- The current Serve API worker allocation ends around 2026-10-03 10:00 local
  cluster time. Its coordinator has a dependent renewal job, but continuity must
  be verified before relying on it for an unattended run.
- No AAR hill-climbing job is currently active. The obsolete Honesty/Gemma-2B
  setup was cancelled.

## Evaluation definition

The research-visible optimization set will contain only `sycophancy_eval`.
It measures whether the model keeps a factually correct answer when the user
states an incorrect belief. The source-paper GPT-4 judge grades factual
correctness; higher is less sycophantic.

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

- Claude/the AAR must not author training answers or labels.
- No stronger model may generate training data or labels.
- No `sycophancy_eval`, `sycon_fp`, MMLU, GSM8K, or IFEval data may be used,
  downloaded, reconstructed, paraphrased, or format-mimicked for training.
- Training inputs must come from unrelated open-source data or simple
  programmatic templates.
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
- Use the source-paper judges: GPT-4 for `sycophancy_eval` and GPT-4o for
  `sycon_fp`.
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
- Keep all checkpoints for v0 unless storage pressure is measured and the user
  explicitly approves a retention policy.
- Monitor the first proposal, monitor verdict, training job, evaluation, score
  publication, and leaderboard update before treating the run as healthy.

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

## Decisions and authorizations required before autonomous execution

The following choices materially affect the experiment. Recommended defaults
are stated explicitly so the user can approve them together or override any
item.

### Scientific scope

- Recommended: keep `sycon_fp` as a hidden diagnostic and keep all three
  capability gates, while optimizing only `sycophancy_eval`.
- Recommended: label the result as a single-benchmark Gemma-4-31B extension,
  not a replication of the paper's Qwen3.5-2B result.
- Required clarification: whether "thinking enabled" applies to both Claude
  Opus and Gemma, as currently planned, or only to the AAR researcher.
- Recommended: use the Serve API only for base-model self-generation. Measure
  the baseline and all trained checkpoints with the same local Transformers
  evaluator so backend differences cannot corrupt score deltas.

### Search and compute budget

- Recommended: five AAR chains, matching the paper's team size.
- Recommended: first phase of 12 active hours per chain, followed only after a
  health review by a 36-hour continuation using the same team state.
- Required clarification: whether the 36-hour continuation should be scheduled
  automatically or wait for explicit approval after the 12-hour report.
- Recommended: keep one GPU per training job and two GPUs for the evaluator.
- Required clarification: retain the paper's roughly 30-minute method-training
  target or allow up to 90 minutes for the 31B model if the timed LoRA smoke
  demonstrates that 30 minutes is infeasible.
- Required authorization: paid Claude Opus researcher/monitor calls and GPT-4 /
  GPT-4o judge calls. Five AARs for 48 hours imply substantial API spend beyond
  GPU allocation costs.

### Checkpoint retention and storage

- Do not retain a full merged 59-GiB base-model copy for every proposal.
- Recommended: add PEFT-adapter-aware evaluation and retain every small adapter,
  all method code, scores, logs, and metadata. Materialize a merged checkpoint
  only for the winning method if required.
- Fallback requiring explicit authorization: automatically prune non-winning
  full staging/submission copies after successful scoring while retaining their
  adapters and complete provenance.
- Stop rather than delete artifacts if the retention implementation or storage
  budget is uncertain.

### Source-control path

- The current devserver `winnie` branch and validated `uv` launcher line have
  diverged. `winnie` has one unique commit, lacks 89 `uv` commits, and its
  worktree contains unrelated user changes.
- Recommended: create a clean `winnie-replication-v0` worktree from `uv`, apply
  only the experiment changes there, and leave the existing dirty `winnie`
  worktree untouched.
- Alternative: reconcile `uv` into the exact `winnie` branch, but only after the
  user decides how its unrelated changes should be handled.
- Required authorization: commit the scoped implementation and use direct
  Git-over-SSH synchronization to a matching HPC worktree. GitHub will not be
  updated unless separately requested.

### Isolation and sandbox policy

- Recommended: keep researchers CPU-only and keep GPUs confined to training and
  evaluation jobs.
- Required acknowledgement: the current same-user deployment is not a secure
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
  commit them to the approved experiment branch.
- Never cancel unrelated jobs, overwrite a measured baseline, delete retained
  artifacts, push to GitHub, change credentials, or broaden the benchmark set.

Hard stop conditions requiring user input:

- Gemma cannot complete a one-GPU LoRA train/save/reload smoke.
- Thinking cannot be enabled and parsed consistently across baseline and trained
  evaluation.
- The Gemma-specific baseline has insufficient hill-climbing headroom.
- The OpenAI judge model is unavailable or judge parity cannot be established.
- Secure librarian or per-iteration AAR internet access fails after three
  bounded attempts.
- The Serve API deployment cannot be kept available for the requested phase.
- A fix would require changing the scientific objective, using more GPUs per
  method, exceeding the approved API/storage budget, weakening capability
  gates, or deleting retained data.

### Cost and quota values still needed

- Maximum permitted Claude/Model API spend.
- Maximum permitted OpenAI judge spend.
- Maximum retained storage for the experiment.
- Maximum number of simultaneously running training jobs.
- Whether queued time counts against the requested 12/48 hours. Recommended:
  count only active AAR wall-clock time, not scheduler wait time.

## Current hold point

No hill-climbing run is active. Implementation, baseline measurement, and launch
remain pending. Source synchronization and any actual launch should occur only
after the user reviews this plan and authorizes the next step.
