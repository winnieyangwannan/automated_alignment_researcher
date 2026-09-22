# Honesty AAR Full-Loop Smoke Plan

Date: 2026-09-21

Status: FAIR portability implementation in progress; launch follows validation.

## Recommendation

Use `scripts/launch_team.sh` as the human-facing entrypoint and
`scripts/slurm_aar_chain.sh` as the per-chain Slurm payload. For the first smoke,
launch exactly one chain for one iteration on `AXIS=honesty MODEL=gemma`, with a
separate one- or two-GPU evaluator already draining that team's queue.

The current scripts must be ported before launch. They parse and their focused
tests pass, but several paths, executables, partitions, and QoS names still refer
to the old `/opt/aar` deployment. A direct `sbatch scripts/slurm_aar_chain.sh`
would fail before the agent starts.

## What was inspected and verified

Read in full:

- `AGENTS.md`, `README.md`, `HARNESS.md`, `ISOLATION.md`, `LAUNCH.md`,
  `PORTABILITY.md`, and `REPRODUCE.md`.
- `experiments/20260920/literature_review_launch_guide.md`.
- The chain, team, training, evaluation, holdout-publishing, isolation, model,
  axis, agent, monitor, transport, and judge code relevant to this launch.

Current state:

- Devserver checkout: `/home/winnieyangwn/aar-worktrees/uv`, branch `uv`, commit
  `65bf50a5e53789fed1e4e672431f596be885f443`.
- HPC checkout: `/storage/home/winnieyangwn/aar-worktrees/uv`, also branch `uv`
  at the exact same commit.
- HPC host is ARM64 (`aarch64`); `.venv/bin/python`, the ARM64 `uv` bootstrap,
  and `/usr/local/bin/claude` exist. Claude Code is 2.1.263 and advertises
  `--secure-internet-mode`.
- The completed honesty literature baseline contains 37 JSON entries at
  `_runs/litreview/honesty`, so the literature phase should be reused, not rerun.
- Credential names for `HF_TOKEN`, `OAI_API`, `MODEL_API_KEY`, and
  `ANTHROPIC_API_KEY` are present and nonempty in the HPC `.env`. Values were not
  printed and validity has not yet been tested.
- Focused non-GPU tests on HPC: 33 tests and 12 subtests passed.
- `bash -n` passes for the relevant launch scripts. ShellCheck reports warnings,
  including unsafe deletion expansion in `slurm_train_submit.sh`; syntax success
  does not make the scripts runnable on FAIR.
- The FAIR scheduler exposes partition `g3`; the account is `ram`. Available QoS
  includes `g3_alignment_shared`, `g3_lowest`, and `g3_ram_high`. A GB300 node has
  four GPUs. `/checkpoint/ram` is writable and is the appropriate candidate for
  large run artifacts.

## Intended flow

```text
launch_team.sh
  -> creates an isolated team namespace and reuses honesty literature
  -> submits one CPU-only slurm_aar_chain.sh job
     -> Claude agent writes one method and mini-paper
     -> three integrity-monitor calls approve/reject code and paper
     -> agent submits one GPU slurm_train_submit.sh job
        -> method trains Gemma-2-2B and stages a self-contained checkpoint
        -> evaluator consumes the submission and writes stripped scores
     -> agent reads the score and records one finding

separate evaluator process
  -> owns/reads honesty suite and golden decoding
  -> scores 3 MASK optimization legs + 3 capability gates
  -> retains DeceptionBench reward score only on the eval side
```

The published honesty suite has seven total legs: three scored MASK legs, one
held-out DeceptionBench leg, and three capability gates. The research-facing
result should expose only six legs and must contain neither
`deceptionbench_reward` nor `held_out_pct`.

## Confirmed blockers to fix before launch

