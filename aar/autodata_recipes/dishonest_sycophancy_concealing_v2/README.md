# Dishonesty, sycophancy, and uncertainty recipe v2

This recipe is a distinct, self-contained Run 12 recipe. It descends from the
canonical `dishonest_sycophancy_concealing` structured recipe and retains its
axis-local generation strategy, trusted prompt hardening, incidental-format
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

- Kimi Chat Completions must return the strict four-field structured schema:
  `scenario_facts`, `pressure_frame`, `task_request`, and `response`.
- Luna uses strict Responses JSON Schema followed by local semantic validation.
- One primary alignment axis is bound to every example and every authoring dry
  run covers all three axes.
- Target-not-challenging examples may use only the protected prompt-hardening
  variants; facts and the accepted teacher response remain unchanged.
- Provider usage must bind generator, judge, and configured target identities
  before any row is accepted.
- Rejected examples never enter production training data.
- Only `recipe/generation_strategy.json` is mutable during native optimization.

The hosted Model API generator protocol from v1 is intentionally not included;
this recipe uses the trusted internal Kimi Chat Completions deployment.
