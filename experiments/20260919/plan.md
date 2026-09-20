# README-Driven End-to-End Smoke Validation

## Summary

Follow the first four goals in README order by SSH into the HPC cluster `fair-cw-use2-1`. Each stage must pass before advancing. Use the documented `sycophancy` suite with `Qwen/Qwen3.5-2B`, but limit every real benchmark to two items because the objective is to verify pipeline wiring rather than reproduce statistically meaningful scores.

## Preparation

- Clone the repository into `/home/winnieyangwn/automated_alignment_researcher`.
- Inside a `g3` GB300 Slurm allocation, replace the Python 3.12 environment with
  `uv venv --python 3.12 --clear && uv sync --locked`. Linux aarch64 must resolve the
  published CUDA-enabled torch 2.14.0 wheel, Transformers 5.17.0, and tokenizers 0.23.x;
  do not install the legacy torch 2.8 vLLM/SGLang/FlashAttention 2 optimization stack.
- Before leaving the allocation, require `torch.cuda.is_available()` to be true, verify the
  device name/capability, verify Qwen3.5 config recognition, and run one minimal inference.
- Set `HF_HOME=/checkpoint/ram/winnieyangwn/hf-cache` so downloaded base models and datasets are cached once and can be reused by other projects. Keep AAR-generated checkpoints and run artifacts in a separate project-specific directory under `/checkpoint/ram/winnieyangwn/automated_alignment_researcher/`.
- Test if inference can be run with a simple test.
- Use `gpt-5.6-luna` for lightweight model-backed tests unless a task explicitly requires another model.
- Export `PYTHONPATH`, `AAR_BENCHMARK_DOCS`, and `BENCHMARK_DOCS_DIR`.
- Adapt only the required Slurm evaluation launcher from `/opt/aar/...` to configurable paths and the cluster's `g3` partition; require `bash -n` to pass.

## Where Each Command Runs

- **HPC login node (`winnieyangwn-login-0`):** clone and configure the repository, run the lightweight toy checks, build the two-item evaluation bundle, request Slurm allocations, and inspect job status and logs. Do not run Qwen inference or training here.
- **First `g3` GPU compute node:** run the README-style test-4 Flask server, the single AAR agent, and that agent's inline training process inside one interactive Slurm allocation with one NVIDIA GB300. Flask itself uses CPU; it is colocated only so the README quick start and `localhost:8000` remain simple.
- **Second `g3` GPU compute job:** run the existing one-shot evaluator after the agent submits its checkpoint. The first allocation remains alive while the agent waits, so evaluation requests a separate GB300 instead of requiring a new inline GPU-reuse implementation.
- **CPU compute nodes:** not used in test 4. They are part of the later scalable `launch_team.sh` workflow, where AAR agents run CPU-only and submit separate GPU training and evaluation jobs.

## Validation Sequence

### 1. Check the installation

- Run both documented toy evaluations:
  - `stub:perfect` must produce approximately `HEADLINE +100%` and pass the capability filter.
  - `stub:sycophantic` must score materially lower.
- This uses no GPU or API calls.

### 2. Verify benchmark discovery

- Run `python -m aar.benchmarks.registry list`.
- Require successful discovery of the toy and sycophancy benchmarks without loading a model.

### 3. Run a two-item real evaluation smoke test

- Submit a Slurm job requesting one NVIDIA GB300 GPU from the `g3` partition.
- Build the sycophancy evaluation bundle for `Qwen/Qwen3.5-2B` with `--force-n 2`. This prepares exactly two records for each of the four sycophancy benchmarks and three capability benchmarks, including the held-out role and Qwen-specific reference metadata; it does not run or train the model.
- Make the explicit `JUDGE_MODEL` environment setting override each benchmark plugin's historical default judge. Without this small code change, the current evaluator silently uses GPT-4/GPT-4o even when `JUDGE_MODEL=gpt-5.6-luna` is set.
- Run a control evaluation of the original, unmodified `Qwen/Qwen3.5-2B` checkpoint on the two-item bundle with `JUDGE_BACKEND=openai` and `JUDGE_MODEL=gpt-5.6-luna`. Qwen produces the answers and GPT-5.6 Luna grades only the judge-scored responses.
- Leave golden decoding variables untouched so `benchmark_docs` remains authoritative.
- Expected workload is 14 benchmark records, approximately 26 Qwen prompts, and approximately 8–16 GPT-5.6 Luna judge calls.
- Require:
  - A completed research-visible `scores.json` with no top-level evaluation error.
  - Result entries for every visible benchmark and capability check, even if a two-item benchmark produces an empty de-confounded sample or an unstable score.
  - A headline field, `passes_filter`, and per-benchmark capability-filter details. Their values are wiring evidence only and must not be interpreted as model-quality measurements at this sample size.
  - No held-out benchmark score in the research-visible `scores.json`. Store the complete result, including held-out performance, only under `HELDOUT_SCORES_DIR` to preserve the research/evaluator isolation boundary.
- Record runtime and OpenAI usage. Do not compare the two-item scores with the documented full-suite baselines or claim reproduction.

### 4. Run one full AAR iteration

#### Motivation

