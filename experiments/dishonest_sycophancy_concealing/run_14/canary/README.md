# Run 14 canaries

- Status: Opus 5 source launch path validated; not launched
- Created: 2026-10-12 23:46 PT
- Last updated: 2026-10-12 23:55 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Contain bounded gates that validate Run 14 before any larger experiment.

## Context

The first gate is `opus5_autodata_comparison`, a one-chain counterpart to Run
13 Canary Trial 14 with only the AAR researcher and AutoData generator roles
changed to Opus 5.

## Launch

Recorded: 2026-10-12 23:46 PT

The runnable entrypoint is
`opus5_autodata_comparison/launch/launch.sh`. Use the gate-specific README for
the exact prerequisite variables and command. The documented command does not
itself authorize a launch; model roles and the source revision must be
explicitly reconfirmed first.

## Pass criteria

Each gate must retain fail-closed, machine-readable evidence for its declared
configuration and lifecycle boundary.

## Stop criteria

Stop if a gate has no reviewed launcher, its model roles are unconfirmed, its
resolved configuration drifts, or required isolation/provenance cannot be
proven.
