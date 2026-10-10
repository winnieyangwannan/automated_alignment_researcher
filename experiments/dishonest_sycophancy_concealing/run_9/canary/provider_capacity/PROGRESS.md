# Provider-capacity check progress

- 2026-10-09 23:17 PT — Five aggregate jobs failed closed before provider
  calls because policy and client generator deployment identities differed.
  Source commit: `baa9a893fb8af3a10ecec2f44455af267ac93398`
  Attempt: five retained `capacity-20261010T0616*Z-baa9a893fb8a` roots
  Jobs: `1798083`, `1798085`, `1798086`, `1798087`, `1798088` — failed
  Evidence: per-attempt broker and client logs
  Decision: fix provenance propagation; do not count this as a capacity test.

- 2026-10-09 23:20 PT — The retry failed closed before provider calls because
  duplicated policy/client generator-input limits differed.
  Source commit: `f9875174b06c3f6fed1c91597733b97f61352ff3`
  Attempt: five retained `capacity-20261010T0619*Z-f9875174b06c` roots
  Jobs: `1798149`, `1798150`, `1798151`, `1798152`, `1798153` — failed
  Evidence: per-attempt HTTP 422 contract errors
  Decision: replace duplicated settings with one validated YAML profile.

- 2026-10-09 23:28 PT — The five-chain burst passed: 160/160 broker and client
  tasks completed, Kimi and Gemma were called 160 times, and 159 tasks reached
  Luna. Aggregate broker execution spanned approximately 25 seconds. Eight
  task results were model/format failures rather than transport failures.
  Source commit: `983e776008370ade1ec174bd6207a681dfe8641c`
  Attempt: five retained `capacity-20261010T0626*Z-983e77600837` roots
  Jobs: `1798273`, `1798274`, `1798275`, `1798276`, `1798278` — completed
  Evidence: each attempt's `summary.json` and node-local broker snapshot
  Decision: pass the aggregate transport/concurrency check; do not treat row acceptance as a quality estimate.

- 2026-10-10 16:10 PT — Source files were reorganized by responsibility; no
  canary was launched, resumed, cancelled, or otherwise mutated.
  Source commit: this organizational commit (resolved by Git history)
  Attempt: not created
  Jobs: none
  Evidence: this source tree
  Decision: preserve retained evidence and use the new launcher/config paths.
