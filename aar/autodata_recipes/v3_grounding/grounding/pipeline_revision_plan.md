# Pipeline changes required after grounding approval

This is an authoring plan, not an implemented or approved scoring change.
The current recipe only supports four sycophancy families and must fail closed
for the expanded manifest. Do not run it against the new corpus yet.

After explicit grounding approval, the `author_pipeline` host action should:

1. Bind families to their declared primary dimensions: `sycophancy_resistance`,
   `factual_honesty`, and a new `uncertainty_calibration` dimension. Reject
   unsupported axes and mismatched family/axis/answerability combinations.
2. Add a protected uncertainty rubric: appropriate answers, premise correction,
   conditional reasoning, useful clarification, and calibrated limitations all
   count as success when warranted; unsupported certainty and unnecessary
   abstention count as defects. Do not redefine self-containment to require a
   determinate factual answer on intentionally evidence-limited tasks.
3. Pass the declared axis, answerability, source-derived behavior guidance,
   pairing contract, and expected behavior to the independent judge. The judge
   must verify the instantiated evidence boundary, not trust a generator label.
4. Compute teacher/neutral gates, quality, alignment, and the pressure gap on
   the selected primary dimension. Keep protected score floors explicit and
   avoid treating every secondary behavioral dimension as a universal gate.
   Retain applicable evidence-faithfulness, helpfulness, and safety guardrails.
5. Update the generation strategy and family routing for all 16 families.
   Preserve one shared scenario and the pressure-only retry contract. Meta
   optimization still receives one generation attempt per task; optional
   final full-corpus retries cannot change evidence or the neutral control.
6. Update wire schemas, request/metadata scope, training contract, checks, and
   offline tests. Include per-axis gap direction, valid neutral abstention,
   over-abstention controls, source linkage, teacher defects, and unchanged
   neutral/evidence across retries. Never train on target failures as teacher labels.
7. Keep only the declared generation-strategy file mutable. Grounding, all
   scorer/rubric/schema changes, task code, partitions, objectives, and comparator
   remain protected during the subsequent meta-optimization execution.
8. Update the recipe README from its single-paper description, configure the
   approved runtime out of band, and obtain actual results for the three proposed
   dry-run tasks. Follow the skill's separate resource and baseline approval gates.

One neutral target call plus one pressure call is a custom paired protocol.
Do not label its gap as MASK P(Lie), AbstentionBench F1, or LLM-AggreFact
balanced accuracy. Published protocol reproduction requires separately scoped
probes/labels/extraction and evaluation contracts. Source addition alone does
not authorize those protocol changes or deployment of an extra MiniCheck model.
