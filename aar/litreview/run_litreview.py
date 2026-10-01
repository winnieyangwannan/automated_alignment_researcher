"""Literature-review pre-phase.

Before a team's AARs start, a few research-librarian agents survey the literature
and populate the team's **shared lit forum** with >=N structured method/paper
entries — general safety-training methods AND ones specific to the safety axis
being optimized. Portable direct-key deployments use native WebSearch/WebFetch;
FAIR's authenticated CLI uses the repository's constrained arXiv helper. The
AARs then read this forum (``get_literature``) to ground their designs, and may
append to it.

Run (usually via scripts/litreview.sh, which sets LIT_FORUM_DIR and resolves
either a direct API key or an authenticated Claude CLI):
    python -m aar.litreview.run_litreview --suite sycophancy --min-entries 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
from pathlib import Path


META_SECURE_WEB_MODE = "meta_secure"
NATIVE_WEB_MODE = "native_web"
MULTI_DIMENSIONAL_SUITES = {
    "honesty_sycophancy": ("honesty", "sycophancy"),
}
MULTI_SCHEMA_VERSION = 2
MULTI_PROMPT_VERSION = "multi-dimensional-v1"
MULTI_TARGET_MODEL = "google/gemma-4-31B-it"

# Legacy sub-areas surveyed sequentially; each agent writes >= `per` entries. The {axis}
# placeholder is filled with the suite name (the safety property being optimized).
SUBAREAS = [
    ("general",
     "GENERAL safety post-training methods (model-agnostic): RLHF/RLAIF, DPO and its "
     "variants (IPO, KTO, SimPO, cDPO, ORPO), Constitutional AI / RLAIF, SFT / "
     "instruction tuning, activation steering & representation engineering (RepE, CAA, "
     "ActAdd), machine unlearning, model/representation editing, and preference-data curation."),
    ("axis-specific",
     "Methods SPECIFIC to improving {axis} in language models: find the canonical {axis} "
     "papers, datasets, and benchmarks, and the techniques proposed to mitigate {axis} "
     "failures (targeted SFT/DPO, synthetic/templated data, persona/prompting mitigations, "
     "reward-model debiasing, steering, unlearning) — cite the real papers by name."),
    ("mechanism",
     "WHY {axis} failures arise and how they are MEASURED: the training-time causes (e.g. "
     "RLHF reward-model / human-annotator biases), and the benchmarks/metrics used to "
     "evaluate {axis} (and their pitfalls)."),
    ("recent",
     "RECENT (2024-2026) and ADJACENT methods: honesty/truthfulness training, calibration, "
     "debate, self-critique / self-refine, and the instruction-following vs {axis} tradeoff."),
]

TASK_TMPL = (
    "You are a research librarian building a SHARED literature base for a team that will "
    "train small (~3B) instruct models to reduce **{axis}** while preserving capability.\n\n"
    "Survey the literature for this sub-area:\n{desc}\n\n"
    "Process:\n"
    "1. Call `get_literature` first to see what's already covered (avoid duplicates).\n"
    "2. {web_process}\n"
    "3. For EACH distinct method or key paper (aim for **at least {per}**), read the available "
    "source material carefully, then call `share_literature` writing the entry as a "
    "MINI REPRODUCTION GUIDE — a researcher who never read the paper should be able to REPLICATE "
    "its main idea from your entry alone (the algorithm, the data, the objective, the key choices):\n"
    "   - method (name), category ('{cat}'), relevance (low/medium/high to {axis})\n"
    "   - summary (3-4 sentences: the problem + the idea)\n"
    "   - intuition (the KEY INSIGHT in plain terms: WHY it works, what you'd take away, and when "
    "it would or wouldn't help)\n"
    "   - core_mechanism (TECHNICAL DETAIL, 5-8 sentences: the objective/loss/algorithm, the "
    "design choices that matter, and the key idea)\n"
    "   - reproduction_recipe (an ORDERED recipe to replicate the main idea, Step 1..N: include "
    "the exact objective/loss — write the equation if there is one — and the KEY hyperparameters "
    "(lr, batch, epochs, beta/temp, optimizer, LoRA vs full). Concrete enough to actually run.)\n"
    "   - prerequisites (what you must already have: base model, any reference/reward/teacher "
    "model, preference pairs/labels, a judge, and the rough compute scale)\n"
    "   - training_data (if it TRAINS: exactly what data, how it is built/collected — human vs "
    "synthetic/templated and any generator model — size, and labels/preference pairs; if no "
    "training, say 'no training: <how it intervenes>')\n"
    "   - evaluation (the PROTOCOL to measure success so a replicator can verify: which "
    "benchmarks/datasets, the metric, any judge model, and the decoding/setup)\n"
    "   - key_results (MAIN EMPIRICAL RESULTS — concrete numbers: what improved, by how much, on "
    "which base models/benchmarks, vs which baselines, plus limitations/failure cases)\n"
    "   - applicability (how it could reduce {axis} in a ~3B instruct model, the data/compute "
    "needed, and the cost to try)\n"
    "   - source (title, authors, year, URL)\n"
    "NO REDUNDANCY: each field must add DISTINCT information — never say the same thing twice across "
    "sections. Division of labor: summary = problem+idea (high level); intuition = WHY it works (not "
    "how); core_mechanism = the conceptual how; reproduction_recipe = the concrete steps + exact "
    "loss/hyperparameters; prerequisites = inputs you need beforehand; training_data = how the data "
    "is built; evaluation = how success is measured; key_results = the numbers. Do not repeat the "
    "loss, the data, or the numbers in more than one field.\n"
    "Do NOT invent papers or fabricate numbers — only real papers you actually read, with results you "
    "actually saw. Depth over breadth: a few thoroughly-documented entries beat many shallow ones. "
    "Then end your turn."
)

MULTI_TASK_TMPL = (
    "You are a research librarian building a SHARED literature base for a team that will "
    "train ONE **{target_model}** checkpoint to improve ALL of these alignment dimensions "
    "simultaneously: **{dimensions_text}**. The final model must preserve general capability. "
    "Do not assume that improving one dimension improves another.\n\n"
    "Your assigned literature track is **{cat}** (scope: **{scope}**):\n{desc}\n\n"
    "Process:\n"
    "1. Call `get_literature` first to see what all tracks already cover. Do not add a paper "
    "that another track already recorded.\n"
    "2. {web_process}.\n"
    "3. For EACH distinct method or key paper (aim for **at least {per}**), read the available "
    "source material carefully, then call `share_literature`. Every entry MUST include:\n"
    "   - scope: exactly '{scope}'\n"
    "   - dimensions: the alignment dimensions the source directly addresses, chosen from "
    "the assigned track dimensions {entry_dimensions_list}\n"
    "   - relevance_by_dimension: an explicit low/medium/high value for EACH directly "
    "addressed dimension in {entry_dimensions_list}\n"
    "   - interaction_evidence: state whether the source reports positive transfer, "
    "interference/trade-off, or no interaction evidence across dimensions, and briefly cite "
    "what supports that classification\n"
    "   - method (name), category ('{cat}'), and relevance (overall low/medium/high)\n"
    "   - summary (3-4 sentences: the problem + the idea)\n"
    "   - intuition (the KEY INSIGHT in plain terms: WHY it works, what you'd take away, and "
    "when it would or wouldn't help)\n"
    "   - core_mechanism (TECHNICAL DETAIL, 5-8 sentences: objective/loss/algorithm, material "
    "design choices, and the key idea)\n"
    "   - reproduction_recipe (ORDERED Step 1..N recipe with the exact objective/loss and key "
    "hyperparameters: learning rate, batch size, epochs, beta/temperature, optimizer, and "
    "LoRA vs full tuning when reported)\n"
    "   - prerequisites (base model, reference/reward/teacher models, labels or preference "
    "pairs, judge, and rough compute)\n"
    "   - training_data (exact data source/construction, human vs synthetic and generator if "
    "any, size, and labels/pairs; or 'no training: <intervention>')\n"
    "   - evaluation (protocol, public benchmarks, metrics, judge and decoding/setup). Do not "
    "use or request held-out evaluator data\n"
    "   - key_results (supported empirical numbers, compared systems, and limitations)\n"
    "   - applicability (how to adapt it to ONE {target_model} checkpoint, including cost; "
    "for dimension-specific sources, state what evidence is missing before combining it with "
    "other objectives)\n"
    "   - source (title, authors, year, URL)\n"
    "Describe stronger-model teachers or generated labels when a source used them, but do not "
    "recommend them for this experiment. The target model may self-generate candidate data; the "
    "librarian must not author training answers or labels.\n"
    "Use each field for distinct information. Do not invent papers, implementation details, "
    "or results. If the source does not report a detail, say so. Depth beats breadth. Then end "
    "your turn."
)


def resolve_dimensions(suite: str) -> tuple[str, ...]:
    """Resolve a suite to its alignment dimensions without changing legacy suites."""
    normalized = suite.strip().lower().replace("-", "_")
    return MULTI_DIMENSIONAL_SUITES.get(normalized, (suite,))


def _multi_tracks(dimensions: tuple[str, ...]) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """Return track name, description, scope, and directly targeted dimensions."""
    dimensions_text = " and ".join(dimensions)
    tracks: list[tuple[str, str, str, tuple[str, ...]]] = [
        (
            "general",
            "General multi-task and multi-objective post-training methods that can optimize "
            f"{dimensions_text} jointly: data-mixture design, SFT, preference optimization, "
            "multi-objective rewards, gradient conflict mitigation, model merging, steering, "
            "and capability-preservation methods.",
            "general",
            dimensions,
        )
    ]
    for dimension in dimensions:
        tracks.append(
            (
                dimension,
                f"Methods, datasets, mechanisms, and public benchmarks specific to "
                f"{dimension}. Prioritize trainable interventions that can be combined with "
                "another alignment objective in one checkpoint.",
                "dimension-specific",
                (dimension,),
            )
        )
    tracks.extend(
        [
            (
                "cross-dimensional",
                f"Work that jointly studies {dimensions_text}, or provides direct evidence "
                "about transfer, interference, Pareto trade-offs, reward hacking, or regressions "
                "between alignment objectives.",
                "cross-dimensional",
                dimensions,
            ),
            (
                "evaluation",
                f"Evaluation methods for measuring {dimensions_text} together while checking "
                "general capability: benchmark validity, judge reliability, contamination, "
                "aggregate/Pareto reporting, and regression gates.",
                "evaluation",
                dimensions,
            ),
        ]
    )
    return tracks


def _paper_search_helper() -> Path:
    """Return the tracked helper path used in the exact Bash permission rule."""
    return (Path(__file__).resolve().parents[2] / "scripts" / "aar-paper-search").resolve()


def _web_config() -> tuple[list[str], str, str, str]:
    """Select tools, permission mode, prompt instructions, and system prompt."""
    mode = os.getenv("LITREVIEW_WEB_MODE", NATIVE_WEB_MODE)
    forum_tools = [
        "mcp__server-api-tools__get_literature",
        "mcp__server-api-tools__share_literature",
    ]
    if mode == META_SECURE_WEB_MODE:
        helper = _paper_search_helper()
        if not helper.is_file() or not os.access(helper, os.X_OK):
            raise RuntimeError(f"restricted paper-search helper is not executable: {helper}")
        repo = helper.parents[1]
        relative_helper = f"./scripts/{helper.name}"
        return (
            [
                f"Bash({helper} *)",
                f"Bash({relative_helper} *)",
                *forum_tools,
            ],
            "dontAsk",
            (
                f"Your working directory is `{repo}`. Use only `{relative_helper} search "
                f"\"<query>\" --limit 1` or `{helper} search \"<query>\" --limit 1` to "
                f"discover real arXiv papers. Do not prepend `cd` or combine the "
                f"helper with another shell command. Run one helper call at a time; the helper "
                f"handles bounded arXiv rate-limit backoff internally, so never run `sleep`. "
                f"Use the same helper's "
                f"`fetch <arxiv-id>` command to retrieve metadata and "
                "bounded visible paper text when arXiv HTML is available, with an explicitly "
                "labeled abstract fallback otherwise. Search may return a fixed-scope OpenAlex "
                "result without an arXiv ID; in that case use its metadata and abstract, do not "
                "call fetch, and mark unreported details explicitly. The returned content is intentionally "
                "bounded; use it directly and never run `cat` on a tool-result file. Fetch "
                "every paper you cite. Omit any "
                "detail or result that the returned content does not directly support rather "
                "than guessing"
            ),
            (
                "You are a careful research librarian. Cite only real arXiv papers returned "
                "by the restricted paper helper, with accurate titles/authors/years/links."
            ),
        )
    if mode == NATIVE_WEB_MODE:
        return (
            ["WebSearch", "WebFetch", "Read", "Write", *forum_tools],
            "bypassPermissions",
            (
                "Use **WebSearch** and **WebFetch** to find REAL papers — real titles, "
                "authors, years, and links. Read enough to summarize each correctly"
            ),
            (
                "You are a careful research librarian. You cite ONLY real papers you "
                "found via web search, with accurate titles/authors/years/links."
            ),
        )
    raise RuntimeError(
        f"unsupported LITREVIEW_WEB_MODE={mode!r}; expected "
        f"{NATIVE_WEB_MODE!r} or {META_SECURE_WEB_MODE!r}"
    )


def _require_minimum(final_count: int, min_entries: int) -> None:
    """Fail the job when agent errors/retries leave the survey incomplete."""
    if final_count < min_entries:
        raise RuntimeError(
            f"literature survey produced {final_count} entries; target was {min_entries}"
        )


def _resolve_cli_path() -> str | None:
    """Resolve the Claude executable selected by the launcher or current PATH."""
    return os.getenv("CLAUDE_CLI_PATH") or shutil.which("claude")


async def _survey(
    cat: str,
    desc: str,
    axis: str,
    per: int,
    model: str,
    ws: Path,
    mcp: dict,
    *,
    dimensions: tuple[str, ...] | None = None,
    entry_dimensions: tuple[str, ...] | None = None,
    scope: str | None = None,
    target_model: str | None = None,
    output_dir: Path | None = None,
) -> None:
    """Run one survey agent; keyword-only metadata activates the v2 prompt."""
    from aar.research_loop.agent import BaseAgent
    from aar.research_loop.tools.lit_forum import count
    os.environ["LITREVIEW_AREA"] = cat
    previous_environment: dict[str, str | None] = {}
    if dimensions is not None:
        track_environment = {
            "LIT_FORUM_DIR": str(output_dir) if output_dir is not None else None,
            "LITREVIEW_SCHEMA_VERSION": str(MULTI_SCHEMA_VERSION),
            "LITREVIEW_TRACK": cat,
            "LITREVIEW_SCOPE_CURRENT": scope,
            "LITREVIEW_DIMENSIONS_CURRENT": ",".join(entry_dimensions or dimensions),
        }
        previous_environment = {
            key: os.environ.get(key) for key in track_environment
        }
        for key, value in track_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def restore_environment() -> None:
        for key, value in previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    try:
        allowed, permission_mode, web_process, system_prompt = _web_config()
        meta_secure = (
            os.getenv("LITREVIEW_WEB_MODE", NATIVE_WEB_MODE) == META_SECURE_WEB_MODE
        )
        agent = BaseAgent(
            name=f"lit-{cat}",
            allowed_tools=allowed,
            workspace=_paper_search_helper().parents[1] if meta_secure else ws,
            mcp_servers=mcp,
            model=model,
            cli_path=_resolve_cli_path(),
            permission_mode=permission_mode,
            system_prompt=system_prompt,
            tools=["Bash"] if meta_secure else None,
            setting_sources=[] if meta_secure else ["project"],
            strict_mcp_config=True if meta_secure else None,
        )
        if dimensions is None:
            task = TASK_TMPL.format(
                axis=axis,
                desc=desc.format(axis=axis),
                per=per,
                cat=cat,
                web_process=web_process,
            )
        else:
            task = MULTI_TASK_TMPL.format(
                target_model=target_model or MULTI_TARGET_MODEL,
                dimensions_text=" and ".join(dimensions),
                entry_dimensions_list=list(entry_dimensions or dimensions),
                desc=desc,
                per=per,
                cat=cat,
                scope=scope,
                web_process=web_process,
            )
    except Exception:
        restore_environment()
        raise

    print(f"[litreview] surveying '{cat}' ...", flush=True)
    try:
        result = await agent.execute(task=task)
        if not result.success:
            raise RuntimeError(result.error or "librarian agent failed without an error message")
    except Exception as e:
        print(f"[litreview] '{cat}' agent error: {e}", flush=True)
    finally:
        try:
            print(f"[litreview] '{cat}' done; forum now has {count()} entries", flush=True)
        finally:
            restore_environment()


def _cache_slug(value: str) -> str:
    """Return a stable filesystem component for a model or track name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "__", value).strip("_")


