# Run 16 notes

## Evaluation batch-size observation

Recorded: 2026-10-11 23:08 PDT

Run 16 reports a target-model benchmark batch size of `2`. During Alpha's third
candidate evaluation, the live vLLM telemetry showed:

- `max_num_seqs=256` and `max_num_batched_tokens=32768`;
- as many as 96 running requests per engine and zero waiting requests;
- GPU KV-cache utilization ranging from approximately 0.6% to 37.2%; and
- no out-of-memory or allocator warnings.

The apparent `2` versus 96 discrepancy comes from the backend implementation.
The Transformers backend chunks `generate_batch()` calls using
`self.batch_size`, but the vLLM backend does not: it stores and reports the
configured value, then passes the entire prompt list to vLLM. For example,
AbstentionBench passes all selected prompts in one `generate_batch()` call.
vLLM then performs continuous dynamic batching subject to
`max_num_seqs=256`, the `32768` batched-token budget, and available KV cache.
Consequently, 96 running requests is compatible with a reported batch of `2`.

Therefore changing the reported benchmark batch from `2` to `4` or `8` is not
expected to change vLLM throughput in the current implementation. The earlier
interpretation that cache headroom alone justified a `2` versus `4` canary was
incorrect.

Do not change the active Run 16 attempt. Evaluation uses sampled generation at
temperature `1.0`, so changing batch composition can change outputs and make
later candidates inconsistent with the retained baseline and earlier
candidates.

For a future optimization, first decide whether vLLM should continue using
native continuous batching or whether `batch_size` should become an enforced
submission chunk. Measure the vLLM scheduler controls—not the currently inert
benchmark batch label—in a separate public-only throughput canary. Run 16's
observed zero waiting requests provides no current evidence that its scheduler
caps are the limiting bottleneck.
