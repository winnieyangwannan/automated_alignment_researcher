# Run 6 invalid-adapter recovery

## Failure

The Beta research chain produced a PEFT adapter after its training loss became
NaN. All 220 saved adapter tensors contain NaN or infinite values. The safe
merge gate correctly rejected the candidate, but the evaluator removed its
claim and retried the immutable adapter indefinitely instead of publishing a
terminal failure. Consequently, the Beta agent remained blocked polling for a
score or failure file.

## Fix

- Validate PEFT safetensors values before the transport creates the atomic
  `.submitted` marker.
- Publish merge and scoring failures through one idempotent atomic helper.
- Treat a missing merge-complete manifest as terminal.
- Teach the synchronous training poller to recognize terminal evaluator
  failures.
- Preserve Beta's invalid adapter and evaluator logs, publish a held-out-safe
  failure marker for its existing run ID, and verify that the agent unblocks.

## Planned validation

Run focused transport, evaluator-failure, orchestration, and Run 6 launch tests;
shell-validate the modified workers; commit on `multi_vllm`; synchronize the
exact commit to the isolated HPC worktree by fast-forward; run the same tests
with the HPC environment; then recover Beta without stopping unrelated Run 6
research or evaluation jobs.
