# Run 6 parallel launch

## Objective

Launch five one-iteration research agents concurrently and five independent
four-GPU evaluator jobs, then monitor the run until scheduler state and runtime
logs demonstrate that the parallel setup is active and candidates are being
claimed without duplication.

## Implementation contract

- Five research seeds: `alpha`, `beta`, `gamma`, `delta`, and `epsilon`.
- One research iteration per seed; no sequential five-session chain.
- Up to five simultaneous one-GPU training jobs.
- Five evaluator jobs, each requesting four GPUs on one node.
- One atomic shared candidate queue; one merged checkpoint and one score file
  per candidate run ID.
- vLLM 0.25.1, language-model-only mode, merged-checkpoint LoRA strategy, exact
  8,192-token contract, and a 10% truncation-rate gate.
- The launch parent fails unless five distinct evaluator IDs and five distinct
  chain IDs are retained in the attempt metadata.

## Initial state

- Devserver branch and HEAD: `multi_vllm` at
  `1dff79774d95a622c70401b418d51aa87d653d79`.
- HPC branch and HEAD before synchronization: `multi_vllm` at the same commit.
- Run 6 directory was empty before this implementation.
- Run 5's evaluator queue already used atomic claim directories, but its launch
  wrapper could submit only one evaluator job.