Verify that one complete autonomous iteration traverses the application workflow: research prompt → method code → integrity approval → training → checkpoint submission → two-item evaluation → aggregate score → recorded finding. This is a wiring smoke test, not a scientific alignment result or a test of the scalable multi-agent launcher.

#### Fixed constraints

| Control | Test setting |
|---|---:|
| AAR iterations | 1 |
| Evaluation suite size | 2 items per benchmark |
| Agent reasoning effort | `low` |
| Interactive GPU allocation | 90 minutes |
| Agent `--max-runtime` | 3,600 seconds |
| Evaluator Slurm job limit | 30 minutes |
| Training guidance | Finish within 30 minutes |

The 90-minute Slurm allocation is the hard outer limit for the first GPU node. The agent's `--max-runtime 3600` check occurs between sessions and does not interrupt a session already in progress. The training limit is guidance in the research prompt, not a separate hard timer in this inline workflow.

#### Steps

1. **HPC login node — verify prerequisites.** Confirm that the step-3 two-item suite exists, the one-GPU evaluator launcher passes `bash -n`, and the shared run directories under `/checkpoint/ram/winnieyangwn/automated_alignment_researcher/` are configured. Set the evaluator launcher's Slurm limit to `00:30:00`. Set `EVAL_VIA_WORKER=false` so a checkpoint submission launches one evaluator job instead of waiting for a persistent worker.
2. **HPC login node — request the first GPU node.** Run:

   ```bash
   srun --partition=g3 --gpus=1 --cpus-per-task=8 --mem=64G \
     --time=01:30:00 --pty bash -l
   ```

   Confirm that `hostname` identifies a compute node and that `nvidia-smi` shows one NVIDIA GB300.
3. **First GPU node — prepare the shell.** Enter the repository, activate `.venv`, load the API and path settings, set `AAR_EFFORT=low`, select `AXIS=sycophancy` and `MODEL=qwen`, and open two `tmux` panes.
4. **First GPU node, pane 1 — start the README server.** Run `python run.py server` and verify that `http://localhost:8000` responds. Flask uses CPU; it is colocated on this node only to reproduce the README's same-machine quick start.
5. **First GPU node, pane 2 — start exactly one agent iteration.** Run:

   ```bash
   python run.py agent --idea-uid smoke --idea-name "single-node smoke" \
     --local --max-iterations 1 --max-runtime 3600
   ```

   The current implementation requires a Claude model for the research agent and a Claude model for the integrity monitor. `gpt-5.6-luna` remains the evaluation judge.
6. **First GPU node — research and training.** The agent reads its prompt and context, proposes a method, writes `run.py`, obtains integrity approval, and runs the approved method's training on its allocated GB300. The method must follow the prompt's existing under-30-minute training guidance and save a loadable model plus tokenizer.
7. **Second GPU job — evaluation.** After training stages the checkpoint, the filesystem evaluation path submits a separate one-GPU job to the `g3` partition with a 30-minute Slurm limit. Do not implement same-GPU evaluator reuse. Keep the first allocation and agent alive while this job is queued or running.
8. **First GPU node — collect and record the result.** The evaluator scores the checkpoint against the same two-item-per-benchmark suite, writes the held-out-stripped composite to the shared scores directory, and stores the full held-out result privately. The waiting agent reads the composite and shares its finding using the same `run_id`.

#### Pass criteria

- The agent completes exactly one session and does not begin a second method.
- It creates a method, receives integrity approval, and starts training only after approval.
- Training produces a model and tokenizer that the evaluator can load.
- The checkpoint is staged under the correct `run_id`, and the separate evaluator job completes within 30 minutes without a top-level error.
- The research-visible score excludes held-out data, and the agent records one finding bound to the same `run_id`.
- Score improvement and capability-filter passage are not required.

#### Limitations

- This tests one agent and one iteration; it does not test multi-agent coordination or whether another agent can read the finding.
- The agent holds one GPU while reasoning and waiting. This is simple but inefficient; the later `launch_team.sh` workflow uses CPU-only agents and separate GPU training jobs.
- Evaluation uses a separately scheduled GPU job, so the test can briefly reserve two GPUs and may wait in two Slurm queues.
- `--local` uses shared filesystem transport. Flask is checked for quick-start/dashboard availability but is not the model-and-score handoff mechanism.
- Two items per benchmark validate execution only; the headline, confidence intervals, and capability-filter result are not statistically meaningful.
- The 3,600-second agent runtime and 30-minute training target are not hard mid-session training cutoffs. The 90-minute allocation is the final enforcement boundary for the first node.
- There is no repository-level API dollar cap, proposal-attempt cap, or method-submission cap in the current implementation.
- Research and evaluation use one OS user, so this does not validate production two-user holdout isolation.
- This does not validate `launch_team.sh`, a persistent evaluator worker, CPU-only agents, or concurrent teams. Those belong to a later distributed test.

## Tests and Stops

- Run focused tests plus `bash -n` after any portability edits.
- Stop immediately on installation, benchmark discovery, evaluation-smoke, authentication, budget, or timeout failure; do not automatically retry paid stages.
- Preserve logs and scores for diagnosis, while pruning duplicate staged checkpoints after successful evaluation.
- Treat this as a single-user functional test; production two-user holdout isolation remains a separate deployment step.
