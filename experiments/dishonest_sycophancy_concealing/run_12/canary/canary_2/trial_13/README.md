# Run 12 Canary 2 Trial 13

**Experiment code branch:** `autodata`

- Status: repair validated; launch pending
- Created: 2026-10-11 15:35 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Run the unchanged confirmed Trial 12 scientific contract from a fresh attempt,
with corrected host-FSM re-entry after model-authored native action results.

## Configuration

- Kimi-K2.6 researcher `aar_8-kimi26`.
- Kimi-K2.6 generator `autodata_8-kimi26`.
- Gemma 4 31B target deployment `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Luna judge `gpt-5-6-luna`, with at most two judge-format attempts.
- Exact `3/3/3`, disjoint `64/32/32`, concurrency 32.
- Production 1,250→1,000; five final feedback rounds; 707 native attempts.
- Campaign ceiling `$41,775`; stop after verified one-step training smoke.
- Evaluator disabled.

## Trial 12 repair

Trial 12 failed before native execution because a corrected action result was
not consumed before generic stall detection. Trial 13 immediately consumes a
ready result after each tool turn and treats trusted action, feedback, strategy,
and handoff artifacts as durable progress. Trial 12 remains preserved.

## Stop criteria

Stop and preserve evidence on any new code defect, identity drift, evaluator
start, or contract failure. Do not mutate or resume a failed retained attempt.
