# Run 16 notes

## Evaluation batch-size observation

Recorded: 2026-10-11 23:08 PDT

Run 16 currently uses a target-model benchmark batch size of `2`. During
Alpha's third candidate evaluation, the live vLLM telemetry showed:

- `max_num_seqs=256` and `max_num_batched_tokens=32768`;
- as many as 96 running requests per engine and zero waiting requests;
- GPU KV-cache utilization ranging from approximately 0.6% to 37.2%; and
- no out-of-memory or allocator warnings.

This indicates enough scheduler and KV-cache headroom to test batch size `4`,
but it does not establish a speedup. Some evaluator time is spent loading the
merged model, making judge calls, or processing low-concurrency tail requests,
none of which necessarily becomes faster with a larger benchmark batch.

Do not change the active Run 16 attempt. Evaluation uses sampled generation at
temperature `1.0`, so changing batch composition can change outputs and make
later candidates inconsistent with the retained baseline and earlier
candidates.

For a future run, use a separate public-only throughput canary with one
representative candidate and otherwise identical settings. Compare batch sizes
`2` and `4` for wall time, throughput, OOM/allocator warnings, truncation,
errors, and aggregate score/filter parity. Test batch size `8` only if `4` is
stable and has measurable benefit. Adopt a larger batch only with a matching
baseline protocol or a separate parity proof.
