# Run 14 recipe comparison setup

Recorded: 2026-10-13 00:44 PT. Branch: `autodata`.

## Request and decision

Set up Run 14 exactly like Run 13 Canary Trial 14, with recipe root
`aar/autodata_recipes/dishonest_sycophancy_concealing`. The stated scientific
intent is stronger v3 grounding versus v2. The two YAML differences are
`run_id` and `recipe_root`; keep Opus 4.8 and all run settings unchanged.

The supplied directory currently holds the older synthetic recipe. A pending
clarification offers `v3_grounding`, which contains the paper-grounded work but
has incompatible rubric/builder contracts and an unfinished expanded pipeline.
Honor the exact supplied path in the reviewable YAML and disclose the mismatch;
do not claim a completed v3 comparison or silently change recipe contents.

## Source and validation

- Devserver: `/home/winnieyangwn/aar-worktrees/autodata`.
- Setup HEAD: `e17ab31781fc67edfaa8d19b160296340378cd13`.
- Skills: `organize-aar-experiment`; `git-sync-from-dev-to-hpc` for destination
  preflight and the eventual transfer workflow.
- Strict YAML loading, unchanged profile, offline compilation/artifact
  validation and native recipe staging passed.
- Focused pytest: 14 passed; shell syntax/ShellCheck error checks: six files;
  focused Ruff: passed.
- Unrelated v3 work, PDFs/papers, figures and the untracked `1864603` remain
  unstaged. No Run 14 model calls, job submission, cancellation or resume.

## HPC synchronization

Destination: `fair-cw-use2-1`,
`/storage/home/winnieyangwn/aar-worktrees/autodata`, branch `autodata`,
pre-transfer HEAD `9fefddeb81367b3f5a8c63ad5c2717322422e9cd`.
The origin identity matches the devserver repository.

Synchronization is deferred by the organization skill's active-checkout rule:
training jobs `1865857` and `1865841` use this checkout directly. Preserve
HPC-local ignored state and untracked `.aar-method-contract.json` and `output/`.
No transfer was attempted and no temporary ref was created.

When the checkout is safe to advance, use direct Git-over-SSH, require a
fast-forward to the captured setup commit, check incoming tracked paths against
all ignored/untracked state, and run the push through `with-proxy`. No GitHub
push is requested. Explicit model-role confirmation is required before launch.
