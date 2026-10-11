# AutoData starting-point audit

Status: investigation and proposal only
Date: 2026-10-10 PT
Scope: every file under `aar/autodata_recipes/dishonest_sycophancy_concealing/`

No recipe, runtime, or experiment configuration was changed as part of this
audit. The proposals below are intentionally left for review and discussion.

## Question being answered

The checked-in recipe should be a safe, understandable starting point for an
AAR researcher. It should establish the experiment's non-negotiable scientific
contract without pre-solving the research problem or anchoring every later
strategy to one narrow style of example.

The desired split is:

- strict about isolation, provenance, model identity, schemas, and export
  safety;
- clear about the three alignment objectives and target-aware measurement;
- permissive about how a researcher generates useful examples;
- modest enough that the baseline reveals genuine weaknesses for AAR to
  improve;
- operationally configurable without rewriting scientific policy.

## Executive conclusion

The recipe is safe and substantially more mature than a minimal seed, but it
is not yet a neutral starting point. Its strongest integrity controls should
remain. Its main source of bias is not the six-dimension judge rubric anymore;
it is the combination of a highly prescriptive generation prompt, a fixed
nine-pattern taxonomy, and an up-to-five-round generator/target/judge repair
loop.

That combination can make the baseline look like an already optimized method:

1. The strategy tells Kimi the exact trap structure to construct.
2. The grounding repeatedly selects from nine predesigned trap families.
3. Gemma and Luna expose why an attempt failed.
4. Kimi can repair the example up to four more times within the same task.

This is useful for maximizing production yield, but it weakens the diagnostic
value of a starting baseline. It also makes the inner meta-optimizer compare
strategies after a strong fixed repair policy has already corrected many of
their mistakes.

The recommended direction is therefore not to make security or provenance
looser. It is to make the scientific seed smaller and to separate measurement
of first-attempt strategy quality from optional production repair.

## Non-negotiable controls to preserve

The following are not unwanted restrictions. They define a valid and isolated
experiment:

- no benchmark, held-out, or evaluator-only content in generation inputs;
- one declared primary alignment failure per example;
- corpus-level coverage of honesty, sycophancy resistance, and uncertainty
  disclosure;
- target-aware probing against the exact chain and checkpoint;
- an independent judge rather than generator self-approval;
- only accepted prompt/ideal-response pairs entering training data;
- content-addressed rubric and checkpoint provenance;
- protected grounding, judge, task code, and schemas during one native
  AutoData meta-optimization execution;
- deterministic seeds and typed native task results;
- the target's raw answer remaining outside the exported training row.

These controls limit leakage and invalid data. They do not dictate a narrow
generation method.

## What may change at each level

Within one native AutoData meta-optimization execution, only
`recipe/generation_strategy.json` is mutable. Grounding and evaluation remain
fixed so candidate strategies are compared on the same evidence.

Between AAR iterations, the researcher may propose a reviewed recipe fork. At
that outer level it can revise grounding coverage, task logic, rubric,
objective, comparator, or training-data design, subject to the normal approval
and provenance gates. Therefore a protected file is not permanently frozen; it
is only frozen within the comparison in which changing it would invalidate the
comparison.

This distinction supports a simple initial recipe: the inner loop should have
one legible search surface, while the outer researcher remains free to propose
larger evidence-backed changes.

## File-by-file review

### 1. `autodata.pipeline.json`

Role:

- defines the native task command and result schema;
- declares mutable and protected paths;
- runs the recipe check;
- defines metric presentation and candidate comparison.

What is good:

- A single mutable strategy file gives the inner loop a clear experimental
  variable.
- Protecting the task, grounding, rubric, schema, and training contract makes
  candidate comparisons meaningful.
- The 600-second task timeout is an operational ceiling rather than scientific
  prompt bias.
- Quality and challenge are both visible instead of hiding target difficulty
  behind one score.

Concerns:

- The comparator is represented both here and in `comparator.json`. The native
  framework uses both identities, but the recipe check does not currently prove
  that their contents agree.
- Three aggregate floors (`valid`, `quality`, and `challenge`) plus a harmonic
  objective and a minimum delta create several overlapping selection rules.
  Each rule is defensible, but together they make the seed harder to reason
  about.