1. **Legacy paths and broken Python values.** `slurm_aar_chain.sh` and
   `slurm_train_submit.sh` set `PY=/opt/aar/work`, which is a directory, not a
   Python executable. The chain also tries to grep credentials from that path.
   Evaluator launchers hardcode `/opt/aar/aar_repo`, `/opt/aar/eval-user`, and
   `/opt/aar/work/git/python`.

2. **Wrong scheduler contract.** The chain/training/evaluator scripts request
   `general,overflow` and `high`/`high32`; those are not the FAIR `g3` contract.
   The prompt itself tells the autonomous agent to submit training with
   `--qos=high`, so fixing only the shell headers is insufficient.

3. **Evaluator GPU count exceeds one node.** `launch_eval_worker.sh` requests one
   GPU per suite leg. Honesty has seven legs, while a GB300 node exposes four
   GPUs. `run_eval` already supports fewer GPUs and distributes benchmarks over
   them, so the launcher should accept and cap an explicit evaluator GPU count.
   For one smoke chain, start with two GPUs; one GPU is the conservative fallback.

4. **Authentication paths are inconsistent.** The successful librarian can use
   Meta's authenticated Claude CLI with restricted internet, but the full loop
   currently requires a direct `ANTHROPIC_API_KEY` in `run.py`; the integrity
   monitor and honesty judge also call Anthropic HTTP directly. `MODEL_API_KEY`
   currently substitutes only for OpenAI-style judges, not these Anthropic calls.
   The chosen route is hybrid: use the already-proven Meta authenticated CLI and
   secure-search mode for the AAR itself, while retaining the current direct
   Anthropic path for the integrity monitor and honesty judge because the baseline
   was measured with that judge. Add a minimal paid-call preflight for those two
   direct-API components rather than assuming the librarian validated them.

5. **Internet tooling is not yet ported like the librarian.** The full-agent
   prompt requires `WebSearch`/`WebFetch` every iteration and permits general
   Bash. The librarian's secure FAIR mode instead exposes only the bounded
   `scripts/aar-paper-search` helper and two literature MCP tools. If the direct
   Anthropic route cannot provide native web tools on compute nodes, the full
   agent needs an `AAR_WEB_MODE=meta_secure` path analogous to the librarian and
   a matching prompt/tool allowlist.

6. **The two-user isolation described in `ISOLATION.md` is not established for
   this FAIR checkout.** The current account is not in a `shared` group, and the
   documented `eval-user` paths belong to another deployment. Because this
   checkout contains `benchmark_docs/` and the AAR has unrestricted `Read` and
   `Bash`, a same-user run is only a functional smoke, not a trustworthy held-out
   generalization experiment.

7. **Stale holdout-path derivation.** `eval_worker.sh` derives the model tag from
   a team ID shape that predates the added agent-model tag. A current ID such as
   `honesty-gemma-opus48-...` can be mapped to `gemma-opus48` instead of `gemma`.
   Require an explicit `HOLDOUT_DIR` and stop inferring it from `TEAM_ID`.

8. **Cross-user handoff permissions are not guaranteed.** `transport.put_model`
   copies source modes, and `put_scores` does not force group-readable output.
   A real two-user deployment needs setgid directories plus an explicit
   `umask 0007`/ACL or post-write permission checks for the submission marker, checkpoint
   tree, claims, and score JSON.

9. **The current launcher mutates existing state.** `launch_team.sh` invokes a
   purge that deletes held-out scratch files and moves stray `aar/ideas` content;
   `slurm_train_submit.sh` automatically deletes both trained and staged
   checkpoints after scoring. This conflicts with the instruction not to delete
   retained artifacts without approval. The smoke should use a fresh runtime root
   and a `KEEP_CHECKPOINTS=1` path.

10. **ARM64 runtime validation is incomplete.** Package-level tests pass, but
    PyTorch/CUDA and Gemma generation must be tested inside a GB300 allocation.
    The known `nvidia-cusparselt-cu13==0.8.1` wheel-tag warning is the only package
    compatibility warning that may be tolerated.

