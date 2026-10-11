# Run 12 Canary 2 Trial 9 progress

All timestamps use Pacific Time (`PT`). This log contains orchestration metadata
only; never record generated rows, prompts, responses, credentials, or held-out
content.

### ⏳ 03:59 PT — PREPARING: Trial 9 created from the frozen contract

Trial 8 stopped safely before mutation after exposing an AAR/native action-result
shape mismatch. Repair commit `7b7d73e` is synchronized exactly to the clean
HPC `autodata` worktree.

Validated repair coverage:

- supported AAR envelopes normalize to native flat output fields;
- schema, status, action identity, declared outputs, and key value shapes fail
  closed before native `action complete`;
- correctable invalid results preserve the native lease and receive explicit
  retry feedback;
- bridge, broker, and supervisor diagnostics are retained in every isolation
  mode;
- allowlisted native contract diagnostics propagate through typed supervisor
  status;
- an isolated copy of Trial 8 advances to `mutate_candidate` after normalization.

Local and HPC focused gates each pass 114 tests plus 6 subtests. The broader
local AutoData gate passes 345 tests plus 6 subtests; its sole failure is the
unrelated user-deleted Run 13 fixture.

Next: commit Trial 9 records, synchronize the exact commit, run the final
immutable preflight, launch one `alpha` bootstrap canary, and monitor through
the verified training-smoke boundary. Evaluator count must remain zero.

### ❌ 04:01 PT — PRELAUNCH FAILED SAFELY: logical/physical checkout alias

The live Kimi/MCP proof passed, but immutable config compilation stopped before
`sbatch` with:

```text
ValueError: explicit runtime profile does not match the run config declaration
```

No Trial 9 launcher, research, controller, training, or evaluator job was
created. The preserved attempt root is
`/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T110006Z-ce9163e152f2`.

Root cause: Trial 9 was invoked through FAIR's `/home/...` spelling while
`realpath` canonicalized configuration files to `/storage/home/...`. The
launcher retained a logical `/home` repository root, misclassified both
in-repository YAML files as external, and copied them outside the immutable
source snapshot. The compiler correctly rejected the copied explicit profile
because the copied run config's declared relative profile resolves inside the
snapshot. The identical files differed only by location.

Required repair: canonicalize the launcher script, Run 12, and repository roots
with physical paths before any containment or snapshot classification. Do not
weaken the compiler's exact-path integrity check. Trial 9 remains terminal;
launch a fresh Trial 10 only after committing, synchronizing, and validating
the canonical-path repair.