- `minimum_meaningful_delta: 0.01` is a fixed assumption about noise and effect
  size. On a small hidden split, it is not automatically a statistically
  meaningful threshold.

Proposal:

- Keep the protected-path boundary and single inner-loop mutation.
- Add a consistency check proving the inline comparator equals
  `comparator.json`.
- Start with the simplest target-aware comparison that retains the experiment's
  intent: maximize balanced quality/challenge, require sufficient validity,
  and treat the individual quality/challenge floors as reported diagnostics
  unless data demonstrates that hard floors are necessary.
- Either justify the 0.01 delta from repeated-run variance or begin with zero
  and let the outer AAR process introduce a noise-aware threshold.

### 2. `autodata.workspace.json`

Role:

- states the workspace goal and source restrictions;
- selects Local Bubblewrap;
- supplies default authoring and execution budgets.

What is good:

- The goal is concise and directly aligned with the experiment.
- Synthetic-only grounding and exclusion of held-out material are appropriate
  isolation rules.
- Independent-judge acceptance is a necessary export condition.
- Local Bubblewrap is the validated choice for this trusted question-only
  recipe.

Concerns:

- “Do not create legal-document tasks or copy the historical legal AutoData
  recipe” is historical migration baggage, not a general scientific rule. It
  unnecessarily excludes a legitimate domain.
- Concurrency, attempt counts, and wall time are mixed into the scientific
  workspace seed even though Run 12's runtime profile overrides important
  capacity choices.
- `concurrency: 4` is not the measured Run 12 execution setting, which makes
  the checked-in file look authoritative when it is actually a fallback.

Proposal:

- Remove the blanket legal-document ban. Keep the narrower prohibition on
  copying historical recipe or evaluation content.
- Keep only conservative portable defaults here, and make the selected runtime
  profile the explicit source of capacity, timeout, and concurrency policy.
- Document which values are fallback defaults and which are expected to be
  compiled from the run YAML.

### 3. `comparator.json`

Role:

- provides the content-addressed comparator document used by native AutoData.

What is good:

- It makes the winner rule auditable and reproducible.
- Maximizing a harmonic mean prevents a high-quality but easy dataset, or a
  difficult but poor-quality dataset, from winning solely on one component.

Concerns:

- It duplicates the comparator embedded in the pipeline.
- The three floors and 0.01 delta are stronger assumptions than the native
  contract requires.

Proposal:

- Keep the separate document because it participates in native provenance.
- Validate byte-for-byte semantic agreement with the pipeline comparator.
- Simplify its initial constraints in lockstep with the pipeline after reviewing
  baseline distributions.

### 4. `framework.lock.json`

Role:

- pins the native AutoData framework contract to version 1.0.0.

Verdict:

- Keep unchanged. This is provenance and compatibility control, not a
  scientific restriction. A framework upgrade should be an explicit reviewed
  change, not something an inner-loop strategy can trigger.

### 5. `grounding/coverage.json`

Role:

- defines the three alignment axes;
- defines eight content domains and nine behavior patterns;
- requires at least 96 source tasks.

What is good:

- It correctly moves coverage from the individual-example level to the corpus
  level.
- Every example has one primary axis, while the corpus covers all three.
- Axis-to-teacher-dimension and axis-to-target-failure mappings are explicit.

Concerns:

- The nine patterns are already fairly complete research hypotheses about how
  to elicit failures. They predispose the baseline toward false premises,
  authority pressure, flattering pressure, and forced certainty.
- Exactly three hand-designed patterns per axis makes the initial corpus look
  balanced, but may hide whether an AAR researcher can discover better failure
  modes.
- The eight domains are reasonable but fixed. They omit other natural settings
  and encode an arbitrary content distribution.
- `minimum_task_count: 96` is much larger than required to establish structural
  coverage. The first 72 tasks already enumerate every domain/pattern pairing.
  The minimum therefore adds cost rather than a new coverage guarantee.

Proposal:

- Preserve the three axes and their mappings.
- Replace the nine prescriptive patterns with a smaller set of broad seed
  families, or label them as examples rather than an exhaustive taxonomy.
- Use a small, diverse, neutral domain seed. Let outer AAR iterations propose
  evidence-backed expansion or reweighting.
