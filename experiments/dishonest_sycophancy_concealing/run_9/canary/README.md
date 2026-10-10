# Run 9 canaries

Run 9 retains two bounded infrastructure workflows:

- [`native_lifecycle/`](native_lifecycle/README.md) exercises approvals,
  meta-optimization, production, export, and training consumption.
- [`provider_capacity/`](provider_capacity/README.md) exercises concurrent
  Kimi → Gemma → Luna tasks through isolated local brokers.

These canaries validate infrastructure and provenance. Their generated rows and
scores are not scientific Run 9 results. Each launcher writes evidence outside
Git under the attempt root it prints at submission time.
