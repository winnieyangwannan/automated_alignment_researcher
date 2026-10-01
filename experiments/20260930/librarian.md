# Librarian: Working FAIR Setup and Lessons

Date: 2026-09-30

## BLUF

Use the authenticated Meta Claude CLI with FAIR secure-internet mode. Use
`claude-sonnet-4-6`. Give Claude the absolute helper path and the complete
command to copy. Do not rely on Claude to infer the helper syntax.

The failed smoke was not a model-access or API-key problem. Claude Sonnet 4.6
was available. The prompt only named the helper, so Claude invented this invalid
command:

```text
aar-paper-search --limit 1 'sycophancy language models'
```

The helper requires the `search` subcommand and an absolute path:

```text
/storage/home/winnieyangwn/aar-worktrees/uv/scripts/aar-paper-search search 'sycophancy language models' --limit 1
```

With that exact command in the prompt, the smoke succeeded and returned a real
paper and arXiv ID.

## Verified environment

- Host: `fair-cw-use2-1`.
- Execution checkout: `/storage/home/winnieyangwn/aar-worktrees/uv`.
- Branch during verification: `uv`.
- Claude CLI: `/usr/local/bin/claude`, version `2.1.281` on the HPC node.
- Claude Agent SDK: `0.2.157`.
- Model: `claude-sonnet-4-6`.
- Authentication: the Meta Claude CLI. No direct `ANTHROPIC_API_KEY` was needed.
- Network: `META_CLAUDE_SECURE_INTERNET_MODE=1`.

The successful smoke reported `claude-sonnet-4-6` as the canonical model. It
used the Anthropic upstream through the Meta launcher.

## What worked

Use all of these controls together:

1. Set `cli_path=/usr/local/bin/claude`.
2. Set `model=claude-sonnet-4-6`.
3. Set `META_CLAUDE_SECURE_INTERNET_MODE=1`.
4. Use `permission_mode="dontAsk"`.
5. Set built-in `tools=["Bash"]`.
6. Set `setting_sources=[]` and `strict_mcp_config=True`.
7. Allow only `Bash(<absolute-helper-path> search *)` for the search smoke.
8. Put the exact absolute command, including `search` and `--limit`, in the
   prompt.
9. Shell-quote the query before inserting it into the command.
10. Remove unrelated credentials from the secure-internet child.

The repository's full librarian prompt already includes the absolute helper
path and valid `search` and `fetch` forms. A one-agent diagnostic used that path
and wrote one valid structured entry through `share_literature`.

## Why an MCP search tool was not used

The host process did not have reliable direct arXiv access. A direct helper call
outside the secure Claude child failed DNS on the devserver and did not finish
within 30 seconds on the HPC login node.

An in-process MCP wrapper would run the network request in the Python host, not
in Claude's secure-internet sandbox. It would therefore lose the working egress
path. Keep search and fetch behind the constrained Bash helper until a typed MCP
tool has an explicitly verified network route.

## Code changes

- `scripts/smoke_secure_paper_search.py` now gives Claude the exact absolute
  command. It also mirrors the librarian's restricted tool configuration.
- `aar/litreview/run_litreview.py` now reports a failed `AgentResult`. Previously
  it silently ignored that failure and only showed a zero-entry count.
- `tests/test_litreview_launch.py` now covers failed-result reporting.

## Verification evidence

The original smoke reached Claude but failed locally after Claude emitted the
wrong command. The corrected direct contract returned:

```text
Title: From Yes-Men to Truth-Tellers: Addressing Sycophancy in Large Language Models with Pinpoint Tuning
arXiv ID: 2409.01658v3
```

The real librarian diagnostic then wrote a structured `Supervised Pinpoint
Tuning (SPT) for Sycophancy Reduction` entry to a disposable forum. This proves
that Claude authentication, secure arXiv access, and `share_literature` all work
together.

The diagnostic was stopped at five minutes after the entry had been written.
It did not prove that a full 30-entry survey finishes within the current
two-hour Slurm limit. Treat runtime sizing as a separate unresolved issue.

