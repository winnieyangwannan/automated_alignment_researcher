# Run 12 Canary 2 — Winnie's notes

All timestamps use Pacific Time (`PT`). This file records conclusions and
operational evidence only; it must not contain generated prompts, responses,
held-out content, or credentials.

## 2026-10-11

### 19:19 PT — Trial 15 stopped: production could not reach its row target

Trial 15 was stopped and its artifacts preserved after a yield audit showed
that native task completion was not equivalent to accepted training-data
production. The research job `1821476` and dependency-held controller job
`1821477` were cancelled. The retained attempt is:

`/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T235806Z-a1239f63e9c6`

Important distinction:

- A native task marked `succeeded` means the recipe executed and returned a
  schema-valid task result.
- An accepted row additionally requires the teacher response to pass the Luna
  rubric and the fixed Gemma target to exhibit the exact axis-mapped failure.
  Rejected tasks intentionally export no `generated_items`.

The final read-only audit covered 319 completed production results:

- 1 accepted row;
- 276 `target_not_challenging` rejections;
- 31 `judge_rejected` results; and
- 11 provider/format failures.

The observed accepted-row yield was therefore about 0.32%. At that yield,
1,250 initial tasks would produce only about four accepted rows, so the exact
1,000-row contract was unattainable. Monitoring must report accepted exported
rows separately from successfully executed tasks and must flag an impossible
yield before waiting for the complete production corpus.

### 19:19 PT — Production slowness was five serial feedback cycles

This was not a scheduler hang or idle-worker problem. Across a 310-task timing
snapshot:

- mean task wall time was 99.5 seconds, median 99 seconds, p95 131 seconds;
- configured concurrency 8 was utilized 99.65% of the measured interval;
- 299 of 310 tasks exhausted all five feedback cycles; and
- the recipe made 4,546 model requests, or 14.66 requests per completed task.

Each feedback cycle is dependent and serial:

`Kimi generator -> Gemma target -> Luna judge`

Gemma target decoding was the largest per-call component at about 10.98
seconds per request. Kimi averaged about 5.8 seconds per request. Luna,
container, and HTTP overhead accounted for the remainder. Luna rate limiting
was real but not the throughput root cause: 24 rate-limit signals among 1,537
judge attempts were about 1.6% of judge requests. The dominant multiplier was
`generation.target_feedback_max_attempts: 5` combined with almost universal
scientific rejection.

### 19:19 PT — Meta-optimization ran, but found no valid strategy

The exact three meta-optimization iterations executed, but none produced a
valid improvement:

- baseline winner: `constraints.valid=false`, fitness 0, challenge 0;
- iteration 1: checker failure
  `generation_strategy_unsupported_fields`;
- iteration 2: `constraints.valid=false`, paired improvement 0;
- iteration 3: `constraints.valid=false`, paired improvement 0; and
- final held-out evaluation: `constraints.valid=false`.

The baseline remained the exported winner solely because every proposed
candidate was rejected. Native `success_rate=1.0` described task execution,
not scientific validity.

Measured timing:

- baseline evaluation: 2 minutes 43 seconds;
- iteration 1: 4 minutes 54 seconds;
- iteration 2: 6 minutes 34 seconds;
- iteration 3: 6 minutes 9 seconds;
- final held-out/full-corpus validation and retry: 39 minutes 49 seconds; and
- total native meta execution: 1 hour 9 seconds.

The three mutation/evaluation rounds themselves took about 17.5 minutes. Most
of the total was final validation. More iterations alone are not supported by
this evidence: all mutations remained invalid and fitness stayed at zero.

### 19:25 PT — Root cause and minimal next-trial correction

Trial 15 selected the legacy recipe root
`aar/autodata_recipes/dishonest_sycophancy_concealing_v1`, while canonical Run
12 selects `aar/autodata_recipes/dishonest_sycophancy_concealing`.

The retained v1 recipe is `minimal-target-aware-v1`. It generates only a
`prompt` and `response`. When Gemma is not challenged, it asks Kimi to generate
another complete prompt/response pair and then repeats the Gemma and Luna
calls. It has no structured scenario parts or trusted prompt-hardening path.

The canonical non-v1 recipe is `axis-local-structured-target-aware-v8`. It
separates scenario facts, the pressure frame, the task request, and the teacher
response. It performs one Kimi generation, then can apply bounded,
axis-specific trusted pressure variants while preserving the facts and teacher
answer. Existing focused tests verify that hardening preserves those fields,
uses only one generator call, and re-probes the target and judge.

This makes the canonical recipe a better targeted candidate because Trial 15's
dominant failure was `target_not_challenging`, precisely the case its trusted
hardening path addresses. It is better by design and existing unit evidence,
but it is not yet live proof of acceptable yield; the next bounded canary must
measure that.

A separate integration defect allowed the failed meta result to enter
production. `scripts/autodata_lifecycle_supervisor.py` verified completed
status, winner identity, source/digest integrity, partitions, and settings, but
did not require the final held-out winner's `constraints.valid` to be true.
Trial 15 should have stopped before production.

Minimal correction before another trial:

1. Use the existing canonical non-v1 recipe; do not copy another hardening
   implementation into v1 and do not weaken the judge or challenge contract.
2. Add a fail-closed pre-production check requiring held-out winner evidence
   for the same winner candidate with `constraints.valid is true`.
3. Keep three meta iterations for the next canary. Consider five only after a
   corrected run shows genuine improvement without convergence.
4. Monitor accepted-row yield, not only native task status, and stop early when
   the required production row count is mathematically unreachable.

### 22:18 PT — Kimi skill loading, SDK, and ACP integration conclusions

