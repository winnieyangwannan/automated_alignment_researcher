"""Unit tests for the fixed-scope arXiv helper."""

from __future__ import annotations

import subprocess
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
def completed(
    stdout: bytes, returncode: int = 0, stderr: bytes = b""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class PaperSearchTest(unittest.TestCase):
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
        self.assertEqual(params["search_query"], ['all:"sycophancy language models"'])
        self.assertEqual(params["max_results"], ["1"])
        self.assertEqual(result["results"][0]["arxiv_id"], "2310.13548v2")
        self.assertEqual(result["results"][0]["authors"], ["Test Author"])

    @patch.object(paper_search, "_require_executable")
    @patch("subprocess.run")
    def test_fetch_returns_bounded_arxiv_metadata_and_abstract(
        self, run, require_executable
    ) -> None:
        del require_executable
        run.return_value = completed(ATOM)

        result = paper_search.fetch("2310.13548v2")

        self.assertEqual(result["content_source"], "arxiv_abstract")
        self.assertEqual(result["content"], "A useful abstract.")
        self.assertEqual(
            urllib.parse.parse_qs(
                urllib.parse.urlsplit(run.call_args.args[0][-1]).query
            )["id_list"],
            ["2310.13548v2"],
        )

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
