# Run 5 evaluation recovery

Run 5 iterations 1 and 2 are being re-evaluated from their retained adapters;
training is not repeated. The original evaluations configured a run ceiling of
8,192 tokens, but `verbalized_ece` passed its local 96-token default as an
explicit per-request override. This made the effective vLLM generation limit 96
tokens and caused 193/300 and 268/300 length-truncated completions.

The recovery makes the run-ceiling contract explicit: an allowlisted benchmark
passes exactly `EVAL_RUN_GEN_CEILING` to the backend, invalid ceilings fail
closed, launch preflight resolves both `verbalized_ece` and `abstentionbench` to
8,192, and vLLM logs the requested and effective budgets. The Run 5 candidate
truncation gate is 10%; historical retained-baseline metadata remains immutable
at its original 5% gate because that baseline already passed both thresholds.

The recovery uses a fresh attempt root and score namespace, republishes the
suite from pinned sources, atomically merges the two retained PEFT adapters into
new checkpoints, and runs the complete evaluation suite under vLLM 0.25.1 in
language-model-only mode. It does not launch a research chain or any training
job.