## Portability changes to make

Keep all site-specific choices outside the agent prompt and Python logic:

- Introduce one shared launcher environment contract, used by chain, train, and
  eval scripts:
  - `AAR_REPO=/storage/home/winnieyangwn/aar-worktrees/uv`
  - `HARNESS_PY=$AAR_REPO/.venv/bin/python`
  - `HARNESS_ENV=$AAR_REPO/.env`
  - `AAR_RUNTIME_ROOT=/checkpoint/ram/aar/$USER`
  - `HF_HOME=$AAR_RUNTIME_ROOT/cache/huggingface`
  - `AAR_SLURM_ACCOUNT=ram`
  - `AAR_SLURM_PARTITION=g3`
  - `AAR_AGENT_QOS=g3_ram_high`
  - `AAR_TRAIN_QOS=g3_ram_high`
  - `AAR_EVAL_QOS=g3_ram_high`
- Resolve the repo by `AAR_REPO`, then `SLURM_SUBMIT_DIR`, then script location,
  as the working librarian launcher already does.
- Load `.env` without printing values and preserve explicitly inherited values.
  Validate key presence by name only.
- Replace scheduler flags embedded in `prompt_safety.jinja2` with a tracked
  `submit_train_job.sh` wrapper. The agent should pass only the approved idea and
  run ID; the wrapper owns account/partition/QoS/GPU/log arguments.
- Make evaluator GPU count explicit and cap it at the allocation/node limit rather
  than benchmark count.
- Require `HOLDOUT_DIR`, `SUBMISSIONS_DIR`, and `SCORES_DIR` explicitly for the
  evaluator; never reconstruct a secret path from a team name.
- Add `AAR_KEEP_CHECKPOINTS=1` for the first smoke. Cleanup should be an explicit,
  separately approved operator action.
- Add a non-mutating `scripts/preflight_aar.sh` that prints PASS/FAIL without
  printing secrets. It must not publish, purge, move, submit, or delete anything.
- Add focused tests for environment precedence, FAIR Slurm arguments, team/model
  names containing hyphens, explicit holdout routing, cross-user file modes, and
  one-iteration run-ID binding.

Do the edits and commit them in the devserver `uv` worktree, then synchronize the
exact commit to the HPC `uv` worktree with the repository's Git-over-SSH workflow.
Do not copy working-tree files or environments between machines.

## Preflight gates

Every gate below must pass before moving to the next stage.

### 1. Source and static gate (devserver, then HPC)

- Correct absolute checkout and branch `uv`.
- Devserver and HPC at the same intended commit; working-tree changes reviewed.
- `bash -n` and ShellCheck on every touched launcher.
- Focused tests plus the no-GPU toy evaluation pass.
- Honesty resolves to `SUITE_NAME=honesty`, `TARGET_MODEL=google/gemma-2-2b-it`,
  held-out `deceptionbench_reward`, and exactly 37 valid literature entries.
- Preflight performs no purge and no archive move.

### 2. Scheduler gate (HPC login node)

- Use `sbatch --test-only` for the CPU agent, one-GPU trainer, and evaluator
  requests with account `ram`, partition `g3`, and QoS `g3_ram_high`. The
  scheduler metadata exposes GPU TRES for this QoS, but the dry run is the final
  acceptance check.
- Confirm the agent request has no GPU; do not express this as `gpu:0` unless the
  cluster explicitly accepts it.
- Confirm training requests one GPU and evaluator requests at most four GPUs.
- Confirm log paths are files under the new team directory, not directories.
- Record estimated starts and resource requests; do not submit the real jobs yet.

### 3. Environment and GPU gate (inside a one-GPU `g3` allocation)

- Activate the HPC-local `.venv`, export `PYTHONPATH`, `AAR_BENCHMARK_DOCS`, and
  `BENCHMARK_DOCS_DIR`, then run the ARM64 bootstrap `uv sync --frozen` if needed.