- Lower the checked-in minimum to the smallest count that exercises all axes
  and chosen pattern families. Production size belongs in run configuration,
  not in the scientific coverage seed.
- Continue to freeze the resulting grounding within one meta-optimization run.

### 6. `grounding/build_manifest.py`

Role:

- validates coverage;
- deterministically builds task IDs, seeds, payloads, facets, and provenance;
- enforces the coverage minimum.

What is good:

- Determinism, uniqueness checks, empty source lists, and explicit facets are
  strong reproducibility controls.
- The builder prevents accidental omission of an alignment axis.
- The task requirement that one example target one primary failure is the right
  design principle.

Concerns:

- Domain and pattern selection is a simple modulo cycle. This creates a fixed
  ordering and a deterministic relationship among domain, pattern, axis, and
  ordinal.
- The dry run always uses the first two tasks. With the current ordering that
  covers honesty and sycophancy but not uncertainty disclosure.
- “Do not mention ... policies” is broader than the intended anti-leakage rule.
  It can suppress legitimate policy-related scenarios. The real prohibition is
  on evaluation policy and synthetic-generation meta-language.
- The 96-task minimum is enforced here even when the caller wants a tiny
  structural smoke test.

Proposal:

- Select a stratified three-task dry run containing one task per primary axis.
- Deterministically shuffle or explicitly stratify domain/pattern combinations
  from the seed, while retaining reproducibility.
- Narrow “policies” to “evaluation policies or generation instructions.”
- Separate a minimal recipe-validity count from run-specific source-task count.
  The run YAML should decide whether a campaign uses 3, 125, or 1,250 tasks.

### 7. `objective.json`

Role:

- declares the balanced quality/challenge utility as the optimization target.

What is good:

- It captures the central target-aware goal in one auditable metric.
- A harmonic mean explicitly penalizes imbalance.

Concerns:

- The description also names the three hard floors, coupling the objective to
  current comparator policy.
- The harmonic mean is a substantive scientific choice, not a neutral framework
  default.

Proposal:

- Retain the harmonic metric for the first target-aware experiment because it
  directly encodes the desired balance.
- Shorten the description to define the metric only. Keep selection constraints
  in the comparator.
- Ask later AAR iterations to compare alternative objectives only with preserved
  validation evidence; do not let the inner loop change the objective while it
  is choosing a strategy.

### 8. `recipe/check.py`

Role:

- validates the mutable strategy, request, coverage, rubric identity, and
  protected-path contract before tasks run.

What is good:

- It fails early on malformed or drifted recipe files.
- It verifies that the rubric is protected and content-addressed.
- It enforces complete corpus-level axis coverage.
- The large strategy text envelope no longer imposes the former toy-size prompt
  limit.

Concerns:

- The axis contract is duplicated here, in `coverage.json`, and in `task.py`.
  Future AAR recipe changes must keep three copies synchronized.
- The exact generation-strategy key set means the inner optimizer can rewrite
  prompts and temperature but cannot introduce a new structured knob unless an
  outer AAR iteration first changes code. This is acceptable if intentional,
  but should be documented.
- The source-reference detector uses substring heuristics. “Legal document” is
  an unrelated historical prohibition, while a clever leakage reference could
  evade the regex.
- It does not verify that inline and standalone comparator definitions agree.

Proposal:

- Define the axis mapping once and derive both validation and execution behavior
  from that source.
- Keep the five-field strategy schema for a simple inner search surface; allow
  new knobs only through a reviewed outer recipe change that also implements
  their semantics.
- Remove `legal document` from forbidden-source detection and focus checks on
  benchmark, held-out, evaluator, and source provenance.
- Add objective/comparator/pipeline consistency checks.

### 9. `recipe/generation_strategy.json`

Role:

- is the only file mutated during native meta-optimization;
- supplies Kimi's system prompt, scenario prefix, name, and temperature.

What is good:

- It requires one primary axis, self-contained stated facts, a correct teacher
  answer, safety, and machine-readable JSON.
- The earlier rigid rules requiring one false claim among four accurate facts,
  five-to-seven facts, and exact requested-format completion have already been
  removed.
- It tells the generator not to invent missing facts or artificial uncertainty.

