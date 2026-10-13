# Sycophancy grounding v3

This directory is an AutoData authoring workspace for grounding a future AAR
alignment recipe in the behavioral taxonomy from *Towards Understanding
Sycophancy in Language Models* (Sharma et al., ICLR 2024; arXiv:2310.13548).

The grounding design uses matched neutral and pressure conditions. Each pair
keeps the underlying scenario, facts, task, and expected truth-preserving
behavior fixed; only the social or preference pressure changes. This supports
measuring challenge as the target model's behavioral gap between the two
conditions.

The paper is evidence for the behavior taxonomy, not a pool of prompts to copy.
Exact paper examples, benchmark questions, dataset items, and held-out AAR
evaluation content are excluded. The manifest contains original abstract
scenario specifications from which a later pipeline can generate original
examples.

## Authoring state

- Grounding source and provenance: staged under `grounding/sources/`.
- Coverage plan: `grounding/coverage.json`.
- Canonical AutoData manifest: `grounding/manifest.json`.
- Reproducible manifest builder and checks: `grounding/build_manifest.py`.
- Grounding approval: intentionally pending explicit user review.

Rebuild and validate the manifest from this directory with:

```bash
python3 grounding/build_manifest.py --output grounding/manifest.json
```

Approval of this grounding does not approve or create a pipeline. Pipeline
code, objectives, comparator thresholds, judge rubrics, and mutable boundaries
belong to the later `author_pipeline` stage and must treat the approved
grounding as read-only.
