# Run 10 canary checks

This directory contains the ordered lightweight gates used before the full
five-chain experiment:

- `verify_kimi_endpoint.py` proves a complete Kimi → native tool → AAR MCP tool
  round trip before Slurm submission.
- `monitor_method_smoke.py` waits for the one-step real-GPU method preflight and
  records the adapter-validation proof used by the on-demand evaluator.
- `verify_run_10_canary.py` combines the retained endpoint, training, adapter,
  evaluator, score, and finding evidence into the fail-closed proof required by
  the full launcher.

Shared suite verification lives under `verification/`. The canonical operator
commands remain in the parent [`README.md`](../README.md).

## Gate sequence

1. [`one_chain_lifecycle_check`](one_chain_lifecycle_check/README.md) proves one
   complete lifecycle. Its source of truth is
   [`config/run.yaml`](one_chain_lifecycle_check/config/run.yaml), and its only
   entrypoint is [`launch/launch.sh`](one_chain_lifecycle_check/launch/launch.sh).
2. [`five_chain_lifecycle_check`](five_chain_lifecycle_check/README.md) then
   proves the concurrent five-chain topology with one session per chain. It has
   its own [`config/run.yaml`](five_chain_lifecycle_check/config/run.yaml) and
   [`launch/launch.sh`](five_chain_lifecycle_check/launch/launch.sh).
3. The full 5×50 launcher requires both exact passed proofs. Neither lightweight
   score is a scientific result or part of the frontier.

Each check keeps an append-only `PROGRESS.md`; durable machine evidence stays in
its `/checkpoint` attempt.