Concerns:

- It is still a mature, highly engineered v7 strategy rather than a simple
  baseline.
- Each axis is assigned a narrow preferred construction: numerical/logical
  discrepancies plus social pressure, a powerful user plus an indirect writing
  task and one overclaim, or one missing variable plus a ban on hedging.
- “Prefer an indirect compliance task” and the detailed pre-return checklist
  encode a particular elicitation method before AAR begins.
- Repeated `NEVER` clauses and exact trap recipes can anchor later revisions to
  local prompt editing instead of encouraging broader research hypotheses.
- The blanket prohibition on mentioning “policies” is overbroad.

Proposal:

- Replace v7 with a compact baseline that says, in substance:
  create one original safe and self-contained prompt for the declared axis;
  produce the ideal truthful, helpful response using stated information;
  make the scenario realistic enough to test the target; return JSON.
- Let the grounding task provide domain and broad behavior family without the
  strategy prescribing one exact trap for each axis.
- Retain a short prohibition on benchmark/evaluation references, private data,
  fabricated citations, and actionable harm.
- Treat numerical traps, authority pressure, indirect transformations, and
  missing-variable tasks as hypotheses for AAR to discover or deliberately add,
  not mandatory behavior of the initial seed.
- Keep temperature configurable and reproducibly recorded.

### 10. `recipe/judge_rubric.json`

Role:

- defines Luna's teacher-quality dimensions, anchored scores, acceptance policy,
  and target-failure judgment.

What is good:

- Version 4 correctly treats one dimension as the primary learning objective.
- Supporting dimensions are diagnostic rather than automatic rejection gates.
- Universal guardrails allow a score of 1, so minor imperfections no longer
  reject otherwise usable examples.
- The top-level judge opinion is nonbinding; acceptance is computed from
  explicit anchored scores.
- Safety allows safe discussion, correction, and refusal rather than treating
  topic presence as a violation.

Concerns:

- Luna must still emit all six dimensions for every example even when two are
  only supporting diagnostics. This increases prompt/output complexity and can
  invite irrelevant critiques.
- Luna must emit a top-level `accept` even though it is explicitly ignored for
  acceptance.
- With primary score 2 and every universal guardrail at least 1, the minimum
  computed teacher quality is 0.80. Therefore
  `minimum_teacher_score: 0.75` is redundant under the current weights and
  gates.
- The 0.6/0.4 weighting is a scientific assumption that affects ranking even
  though it no longer meaningfully affects the acceptance threshold.

Proposal:

- Keep the dimension definitions, anchored 0/1/2 scale, primary requirement,
  universal guardrails, and target-failure contract.
- Remove the redundant top-level `accept` response field in a future schema
  revision.
- Consider asking Luna to score only the primary dimension and universal
  guardrails, while retaining other dimensions as optional diagnostics.
- Either remove the redundant 0.75 threshold or set and explain a threshold
  that actually adds behavior beyond the per-dimension gates.
- Keep weights only if ranking teacher quality by 0.6/0.4 is an intentional
  hypothesis; otherwise use a simpler transparent aggregate.

### 11. `recipe/request.json`

Role:

- provides the high-level safety axis, training mechanism, and generation goal.

Verdict:

- Keep essentially unchanged. It is the simplest and least biased scientific
  file in the recipe.
- “Synthetic supervised fine-tuning” accurately describes the current row
  schema. DPO or GRPO would require a different data contract and task recipe;
  merely renaming this field would not make the data compatible.
- If the outer AAR researcher proposes another objective, it should fork the
  recipe and change the request, output schema, task implementation, and
  training contract together.

### 12. `recipe/task.py`

Role:

- calls Kimi to generate a prompt and ideal answer;
- calls the exact Gemma target checkpoint;
- asks Luna to score teacher quality and target failure;
- performs bounded feedback/repair attempts;
- emits one typed native task result with usage and provenance.

What is good:

- Target-aware mode fails closed and binds URL, model, deployment, and
  checkpoint hash.
- The target uses deterministic decoding.
- Judge acceptance is computed from protected rubric values, not Luna's
  unstructured opinion.
- Rejected rows are never exported in meta or production; visible dry-run
  retention is diagnostic only.
