# Run 14 execution plan

## Objective

Run five independent Kimi AAR chains against the same multidimensional Gemma-4
evaluation used by Run 12, but let each researcher implement its own training
data generation without AutoData.

## Invariants

- `config/run.yaml` must resolve `data_generation.backend: native` to
  `AAR_AUTODATA=0`.
- No AutoData checkout, plugin, broker, recipe, lifecycle state, judge, target
  binding, or production export may be initialized.
- Every method must declare reproducible data provenance and pass the existing
  proposal monitor and source-bound method contract.
- Benchmark and held-out items remain unavailable to research chains.
- Each chain stops after five complete score/result pairs or eight sessions,
  whichever occurs first.

## Ordered gates

1. Validate YAML resolution, shell syntax, and focused unit contracts.
2. Run one bounded native-generation lifecycle with one research session, one
   real optimizer step, and a two-item `verbalized_ece` evaluation.
3. Confirm the one-chain canary produced one adapter, score, and published
   finding without any AutoData process or artifact.
4. Bind a five-chain topology check to that exact passed proof. Run one session
   for each of five parallel research chains, retain five real-GPU adapters,
   and let one on-demand evaluator drain all five staged submissions.
5. Confirm five complete score/result pairs and a passed topology proof.
6. Launch five isolated full chains.
7. Treat success as complete score/result pairs, not session count alone.

## Stop conditions

Stop before scale-up if the canary loads AutoData, lacks declared training-data
provenance, fails the real-GPU adapter smoke, cannot join its score to its
finding by run ID, or exposes evaluator-only data to the research side.
