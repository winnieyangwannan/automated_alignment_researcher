# Run 10 progress

This log is append-only. Times are UTC.

- 2026-10-08 22:55 — Created the persistent Run 10 goal: preserve Claude, add an opt-in Kimi research backend, validate it, launch a scored canary, then launch and monitor five 50-session chains.
- 2026-10-08 23:19 — Verified `steerability_8-kimi26` is serving 2/2 `Kimi-K2.6` replicas through vLLM 0.25.1 with a 262,144-token context.
- 2026-10-08 23:31 — Passed direct gateway and direct-proxy structured tool-call checks without printing the generated endpoint key.
- 2026-10-08 23:43 — Installed a temporary ARM64 Kimi Code 2.1.1 runtime and passed a complete Bash tool round trip against the endpoint. Observed and fixed Kimi's non-JSON terminal-output line in the stream parser.
- 2026-10-08 23:55 — Added per-session `serve_api_v2` resolution, endpoint model validation, Kimi provider defaults, secret cleanup, focused tests, pinned-runtime installer, canary/full launchers, proof checker, status tool, and experiment documentation. Validation and HPC synchronization are in progress.
