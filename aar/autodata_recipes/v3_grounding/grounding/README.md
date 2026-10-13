# Multi-benchmark grounding proposal for v3

Updated 2026-10-13 PT. This grounding review supersedes the single-paper coverage
description in the recipe's existing README. **Not ready for execution:** the
expanded grounding needs user approval, then the sycophancy-only pipeline needs
the revision described in [pipeline_revision_plan.md](pipeline_revision_plan.md).
No model calls or training have run on this proposal.

## Sources and roles

Four user-provided PDFs are staged independently, each with a provenance-tracked
concept summary. [source_registry.json](source_registry.json) pins all eight
files with SHA-256 hashes. Unknown licenses remain null, not inferred permissions
to redistribute the PDFs.

- SycophancyEval paper: four sycophancy families.
- MASK: three project-authored truthful-reporting families and a shared
  pressure-design constraint. No omission coverage is attributed to MASK.
- AbstentionBench: six uncertainty scenarios plus answerable controls against
  over-abstention.
- MiniCheck paper introducing LLM-AggreFact: two evidence-faithfulness families
  and a shared teacher-evidence-quality constraint.

The registry is explicit: adding a PDF to `papers/` does not silently add it to
an execution. The builder accepts only reviewed, staged, hash-pinned sources.
Summaries identify paper versions, origin, extraction provenance, concepts,
translation rules, exclusions, and protocol limitations.

## Coverage and tasks

[coverage.json](coverage.json) declares three axes and 16 families. Each family
crosses six domains and two difficulty levels:

- Sycophancy resistance: 48 atomic pairs, `syco-p001`–`syco-p048`.
- Factual honesty / evidence faithfulness: 60 pairs, `honesty-p001`–`honesty-p060`.
- Uncertainty calibration: 84 pairs, `uncertainty-p001`–`uncertainty-p084`.
  This includes 72 evidence-limited cases and 12 fully answerable controls.

[manifest.json](manifest.json) is the canonical `autodata.grounding/v1` manifest:
192 original abstract task specifications, not copied benchmark questions or
already-generated SFT examples. Each task includes both neutral and pressure
conditions, one shared seed, answerability, primary axis, source-specific concept
guidance, and exact source IDs/digests. Source roles distinguish the primary
taxonomy from shared design constraints; a shared citation does not turn every
task into an example of that benchmark.

The original 48 sycophancy IDs and seeds are retained, but their payloads and
source references have changed. This is a new grounding revision, not something
that may replace the corpus within an existing meta-optimization execution.

The challenger receives the task payload, including compact source guidance.
It does **not** automatically receive the full PDFs. It invents one original
scenario and teacher answer; trusted code composes both prompts from identical
facts, history, request, and evidence boundaries. Only pressure changes. For
uncertainty cases, neutral success can mean a useful clarification, correction,
conditional answer, or explicit uncertainty. Pressure must never supply the
missing evidence. Answerable controls instead require an answer and can test
pressure-induced over-abstention.

## What is not claimed

The proposed per-axis neutral/pressure gap is a custom training challenge signal.
It is not MASK's belief-consistency-based P(Lie), AbstentionBench precision,
recall or F1, or LLM-AggreFact balanced accuracy. Document support is not the
same as world truth or intention to deceive. The papers' released and held-out
datasets are not imported, and exact or closely paraphrased examples are excluded.
These exclusions reduce contamination risk; they do not prove absence of overlap
with every inaccessible benchmark item.

## Review samples and validation

Three proposed model-backed dry-run task IDs cover all three axes:

- `syco-p024`: layered unsupported challenge, workplace review; re-check a
  correct shared earlier answer without changing it to appease pressure.
- `honesty-p001`: direct provided-fact misstatement, everyday planning; report
  the supplied result truthfully despite a consequence-bearing incentive.
- `uncertainty-p025`: direct stale-evidence case, everyday planning; retain an
  explicit snapshot boundary rather than claim a later unsupported value.

These are reviewed **specifications**, not live model outputs. Approval of
grounding is followed by pipeline authoring, checks, real sample evidence,
and the separate baseline approval before any execution is frozen.

From the recipe root, run the grounding-only checks:

```bash
python3 grounding/build_manifest.py --check
python3 grounding/test_grounding.py
```

The existing full-recipe check is expected to reject the new axes until the
approved pipeline revision is implemented; do not bypass it to launch a run.

## Adding another paper later

1. Start a new authoring revision; for a frozen workspace, use `workspace fork
   --edit grounding` or `--edit both` into a new draft. Do not edit its snapshot.
2. Stage the PDF and a reviewed concept summary under `grounding/sources/`.
3. Add separate source entries with pinned hashes and a summary `derived_from`
   reference. Register only origins verified from the provided paper.
4. Merge relevant concepts into the shared coverage plan, map each family to
   its actual contributing paper/summary, and identify cross-cutting roles.
   Do not duplicate tasks merely because two papers describe overlapping concepts.
5. Regenerate the manifest, validate references/hashes/coverage, and propose
   one to three representative samples. Review scope gaps and protocol differences.
6. Obtain explicit new grounding approval. Revise the pipeline if any new axis,
   label, answerability mode, scorer, or judge contract is required.

During meta-optimization keep sources, summaries, coverage, task IDs/payloads,
partitions, seeds, scoring, schemas, comparator, and protected code fixed.
Only declared mutable pipeline paths may change. Reused hidden validation is
selection evidence, not an untouched scientific test estimate.

## Authoring record

The expanded draft workspace is `ws_5266db2d4b4b498c9972bb08c2767797`, in study
`study_1432b0cbb9c8bfb666cfcef36ed424f2`. The superseded, idle single-paper
workspace `ws_ad3a4658efcb4cd188c0afe1b170d939` was cancelled; its recorded
revisions remain preserved. It had no execution and no task attempts. Resume
the expanded workspace with the same AutoData state/artifact/workspace paths.
