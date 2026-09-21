"""Small, fixed-scope client for the public arXiv API.

This module deliberately accepts no URL from its caller. Both supported
operations build requests to the fixed arXiv HTTPS API and emit JSON so an
agent does not need general-purpose web or shell access. Curl is invoked with a
fixed argument vector; no command is interpreted by a shell.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import os
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Sequence


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_HTML_BASE_URL = "https://arxiv.org/html"
DEFAULT_USER_AGENT = "automated-alignment-researcher/0.1 (academic-paper helper)"
MAX_QUERY_CHARS = 500
MAX_RESULTS = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_HTML_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 160_000
REQUEST_TIMEOUT_SECONDS = 30
CURL_PATH = Path("/usr/bin/curl")

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
_MODERN_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
_LEGACY_ARXIV_ID = re.compile(
    r"^[A-Za-z][A-Za-z0-9.-]*(?:/[A-Za-z0-9.-]+)?/\d{7}(?:v\d+)?$"
)


class PaperSearchError(RuntimeError):
    """Expected input, network, or response error from the helper."""


def normalize_query(value: str) -> str:
    """Validate and normalize a human-readable search query."""
    query = " ".join(value.split())
    if not query:
        raise PaperSearchError("query must not be empty")
    if len(query) > MAX_QUERY_CHARS:
        raise PaperSearchError(f"query must be at most {MAX_QUERY_CHARS} characters")
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise PaperSearchError("query must not contain control characters")
    return query


def normalize_arxiv_id(value: str) -> str:
    """Accept modern and legacy arXiv identifiers, but never a caller URL."""
    arxiv_id = value.strip()
    if arxiv_id.lower().startswith("arxiv:"):
        arxiv_id = arxiv_id[6:]
    if not (
        _MODERN_ARXIV_ID.fullmatch(arxiv_id)
        or _LEGACY_ARXIV_ID.fullmatch(arxiv_id)
    ):
        raise PaperSearchError("invalid arXiv identifier")
    return arxiv_id


def _text(element: ET.Element, name: str) -> str:
    child = element.find(f"{_ATOM}{name}")
    if child is None or child.text is None:
        return ""
    return " ".join(child.text.split())


def _entry_to_dict(entry: ET.Element) -> dict[str, Any]:
    entry_url = _text(entry, "id")
    arxiv_id = entry_url.rstrip("/").rsplit("/", 1)[-1]
    links = {
        link.attrib.get("rel", "alternate"): link.attrib.get("href", "")
        for link in entry.findall(f"{_ATOM}link")
    }
    categories = [
        item.attrib["term"]
        for item in entry.findall(f"{_ATOM}category")
        if item.attrib.get("term")
    ]
    primary = entry.find(f"{_ARXIV}primary_category")
    return {
        "arxiv_id": arxiv_id,
        "title": _text(entry, "title"),
        "authors": [
            _text(author, "name") for author in entry.findall(f"{_ATOM}author")
        ],
        "published": _text(entry, "published"),
        "updated": _text(entry, "updated"),
        "abstract": _text(entry, "summary"),
        "categories": categories,
        "primary_category": primary.attrib.get("term", "") if primary is not None else "",
        "entry_url": entry_url,
        "pdf_url": links.get("related", ""),
    }


def parse_atom_feed(payload: bytes) -> list[dict[str, Any]]:
    """Parse the bounded arXiv Atom response into JSON-compatible records."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise PaperSearchError("arXiv returned malformed XML") from error
    return [_entry_to_dict(entry) for entry in root.findall(f"{_ATOM}entry")]


def _require_executable(path: Path, purpose: str) -> None:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise PaperSearchError(f"{purpose} executable is unavailable: {path}")


def _approved_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        return False
    return (
        parsed.hostname == "export.arxiv.org" and parsed.path == "/api/query"
    ) or (
        parsed.hostname == "arxiv.org"
        and parsed.path.startswith("/html/")
        and not parsed.query
    )