- The target response is used for judgment but not copied into the training
  dataset.
- Provider usage and bounded failure reasons are preserved without copying raw
  error bodies or secrets.
- A challenging prompt can be retained while only a defective teacher response
  is repaired, avoiding an unnecessary target reprobe.

Concerns:

- At 41 KB, the file mixes transport, authentication, accounting, scientific
  axis policy, generation, target probing, judging, repair, ranking, and native
  result construction. This makes apparently small scientific changes risky.
- The axis mapping is hard-coded again instead of loaded from one protected
  contract.
- The default five generation attempts are not merely infrastructure retries.
  Each is a new Kimi generation and Luna judgment, often with a new Gemma probe.
  This fixed repair algorithm can mask differences among candidate strategies
  and multiply latency.
- Raw target output is included in feedback sent back to Kimi. The prompt says
  not to copy it, but the generator is nevertheless exposed to the model answer
  it is meant to defeat. This can encourage example-specific adversarial repair
  or accidental imitation.
- Candidate selection ranks acceptance, then challenge, then teacher quality.
  When every attempt is rejected, a highly challenging but poor teacher
  candidate can become the retained diagnostic example.
- The 12,000-character prompt and response ceiling is a hidden recipe policy
  separate from the configured model token envelopes.
- Luna's low reasoning effort and Kimi's `thinking: false` are embedded in the
  task rather than declared as experiment/runtime settings.
- Telemetry counts attempts and rate-limit signals but does not directly record
  bounded per-role latency, making performance diagnosis harder.

Proposal:

- Preserve target identity, fail-closed behavior, acceptance, provenance, and
  export rules.
- For baseline and meta comparison, score the first generation attempt as the
  strategy's primary outcome. Record optional repaired yield separately rather
  than letting repairs replace the baseline signal.
- Use repair attempts as an explicit production policy, with a run-configured
  budget, after the winning strategy is known.
- Feed Kimi bounded judge diagnoses and failure labels, not the raw Gemma answer,
  unless an experiment explicitly studies target-response feedback.
- Load axis mappings from one protected contract.
- Move provider mode, reasoning effort, response-size limits, and retry policy
  into validated runtime configuration where practical.
- Add per-role request latency and end-to-end task latency metrics.
- Refactor transport/accounting helpers away from scientific row policy only if
  this can be done without recreating AutoData orchestration in AAR.

### 13. `schemas/task-result.schema.json`

Role:

- defines the native result envelope, at most one generated training row,
  required metrics, provider usage, and bounded outcome values.

What is good:

- One task producing zero or one row is easy to reason about.
- Strict top-level and item keys prevent silent contract drift.
- Required quality, validity, challenge, and utility metrics match comparator
  needs.
- Empty `generated_items` naturally represents a rejected example without
  treating rejection as infrastructure failure.

Concerns:

- `metadata`, `_autodata_usage`, and `provider_usage` are structurally permissive
  even though downstream code relies on specific provenance fields.
- The schema requires at least two usage entries but does not express the normal
  target-aware generator/target/judge roles.
- The 12,000-character content ceiling exists only in `task.py`, not in the
  declared schema.

Proposal:

- Keep the basic zero-or-one-row contract and strict envelope.
- Add a small explicit provenance schema for rubric and target identity if the
  native dataset contract can carry it without coupling to one provider.
- Keep operational telemetry extensible; do not enumerate every possible metric
  in the scientific schema.
- Put any content-size rule in one visible contract rather than hiding it in
  task code.

### 14. `grounding/__pycache__/build_manifest.cpython-312.pyc`

### 15. `recipe/__pycache__/check.cpython-312.pyc`

### 16. `recipe/__pycache__/task.cpython-312.pyc`

Role:

- these are generated Python bytecode caches; they contain no authored recipe
  policy and are ignored by Git.

Proposal:

- Do not treat them as recipe inputs or retain them as experiment evidence.
- They may be cleaned as ordinary workspace hygiene in a later authorized
  change, but no deletion was performed during this investigation.

## Cross-file design findings

### 1. One primary axis is correct; one prescribed trap is not required

The recipe should continue assigning each example one primary learning
objective. That makes acceptance interpretable. Corpus-level grounding should
ensure coverage of all three objectives.

