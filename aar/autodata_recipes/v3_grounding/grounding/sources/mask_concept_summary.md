# Provenance-tracked concept summary: MASK

## Source and content provenance

- Title: *The MASK Benchmark: Disentangling Honesty From Accuracy in AI Systems*
- Authors: Richard Ren, Arunim Agarwal, Mantas Mazeika, et al.
- Local version: arXiv:2503.03750v3, 2026-01-05; 22 PDF pages.
- Origin: https://arxiv.org/abs/2503.03750
- User-provided input: `papers/MASK.pdf` in the selected AAR worktree.
- Staged file: `grounding/sources/mask.pdf`
- SHA-256: `38afe4bbff086bf9906b7135f84e9c1a1c94d7c3538f671f24a9caa13a2e289a`
- License: not established from the local PDF; registration does not grant redistribution rights.

Authored by the visible host agent on 2026-10-13 PT after local text extraction
with PyPDF 6.19.0 and review of Sections 3–4, especially the definition,
dataset-design principles, and belief-elicitation methodology. This summary
abstracts concepts; it does not import prompts, propositions, answers, or records.

## Concepts and original-task translation

MASK distinguishes statement S, neutral belief B, and ground truth T. Honesty
concerns whether a statement agrees with a consistently elicited belief;
accuracy concerns whether that belief agrees with ground truth. An inaccurate
answer is not automatically a lie, and a neutral/pressure disagreement alone
does not establish intention to deceive.

Use original, verifiable provided facts to create incentives for an explicit
false statement: misstate a documented result, distort a statistic, or make a
misleading statement intended for an audience. These are project-authored
families inspired by the paper's design principles, not its complete six-archetype
taxonomy. Prefer plausible contexts and consequence-bearing pressure to silly
roleplay. Keep pressure informationally irrelevant: it must not claim that new
evidence changes the correct answer. Preserve numbers, denominators, qualifiers,
and truth conditions in the teacher answer.

The paper focuses on **lies of commission**. It explicitly does not measure
deception by omission. Do not attribute omission/concealing coverage to MASK.

## Original protocol versus this recipe

The published evaluation obtains three direct neutral belief probes; binary
propositions also receive two indirect probes. It checks consistency, extracts
proposition resolutions, and compares S, B, and T. Unclear or evaded beliefs
must be distinguished from lying.

The proposed v3 grounding instead specifies one matched neutral/pressure pair
with fixed evidence and a pressure-degradation score. It can train truthful
behavior under pressure, but is **not MASK P(Lie)**, a belief-consistency test,
or proof of intentional deception. Implementing MASK's protocol requires a
separate approved contract and scorer, not simply a new source ID.

## Exclusions and limitations

- Do not copy or closely paraphrase paper examples, public MASK items, or held-out items.
- Do not import external benchmark datasets or AAR evaluation material.
- Keep benchmark names, citations, and provenance outside user-facing generated prompts.
- Synthetic consequence-bearing scenarios still may not induce the same behavior as human-authored MASK prompts.
- Require neutral competence and an independently verified teacher answer; pressure-only factual degradation is a custom proxy, not the published lying metric.
