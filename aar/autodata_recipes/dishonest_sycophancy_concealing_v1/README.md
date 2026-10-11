# Dishonesty, sycophancy, and uncertainty recipe v1

This is a self-contained, deliberately minimal starting recipe for AAR-guided
AutoData experiments. It does not replace or mutate the existing
`dishonest_sycophancy_concealing` recipe.

Select it explicitly in an experiment run YAML:

```yaml
recipe_root: aar/autodata_recipes/dishonest_sycophancy_concealing_v1
training_contract:
  objective: sft
  judge_rubric: recipe/judge_rubric.json
```

No existing run selects this directory automatically. A run continues using
the recipe recorded in its own `recipe_root` setting.

## Design

The recipe preserves strict experiment boundaries:

- one primary alignment axis per example and coverage of all three axes;
- target-aware probing against an identity-bound target model;
- independent rubric-based teacher and target judgment;
- rejected examples never enter production training data;
- protected grounding, judge, task, schema, and provenance contracts during
  one native meta-optimization execution.

The starting method is intentionally less prescriptive:

- a compact generic generation prompt replaces axis-specific trap scripts;
- six broad behavior families replace nine narrow templates;
- the minimum structural grounding contains six tasks;
- the authoring dry run includes one task per axis;
- the comparator hard-gates validity while reporting quality and challenge;
- meta-optimization measures one first attempt per scenario;
- target/judge-guided repair is reserved for final production generation;
- production feedback contains bounded judge diagnoses, not Gemma's raw answer.

Production results also expose first-attempt metrics separately from eventual
post-repair yield. This prevents the fixed repair loop from hiding whether the
mutable generation strategy itself improved.

## Intended evolution

Within one native meta-optimization execution, only
`recipe/generation_strategy.json` may change. Between AAR iterations, a
reviewed outer recipe revision may change grounding, comparison, judging, or
task behavior while preserving provenance and evaluator isolation.

The investigation that motivated this version is recorded in
`experiments/dishonest_sycophancy_concealing/run_12/doc/autodata_starting_point.md`.
