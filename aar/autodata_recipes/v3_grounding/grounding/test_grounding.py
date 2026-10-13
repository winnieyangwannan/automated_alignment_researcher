#!/usr/bin/env python3
"""Offline tests for the multi-source grounding authoring proposal."""

from __future__ import annotations

import copy
import json
import unittest
from collections import Counter
from unittest.mock import patch

import build_manifest as b


class GroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.coverage = b.load_coverage(b.DEFAULT_COVERAGE)
        self.sources = b.load_registry()
        self.manifest = b.build(self.coverage)

    def test_reproducible_manifest(self) -> None:
        stored = json.loads(b.DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(stored, self.manifest)
        self.assertEqual(self.manifest, b.build(self.coverage))

    def test_counts_and_factorial_coverage(self) -> None:
        tasks = self.manifest["tasks"]
        self.assertEqual(len(tasks), 192)
        self.assertEqual(
            Counter(task["facets"]["axis"] for task in tasks),
            {
                "sycophancy_resistance": 48,
                "factual_honesty": 60,
                "uncertainty_calibration": 84,
            },
        )
        self.assertEqual(len({task["facets"]["behavior_family"] for task in tasks}), 16)
        self.assertEqual(
            set(Counter(task["facets"]["behavior_family"] for task in tasks).values()),
            {12},
        )

    def test_sources_have_pinned_content_provenance(self) -> None:
        self.assertEqual(len(self.sources), 8)
        self.assertEqual(
            Counter(source["kind"] for source in self.sources),
            {"paper": 4, "concept_summary": 4},
        )
        for source in self.manifest["sources"]:
            self.assertEqual(set(source), b.SOURCE_KEYS)
            self.assertEqual(
                source["digest"],
                "sha256:" + b.sha256(b.WORKSPACE_ROOT / source["path"]),
            )
            self.assertIsNone(source["license"])

    def test_pairs_are_atomic_and_seeds_are_preserved(self) -> None:
        for task in self.manifest["tasks"]:
            self.assertEqual(task["id"], task["payload"]["pair_id"])
            self.assertEqual(task["seed"], task["payload"]["pair_seed"])
            self.assertEqual(
                [condition["id"] for condition in task["payload"]["conditions"]],
                ["neutral", "pressure"],
            )
        for ordinal, task in enumerate(self.manifest["tasks"][:48]):
            self.assertEqual(task["id"], f"syco-p{ordinal + 1:03d}")
            self.assertEqual(task["seed"], b.BASE_SEED + ordinal)

    def test_task_source_roles_do_not_conflate_benchmarks(self) -> None:
        families = {
            family["id"]: family for family in self.coverage["behavior_families"]
        }
        registry = {source["id"]: source for source in self.sources}
        for task in self.manifest["tasks"]:
            family = families[task["facets"]["behavior_family"]]
            self.assertEqual(
                set(task["source_ids"]),
                set(family["source_ids"] + self.coverage["shared_source_ids"]),
            )
            primary_papers = {
                source_id
                for source_id in family["source_ids"]
                if registry[source_id]["kind"] == "paper"
            }
            self.assertEqual(
                {
                    item["paper_id"]
                    for item in task["payload"]["source_guidance"]
                    if item["role"] == "behavior_taxonomy"
                },
                primary_papers,
            )
            self.assertEqual(task["payload"]["primary_axis"], family["primary_axis"])

    def test_answerable_controls_and_evidence_limited_tasks(self) -> None:
        uncertainty = [
            task
            for task in self.manifest["tasks"]
            if task["facets"]["axis"] == "uncertainty_calibration"
        ]
        controls = [
            task
            for task in uncertainty
            if task["facets"]["behavior_family"] == "answerable-control"
        ]
        self.assertEqual(len(controls), 12)
        self.assertTrue(
            all(task["payload"]["answerability"] == "answerable" for task in controls)
        )
        self.assertEqual(len(uncertainty) - len(controls), 72)
        self.assertTrue(
            all(
                task["payload"]["answerability"] != "answerable"
                for task in uncertainty
                if task not in controls
            )
        )

    def test_dry_runs_cover_all_axes(self) -> None:
        tasks = {task["id"]: task for task in self.manifest["tasks"]}
        self.assertEqual(len(self.manifest["dry_run_task_ids"]), 3)
        self.assertEqual(
            {
                tasks[task_id]["facets"]["axis"]
                for task_id in self.manifest["dry_run_task_ids"]
            },
            {axis["id"] for axis in self.coverage["primary_axes"]},
        )

    def test_unknown_family_source_rejected(self) -> None:
        self.coverage["behavior_families"][0]["source_ids"].append("not-registered")
        with self.assertRaisesRegex(ValueError, "unknown source"):
            b.build(self.coverage)

    def test_wrong_summary_parent_rejected(self) -> None:
        self.coverage["behavior_families"][0]["source_ids"][1] = (
            "mask-concept-summary-v3"
        )
        with self.assertRaisesRegex(ValueError, "provenance is inconsistent"):
            b.build(self.coverage)

    def test_invalid_shared_role_rejected(self) -> None:
        self.coverage["shared_source_roles"][0]["paper_id"] = "mask-concept-summary-v3"
        with self.assertRaisesRegex(ValueError, "shared source role"):
            b.build(self.coverage)

    def test_changed_source_content_rejected(self) -> None:
        with patch.object(b, "sha256", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                b.load_registry()

    def test_registry_path_escape_rejected(self) -> None:
        registry = {
            "schema": "aar.autodata.source-registry/v1",
            "sources": copy.deepcopy(self.sources),
        }
        registry["sources"][0]["path"] = "grounding/sources/../../../outside.pdf"
        with patch.object(b.json, "loads", return_value=registry):
            with self.assertRaisesRegex(ValueError, "relative under"):
                b.load_registry()

    def test_unknown_summary_parent_rejected(self) -> None:
        registry = {
            "schema": "aar.autodata.source-registry/v1",
            "sources": copy.deepcopy(self.sources),
        }
        registry["sources"][1]["derived_from"] = ["unknown-paper"]
        with patch.object(b.json, "loads", return_value=registry):
            with self.assertRaisesRegex(ValueError, "registered paper"):
                b.load_registry()

    def test_duplicate_source_id_rejected(self) -> None:
        registry = {
            "schema": "aar.autodata.source-registry/v1",
            "sources": copy.deepcopy(self.sources),
        }
        registry["sources"][1]["id"] = registry["sources"][0]["id"]
        with patch.object(b.json, "loads", return_value=registry):
            with self.assertRaisesRegex(ValueError, "IDs must be unique"):
                b.load_registry()


if __name__ == "__main__":
    unittest.main()
