"""Focused coverage for composed, multi-dimensional literature baselines."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from aar.litreview import run_litreview


ROOT = Path(__file__).resolve().parents[1]


def _load_lit_forum():
    spec = importlib.util.spec_from_file_location(
        "multidimensional_lit_forum_under_test",
        ROOT / "aar" / "research_loop" / "tools" / "lit_forum.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_server_tools():
    """Load the tool functions without requiring optional runtime dependencies."""
    sdk = types.ModuleType("claude_agent_sdk")

    def tool(*_args, **_kwargs):
        def decorate(function):
            return function

        return decorate

    sdk.tool = tool
    sdk.create_sdk_mcp_server = lambda **kwargs: kwargs

    package_name = "multidimensional_server_tools"
    package = types.ModuleType(package_name)
    package.__path__ = []
    http_utils = types.ModuleType(f"{package_name}.http_utils")
    http_utils.get_server_url = lambda: "http://unused"

    async def unused_http(*_args, **_kwargs):
        raise AssertionError("literature tests must not make HTTP requests")

    http_utils.async_http_post = unused_http
    http_utils.async_http_get = unused_http
    fs_forum = types.ModuleType(f"{package_name}.fs_forum")
    fs_forum.use_fs_forum = lambda: False
    fs_forum.write_finding = lambda *_args, **_kwargs: None
    fs_forum.leaderboard = lambda: []

    module_name = f"{package_name}.server_api_tools"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "aar" / "research_loop" / "tools" / "server_api_tools.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "claude_agent_sdk": sdk,
            package_name: package,
            f"{package_name}.http_utils": http_utils,
            f"{package_name}.fs_forum": fs_forum,
            module_name: module,
        },
    ):
        spec.loader.exec_module(module)
    return module


lit_forum = _load_lit_forum()
server_tools = _load_server_tools()


def _write_entry(
    directory: Path,
    filename: str,
    *,
    entry_id: str,
    track: str | None = None,
    schema_version: int | None = None,
    source: str | None = None,
    scope: str | None = None,
    dimensions: list[str] | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    entry_dimensions = dimensions or ([track] if track else [])
    payload = {
        "id": entry_id,
        "method": entry_id,
        "track": track,
        "schema_version": schema_version,
        "source": source or f"Source {entry_id}",
        "scope": scope or ("dimension-specific" if track else None),
        "dimensions": entry_dimensions,
        "relevance_by_dimension": {
            dimension: "high" for dimension in entry_dimensions
        },
        "interaction_evidence": "not studied",
    }
    (directory / filename).write_text(json.dumps(payload))


def _write_manifest(root: Path, *, complete: bool = True) -> None:
    payload = {
        "schema_version": 2,
        "prompt_version": "multi-dimensional-v1",
        "complete": complete,
        "tracks": [
            {"name": "honesty", "directory": "tracks/honesty", "min_entries": 1},
            {
                "name": "sycophancy",
                "directory": "tracks/sycophancy",
                "min_entries": 1,
            },
        ],
    }
    (root / "manifest.json").write_text(json.dumps(payload))


class MultidimensionalBaselineTest(unittest.TestCase):
    def test_runner_builds_five_tracks_for_honesty_and_sycophancy(self) -> None:
        dimensions = run_litreview.resolve_dimensions("honesty_sycophancy")
        tracks = run_litreview._multi_tracks(dimensions)

        self.assertEqual(dimensions, ("honesty", "sycophancy"))
        self.assertEqual(
            [track[0] for track in tracks],
            ["general", "honesty", "sycophancy", "cross-dimensional", "evaluation"],
        )

    def test_runner_manifest_is_versioned_and_requires_unique_total(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "honesty_sycophancy"
            root.mkdir()
            target = "google/gemma-4-31B-it"
            cache_root = parent / "schema-v2" / run_litreview._cache_slug(target)
            dimensions = ("honesty", "sycophancy")
            tracks = run_litreview._multi_tracks(dimensions)
            for name, _description, scope, track_dimensions in tracks:
                track_dir = run_litreview._track_directory(
                    cache_root, name, scope, dimensions
                )
                _write_entry(
                    track_dir,
                    f"{name}.json",
                    entry_id=f"{name}-paper",
                    track=name,
                    schema_version=2,
                    source=f"Distinct source for {name}",
                    scope=scope,
                    dimensions=list(track_dimensions),
                )

            manifest = run_litreview._manifest_payload(
                "honesty_sycophancy",
                dimensions,
                target,
                root,
                cache_root,
                tracks,
                per_track=1,
                min_entries=5,
            )

            self.assertTrue(manifest["complete"])
            self.assertEqual(manifest["prompt_version"], "multi-dimensional-v1")
            self.assertEqual(manifest["entry_count"], 5)
            self.assertEqual(len(manifest["tracks"]), 5)
            self.assertTrue(manifest["tracks"][0]["directory"].startswith("../"))

            run_litreview._write_manifest(root / "manifest.json", manifest)
            with patch.dict(
                os.environ,
                {
                    "LIT_AXIS_DIR": str(root),
                    "LIT_FORUM_DIR": "",
                    "LITREVIEW_DIMENSIONS": "honesty,sycophancy",
                },
                clear=False,
            ):
                self.assertTrue(lit_forum.baseline_ready(5))
                self.assertEqual(lit_forum.count(), 5)

    def test_manifest_resolves_and_reads_multiple_relative_track_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_manifest(root)
            _write_entry(
                root / "tracks" / "honesty",
                "honesty.json",
                entry_id="honesty-paper",
                track="honesty",
                schema_version=2,
            )
            _write_entry(
                root / "tracks" / "sycophancy",
                "sycophancy.json",
                entry_id="sycophancy-paper",
                track="sycophancy",
                schema_version=2,
            )

            with patch.dict(
                os.environ,
                {"LIT_AXIS_DIR": str(root), "LIT_FORUM_DIR": ""},
                clear=False,
            ):
                self.assertEqual(
                    {entry["id"] for entry in lit_forum.read_lit_entries()},
                    {"honesty-paper", "sycophancy-paper"},
                )
                self.assertTrue(lit_forum.baseline_ready(2))

    def test_manifest_readiness_requires_complete_matching_tracks_and_minimums(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            honesty = root / "tracks" / "honesty"
            sycophancy = root / "tracks" / "sycophancy"
            _write_manifest(root, complete=False)
            _write_entry(
                honesty,
                "paper.json",
                entry_id="honesty-paper",
                track="honesty",
                schema_version=2,
            )
            _write_entry(
                sycophancy,
                "paper.json",
                entry_id="sycophancy-paper",
                track="sycophancy",
                schema_version=2,
            )

            environment = {"LIT_AXIS_DIR": str(root), "LIT_FORUM_DIR": ""}
            with patch.dict(os.environ, environment, clear=False):
                self.assertFalse(lit_forum.baseline_ready(2), "complete flag")

                _write_manifest(root, complete=True)
                _write_entry(
                    honesty,
                    "paper.json",
                    entry_id="honesty-paper",
                    track="honesty",
                    schema_version=1,
                )
                self.assertFalse(lit_forum.baseline_ready(2), "schema version")

                _write_entry(
                    honesty,
                    "paper.json",
                    entry_id="honesty-paper",
                    track="wrong-track",
                    schema_version=2,
                )
                self.assertFalse(lit_forum.baseline_ready(2), "track identity")

                _write_entry(
                    honesty,
                    "paper.json",
                    entry_id="honesty-paper",
                    track="honesty",
                    schema_version=2,
                )
                (sycophancy / "paper.json").unlink()
                self.assertFalse(lit_forum.baseline_ready(2), "per-track minimum")

                _write_entry(
                    sycophancy,
                    "paper.json",
                    entry_id="sycophancy-paper",
                    track="sycophancy",
                    schema_version=2,
                )
                self.assertTrue(lit_forum.baseline_ready(2))

                manifest = json.loads((root / "manifest.json").read_text())
                manifest["prompt_version"] = "stale-prompt"
                (root / "manifest.json").write_text(json.dumps(manifest))
                self.assertFalse(lit_forum.baseline_ready(2), "prompt version")

    def test_same_arxiv_source_is_deduplicated_across_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_manifest(root)
            _write_entry(
                root / "tracks" / "honesty",
                "first.json",
                entry_id="first-copy",
                track="honesty",
                schema_version=2,
                source="Example Paper, https://arxiv.org/abs/2401.12345",
            )
            _write_entry(
                root / "tracks" / "sycophancy",
                "second.json",
                entry_id="second-copy",
                track="sycophancy",
                schema_version=2,
                source="Example Paper PDF, https://arxiv.org/pdf/2401.12345v2",
            )

            with patch.dict(
                os.environ,
                {"LIT_AXIS_DIR": str(root), "LIT_FORUM_DIR": ""},
                clear=False,
            ):
                entries = lit_forum.read_lit_entries()

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["id"], "first-copy")

    def test_legacy_single_directory_remains_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_entry(root, "one.json", entry_id="legacy-one")
            _write_entry(root, "two.json", entry_id="legacy-two")

            with patch.dict(
                os.environ,
                {"LIT_AXIS_DIR": str(root), "LIT_FORUM_DIR": ""},
                clear=False,
            ):
                self.assertEqual(lit_forum.count(), 2)
                self.assertTrue(lit_forum.baseline_ready(2))
                self.assertFalse(lit_forum.baseline_ready(3))


class MultidimensionalServerToolsTest(unittest.TestCase):
    def test_multi_survey_renders_joint_prompt_and_track_metadata(self) -> None:
        captured: dict[str, object] = {}

        class FakeAgent:
            def __init__(self, **kwargs: object) -> None:
                captured["options"] = kwargs

            async def execute(self, task: str) -> object:
                captured["task"] = task
                captured["track"] = os.environ.get("LITREVIEW_TRACK")
                captured["scope"] = os.environ.get("LITREVIEW_SCOPE_CURRENT")
                captured["dimensions"] = os.environ.get(
                    "LITREVIEW_DIMENSIONS_CURRENT"
                )
                return types.SimpleNamespace(success=True, error=None)

        agent_module = types.ModuleType("aar.research_loop.agent")
        agent_module.BaseAgent = FakeAgent
        forum_module = types.ModuleType("aar.research_loop.tools.lit_forum")
        forum_module.count = lambda: 0
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "honesty"
            with (
                patch.dict(
                    os.environ,
                    {"LITREVIEW_WEB_MODE": "native_web"},
                    clear=False,
                ),
                patch.dict(
                    sys.modules,
                    {
                        "aar.research_loop.agent": agent_module,
                        "aar.research_loop.tools.lit_forum": forum_module,
                    },
                ),
            ):
                asyncio.run(
                    run_litreview._survey(
                        "honesty",
                        "Honesty methods.",
                        "honesty_sycophancy",
                        2,
                        "claude-sonnet-4-6",
                        Path(directory),
                        {},
                        dimensions=("honesty", "sycophancy"),
                        entry_dimensions=("honesty",),
                        scope="dimension-specific",
                        target_model="google/gemma-4-31B-it",
                        output_dir=output_dir,
                    )
                )

        task = str(captured["task"])
        self.assertIn("ONE **google/gemma-4-31B-it** checkpoint", task)
        self.assertIn("honesty and sycophancy", task)
        self.assertIn("assigned track dimensions ['honesty']", task)
        self.assertIn("must not author training answers or labels", task)
        self.assertEqual(captured["track"], "honesty")
        self.assertEqual(captured["scope"], "dimension-specific")
        self.assertEqual(captured["dimensions"], "honesty")

    def test_get_literature_filters_by_dimension_and_scope(self) -> None:
        entries = [
            {
                "id": "honesty-only",
                "method": "Honesty method",
                "dimensions": ["honesty"],
                "scope": "dimension-specific",
            },
            {
                "id": "joint",
                "method": "Joint method",
                "dimensions": ["honesty", "sycophancy"],
                "scope": "cross-dimensional",
            },
            {
                "id": "sycophancy-only",
                "method": "Sycophancy method",
                "dimensions": ["sycophancy"],
                "scope": "dimension-specific",
            },
        ]
        forum_module = types.ModuleType("aar.research_loop.tools.lit_forum")
        forum_module.read_lit_entries = lambda: entries

        with patch.dict(
            sys.modules,
            {"aar.research_loop.tools.lit_forum": forum_module},
        ):
            result = asyncio.run(
                server_tools.get_literature(
                    {"dimension": "HONESTY", "scope": "cross-dimensional"}
                )
            )

        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["mode"], "full")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["literature"][0]["method"], "Joint method")

    def test_share_literature_applies_environment_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "LIT_FORUM_DIR": directory,
                "LIT_AXIS_DIR": "",
                "LITREVIEW_SCHEMA_VERSION": "2",
                "LITREVIEW_TRACK": "cross-dimensional",
                "LITREVIEW_SCOPE_CURRENT": "cross-dimensional",
                "LITREVIEW_DIMENSIONS_CURRENT": "honesty, sycophancy",
                "LITREVIEW_AREA": "joint-survey",
                "IDEA_NAME": "",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch.dict(
                    sys.modules,
                    {"aar.research_loop.tools.lit_forum": lit_forum},
                ),
            ):
                result = asyncio.run(
                    server_tools.share_literature(
                        {
                            "method": "Joint alignment",
                            "relevance_by_dimension": {
                                "honesty": "high",
                                "sycophancy": "high",
                            },
                            "interaction_evidence": "positive transfer reported",
                            "summary": "Summary",
                            "intuition": "Intuition",
                            "core_mechanism": "Mechanism",
                            "reproduction_recipe": "Recipe",
                            "prerequisites": "Prerequisites",
                            "training_data": "Training data",
                            "evaluation": "Evaluation",
                            "key_results": "Results",
                            "source": "Example source",
                        }
                    )
                )

            response = json.loads(result["content"][0]["text"])
            saved = json.loads(next(Path(directory).glob("*.json")).read_text())
            self.assertTrue(response["success"])
            self.assertEqual(saved["schema_version"], 2)
            self.assertEqual(saved["track"], "cross-dimensional")
            self.assertEqual(saved["scope"], "cross-dimensional")
            self.assertEqual(saved["dimensions"], ["honesty", "sycophancy"])
            self.assertEqual(saved["by"], "joint-survey")


if __name__ == "__main__":
    unittest.main()
