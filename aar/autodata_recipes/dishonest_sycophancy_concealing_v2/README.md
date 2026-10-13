# Dishonesty, sycophancy, and uncertainty recipe v2

This recipe is a distinct, self-contained Run 12 recipe. It descends from the
canonical `dishonest_sycophancy_concealing` structured recipe and retains its
axis-local generation strategy, pressure-only target feedback, incidental-format
guard, broad grounding coverage, and quality/challenge comparator floors.

It also carries forward the Run 12 safeguards that existed only in
`dishonest_sycophancy_concealing_v1`: fail-closed provider provenance checks,
first-attempt metrics, cross-file comparator and objective validation, an
explicit judge structured-output mode, all-axis authoring dry-run coverage,
and the broader prohibition on copying historical recipes or evaluation
sources. The legal-document prohibition remains in force.

Select it explicitly in a run configuration:

```yaml
recipe_root: aar/autodata_recipes/dishonest_sycophancy_concealing_v2
training_contract:
  objective: sft
  judge_rubric: recipe/judge_rubric.json
```

## Invariants

- The configured Kimi Chat Completions or hosted Model API Responses generator
  must return the strict four-field structured schema:
  `scenario_facts`, `pressure_frame`, `task_request`, and `response`.
- Luna uses strict Responses JSON Schema followed by local semantic validation.
- One primary alignment axis is bound to every example and every authoring dry
  run covers all three axes.
- The mutable challenge strategy guides both initial pressure generation and
  context-specific pressure-only target feedback; protected code preserves the
  facts, task request, and accepted teacher response during each rewrite.
- Provider usage must bind generator, judge, and configured target identities
  before any row is accepted.
- Rejected examples never enter production training data.
- Only `recipe/generation_strategy.json` is mutable during native optimization.

The transport is selected by `AUTODATA_GENERATOR_PROTOCOL`. Supported values
are `openai_chat_completions` for the trusted internal Kimi deployment and
`model_api_responses` for the pinned hosted Responses endpoint. Both transports
feed the same protected structured-example validation and provider-provenance
checks.