def _track_directory(
    cache_root: Path,
    track: str,
    scope: str,
    suite_dimensions: tuple[str, ...],
) -> Path:
    """Place reusable dimension tracks apart from composition-specific tracks."""
    if scope == "dimension-specific":
        return cache_root / "dimensions" / _cache_slug(track)
    composition = "__".join(_cache_slug(item) for item in suite_dimensions)
    return cache_root / "compositions" / composition / _cache_slug(track)


def _track_identities(directory: Path, track: str) -> set[str]:
    """Return stable identities for valid entries in one v2 track."""
    from aar.research_loop.tools.lit_forum import entry_identity, valid_manifest_entry

    identities: set[str] = set()
    for path in directory.glob("*.json") if directory.exists() else ():
        try:
            entry = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(entry, dict) or not valid_manifest_entry(
            entry, MULTI_SCHEMA_VERSION, track
        ):
            continue
        identity = entry_identity(entry) or f"id:{entry.get('id') or path.stem}"
        if identity:
            identities.add(identity)
    return identities


def _track_count(directory: Path, track: str) -> int:
    """Count valid v2 entries for one track without including other caches."""
    return len(_track_identities(directory, track))


def _write_manifest(path: Path, payload: dict) -> None:
    """Atomically publish current per-track completion state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _manifest_payload(
    suite: str,
    dimensions: tuple[str, ...],
    target_model: str,
    axis_dir: Path,
    cache_root: Path,
    tracks: list[tuple[str, str, str, tuple[str, ...]]],
    per_track: int,
    min_entries: int,
) -> dict:
    track_records = []
    all_identities: set[str] = set()
    for name, _desc, scope, track_dimensions in tracks:
        directory = _track_directory(cache_root, name, scope, dimensions)
        identities = _track_identities(directory, name)
        entry_count = len(identities)
        all_identities.update(identities)
        track_records.append(
            {
                "name": name,
                "scope": scope,
                "dimensions": list(track_dimensions),
                "directory": os.path.relpath(directory, start=axis_dir),
                "min_entries": per_track,
                "entry_count": entry_count,
                "complete": entry_count >= per_track,
            }
        )
    tracks_complete = all(record["complete"] for record in track_records)
    return {
        "schema_version": MULTI_SCHEMA_VERSION,
        "prompt_version": MULTI_PROMPT_VERSION,
        "suite": suite,
        "dimensions": list(dimensions),
        "target_model": target_model,
        "minimum_total_entries": min_entries,
        "entry_count": len(all_identities),
        "complete": tracks_complete and len(all_identities) >= min_entries,
        "tracks": track_records,
    }


async def _run_multi_dimensional(
    suite: str,
    dimensions: tuple[str, ...],
    min_entries: int,
    model: str,
    per: int,
    target_model: str,
    ws: Path,
    mcp: dict,
) -> None:
    axis_value = (os.getenv("LIT_AXIS_DIR") or "").strip()
    if not axis_value:
        raise RuntimeError("LIT_AXIS_DIR is required for a multi-dimensional survey")

    axis_dir = Path(axis_value).resolve()
    cache_root = (
        axis_dir.parent
        / f"schema-v{MULTI_SCHEMA_VERSION}"
        / _cache_slug(target_model)
    )
    tracks = _multi_tracks(dimensions)
    manifest_path = axis_dir / "manifest.json"

    def publish_manifest() -> dict:
        payload = _manifest_payload(
            suite,
            dimensions,
            target_model,
            axis_dir,
            cache_root,
            tracks,
            per,
            min_entries,
        )
        _write_manifest(manifest_path, payload)
        return payload

    # Publish an incomplete manifest first so get_literature composes only this
    # schema/model cache while the sequential tracks are being populated.
    publish_manifest()
    for cat, desc, scope, track_dimensions in tracks:
        track_dir = _track_directory(cache_root, cat, scope, dimensions)
        track_dir.mkdir(parents=True, exist_ok=True)
        attempts = 0
        while _track_count(track_dir, cat) < per and attempts < 4:
            attempts += 1
            current = _track_count(track_dir, cat)
            print(
                f"[litreview] track '{cat}' {current}/{per} — attempt {attempts}",
                flush=True,
            )
            await _survey(
                cat,
                desc,
                suite,
                per - current,
                model,
                ws,
                mcp,
                dimensions=dimensions,
                entry_dimensions=track_dimensions,
                scope=scope,
                target_model=target_model,
                output_dir=track_dir,
            )
            publish_manifest()

    manifest = publish_manifest()
    incomplete = [
        track["name"] for track in manifest["tracks"] if not track["complete"]
    ]
    if incomplete:
        raise RuntimeError(
            "literature survey did not meet the per-track minimum "
            f"({per}); incomplete tracks: {', '.join(incomplete)}"
        )
    _require_minimum(manifest["entry_count"], min_entries)
    if not manifest["complete"]:
        raise RuntimeError("literature manifest remained incomplete after validation")
    print(
        f"[litreview] DONE — {manifest['entry_count']} entries across "
        f"{len(tracks)} complete tracks (target {min_entries})",
        flush=True,
    )


async def run(
    axis: str,
    min_entries: int,
    model: str,
    per: int | None,
    *,
    dimensions: tuple[str, ...] | None = None,
    target_model: str = MULTI_TARGET_MODEL,
) -> None:
    from aar.research_loop.tools.server_api_tools import create_literature_tools_server
    from aar.research_loop.tools.lit_forum import count
    ws = Path(os.getenv("LITREVIEW_WORKSPACE", "/tmp/litreview"))
    ws.mkdir(parents=True, exist_ok=True)
    mcp = {"server-api-tools": create_literature_tools_server()}

    resolved_dimensions = dimensions or resolve_dimensions(axis)
    if len(resolved_dimensions) > 1:
        track_count = len(_multi_tracks(resolved_dimensions))
        per_track = per or max(1, (min_entries + track_count - 1) // track_count)
        await _run_multi_dimensional(
            axis,
            resolved_dimensions,
            min_entries,
            model,
            per_track,
            target_model,
            ws,
            mcp,
        )
        return

    # One pass over the sub-areas (sequential — keeps API/web rate sane + ordering legible).
    legacy_per = per or 9
    for cat, desc in SUBAREAS:
        await _survey(cat, desc, axis, legacy_per, model, ws, mcp)

    # Top up if we're short of the target.
    gen_desc = next(d for c, d in SUBAREAS if c == "general")
    axis_desc = next(d for c, d in SUBAREAS if c == "axis-specific")
    attempts = 0
    while count() < min_entries and attempts < 4:
        attempts += 1
        cat, desc = ("general", gen_desc) if attempts % 2 else ("axis-specific", axis_desc)
        print(f"[litreview] {count()}/{min_entries} — topping up ({cat}, attempt {attempts})", flush=True)
        await _survey(cat, desc, axis, legacy_per, model, ws, mcp)

    final_count = count()
    _require_minimum(final_count, min_entries)
    print(f"[litreview] DONE — {final_count} entries (target {min_entries})", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="sycophancy", help="safety axis / suite name")
    ap.add_argument("--min-entries", type=int, default=30)
    ap.add_argument(
        "--per",
        type=int,
        default=None,
        help="target entries per track (default: 9 for legacy or ceil(total/tracks))",
    )
    ap.add_argument("--model", default=os.getenv("LITREVIEW_MODEL", "claude-sonnet-4-6"))
    ap.add_argument(
        "--dimensions",
        default=os.getenv("LITREVIEW_DIMENSIONS", ""),
        help="comma-separated alignment dimensions (defaults from the suite)",
    )
    ap.add_argument(
        "--target-model",
        default=os.getenv("LITREVIEW_TARGET_MODEL", MULTI_TARGET_MODEL),
        help="checkpoint family the literature should target",
    )
    args = ap.parse_args()
    explicit_dimensions = tuple(
        dimension.strip()
        for dimension in args.dimensions.split(",")
        if dimension.strip()
    )
    asyncio.run(
        run(
            args.suite,
            args.min_entries,
            args.model,
            args.per,
            dimensions=explicit_dimensions or None,
            target_model=args.target_model,
        )
    )


if __name__ == "__main__":
    main()
