# Run 10 canary checks

This directory contains the lightweight gates used before the full five-chain
experiment:

- `verify_kimi_endpoint.py` proves a complete Kimi → native tool → AAR MCP tool
  round trip before Slurm submission.
- `monitor_method_smoke.py` waits for the one-step real-GPU method preflight and
  records the adapter-validation proof used by the on-demand evaluator.
- `verify_run_10_canary.py` combines the retained endpoint, training, adapter,
  evaluator, score, and finding evidence into the fail-closed proof required by
  the full launcher.

The canonical operator commands remain in the parent [`README.md`](../README.md).

## Planned one-chain lifecycle check

Before the stopped five-chain attempt is resumed, use the bounded lifecycle plan
in [`one_chain_lifecycle_check/README.md`](one_chain_lifecycle_check/README.md). It requires one
research session, one-step GPU training, the two-item evaluator, and one joined
score/finding result. The document defines explicit pass and stop criteria; it
does not launch work by itself.
