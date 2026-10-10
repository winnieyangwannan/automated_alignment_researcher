# Run 9 provider-capacity check

- Status: passed at five chains × 32 tasks
- Created: 2026-10-10 16:10 PT
- Last updated: 2026-10-10 16:10 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-10 16:10 PT

Measure concurrent Kimi generation, Gemma target probing, and Luna judgment
through independent local Bubblewrap brokers without launching full AAR chains.

## Context

Recorded: 2026-10-10 16:10 PT

The first aggregate attempts exposed duplicated configuration between the
campaign policy and task client. [`config/run.yaml`](config/run.yaml) is now the
single validated source for provider limits, concurrency, retries, image, and
resources. The passed burst completed 160 broker tasks with no broker, client,
or transport failures.

## Plan

Recorded: 2026-10-10 16:10 PT

Provide a trusted target binding and run [`launch/submit.sh`](launch/submit.sh).
For an aggregate test, submit the bounded launcher once per intended chain and
retain each independent summary.

## Pass criteria

Recorded: 2026-10-10 16:10 PT

- Every requested broker task reaches a terminal successful broker state.
- Every client retains a schema-valid report.
- Generator and target provenance match the supplied deployments and binding.
- Provider rejection or `target_not_challenging` remains separate from
  infrastructure failure.

## Stop criteria

Recorded: 2026-10-10 16:10 PT

Stop on source or profile drift, any broker/client/transport failure, missing
provider provenance, or an unvalidated concurrency/profile value.

## After a pass

Recorded: 2026-10-10 16:10 PT

Use the retained summaries to choose an operator concurrency. Do not interpret
the repeated canary scenario's acceptance rate as production data quality.