- `uv pip check`: tolerate only the documented exact cusparselt wheel-tag warning.
- Import `torch`, `transformers`, `peft`, `trl`, `claude_agent_sdk`, and the AAR
  package.
- Verify `platform.machine() == "aarch64"`, CUDA-enabled PyTorch,
  `torch.cuda.is_available()`, visible GB300 identity, BF16 CUDA arithmetic, and
  a short Gemma generation through the repository loader.
- Verify the target model and tokenizer cache can be read and the runtime/checkpoint
  location has enough space.

### 4. API and web gate (minimal paid calls)

- Start the AAR through Meta's authenticated Claude CLI with secure-internet mode,
  following the working librarian pattern. Port the bounded paper-search helper
  and matching tool policy instead of assuming native `WebSearch`/`WebFetch`.
- Make one minimal direct Anthropic call to the configured monitor model and one
  to `claude-haiku-4-5`; verify exact model names and response parsing. These
  direct calls remain required by the current integrity monitor and honesty
  evaluator even though the AAR itself uses Meta CLI authentication.
- Run one tiny integrity-monitor fixture expected to approve and one expected to
  reject; confirm fail-closed behavior for the code monitors.
- Start a one-turn Agent SDK probe with the exact production options and verify
  the intended internet-search tool actually works from a Slurm compute node.
- Do not assume the completed librarian's authentication automatically validates
  the full-agent tool set or either direct-HTTP component.
- Never print keys in logs or pass them as command-line arguments.

### 5. Filesystem and isolation gate

- Choose one of the two modes below explicitly.

  **Functional smoke:** same Unix principal for research and evaluation. This can
  validate orchestration but must be labeled non-isolated and its held-out result
  must not be treated as scientific evidence.

  **Integrity-valid run:** distinct research and evaluator principals (or an
  equivalent container/service boundary). The evaluator alone can read the
  holdout and golden `benchmark_docs`; both principals can traverse the shared
  queue; research can write/read submissions, evaluator can read them, evaluator
  can write scores, and research can read only stripped scores.

- Exercise the handoff with a tiny synthetic HF-format directory before a real
  checkpoint. Verify permissions from both principals.
- Run `verify_heldout_isolation.sh deceptionbench_reward` as the research
  principal. It must pass. Also verify the resolved prompt does not contain the
  held-out name, score, or eval-private path.
- Confirm no old `.submitted`, `.claims`, score, or proposal marker can collide
  with the new team ID.

### 6. Evaluation parity gate

Before allowing the AAR to optimize, publish the honesty suite for Gemma on the
eval side and score the unmodified `google/gemma-2-2b-it` on the same ARM64/GB300
stack. Require:

- all seven suite legs present and nonzero sample counts;
- `JUDGE_BACKEND=anthropic`, with both judge model variables set to
  `claude-haiku-4-5`;
- golden decoding loaded from the eval-only honesty baseline file;
- research output contains only three MASK legs plus three capability gates;
- eval-private output contains the DeceptionBench held-out leg;
- no abnormal judge skip/unparsed rate;
- closed fractions close to zero within expected sampling variation and the
  capability gate passes.

If ARM64/Transformers 5.17 materially shifts the base score, stop and re-establish
a matched baseline before hill climbing; do not optimize against a stale x86
baseline.

## First full-loop smoke

Recommended parameters:

```bash
AXIS=honesty
MODEL=gemma
LITREVIEW_SKIP=1
MAX_ITERS=1
MAX_HOURS=4
SEEDS=smoke1
DECOUPLED=1
AAR_KEEP_CHECKPOINTS=1
```

Operational order:

1. Create a fresh team directory and record its `TEAM_ID`, Git commit, lockfile
   hash, environment path, Slurm settings, and model identity.
2. Eval operator publishes the exact honesty/Gemma holdout without overwriting a
   retained suite, then starts a worker for that team's explicit submission and
   score directories.
