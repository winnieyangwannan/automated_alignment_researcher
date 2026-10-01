#!/usr/bin/env python3
"""Prepare a bounded OpenAlex snapshot for the restricted paper helper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Sequence


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aar.litreview import paper_search  # noqa: E402


MAX_SEED_QUERIES = 50
MAX_RESULTS_PER_QUERY = 10
MAX_CACHE_PAPERS = 500


def prepare_cache(queries: Sequence[str], per_query: int) -> dict[str, Any]:
    """Fetch and deterministically combine normalized OpenAlex metadata."""
    normalized_queries = sorted(
        {paper_search.normalize_query(query) for query in queries}
    )
    if not normalized_queries:
        raise paper_search.PaperSearchError("at least one seed query is required")
    if len(normalized_queries) > MAX_SEED_QUERIES:
        raise paper_search.PaperSearchError(
            f"at most {MAX_SEED_QUERIES} seed queries are allowed"
        )
    if not 1 <= per_query <= MAX_RESULTS_PER_QUERY:
        raise paper_search.PaperSearchError(
            f"per-query must be between 1 and {MAX_RESULTS_PER_QUERY}"
        )

    papers: dict[str, dict[str, Any]] = {}
    for query in normalized_queries:
        for result in paper_search._search_openalex(query, per_query):
            identity = (
                result.get("arxiv_id")
                or result.get("entry_url")
                or str(result.get("title", "")).casefold()
            )
            if not identity:
                continue
            if identity not in papers:
                papers[identity] = {**result, "seed_queries": []}
            papers[identity]["seed_queries"].append(query)
            if len(papers) > MAX_CACHE_PAPERS:
                raise paper_search.PaperSearchError(
                    f"cache would exceed {MAX_CACHE_PAPERS} papers"
                )

    ordered = sorted(
        papers.values(),
        key=lambda paper: (
            str(paper.get("title", "")).casefold(),
            str(paper.get("arxiv_id") or paper.get("entry_url") or ""),
        ),
    )
    for paper in ordered:
        paper["seed_queries"] = sorted(set(paper["seed_queries"]))
    return {
        "schema_version": paper_search.PAPER_SEARCH_CACHE_SCHEMA_VERSION,
        "source": "OpenAlex",
        "seed_queries": normalized_queries,
        "papers": ordered,
    }


def write_cache(payload: dict[str, Any], output: Path) -> None:
    """Atomically write the cache to the caller-selected ignored path."""
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(encoded) > paper_search.MAX_CACHE_BYTES:
        raise paper_search.PaperSearchError("prepared cache exceeded the size limit")
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
    temporary.replace(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a local OpenAlex cache for secure librarian searches"
    )
    parser.add_argument("--query", action="append", required=True, dest="queries")
    parser.add_argument("--per-query", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = prepare_cache(args.queries, args.per_query)
        write_cache(payload, args.output)
    except paper_search.PaperSearchError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"wrote {len(payload['papers'])} papers from "
        f"{len(payload['seed_queries'])} queries to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
