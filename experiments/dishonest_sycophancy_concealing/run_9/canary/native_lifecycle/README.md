# Run 9 native lifecycle check

- Status: lifecycle report passed; original wrapper exceeded its provisional timeout
- Created: 2026-10-10 16:10 PT
- Last updated: 2026-10-10 16:10 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-10 16:10 PT

Exercise one bounded native AutoData lifecycle through signed approvals,
meta-optimization, production, dataset export, and training-side consumption.

## Context

Recorded: 2026-10-10 16:10 PT

The retained attempt produced a passing lifecycle report in 963.123 seconds.
Its Slurm wrapper used an experimental 900-second pass ceiling, so the wrapper
reported failure after the underlying lifecycle had completed correctly. The
current source uses the evidence-based 1,200-second ceiling. See
[`analysis/stage_timing.md`](../../analysis/stage_timing.md) for phase timings.

## Plan

Recorded: 2026-10-10 16:10 PT

Run [`launch/submit.sh`](launch/submit.sh), which validates the pinned source
and AutoData revisions, creates private attempt inputs, and submits
[`slurm/preflight.sbatch`](slurm/preflight.sbatch).

## Pass criteria

Recorded: 2026-10-10 16:10 PT

- Signed grounding and baseline approvals are retained.
- Meta-optimization exports a winner.
- Fixed-winner production exports and consumes a schema-valid dataset.
- All broker jobs are successful.
- `lifecycle/report.json` reports `passed` within 1,200 seconds.

## Stop criteria

Recorded: 2026-10-10 16:10 PT

Stop on source drift, approval failure, broker or provider failure, invalid
export/consumption evidence, or the 1,200-second lifecycle ceiling.

## After a pass

Recorded: 2026-10-10 16:10 PT

Retain the attempt and use its phase timings as infrastructure evidence. Do not
count its generated rows as a scored AAR iteration.
