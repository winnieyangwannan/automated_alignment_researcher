"""Tests for reproducible OpenAlex cache preparation."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_paper_search_cache


class PreparePaperSearchCacheTest(unittest.TestCase):
    @patch.object(prepare_paper_search_cache.paper_search, "_search_openalex")
    def test_prepare_deduplicates_and_records_sorted_seed_queries(self, search) -> None:
        paper = {
            "arxiv_id": "",
            "title": "Joint Alignment",
            "authors": ["A. Author"],
            "published": "2025",
            "updated": "",
            "abstract": "Honesty and sycophancy evidence.",
            "categories": [],
            "primary_category": "",
            "entry_url": "https://openalex.org/W1",
            "pdf_url": "",
            "metadata_source": "OpenAlex",
        }
        search.side_effect = [[paper], [paper]]

        payload = prepare_paper_search_cache.prepare_cache(
            ["sycophancy", "honesty"], per_query=3
        )

        self.assertEqual(payload["seed_queries"], ["honesty", "sycophancy"])
        self.assertEqual(len(payload["papers"]), 1)
        self.assertEqual(
            payload["papers"][0]["seed_queries"], ["honesty", "sycophancy"]
        )
        self.assertEqual(
            [call.args for call in search.call_args_list],
            [("honesty", 3), ("sycophancy", 3)],
        )

    def test_write_cache_is_stable_json(self) -> None:
        payload = {
            "schema_version": 1,
            "source": "OpenAlex",
            "seed_queries": ["honesty"],
            "papers": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "papers.json"
            prepare_paper_search_cache.write_cache(payload, output)
            first = output.read_bytes()
            prepare_paper_search_cache.write_cache(payload, output)
            second = output.read_bytes()

        self.assertEqual(first, second)
        self.assertEqual(json.loads(first), payload)


if __name__ == "__main__":
    unittest.main()
