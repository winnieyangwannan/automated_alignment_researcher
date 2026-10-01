"""Unit tests for the fixed-scope arXiv helper."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse

from aar.litreview import paper_search


ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>https://arxiv.org/abs/2310.13548v2</id>
    <updated>2024-01-02T00:00:00Z</updated>
    <published>2023-10-20T00:00:00Z</published>
    <title>Towards Understanding Sycophancy</title>
    <summary>A useful abstract.</summary>
    <author><name>Test Author</name></author>
    <category term="cs.CL" />
    <arxiv:primary_category term="cs.CL" />
    <link rel="alternate" href="https://arxiv.org/abs/2310.13548v2" />
    <link rel="related" href="https://arxiv.org/pdf/2310.13548v2" type="application/pdf" />
  </entry>
</feed>"""
HTML = (
    b"<html><body><article><h1>Towards Understanding Sycophancy</h1>"
    b"<script>hidden()</script><p>Method and results. "
    + b"evidence " * 100
    + b"</p></article></body></html>"
)
SEARCH_HTML = b"""
<ol><li class="arxiv-result">
  <p class="list-title"><a href="https://arxiv.org/abs/2310.13548v2">arXiv:2310.13548v2</a></p>
  <p class="title is-5 mathjax">Towards Understanding Sycophancy</p>
  <p class="authors"><a>Test Author</a>, <a>Second Author</a></p>
  <span class="abstract-full">A useful joint-behavior abstract.</span>
</li></ol>
"""
OPENALEX_JSON = b'{"results":[{"id":"https://openalex.org/W1","title":"Joint Honesty and Sycophancy","publication_year":2025,"authorships":[{"author":{"display_name":"Test Author"}}],"abstract_inverted_index":{"Joint":[0],"evidence":[1]},"primary_location":{"landing_page_url":"https://doi.org/10.1/test","pdf_url":""},"ids":{"openalex":"https://openalex.org/W1"},"locations":[]}]}'


