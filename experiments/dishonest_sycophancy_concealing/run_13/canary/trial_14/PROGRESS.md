# Run 13 Canary Trial 14 progress

Append-only operational record. All timestamps use Pacific Time (`PT`).

## 2026-10-12

<a id="run13-trial14-prepared"></a>

### 🛠️ 22:06 PT — FIX: mutable challenge comparison prepared

> [!IMPORTANT]
> **PREPARED, NOT YET LAUNCHED.** Trial 14 replaces protected fixed pressure
> sentences with a typed mutable challenge instruction consumed by protected
> recipe code. It also requires exactly ten meta iterations.

- Models unchanged: Opus 4.8 researcher/monitor/semantic optimizer/generator,
  GPT-5.6 Luna row judge, and Gemma 4 31B IT target/training base.
- Only `recipe/generation_strategy.json` remains mutable.
- Monitor comparison: candidate strategy diffs; per-iteration quality,
  challenge, validity, and utility; pressure-rewrite conversion and diversity;
  final test evidence versus Trial 13.
- AutoData pin: `f53bc2136905461ffdbba0a203a12e351e184aaf`.
- Concurrency: `8`; provider attempts: `5`; finalization passes: `3`.
- Meta iterations: exactly `10`.
- Jobs: none.
- Attempt: none.

<a id="run13-trial14-launch1-cancelled"></a>

### 🔴 22:12 PT — STOP: first submission cancelled before child creation

> [!CAUTION]
> Launcher job `1865035` was cancelled while its pipeline log was still empty
> and before any chain or evaluator child was created. The attempt is retained.

- Attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run13-trial14-bootstrap-canary/20261013T051112Z-af7ad83c19b6`.
- The recovery manifest was correctly verified and snapshotted, but a second
  launcher metadata allowlist still ended at Trial 13, causing
  `recovery_manifest_sha256=none` in `submission.txt`.
- No AutoData workspace, model task, production export, training receipt,
  adapter, evaluator, score, or finding was created.
- Corrective action: extend the metadata-hash allowlist to Trial 14, add a
  regression assertion covering all three launcher allowlist sites, and submit
  a fresh immutable attempt.

<a id="run13-trial14-launch2-team-allowlist-failure"></a>

### 🔴 23:02 PT — STOP: second submission rejected by team recovery allowlist

> [!CAUTION]
> Launcher job `1865385` stopped before chain creation because the shared team
> launcher still limited pre-AutoData recovery to Trials 4 through 13.

- Attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run13-trial14-bootstrap-canary/20261013T060125Z-2c86b8dc421f`.
- The corrected submission metadata recorded recovery manifest digest
  `sha256:2ff96d05599ef9ada2d19f5561b6a80c0bbd57b17d43587e0551264d7685b2e0`.
- No chain, model call, AutoData workspace, evaluator, score, production export,
  training receipt, or adapter was created.
- Corrective action: extend the shared team and supervisor Trial 14 allowlists,
  test every recovery/coordinator enablement boundary, and submit a fresh
  immutable attempt.
