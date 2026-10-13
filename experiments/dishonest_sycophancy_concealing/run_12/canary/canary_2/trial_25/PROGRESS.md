# Run 12 Canary 2 Trial 25 progress

Append-only operational record. All timestamps use Pacific Time (`PT`). Never
record generated rows, prompts, responses, credentials, held-out content, or
partial evaluator scores.

## 2026-10-12

<a id="trial25-event-staged"></a>

### ⏭️ 14:27 PT — NEXT: shared supervisor identity-envelope trial staged

> [!IMPORTANT]
> **Not launched.** Trial 24 evidence remains preserved. Trial 25 keeps the
> exact Trial 24 model and lifecycle settings and changes only the run ID and
> trial identity.

```text
✓ Trial 24 failure reconciled and terminal evidence preserved
✓ Trial 24 single-owner Kimi clarify_design proof retained
✓ Fresh Trial 25 configuration and launcher staged
✓ Trial 24 settings retained exactly
○ Focused supervisor identity-envelope correction committed and tested
○ Exact-commit HPC synchronization and preflight
✓ Exact model-role mapping covered by standing operator approval
○ Fresh Trial 25 attempt and jobs
```

- Source commit: pending the focused implementation and trial-record commit.
- Attempt: not created.
- Jobs: none.
- Model mapping: identical to Trial 24, recorded in `README.md`, and covered by
  standing operator approval for unchanged settings.
- Decision: launch only after exact-commit sync and validation complete.

<a id="trial25-event-identity-fix-validated"></a>

### 🟢 14:31 PT — PASS: targeted identity-envelope correction validated

> [!IMPORTANT]
> The chain now computes and exports `IDEA_UID` and `IDEA_NAME` exactly once,
> before the lifecycle supervisor is forked. The later research process receives
> those same values. No Claude/Kimi adapter, approval implementation, or native
> AutoData behavior changed.

- Added a fail-fast identity assertion at the supervised approval boundary.
- Added regression coverage for launcher ordering and real per-chain proposal
  marker resolution under a supervisor-style environment.
- Validation: 110 focused tests passed; Ruff, Bash syntax, ShellCheck, Trial
  24/25 configuration equivalence, and `git diff --check` passed.
- Independent audit found no blocking inconsistency or Claude-route impact.
- Decision: commit and synchronize this exact source, then launch Trial 25.

<a id="trial25-event-shared-meta-coordinator-conclusion"></a>

### 🔴 16:45 PT — CONCLUSION: use the shared typed meta coordinators for Kimi

> [!IMPORTANT]
> Trial 25 enabled the shared coordinator for `clarify_design` and delegated
> approvals, but explicitly left `AAR_AUTODATA_ANALYSIS_COORDINATOR` and
> `AAR_AUTODATA_MUTATION_COORDINATOR` unset to preserve Trial 24's conservative
> settings. Consequently, outer Kimi handled `analyze_results` and
> `mutate_candidate` through the older action-result loop, while Run 13 Claude
> used the shared typed coordinator. Future Kimi trials should reuse the shared
> implementation already working for Claude.

1. Enable the existing shared `analyze_results` and `mutate_candidate`
   coordinator for Kimi, like Claude.
2. Explicitly tell Kimi:

   > `mutate_candidate` is an edit action, not a recommendation. You must modify
   > `recipe/generation_strategy.json`. “No change needed” is invalid. Diagnose
   > the dominant failure reason—especially `target_not_challenging`—and make one
   > evidence-backed change that improves challenge/valid yield while preserving
   > quality.

3. Require Kimi to examine:

   - `target_not_challenging` frequency;
   - challenge and valid rates;
   - margin above required floors—not merely pass/fail;
   - generator attempts and whether target-aware regeneration occurred.

4. Deterministically reject completion unless the allowed file's digest
   changed. Return precise feedback and retry the same action.

For `target_not_challenging`, likely changes include bounded regeneration,
feedback from the target's non-failing response, and progressively harder
prompts.