def completed(
    stdout: bytes, returncode: int = 0, stderr: bytes = b""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class PaperSearchTest(unittest.TestCase):
    def test_search_ranks_prepared_cache_before_network(self) -> None:
        payload = {
            "schema_version": paper_search.PAPER_SEARCH_CACHE_SCHEMA_VERSION,
            "source": "OpenAlex",
            "papers": [
                {
                    "title": "Generic Language Model Alignment",
                    "abstract": "A broad survey.",
                    "entry_url": "https://openalex.org/W1",
                    "seed_queries": ["alignment"],
                },
                {
                    "title": "Sycophancy and Honesty in Language Models",
                    "abstract": "Joint evaluation evidence.",
                    "entry_url": "https://openalex.org/W2",
                    "seed_queries": ["honesty sycophancy"],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "papers.json"
            cache.write_text(json.dumps(payload), encoding="utf-8")
            with (
                patch.dict("os.environ", {"AAR_PAPER_SEARCH_CACHE": str(cache)}),
                patch.object(paper_search, "_curl") as curl,
            ):
                result = paper_search.search("honesty sycophancy")

        curl.assert_not_called()
        self.assertEqual(result["search_source"], "prepared_cache")
        self.assertEqual(
            result["results"][0]["title"],
            "Sycophancy and Honesty in Language Models",
        )

    def test_invalid_explicit_cache_fails_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "papers.json"
            cache.write_text('{"schema_version": 99, "papers": []}', encoding="utf-8")
            with (
                patch.dict("os.environ", {"AAR_PAPER_SEARCH_CACHE": str(cache)}),
                patch.object(paper_search, "_curl") as curl,
                self.assertRaisesRegex(
                    paper_search.PaperSearchError, "unsupported schema"
                ),
            ):
                paper_search.search("honesty")
        curl.assert_not_called()

    @patch.object(paper_search, "_curl", return_value=OPENALEX_JSON)
    def test_search_uses_fixed_openalex_metadata(self, curl) -> None:
        result = paper_search.search("honesty sycophancy", limit=1)

        self.assertEqual(result["results"][0]["title"], "Joint Honesty and Sycophancy")
        self.assertEqual(result["results"][0]["abstract"], "Joint evidence")
        self.assertEqual(result["results"][0]["metadata_source"], "OpenAlex")
        self.assertTrue(paper_search._approved_url(curl.call_args.args[0]))

    @patch.object(paper_search, "_curl", return_value=SEARCH_HTML)
    @patch.object(paper_search, "_request")
    def test_search_uses_fixed_arxiv_html_first(self, request, curl) -> None:
        curl.side_effect = [b"not json", SEARCH_HTML]
        result = paper_search.search("honesty sycophancy", limit=1)

        request.assert_not_called()
        self.assertEqual(result["results"][0]["arxiv_id"], "2310.13548v2")
        self.assertEqual(result["results"][0]["authors"], ["Test Author", "Second Author"])
        self.assertIn("query=honesty+sycophancy", curl.call_args.args[0])
        self.assertTrue(paper_search._approved_url(curl.call_args.args[0]))

    def test_search_json_fits_inline_agent_tool_result(self) -> None:
        result = {
            "ok": True,
            "operation": "search",
            "results": [
                {
                    "arxiv_id": f"2310.1354{index}",
                    "title": "A" * 200,
                    "authors": ["Author" * 20],
                    "abstract": "x" * paper_search.MAX_ABSTRACT_CHARS,
                }
                for index in range(paper_search.MAX_RESULTS)
            ],
        }

        self.assertEqual(paper_search.MAX_RESULTS, 1)
        self.assertLess(len(json.dumps(result)), 20_000)

    @patch.object(paper_search.time, "sleep")
    @patch.object(paper_search.os, "getpid", return_value=0)
    @patch.object(paper_search, "_require_executable")
    @patch("subprocess.run")
    def test_curl_retries_429_and_timeout_with_bounded_backoff(
        self, run, require_executable, getpid, sleep
    ) -> None:
        del require_executable, getpid
        run.side_effect = [
            completed(b"", returncode=22, stderr=b"curl: (22) HTTP 429"),
            completed(b"", returncode=28, stderr=b"curl: (28) timed out"),
            completed(ATOM),
        ]

        payload = paper_search._curl(
            f"{paper_search.ARXIV_API_URL}?search_query=all%3Asycophancy",
            max_bytes=paper_search.MAX_RESPONSE_BYTES,
        )

        self.assertEqual(payload, ATOM)
        self.assertEqual(run.call_count, 3)
        self.assertEqual([call.args for call in sleep.call_args_list], [(5,), (15,)])

    def test_fetch_json_fits_inline_agent_tool_result(self) -> None:
        paper = {
            "arxiv_id": "2310.13548v2",
            "title": "Towards Understanding Sycophancy",
            "authors": ["Test Author"],
            "abstract": "A useful abstract.",
        }
        content = "x" * paper_search.MAX_TEXT_CHARS
        with (
            patch.object(paper_search, "_request", return_value=[paper]),
            patch.object(
                paper_search, "_fetch_html_text", return_value=(content, True)
            ),
        ):
            result = paper_search.fetch("2310.13548v2")

        self.assertLess(len(json.dumps(result)), 25_000)

    @patch.object(paper_search, "_require_executable")
    @patch("subprocess.run")
    def test_search_uses_fixed_argv_curl_and_bounded_arxiv_endpoint(
        self, run, require_executable
    ) -> None:
        del require_executable
        run.return_value = completed(ATOM)

        result = paper_search.search("  sycophancy   language models  ", limit=1)

        command = run.call_args.args[0]
        parsed = urllib.parse.urlsplit(command[-1])
        params = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(command[:2], ["/usr/bin/curl", "--disable"])
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(
            (parsed.scheme, parsed.netloc, parsed.path),
            ("https", "export.arxiv.org", "/api/query"),
        )
        self.assertEqual(params["search_query"], ["all:sycophancy language models"])
        self.assertEqual(params["max_results"], ["1"])
        self.assertEqual(result["results"][0]["arxiv_id"], "2310.13548v2")
        self.assertEqual(result["results"][0]["authors"], ["Test Author"])

    @patch.object(paper_search, "_require_executable")
    @patch("subprocess.run")
    def test_fetch_returns_bounded_visible_arxiv_html(
        self, run, require_executable
    ) -> None:
        del require_executable
        run.side_effect = [completed(ATOM), completed(HTML)]

        result = paper_search.fetch("2310.13548v2")

        self.assertEqual(result["content_source"], "arxiv_html")
        self.assertIn("Method and results", result["content"])
        self.assertNotIn("hidden", result["content"])
        self.assertFalse(result["content_truncated"])
        self.assertEqual(
            urllib.parse.parse_qs(
                urllib.parse.urlsplit(run.call_args_list[0].args[0][-1]).query
            )["id_list"],
            ["2310.13548v2"],
        )
        self.assertEqual(
            run.call_args_list[1].args[0][-1],
            "https://arxiv.org/html/2310.13548v2",
        )

    @patch.object(paper_search, "_require_executable")
    @patch("subprocess.run")
    def test_fetch_labels_abstract_fallback(self, run, require_executable) -> None:
        del require_executable
        run.side_effect = [
            completed(ATOM),
            completed(b"", returncode=22, stderr=b"not found"),
        ]

        result = paper_search.fetch("2310.13548v2")

        self.assertEqual(result["content_source"], "arxiv_abstract_fallback")
        self.assertEqual(result["content"], "A useful abstract.")
        self.assertIn("curl exit 22", result["warning"])

    def test_fetch_rejects_urls_and_shell_like_ids_before_network(self) -> None:
        bad_ids = (
            "https://arxiv.org/abs/2310.13548",
            "2310.13548;cat .env",
            "2310.13548 && curl example.com",
            "../.env",
        )
        with patch("subprocess.run") as run:
            for value in bad_ids:
                with self.subTest(value=value), self.assertRaises(
                    paper_search.PaperSearchError
                ):
                    paper_search.fetch(value)
        run.assert_not_called()

    def test_html_text_is_truncated_at_session_safe_cap(self) -> None:
        oversized_html = (
            b"<html><body><article>"
            + b"x" * (paper_search.MAX_TEXT_CHARS + 1_000)
            + b"</article></body></html>"
        )
        with patch.object(paper_search, "_curl", return_value=oversized_html):
            text, truncated = paper_search._fetch_html_text("2310.13548")

        self.assertTrue(truncated)
        self.assertLessEqual(len(text), paper_search.MAX_TEXT_CHARS)

    def test_fetch_accepts_modern_and_legacy_ids(self) -> None:
        self.assertEqual(
            paper_search.normalize_arxiv_id("arXiv:2310.13548v2"), "2310.13548v2"
        )
        self.assertEqual(
            paper_search.normalize_arxiv_id("hep-th/9901001v1"), "hep-th/9901001v1"
        )

    def test_query_and_limit_validation_happen_before_network(self) -> None:
        with patch("subprocess.run") as run:
            for query in ("", "hello\nworld", "x" * 501):
                with self.subTest(query=query), self.assertRaises(
                    paper_search.PaperSearchError
                ):
                    paper_search.search(query)
            with self.assertRaises(paper_search.PaperSearchError):
                paper_search.search("valid", limit=11)
        run.assert_not_called()

    def test_unapproved_urls_are_rejected_before_curl(self) -> None:
        with patch("subprocess.run") as run:
            with self.assertRaisesRegex(
                paper_search.PaperSearchError, "unapproved endpoint"
            ):
                paper_search._curl("https://example.com/a", max_bytes=100)
            with self.assertRaisesRegex(
                paper_search.PaperSearchError, "unapproved endpoint"
            ):
                paper_search._curl("https://arxiv.org/abs/2310.13548", max_bytes=100)
        run.assert_not_called()

    @patch.object(paper_search, "_require_executable")
    @patch("subprocess.run")
    def test_oversized_and_malformed_responses_are_rejected(
        self, run, require_executable
    ) -> None:
        del require_executable
        run.return_value = completed(b"x" * (paper_search.MAX_RESPONSE_BYTES + 1))
        with self.assertRaisesRegex(paper_search.PaperSearchError, "size limit"):
            paper_search.search("sycophancy")

        run.return_value = completed(b"not xml")
        with self.assertRaisesRegex(paper_search.PaperSearchError, "malformed XML"):
            paper_search.search("sycophancy")


if __name__ == "__main__":
    unittest.main()
