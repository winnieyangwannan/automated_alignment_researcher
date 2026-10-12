# AutoData pinned-revision notes

Recorded: 2026-10-11 22:24 PT

This note records the AutoData revision comparison used when preparing the Run
13 one-chain lifecycle canary. It does not change the provenance of completed
Run 12 attempts.

## Decision

Run 13 will pin the native `autodata_pipelines` source to the full commit:

```text
51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1
```

The execution checkout must be clean and detached at that exact commit. The run
pins a commit rather than a branch name because a commit is immutable while a
branch can move.

## Branch histories and differences

Both compared histories diverged from common ancestor
`9e623eb25bab4c4ba50642f72ca338f887772e27`.

`winnie/aar_integration` currently ends at
`7d1020bdcc1d9e0a4e01e889f9e95ee15807d50c`, dated 2026-10-08 PT. It has two
commits after the common ancestor:

1. `a282bd6` — avoid repeated task-state writes in the execution engine.
2. `7d1020b` — rebuild the bundled plugin wheel with that polling fix.

Those changes affect the execution engine, its focused regression test, the
bundled wheel, and the wheel lock.

`winnie/finalization-recovery` ends at the selected
`51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`, dated 2026-10-11 PT. It has 27
commits after the same common ancestor. In addition to the task-state polling
fix, this history contains the later AAR lifecycle work needed by Run 13,
including:

- delegated approval and production handoff;
- bounded campaign optimization and terminal budget accounting;
- resumable task attempts and transient transport recovery;
- trusted local Bubblewrap broker execution and node-local state support;
- serialized state-store writes;
- meta-optimization and production finalization recovery;
- provider-usage preservation and safe failure diagnostics;
- bounded judge repairs and structured Luna judge output.

Neither branch tip is an ancestor of the other, so this is not a simple
fast-forward relationship. Chronologically and functionally, however,
`51c18fd` is the newer and more complete lifecycle revision.

## Task-state polling fix is already incorporated

The selected history already contains the functional equivalent of the two
`aar_integration` commits:

1. `10c6d5e` — the same engine behavior that persists task state only when the
   observed backend status changes while retaining bounded control polling.
2. `559c4a9` — the corresponding plugin-wheel rebuild on the newer codebase.

The commit and wheel hashes differ because the fix was applied and bundled
against a newer tree. The functional engine change is the same. Cherry-picking
`7d1020b` onto `51c18fd` would duplicate the fix and risk replacing the newer
plugin wheel with an older wheel that lacks subsequent lifecycle work.

## Why Run 13 uses `51c18fd`

Run 13 needs more than the polling optimization: it needs the complete,
fail-closed AutoData lifecycle from delegated proposal approval through
meta-optimization, production export, verified handoff, and bounded training
smoke. The selected commit contains those capabilities and the polling fix in
one coherent source and wheel snapshot.

A temporary detached checkout of `51c18fd` passed 29 focused native AutoData
tests covering the execution engine, delegated approval, and plugin bootstrap.
It also passed AAR's exact-SHA detached plugin resolver. Based on the broader
capability set and this compatibility evidence, the user confirmed `51c18fd`
as the Run 13 AutoData pin.

This decision authorizes configuration of that revision only. No experiment,
job, model call, or HPC synchronization was started by recording this note.