The authoritative AutoData implementation and instructions live in the pinned
`autodata_pipelines/plugin/autodata` checkout. For Claude, AAR already registers
the complete local plugin and explicitly enables its qualified
`autodata:autodata` skill. The plugin currently publishes only that one skill;
its Python wrapper, bootstrap code, and wheels are supporting resources invoked
through Bash rather than additional plugin tools.

Kimi Code 2.1.1 supports both skills and its own plugin system. The existing
AutoData manifest is Claude-specific (`.claude-plugin/plugin.json`), whereas a
native Kimi plugin expects `kimi.plugin.json` or `.kimi-plugin/plugin.json`.
However, Kimi can load the same authoritative AutoData skill directly and
without copying it by receiving:

```bash
--skills-dir "$AAR_AUTODATA_PLUGIN_ROOT/skills"
```

In Kimi the skill is named `autodata`, not the Claude-qualified
`autodata:autodata`. AAR's current Kimi command does not pass `--skills-dir`, so
the Kimi researcher has not been receiving this skill. This is a likely
contributor to the no-op mutation behavior: the skill explicitly says that a
`mutate_candidate` action must make one evidence-backed change.

The current Kimi integration runs one noninteractive CLI invocation at a time.
Within one AAR research session, `--continue` restores Kimi's conversation from
the isolated `KIMI_CODE_HOME` session store. AAR then inspects durable lifecycle
state and uses `_continuation_prompt()` to select the next checkpoint. This
host-controlled continuation mechanism is separate from the AutoData skill and
should not be removed as part of the small skill-loading repair. Contradictory
generic wording, especially permission to adopt files unchanged during
`mutate_candidate`, should be removed or specialized.

The Kimi Code SDK and ACP provide two possible persistent integrations:

- The SDK is a Node/TypeScript library embedded in a Node application. It
  offers direct access to Kimi's agent engine but would require a maintained
  Python-to-Node bridge because AAR is Python.
- ACP is a language-neutral protocol. AAR can remain Python while managing a
  persistent `kimi acp` subprocess over structured messages. It is therefore
  the cleaner candidate for a Claude-SDK-like Kimi adapter unless an essential
  capability is available only through the direct SDK.

An SDK or ACP migration can reduce host-injected prompt drift by keeping one
continuous agent session, but it does not by itself enforce a valid mutation.
The shared native lifecycle must still reject an unchanged effective strategy,
return precise feedback, retry within the same iteration, and avoid consuming
iteration or patience budget for a no-op.

Recommended sequencing:

1. Make the verified pinned AutoData skill available to every initial and
   continued Kimi invocation.
2. Add deterministic no-op enforcement at the mutation boundary and remove the
   conflicting mutation-specific continuation wording.
3. Independently prove ACP or SDK parity for skill loading, MCP tools, tool
   restrictions, request-policy enforcement, timeouts, cancellation, session
   recovery, and structured logs.
4. Replace the CLI integration only after the persistent adapter passes those
   parity checks; do not combine that migration with the immediate canary
   blocker repair.

### 00:01 PT — Simplify `clarify_design` to one Kimi write

Using Trial 17’s exact action:

```json
{
  "id": "act_d6027f5e83cf9781f64147f2",
  "kind": "clarify_design",
  "allowed_paths": ["autodata.workspace.json"],
  "outputs": ["summary", "decisions"]
}
```

#### 1. Kimi performs one operation

```text
Write:
  path: draft/autodata.workspace.json
  content: <complete updated workspace JSON>
```

No second Kimi turn is requested.

#### 2. AAR validates the edit

AAR checks:

- The action is still active and leased.
- Only `autodata.workspace.json` changed.
- The file is valid JSON and matches its schema.
- Existing required fields and types were preserved.
- The requested success criteria are present.
- The workspace revision has not changed concurrently.

If validation fails, Kimi receives the precise error and repairs the same edit.

#### 3. AAR constructs the result itself

From the validated workspace, AAR produces:

```json
{
  "summary": "Validated the scoped workspace design update.",
  "decisions": [
    "Generate original examples covering honesty, sycophancy resistance, and uncertainty.",
    "Require at least 1,000 accepted examples.",
    "Exclude benchmark-derived content.",
    "Use the configured target model and independent judge."
  ]
}
```

These values are derived from the validated workspace—not invented by AAR.

#### 4. AAR completes the action

AAR privately runs:

```bash
autodata action complete \
  act_d6027f5e83cf9781f64147f2 \
  --lease-token=<hidden-host-token> \
  --result <host-generated-result>
```

The current CLI may require AAR to create a short-lived result file internally,
but Kimi never writes or sees it.

#### 5. AutoData advances

```text
clarify_design: completed
→ next action: author_grounding
```

This preserves validation, auditing, and the secret lease while eliminating
Trial 17’s fragile second model turn.

### 00:15 PT — Correction from the observed Claude-native exchange

The host-owned proposal above is retained as discussion history, but it is not
the Trial 18 implementation. The observed Claude flow establishes that native
`clarify_design` is an intent-confirmation action and may legitimately record a
byte-identical revision. Requiring a Kimi workspace mutation or a new
`success_criteria` field would therefore change the native contract.

Trial 18 instead gives Kimi parity for this action only:

```text
native status and action contract
→ native action begin and scoped lease
→ inspect the reviewed workspace
→ edit only if intent is actually missing; zero edits is valid
→ write summary and decisions for the native CLI
→ native action complete with the same scoped lease
→ trusted supervisor resumes at author_grounding
```

AAR does not auto-begin or auto-complete `clarify_design` in this path. Native
AutoData remains responsible for the lease, allowed paths, result validation,
revision audit, and transition. All later action handling remains unchanged so
this canary tests one targeted compatibility change.
