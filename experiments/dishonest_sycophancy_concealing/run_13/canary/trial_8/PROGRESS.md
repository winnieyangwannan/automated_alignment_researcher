# Run 13 Canary Trial 8 progress

Append-only operational record. All timestamps use Pacific Time (`PT`).

## 2026-10-12

<a id="run13-trial8-prepared"></a>

### ⏭️ 12:24 PT — NEXT: narrow live-proof gate prepared

> [!IMPORTANT]
> **PREPARED, NOT YET LAUNCHED.** Trial 8 tests only reviewed code that has
> passed local and exact-pin integration tests. It will be stopped after
> authoritative state advances beyond `author_pipeline`.

```text
○ External pre-AutoData recovery verification
○ Fresh Trial 8 proposal and AutoData workspace
○ Typed clarify_design
○ Secure typed initial author_grounding
○ Trusted approve_grounding
○ Typed author_pipeline
○ Exact action-ID receipt coexistence proof
○ Post-author_pipeline authoritative state
— Meta-optimization (outside this diagnostic gate)
— Production (outside this diagnostic gate)
— Training smoke (outside this diagnostic gate)
○ Evaluator (disabled; must not start)
```

#### Configuration

- Config identity: `run13-canary-trial8`.
- Configured terminal boundary: `training_smoke`; operational diagnostic stop:
  immediately after the post-`author_pipeline` state is durably verified.
- AAR researcher/monitor and AutoData semantic worker: Claude Opus 4.8.
- Generator: Claude Opus 4.8; row/evaluation judge: GPT-5.6 Luna.
- Target and training base: Gemma 4 31B IT.
- AutoData revision: `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Concurrency: `8`; model-request attempts: `3`.
- Jobs: none.
- Attempt: none.

<a id="run13-trial8-terminal"></a>

### 🔴 12:36 PT — FAIL: trial identity omitted from sanitized chain environment

> [!CAUTION]
> **STOPPED BEFORE THE FIRST NATIVE ACTION.** The supervisor failed closed
> because the chain environment did not contain `AAR_RUN13_TRIAL_ID`. No retry
> or evaluator launched.

```text
✓ External pre-AutoData recovery verification
✓ Fresh Trial 8 proposal and AutoData workspace
✗ Coordinator identity validation
○ Typed clarify_design
○ Secure typed initial author_grounding
○ Trusted approve_grounding
○ Typed author_pipeline
○ Exact action-ID receipt coexistence proof
○ Post-author_pipeline authoritative state
○ Evaluator (disabled; did not start)
```

#### Observation

- Source commit: `79ece427e8695afef587cb27387bea55500e4a82`.
- Attempt: `20261012T192937Z-79ece427e869`.
- Launch job `1856001`: `COMPLETED`, exit `0`.
- Chain job `1856030`: `FAILED`, exit `70`.
- Controller job `1856031`: `FAILED`, exit `1`; durable verdict was
  permanent/no-retry.
- Fresh workspace: `ws_e95498d8e96846da97bdb486cb95fb0e`, native phase
  `clarify_pending`, revision `0`.
- Native actions and receipts: zero.
- Evaluator jobs: zero.

#### Identified bug

The generalized Trial 7/8 authoring-scope check requires
`AAR_RUN13_TRIAL_ID`. `scripts/aar_runtime_env.sh` did not include that variable
in `AAR_RESEARCH_CHAIN_ENV_ALLOWLIST`, so the positive Slurm export allowlist
removed it before the chain started. All coordinator flags were present, but
the supervisor could not authenticate their Trial 8 scope and raised
`pipeline_coordinator_scope_invalid`.

This is an AAR launch-envelope regression, not malformed AutoData state. The
failure occurred before `clarify_design`, so none of the intended live-proof
claims were exercised.

#### Next step

Add only `AAR_RUN13_TRIAL_ID` to the trusted portable/sanitized runtime
environment surface, cover its forwarding with a focused test, and rerun this
same narrow gate. Do not add another lifecycle coordinator slice first.
