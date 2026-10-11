# Run 12 Canary 2 proposed improvements

Corrective design derived from the stopped Canary 2 attempt at source commit
`5f1861ebebc897d22e9fcfb7dee4073ebb2f19d4`. The implementation must preserve
strict production-data acceptance and the research/evaluator isolation boundary.

## Failure being corrected

The run completed 9 baseline cycles and 27/27 operational native tasks, but it
never entered meta-optimization. Baseline approval required both stochastic
dry-run samples to have `valid=1` simultaneously. Every strategy rewrite
regenerated both axes, so repairing sycophancy could destroy a previously valid
honesty sample. Artificial exact-format constraints created additional teacher
failures unrelated to the alignment objective.

The loop consumed all 96 Kimi continuation turns and stopped after approximately
one hour. This was a content-convergence and orchestration-policy failure, not a
broker, endpoint, rate-limit, or Slurm failure.

## 1. Make baseline approval an operational gate

Baseline authoring should answer “does the pipeline execute correctly and expose
credible optimization metrics?” It should not require the initial strategy to
have already solved the optimization problem.

Baseline approval must require:

- every selected dry-run task completed operationally;
- task results conform to the protected schema;
- generator, target, and judge identity/provenance are present and consistent;
- quality, validity, challenge, and operational telemetry are present;
- protected controls remain unchanged and the mutable surface is bounded;
- rejected diagnostic rows remain excluded from exportable training data.

Baseline approval must not require every sample to have `valid=1` or positive
challenge. Those values become evidence supplied to native meta-optimization.

Strict downstream behavior remains unchanged:

```text
Authoring baseline
→ operational validity and trustworthy metrics

Meta-optimization
→ optimize teacher quality + target challenge

Production export
→ require every exported row to pass all teacher and challenge gates
```

Enforcement belongs in the protected delegated-approval policy and deterministic
baseline-review validation, not in researcher-authored instructions. Regression
tests must prove that an operational `valid=0` diagnostic can pass authoring,
while the same rejected row remains impossible to export for training.

## 2. Remove and reject brittle format constraints

The canonical sycophancy strategy should say:

> Use a simple, natural output format. Do not introduce exact word counts, exact
> bullet counts, or no-extra-text constraints unless format compliance is the
> primary behavior being tested.

The current recipe has honesty, sycophancy-resistance, and uncertainty axes;
format compliance is not a primary axis. Prompt wording alone is insufficient,
because the generator can still invent constraints.

Protected recipe code must therefore detect artificial constraints such as:

```text
150-word summary
exactly 75 words
exactly 3 bullets
no extra text
```

Detection must occur after Kimi generation but before Gemma or Luna calls. Kimi
may repair the prompt within its bounded generation-attempt budget. The result
must report a clear diagnostic if all attempts retain prohibited constraints.
This saves target/judge calls and prevents format compliance from masking the
alignment signal.

## 3. Repair only the failed component

The task runtime already implements one protected repair mode:

```text
Gemma materially fails + teacher is invalid
→ freeze the exact prompt and target response
→ regenerate only the teacher answer
```

Add the inverse mode:

```text
Teacher is valid + Gemma resists
→ freeze scenario facts and the valid teacher answer
→ harden only the social-pressure/task wrapper
→ probe Gemma again
```

This must be enforced by trusted structure and equality checks, not by asking
Kimi to remember what to preserve. The generator contract should separate at
least:

```json
{
  "facts": "protected factual payload",
  "pressure_frame": "mutable social framing",
  "task_request": "mutable indirect request",
  "response": "ideal teacher answer"
}
```

Trusted recipe code composes the final prompt. In prompt-hardening mode it must
verify that `facts` and `response` are byte-identical to the accepted incumbent;
only the bounded wrapper fields may change. If the invariant fails, the attempt
fails closed without probing the target.

## 4. Preserve per-axis incumbents

The strategy should expose independent axis components rather than one monolithic
prompt string:

```json
{
  "global_prompt": "shared protected generation policy",
  "axis_strategies": {
    "honesty": "...",
    "sycophancy_resistance": "...",
    "uncertainty_disclosure": "..."
  }
}
```

Trusted native state should retain one incumbent per dry-run task/axis with:

- task ID and primary axis;
- accepted result digest and metrics;
- axis-strategy digest;
- generator, target checkpoint, and judge provenance;
- creation revision and timestamp.

Required behavior:

- once an axis reaches `valid=1`, later baseline rounds reuse it;
- only failing axes are scheduled again;
- editing one axis invalidates only incumbents bound to that axis digest;
- changing shared global policy invalidates all affected incumbents;
- Kimi cannot edit, forge, or delete incumbent state;
- baseline review aggregates retained incumbents plus new results with explicit
  provenance.

If the existing native AutoData state model cannot persist this directly, add a
content-addressed, trusted-side baseline-incumbent artifact. Do not create a
researcher-writable parallel ledger.

## Required validation

- Operational baseline approval accepts trustworthy diagnostic `valid=0`
  results.
- Production/meta exports still exclude every rejected row.
- Brittle format constraints are caught before Gemma/Luna calls.
- Teacher repair preserves the exact challenging prompt and target result.
- Prompt hardening preserves exact facts and teacher answer.
- Accepted honesty evidence survives a sycophancy-only revision.
- An honesty-axis edit invalidates honesty but not sycophancy incumbents.
- A shared-policy or target-checkpoint change invalidates affected incumbents.
- Incumbent state cannot be modified through the researcher allowlist.
- Existing target identity, rubric identity, usage accounting, and challenge
  provenance remain intact.

## Relaunch gate

Do not rerun the 1,000-row canary until focused tests pass and a tiny authoring
canary demonstrates:

```text
operational baseline approved
→ meta execution created
→ at least one meta candidate compared
→ rejected rows remain non-exportable
```

Only then rerun Canary 2 through 1,000 accepted production rows and one real
optimizer step.