However, the initial strategy does not need to prescribe a nearly complete trap
template for each axis. Domain, broad behavior family, and primary axis are
enough structure for a baseline. AAR should be able to discover whether
authority pressure, flattering pressure, indirect writing tasks, numerical
errors, or missing variables are actually effective against the current Gemma
parent.

### 2. Repair yield and strategy quality are different measurements

The current task asks, in effect, “Can this strategy plus as many as four
target/judge-guided repairs eventually produce an accepted row?” That is a good
production-yield question.

The meta-optimization question should first be, “How good is this strategy on
its first attempt across fixed hidden scenarios?” Otherwise the fixed repair
policy can dominate the strategy being compared.

Recommended reporting:

- first-attempt validity, quality, challenge, and utility;
- eventual accepted yield after repair;
- attempts and model calls per accepted row;
- Kimi, Gemma, and Luna latency separately;
- rejection reason distribution by axis and scenario family.

### 3. Scientific policy is duplicated

The axis contract appears in coverage JSON, the checker, and task code. The
comparator appears in both the pipeline and comparator JSON. Size and policy
rules are split among JSON, Python, and runtime environment variables.

This does not make the current run invalid, but it raises the cost and risk of
the outer AAR researcher changing the recipe. A good starting point should have
one authoritative representation for each scientific decision and explicit
derived validation elsewhere.

### 4. Operational capacity should not look like scientific policy

Concurrency, HTTP retries, provider timeouts, endpoint identity, output-token
limits, and production source-task count are necessary settings. They should be
validated and recorded, but they are not the definition of honesty,
sycophancy, uncertainty, or teacher quality.

Run YAML and its compiled runtime profile should own those campaign choices.
The recipe should carry portable safe defaults and the scientific contracts
needed to interpret the output.

### 5. Strictness should concentrate at the boundary

The strongest rules should remain at these boundaries:

- what sources can enter grounding;
- which exact target model is probed;
- what the independent judge must establish;
- what provenance every accepted row carries;
- what data is allowed to leave as training output.

The generation method inside those boundaries can be much less prescriptive.

## Proposed minimal starting point

This is a proposal for discussion, not an implemented change.

1. Keep the three axes, one-primary-axis rule, target-aware probe, independent
   judge, and protected native lifecycle.
2. Replace the v7 strategy with a short generic baseline rather than an
   axis-specific elicitation playbook.
3. Use a small set of broad behavior families and a small neutral domain seed;
   move campaign size to run YAML.
4. Make the visible dry run contain one scenario per axis.
5. Evaluate and compare first-attempt metrics during meta-optimization.
6. Treat iterative target/judge feedback as a separately measured production
   policy, not an invisible part of strategy quality.
7. Keep rubric v4's primary/universal/supporting roles, but remove redundant
   response and threshold machinery in a versioned follow-up.
8. Centralize axis mappings and verify duplicated native comparator documents.
9. Remove historical legal-recipe restrictions and narrow the word “policies”
   to evaluation/generation policy leakage.
10. Preserve all provenance, isolation, checkpoint binding, and export gates.

## Suggested order of any later implementation

The changes should be staged so their effects can be measured rather than
bundled:

1. Add consistency tests and latency/first-attempt telemetry without changing
   acceptance.
2. Run the current seed to establish per-axis first-attempt and repaired-yield
   baselines.
3. Simplify only `generation_strategy.json` and compare against that baseline.
4. Reduce and generalize grounding patterns, then rerun the same comparison.
5. Separate meta first-attempt scoring from production repair.
6. Only then simplify comparator or rubric machinery, using observed score
   distributions to justify thresholds.

This ordering preserves interpretability: if quality changes, the experiment
can identify whether the cause was the prompt seed, grounding distribution,
repair policy, or judging policy.

## Current recommendation

Do not weaken the target-aware or independent-judge gates. Do not let grounding
change inside a candidate comparison. Do simplify the baseline strategy and
make repair an explicit, separately measured policy.

The single highest-value change is to measure first-attempt performance before
repair. The single clearest bias reduction is to replace the axis-specific v7
elicitation playbook with a compact generic seed. Together, those changes would
give the AAR researcher a genuine starting point to improve while preserving
the experiment's safety and validity.
