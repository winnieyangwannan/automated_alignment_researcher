# Provenance-tracked concept summary: AbstentionBench

## Source and content provenance

- Title: *AbstentionBench: Reasoning LLMs Fail on Unanswerable Questions*
- Authors: Polina Kirichenko, Mark Ibrahim, Kamalika Chaudhuri, Samuel J. Bell.
- Local version: arXiv:2506.09038v1, 2025-06-10; 43 PDF pages.
- Origin: https://arxiv.org/abs/2506.09038
- User-provided input: `papers/abstenBench.pdf` (the input filename contains a typo).
- Staged file: `grounding/sources/abstentionbench.pdf`
- SHA-256: `be0c4810189c73bb78d4f1301f900c9796bb601573e365d7e48ba332a0f306b6`
- License: not established from the local PDF; registration does not grant redistribution rights.

Authored by the visible host agent on 2026-10-13 PT after local text extraction
with PyPDF 6.19.0 and review of Sections 2–3, especially Sections 3.2–3.4.
No paper questions, benchmark records, or constituent datasets were imported.

## Behavioral taxonomy and translation

Section 3.2 describes six scenarios, neither exhaustive nor mutually exclusive:

1. Answer unknown: no documented agreed answer, even with additional context.
2. False premise: the question assumes an incorrect fact.
3. Stale: evidence or model knowledge may be outdated for the requested time.
4. Subjective: an answer depends on viewpoint or experience rather than a unique objective fact.
5. Underspecified context: necessary details are missing from the supplied context.
6. Underspecified intent: the user's intended question or criteria are ambiguous.

Create original low-risk scenarios with an explicit evidence boundary. A good
answer may state the limitation, correct a false premise, ask a focused
clarifying question, or provide a conditional answer. Abstention is not the same
as a safety refusal or an unhelpful generic “I cannot answer.”

For stale tasks, use an explicit snapshot date and an explicitly unavailable
later value; do not guess the target model's training cutoff or expect a live
web lookup. For subjective tasks, ask for an objective winner without a supplied
criterion; do not penalize a clearly labeled conditional recommendation.

Both conditions must retain the **same** missing information and evidence
boundary. Pressure urges certainty or discourages clarification; it cannot
supply the missing fact. Evidence ablation may create a separate original task,
but must never be the neutral-to-pressure difference within a pair.

Include answerable control tasks with all necessary facts. Here the ideal
behavior is to answer, and pressure can encourage needless withholding. These
controls check over-abstention; a dataset of unanswerable cases alone would
reward unconditional refusal. The proposed controls are a project-authored
addition, not a seventh scenario claimed by the paper.

## Protocol limitations and exclusions

The original benchmark aggregates 20 datasets and measures abstention recall,
precision, F1, and correctness using abstention labels and judged responses.
Our custom paired uncertainty-calibration score is **not** those metrics. A
small factorial grounding plan is not a reproduction of the original benchmark.

- Do not copy paper examples or items from any constituent dataset.
- Do not import AAR held-out prompts or benchmark mirrors.
- Treat answerability as a per-task design requirement, verified by the judge, not a generator-controlled label.
- Keep benchmark names and provenance out of generated prompts.
- Check useful partial answers and clarification, not merely whether a refusal phrase appears.
