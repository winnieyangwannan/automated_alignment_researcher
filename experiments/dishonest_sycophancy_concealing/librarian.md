# Librarian setup and incremental extension

## Working FAIR setup

Use the authenticated Meta Claude CLI with FAIR secure-internet mode and
`claude-sonnet-4-6`. The search helper must be called with its absolute path and
the `search` subcommand:

```text
/storage/home/winnieyangwn/aar-worktrees/uv/scripts/aar-paper-search search '<query>' --limit 1
```

The validated environment uses `/usr/local/bin/claude`,
`META_CLAUDE_SECURE_INTERNET_MODE=1`, `permission_mode="dontAsk"`, and only the
constrained Bash helper. Direct host networking is not a substitute: the
working egress path is inside the secure Claude child.

## Three-dimensional survey

The canonical suite is `honesty_sycophancy_concealing_uncertainty`, targeting
one `google/gemma-4-31B-it` checkpoint. Its six required tracks are:

1. General multi-task and multi-objective alignment.
2. Honesty and deception.
3. Sycophancy.
4. Concealing uncertainty, calibration, confidence communication, and abstention.
5. Cross-dimensional transfer, interference, and trade-offs.
6. Joint evaluation, judge reliability, aggregation, and regression checks.

Each track must meet its own minimum; a large survey in one dimension cannot
compensate for a missing dimension or interaction track.

Schema-v2 entries record `track`, `scope`, `dimensions`,
`relevance_by_dimension`, `interaction_evidence`, and `schema_version`, in
addition to reproduction metadata. Reported facts must be separated from
proposed adaptations. Stronger models may appear in cited work, but they may
not author training answers or labels for this experiment.

## Reusing the completed searches

Dimension-specific caches are separate from composition-specific tracks. Set
`LITREVIEW_CACHE_ROOT` to the root above the schema-versioned target-model
cache that contains the completed `honesty/` and `sycophancy/` tracks. The new
manifest is written under
`honesty_sycophancy_concealing_uncertainty/`, while the runner resolves the old
dimension caches from the shared root.

On `fair-cw-use2-1`, the completed two-dimension survey is under:

```text
/storage/home/winnieyangwn/aar-worktrees/multi_dimensional/_runs/litreview
```

Its historical `honesty_sycophancy/manifest.json` records FAIR job `1662185`
and 41 unique valid papers. Do not copy those entries into the new suite
directory and do not rerun the honesty or sycophancy dimension tracks.

For the new run, the runner reuses:

```text
<cache-root>/schema-v2/google__gemma-4-31B-it/dimensions/honesty/
<cache-root>/schema-v2/google__gemma-4-31B-it/dimensions/sycophancy/
```

It creates or refreshes:

```text
<cache-root>/schema-v2/google__gemma-4-31B-it/dimensions/concealing_uncertainty/
<cache-root>/schema-v2/google__gemma-4-31B-it/compositions/honesty__sycophancy__concealing_uncertainty/general/
<cache-root>/schema-v2/google__gemma-4-31B-it/compositions/honesty__sycophancy__concealing_uncertainty/cross-dimensional/
<cache-root>/schema-v2/google__gemma-4-31B-it/compositions/honesty__sycophancy__concealing_uncertainty/evaluation/
<cache-root>/honesty_sycophancy_concealing_uncertainty/manifest.json
```

The composition-specific tracks are rerun because their prompts now cover
three-way transfer, interference, calibration, abstention, and joint scoring.

## Launch

After synchronizing the committed code to the HPC `uv` worktree, export the
existing cache root before submitting:

```bash
cd /storage/home/winnieyangwn/aar-worktrees/uv
source .venv/bin/activate
export PYTHONPATH="$PWD"
export AAR_BENCHMARK_DOCS="$PWD/benchmark_docs"
export BENCHMARK_DOCS_DIR="$PWD/benchmark_docs"
export LITREVIEW_CACHE_ROOT=/storage/home/winnieyangwn/aar-worktrees/multi_dimensional/_runs/litreview
export LIT_AXIS_DIR="$LITREVIEW_CACHE_ROOT/honesty_sycophancy_concealing_uncertainty"
export LITREVIEW_DIMENSIONS=honesty,sycophancy,concealing_uncertainty
export LITREVIEW_TARGET_MODEL=google/gemma-4-31B-it
sbatch --export=ALL scripts/litreview.sh \
  honesty_sycophancy_concealing_uncertainty \
  honesty-sycophancy-concealing-gemma4-31b-v0 \
  36
```

The launch is ready only when the new manifest is complete, prompt and schema
versions match, every track meets its minimum, and the unique total satisfies
`LITREVIEW_MIN=36`.

## AAR consumption

`get_literature` can filter by `dimension` and `scope`. Before brainstorming,
the AAR prompt requires reads for honesty, sycophancy,
`concealing_uncertainty`, and cross-dimensional evidence. Entries are
deduplicated by source across tracks and versions. Held-out benchmark identities
and data never enter the librarian forum.

## Known failure signatures

- Command without `search`: prompt/helper contract is underspecified.
- `curl: (6) Could not resolve host`: the helper ran outside secure-internet mode.
- Zero entries with no error: the caller ignored a failed `AgentResult`.
- Repeated 429/timeouts: use the bounded helper backoff and public-paper cache.
- A new honesty or sycophancy job: `LITREVIEW_CACHE_ROOT` or manifest compatibility
  was not configured correctly; stop before duplicating work.
