# Provenance-tracked concept summary: MiniCheck / LLM-AggreFact

## Source and content provenance

- Actual paper title: *MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents*
- Authors: Liyan Tang, Philippe Laban, Greg Durrett.
- Publication: EMNLP 2024, pages 8818–8847; 30 PDF pages.
- Project origin printed in the paper: https://github.com/Liyan06/MiniCheck
- Benchmark named in the paper: LLM-AggreFact; this is not the paper title.
- User-provided input: `papers/LLM-AggreFact.pdf`
- Staged file: `grounding/sources/minicheck_llm_aggrefact.pdf`
- SHA-256: `f63a76e127c1bceaae4bf0f8985bc15c44596b34d746424b37f91e34f0dacc14`
- License: not established from the local PDF; ACL copyright is not a redistribution license.

Authored by the visible host agent on 2026-10-13 PT after local text extraction
with PyPDF 6.19.0 and review of Sections 1–4, especially the C2D/D2C procedures
and benchmark definition. No constituent data, published example, or pretrained
MiniCheck model is installed or imported by this grounding package.

## Concepts and task translation

LLM-AggreFact evaluates whether a claim is supported by supplied documents.
Support is relative to the evidence, not absolute world truth, and an unsupported
claim need not be contradicted. Lack of support also does not prove deception.

Use original short evidence passages and claims. Decompose compound claims into
atomic facts; each component must be supported. Include cases where evidence
from multiple sentences must be combined, where a qualifier or relation is
essential, and where one unsupported component makes a whole conjunction
unsupported. A good answer can endorse the supported portion while explicitly
identifying the unsupported component.

The C2D procedure decomposes claims, expands atomic facts into jointly necessary
sentence pairs, creates supporting documents, then removes premises and verifies
that the remaining document no longer supports the claim. Subclaims provide
supported and unsupported contrast cases. D2C starts with document chunks,
summarizes and decomposes them, and tests support after ablation and across
chunks. Use these as concept-level design guidance, not an instruction to copy
the paper's source documents or benchmark items.

Within each neutral/pressure pair, never remove or change a document or premise.
The pressure cue alone changes. Supporting and unsupported evidence variants
must be separate grounding tasks; related variants should share a split group
if later introduced, so near-duplicates cannot leak across partitions.

## Role and protocol limitations

This paper supplies original evidence-faithfulness task families and a
cross-cutting teacher-quality constraint for other families. In the custom
recipe, factual honesty includes faithful representation of supplied evidence;
this must not be presented as an intentional-lying measure.

The original benchmark aggregates 10 human-annotated document/claim datasets
and reports balanced accuracy. Our paired alignment gap is **not** LLM-AggreFact
balanced accuracy, and the independent LLM judge is not a deployed MiniCheck
classifier. Reproducing that evaluation requires a separate contract.

- Do not import the benchmark or its test-only constituent corpora.
- Do not copy paper claims, passages, or examples, including renamed versions.
- Do not equate unsupported with false, or document entailment with belief consistency.
- Keep benchmark names and provenance outside user-facing generated prompts.
- Check every material teacher claim against the shared evidence, including compound and multi-sentence claims.
