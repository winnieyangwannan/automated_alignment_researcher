# Run 10 progress

This log is append-only. Times are UTC.

- 2026-10-08 22:55 — Created the persistent Run 10 goal: preserve Claude, add an opt-in Kimi research backend, validate it, launch a scored canary, then launch and monitor five 50-session chains.
- 2026-10-08 23:19 — Verified `steerability_8-kimi26` is serving 2/2 `Kimi-K2.6` replicas through vLLM 0.25.1 with a 262,144-token context.
- 2026-10-08 23:31 — Passed direct gateway and direct-proxy structured tool-call checks without printing the generated endpoint key.
- 2026-10-08 23:43 — Installed a temporary ARM64 Kimi Code 2.1.1 runtime and passed a complete Bash tool round trip against the endpoint. Observed and fixed Kimi's non-JSON terminal-output line in the stream parser.
- 2026-10-08 23:55 — Added per-session `serve_api_v2` resolution, endpoint model validation, Kimi provider defaults, secret cleanup, focused tests, pinned-runtime installer, canary/full launchers, proof checker, status tool, and experiment documentation. Validation and HPC synchronization are in progress.
- 2026-10-09 00:09 — Committed the launch package as `52bd48145a85d0c42667023538f0915dab140a83` and synchronized it to a new isolated `/storage/home/winnieyangwn/aar-worktrees/multi_kimi` worktree. Run 7 and the HPC `uv`/`multi_vllm` worktrees were not changed.
- 2026-10-09 00:14 — Setup job `1778083` built the worktree-local ARM64 environment and passed CUDA matrix multiplication on an NVIDIA GB300. Runtime job `1778084` installed Kimi Code 2.1.1 with Node 22.22.0, verified `node-pty`, and recorded package-lock SHA-256 `58f276879f1aaa7c92ae6292eda2191a8c253ca4d7e47300eafe85b32055e5b0`.
- 2026-10-09 00:18 — Public-source job `1778163` failed before preparation because Slurm `--wrap` selected `/bin/sh`; replacement `1778172` used Bash, regenerated both pinned public files, and verified 10,000 rows and their committed hashes.
- 2026-10-09 00:20 — The first canary submission gate stopped before any experiment jobs because the standalone verifier did not pass `KIMI_CLI_PATH` to `KimiAgent`. The failed attempt is retained; the explicit CLI wiring was corrected before retrying.
- 2026-10-09 00:36 — Subsequent gates reached Kimi but stopped because the AAR MCP subprocess exited during initialization. Direct reproduction identified an MCP Python SDK API difference in the locked ARM64 environment; the bridge was updated to support both the existing constructor-callback API and the newer decorator-registration API.