Local deterministic validation passed:

```text
python3 -m unittest tests.test_litreview_launch tests.test_paper_search
28 tests passed
```

## Failure signatures

- Invalid command without `search`: prompt contract is underspecified.
- `curl: (6) Could not resolve host`: helper ran outside secure-internet mode.
- Zero entries with no error: caller ignored `AgentResult.success`.
- `403` from the Llama passthrough: unrelated to this path; the librarian uses
  Claude CLI authentication, not `LLAMA_API_KEY`.
- `404 model_not_found` from Model API: unrelated to this path; the librarian
  does not use `MODEL_API_KEY` in `meta_secure` mode.

## Guidance for a future skill

The skill should:

1. Check the Claude CLI, SDK version, model, and secure-internet flag without
   printing credentials.
2. Run one exact-command search smoke before a full librarian job.
3. Validate the observed tool name and full command.
4. Require a real arXiv ID in the final response.
5. Run one disposable `share_literature` check when MCP behavior changes.
6. Keep host-network failure distinct from Claude secure-network failure.
7. Report the first failing boundary: authentication, tool authorization,
   helper syntax, network, parsing, or forum write.
8. Never copy environments between the x86 devserver and ARM64 HPC cluster.

## Multi-dimensional literature search

### BLUF

The original prompt cannot be reused unchanged. It assumes one `{axis}` and a
small ~3B target. Passing `honesty_sycophancy` as that axis would produce an
ambiguous search and would not force coverage of both properties or their
interaction.

The multi-dimensional prompt now tells the librarian to prepare research for
one `google/gemma-4-31B-it` checkpoint that improves honesty and sycophancy
together while preserving capability. It explicitly says not to assume that an
improvement transfers across dimensions.

### Search tracks

The composed survey has five required tracks:

1. General multi-task and multi-objective alignment methods.
2. Honesty and deception methods, mechanisms, data, and public evaluations.
3. Sycophancy methods, mechanisms, data, and public evaluations.
4. Cross-dimensional transfer, interference, and trade-offs.
5. Joint evaluation, judge reliability, aggregation, and regression checks.

Each track must meet its own minimum. A large honesty survey cannot compensate
for missing sycophancy or interaction coverage.

### Entry contract

Schema-v2 entries add:

- `track` and `scope`.
- `dimensions` directly addressed by the source.
- `relevance_by_dimension`.
- `interaction_evidence`: positive transfer, interference/trade-off, or not
  studied.
- `schema_version`.

The reproduction fields from the original prompt remain. The librarian must
separate reported facts from proposed adaptation. It may describe papers that
used stronger teachers, but it must not recommend stronger-model-authored
training answers or labels for this experiment. Held-out benchmark identities
and data remain unavailable.

### Storage and launch behavior

Dimension-specific caches are stored separately from composition-specific
tracks. This lets a future composed suite reuse a compatible honesty or
sycophancy cache. A suite manifest lists its exact track directories, target
model, schema version, prompt version, minima, counts, and completion state.

The launcher accepts a composed cache only when:

- the manifest is marked complete;
- its prompt and schema versions match;
- every track contains enough valid entries; and
- the unique total meets `LITREVIEW_MIN`.

The AAR prompt now requires dimension-filtered literature reads before
brainstorming. It asks the researcher to compare honesty, sycophancy, and
cross-dimensional evidence before proposing one joint checkpoint.

### Other implementation changes

- `get_literature` can filter by `dimension` and `scope`.
- `share_literature` records dimension metadata and rejects incomplete v2
  entries.
- The same arXiv paper is deduplicated across tracks and versions.
- Existing single-axis directories and prompts remain supported.
- The restricted helper, Sonnet 4.6, and secure-internet boundary are unchanged.

### Remaining validation

A live five-track survey has not run yet. The complete AAR cannot launch until
the broader multi-dimensional suite, baselines, scoring, and evaluator changes
in `multi_dimensional_refactor_plan.md` are implemented. The exact benchmark
roster also remains an explicit decision; it must not be inferred by the
librarian or exposed through held-out metadata.
