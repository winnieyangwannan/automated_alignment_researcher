# Run 14 canaries

- Status: Opus 5 comparison prepared; not launchable; not launched
- Created: 2026-10-12 23:46 PT
- Last updated: 2026-10-12 23:46 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Contain bounded gates that validate Run 14 before any larger experiment.

## Context

The first gate is `opus5_autodata_comparison`, a one-chain counterpart to Run
13 Canary Trial 14 with only the AAR researcher and AutoData generator roles
changed to Opus 5.

## Launch

Recorded: 2026-10-12 23:46 PT

No canary is launchable yet. Use the gate-specific README for the missing
runtime prerequisites. A documented future command will not itself authorize a
launch.

## Pass criteria

Each gate must retain fail-closed, machine-readable evidence for its declared
configuration and lifecycle boundary.

## Stop criteria

Stop if a gate has no reviewed launcher, its model roles are unconfirmed, its
resolved configuration drifts, or required isolation/provenance cannot be
proven.