def _curl(url: str, *, max_bytes: int) -> bytes:
    """GET one approved arXiv URL with curl's argv interface and hard bounds."""
    if not _approved_url(url):
        raise PaperSearchError("refusing request to an unapproved endpoint")
    _require_executable(CURL_PATH, "curl")
    command = [
        str(CURL_PATH),
        "--disable",  # must be first curl option: ignore user-controlled .curlrc
        "--fail",
        "--silent",
        "--show-error",
        "--request",
        "GET",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        "--max-redirs",
        "0",
        "--max-time",
        str(REQUEST_TIMEOUT_SECONDS),
        "--max-filesize",
        str(max_bytes),
        "--user-agent",
        os.getenv("AAR_PAPER_SEARCH_USER_AGENT", DEFAULT_USER_AGENT),
    ]
    command.append(url)
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=REQUEST_TIMEOUT_SECONDS + 5,
        )
    except subprocess.TimeoutExpired as error:
        raise PaperSearchError("arXiv request timed out") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PaperSearchError(
            f"arXiv request failed (curl exit {completed.returncode}): {detail[:300]}"
        )
    if len(completed.stdout) > max_bytes:
        raise PaperSearchError("arXiv response exceeded the size limit")
    return completed.stdout


def _request(params: dict[str, str | int]) -> list[dict[str, Any]]:
    url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"
    return parse_atom_feed(_curl(url, max_bytes=MAX_RESPONSE_BYTES))


class _VisibleTextParser(HTMLParser):
    """Extract visible text while discarding active/non-content elements."""

    _HIDDEN = {"script", "style", "noscript", "svg"}
    _BREAKS = {
        "article", "blockquote", "br", "div", "figcaption", "h1", "h2", "h3",
        "h4", "h5", "h6", "li", "p", "section", "table", "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.parts: list[str] = []
        self.length = 0
        self.truncated = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self._HIDDEN:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag in self._BREAKS:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._HIDDEN:
            self.hidden_depth = max(0, self.hidden_depth - 1)
        elif not self.hidden_depth and tag in self._BREAKS:
            self._append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self._append(data)

    def _append(self, value: str) -> None:
        remaining = MAX_TEXT_CHARS - self.length
        if remaining <= 0:
            self.truncated = True
            return
        self.parts.append(value[:remaining])
        self.length += min(len(value), remaining)
        self.truncated = self.truncated or len(value) > remaining

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line)


def _fetch_html_text(arxiv_id: str) -> tuple[str, bool]:
    encoded_id = urllib.parse.quote(arxiv_id, safe="/")
    payload = _curl(
        f"{ARXIV_HTML_BASE_URL}/{encoded_id}", max_bytes=MAX_HTML_BYTES
    )
    parser = _VisibleTextParser()
    try:
        parser.feed(payload.decode("utf-8", errors="replace"))
        parser.close()
    except Exception as error:
        raise PaperSearchError("arXiv HTML could not be parsed") from error
    text = parser.text()
    if len(text) < 500:
        raise PaperSearchError("arXiv HTML did not contain enough visible paper text")
    return text, parser.truncated


def search(query: str, limit: int = 5) -> dict[str, Any]:
    """Search all arXiv fields for a plain-language query."""
    normalized = normalize_query(query)
    if not 1 <= limit <= MAX_RESULTS:
        raise PaperSearchError(f"limit must be between 1 and {MAX_RESULTS}")
    results = _request(
        {
            "search_query": f'all:"{normalized}"',
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    return {"ok": True, "operation": "search", "query": normalized, "results": results}


def fetch(arxiv_id: str) -> dict[str, Any]:
    """Fetch bounded paper text, explicitly falling back to its abstract."""
    normalized = normalize_arxiv_id(arxiv_id)
    results = _request({"id_list": normalized, "max_results": 1})
    if not results:
        raise PaperSearchError(f"arXiv paper not found: {normalized}")
    paper = results[0]
    try:
        content, truncated = _fetch_html_text(normalized)
        content_source = "arxiv_html"
        warning = ""
    except PaperSearchError as error:
        content = paper["abstract"]
        content_source = "arxiv_abstract_fallback"
        truncated = False
        warning = str(error)
    return {
        "ok": True,
        "operation": "fetch",
        "paper": paper,
        "content": content,
        "content_source": content_source,
        "content_truncated": truncated,
        "warning": warning,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aar-paper-search")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    search_parser = subparsers.add_parser("search", help="search arXiv")
    search_parser.add_argument("query", help="plain-language query (quote multi-word queries)")
    search_parser.add_argument("--limit", type=int, default=5)

    fetch_parser = subparsers.add_parser(
        "fetch", help="fetch bounded arXiv HTML text with abstract fallback"
    )
    fetch_parser.add_argument("arxiv_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = (
            search(args.query, args.limit)
            if args.operation == "search"
            else fetch(args.arxiv_id)
        )
    except PaperSearchError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