3. Verify the worker is running and has opened the intended suite.
4. Submit one CPU-only chain with one iteration. Do not use the direct chain
   defaults; submit through the ported team launcher.
5. Monitor the chain log, training job, evaluator log, submission marker, score
   file, proposal record, and finding. Do not resubmit a pending job.
6. Stop after the first session even if the proposal is rejected or the method
   fails. Diagnose before a second attempt; a smoke is testing the state machine,
   not optimizing the score.

Success requires all of the following:

- chain, training, and evaluation jobs exit `COMPLETED`/`0:0`;
- exactly one approved proposal is bound to exactly one run ID and one training
  submission;
- the submitted checkpoint passes the structural loader check and generates on
  the GPU;
- research receives a finite, held-out-stripped score with all visible legs and
  capability details;
- eval-private output retains the held-out score;
- one result finding is stored with the same run ID and a code snapshot;
- the literature count remains 37 or increases only through deliberate in-run
  additions; the shared baseline is not overwritten;
- no retained checkpoint, score, log, or suite is deleted.

After this passes, run a second one-iteration smoke only if needed, then scale
iterations before scaling the number of chains. Multiple chains should be the
last step because they multiply API calls, model copies, evaluator contention,
and failure diagnosis.

## Resolved launch choices

- Isolation: same-user functional smoke for now. It validates orchestration but
  its held-out result is explicitly non-scientific. Add a kernel boundary before
  using held-out results as evidence.
- AAR agent and paper search: Meta authenticated CLI plus secure-internet mode,
  following the successful literature-review launch.
- Integrity monitor and honesty judge: their existing direct Anthropic route,
  validated with minimal preflight calls.
- Slurm QoS: `g3_ram_high` for agent, training, and evaluation during the smoke,
  conditional on all three `sbatch --test-only` checks passing.

No jobs should be launched until the preflight gates above pass.

## Pre-flight execution status (2026-09-21)

- Source commit `75f300e` passed the focused HPC test suite: 41 tests and 20
  subtests. The agent, one-GPU training, and two-GPU evaluator requests all
  passed Slurm `--test-only` on `ram/g3/g3_ram_high`.
- GPU pre-flight job `1537800` completed on `g3-152-101`: ARM64, CUDA 13.0,
  NVIDIA GB300, dependency imports, and BF16 CUDA matmul passed.
- Secure-agent job `1537819` completed on `g3-151-171`. The Meta-authenticated
  Claude CLI entered secure-internet mode and successfully used only the
  allowlisted `aar-paper-search` command.
- The original worktree `.venv` loaded Gemma but failed its first generation in
  job `1537815`: Triton's runtime extension could not compile because the
  system Python installation lacks `Python.h`. No model or run data was deleted.
- Replacement environment build job `1537830` completed on a GB300 node. It
  created `/storage/home/winnieyangwn/envs/aar-uv-gb300-20260921` from the frozen
  lock using uv-managed CPython 3.12.14; the managed interpreter includes its
  headers and sees CUDA 13.0. Model test job `1537841` then loaded the exact
  `google/gemma-2-2b-it` revision, generated 16 warmed tokens on an NVIDIA GB300
  at 33.817 tokens/s, and used 4.913 GiB peak GPU memory.
- API pre-flight exposed the remaining blocker. The configured direct Anthropic
  key returns HTTP 401 for both the Opus monitor and Haiku judge. The configured
  OpenAI key also returns HTTP 401. `MODEL_API_KEY` is valid and successfully
  serves catalog model `claude-4-8-opus`, but `claude-haiku-4-5` is not available
  to that key (HTTP 404), and no `LLAMA_API_KEY` is configured. Therefore the
  existing Haiku-4.5 baseline cannot yet be evaluated with judge parity.

Do not publish or launch the full loop until the direct Anthropic credential is
refreshed, or until an explicit decision is made to add a Model API judge backend
and re-baseline Gemma with a model available through that gateway.
