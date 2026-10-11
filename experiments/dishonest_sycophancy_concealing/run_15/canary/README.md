# Run 15 canaries

## Goal

Prove the complete native-generation lifecycle and the intended five-chain
topology on the final Run 15 source revision before the full 5×50 launch.

## Context

Run 15 uses an ordered one-chain check followed by a five-chain topology check
before full scale-up. The first proves that native model-authored data reaches
real training, evaluation, and finding publication while AutoData remains
disabled. The second preserves the bounded workload while exercising five
parallel research chains and their shared training and evaluator queues.

The topology gate consumes the exact passed one-chain proof and binds its own
proof to that prerequisite by SHA-256. Canary scores are infrastructure
evidence, not scientific results.

## Launch

Run the one-chain entrypoint first, verify its proof, then pass that exact proof
to the five-chain entrypoint. Exact commands and prerequisites are documented
in each canary's README. Neither canary has launched.

## Pass criteria

The one-chain proof must pass every lifecycle marker. The five-chain proof must
then pass for all five seeds and retain the exact one-chain proof hash.

## Stop criteria

Stop on a source/config mismatch, unconfirmed model-role mapping, any AutoData
initialization, missing proposal/method contract, failed GPU smoke, evaluator
provenance failure, or missing score/finding join.
