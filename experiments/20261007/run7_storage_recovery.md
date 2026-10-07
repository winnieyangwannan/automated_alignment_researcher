# Run 7 storage recovery

## Decision

The user authorized a blue-green recovery of Run 7 after the two relevant
`/checkpoint/ram/aar/winnieyangwn/` top-level namespaces became intermittently
unresolvable. The five original research-chain jobs remain untouched until a
fresh storage-backed canary publishes a terminal score and proves the exact
merged-vLLM runtime and cleanup contract.

The recovery keeps durable run state under
`/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts/`. Each
evaluator atomically merges a submitted adapter into a worker-specific
node-local directory, retains the merge manifest in durable evaluator metadata,
and removes only that exact temporary merged checkpoint after a score or
terminal failure is published. The user explicitly authorized deletion of
these new temporary merged checkpoints; old Run 7 artifacts are excluded.

## Preserved inputs

The exact retained multidimensional baseline was copied to durable storage and
matched its expected SHA-256
`f8825e08954d3798d622e551a1bf326e752400f0ca7e26945037c8d698af13db`.
All three source results and three source manifests named by that baseline were
also copied while the NFS namespace was briefly readable. Each copy matched the
hash recorded in the exact baseline. Recovery validation checks the original
baseline hash, every recovered source hash, the model/protocol contract, the
complete ordered score set, and source-to-baseline score equality.

The prior open-file and Claude-project salvage remains at
`/storage/home/winnieyangwn/aar-recovery/run7_20261007T004406Z-1b3303d02821/`.
No held-out items or full held-out scores will be placed in research-readable
team history during continuation reconstruction.

## Switch gates

1. Synchronize the exact committed recovery source to the isolated HPC
   `multi_vllm` worktree by direct Git-over-SSH fast-forward.
2. Submit the committed storage recovery canary (one research session, one
   four-GPU evaluator).
3. Require logs identifying vLLM 0.25.1, the exact merged checkpoint,
   `language_model_only=True`, and `lora_strategy=merged_checkpoint`.
4. Require a terminal score/result pair, a durable merge manifest, and absence
   of the worker-local merged checkpoint after evaluation.
5. Reconstruct the five-chain continuation state and remaining session budgets
   (alpha 43, beta 44, gamma 45, delta 44, epsilon 44), then launch the committed
   full continuation.
6. Cancel only the five exact old chain job IDs after the new continuation is
   verified active. Preserve all old artifacts and recovery snapshots.

## Validation completed before commit

- Bash syntax checks for the evaluator and recovery launch scripts.
- ShellCheck for the same shell scripts.
- Python compilation for the recovered-baseline validator and focused test.
- Direct execution of the dependency-free recovery contract tests.
- `git diff --check`.

The devserver virtual environment does not contain pytest. The focused pytest
target is therefore deferred to the existing ARM64 HPC environment after exact
commit synchronization; no package installation or environment mutation was
performed on the devserver.

## Continuation reconstruction source

The salvaged Claude project includes exact filesystem-tool result files. Three
independent copies of its latest leaderboard contain the same 14
research-visible findings. The continuation reconstructor selects the newest
maximum-count copy, requires the known per-chain distribution (alpha 2, beta 4,
gamma 4, delta 3, epsilon 1), rejects every evaluator-private benchmark
identifier recursively, and materializes a 14-entry forum plus five chain-local
memory files. It does not reconstruct or expose held-out scores.

The generic team launcher gains two opt-in recovery controls only:
per-seed additional-session budgets and an external directory containing the
five recovered `AGENT_LOG` files. Ordinary launches retain their existing
single-budget and fresh-memory behavior.
