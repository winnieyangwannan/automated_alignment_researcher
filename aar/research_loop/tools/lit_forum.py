"""Shared FS **literature-review forum** — the sibling of ``fs_forum`` for the
literature survey instead of experimental findings.

A team's lit forum lives at ``LIT_FORUM_DIR`` (set per-team by the launcher, e.g.
``aar_litreview/<TEAM_ID>/``). It is **shared** exactly like the findings forum:
the literature-review pre-phase agents populate it (30+ method/paper entries
before the AARs start), and the team's AARs both **read** it (``get_literature``)
and **append** to it (``share_literature``) when their per-iteration search turns
up something useful. One atomic JSON file per entry; no server.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any


def _lit_dir() -> Path | None:
    """The team's OWN lit-forum dir (write target), or None if LIT_FORUM_DIR is
    unset/empty (so we NEVER fall back to Path('') == cwd and pollute the cwd).
    Under TEAM_DIR/litreview — entries the team's AARs add during THIS run, private
    to the team."""
    v = (os.getenv("LIT_FORUM_DIR") or "").strip()
    return Path(v) if v else None


def _axis_lit_dir() -> Path | None:
    """The AXIS-WISE literature baseline (read-only reference), or None. Set via
    LIT_AXIS_DIR (e.g. aar_litreview/<axis>/). Produced once per axis by the survey
    pre-phase and shared by every team on that axis. Teams READ it but never write
    here (their own in-run additions go to LIT_FORUM_DIR), so one team's discoveries
    stay invisible to other teams."""
    v = (os.getenv("LIT_AXIS_DIR") or "").strip()
    return Path(v) if v else None


# Fields a literature entry should carry (free-form text, but structured so the
# AARs and the dashboard can read it consistently).
_FIELDS = (
    "schema_version", "track", "scope", "dimensions",
    "relevance_by_dimension", "interaction_evidence", "method", "category",
    "summary", "intuition", "core_mechanism", "reproduction_recipe",
    "prerequisites", "training_data", "evaluation", "key_results",
    "applicability", "source", "relevance", "by",
)

_ARXIV_ID = re.compile(
    r"(?:arxiv:\s*|arxiv\.org/(?:abs|pdf)/)?"
    r"([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?|[A-Za-z][A-Za-z0-9.-]*/[0-9]{7}(?:v[0-9]+)?)",
    re.IGNORECASE,
)


def entry_identity(entry: dict[str, Any]) -> str | None:
    """Return a stable paper identity for cross-track de-duplication."""
    source = str(entry.get("source") or "")
    match = _ARXIV_ID.search(source)
    if match:
        arxiv_id = re.sub(r"v[0-9]+$", "", match.group(1).lower())
        return f"arxiv:{arxiv_id}"
    normalized_source = " ".join(source.lower().split())
    return f"source:{normalized_source}" if normalized_source else None


def valid_manifest_entry(
    entry: dict[str, Any], schema_version: int, track: str
) -> bool:
    """Return whether an entry satisfies the composed-literature contract."""
    dimensions = entry.get("dimensions")
    relevance = entry.get("relevance_by_dimension")
    return (
        entry.get("schema_version") == schema_version
        and entry.get("track") == track
        and entry.get("scope") in {
            "general", "dimension-specific", "cross-dimensional", "evaluation",
        }
        and isinstance(dimensions, list)
        and bool(dimensions)
        and isinstance(relevance, dict)
        and all(str(dimension) in relevance for dimension in dimensions)
        and bool(str(entry.get("interaction_evidence") or "").strip())
        and bool(str(entry.get("method") or "").strip())
        and bool(str(entry.get("source") or "").strip())
    )


def _manifest() -> tuple[Path, dict[str, Any]] | None:
    axis_dir = _axis_lit_dir()
    if axis_dir is None:
        return None
    path = axis_dir / "manifest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return path, {}
    return path, payload if isinstance(payload, dict) else {}


def _baseline_lit_dirs() -> list[Path]:
    """Resolve legacy single-axis storage or a composed-suite manifest."""
    manifest = _manifest()
    if manifest is None:
        axis_dir = _axis_lit_dir()
        return [axis_dir] if axis_dir is not None else []

    path, payload = manifest
    directories: list[Path] = []
    for track in payload.get("tracks", []):
        if not isinstance(track, dict) or not track.get("directory"):
            continue
        directory = Path(str(track["directory"]))
        if not directory.is_absolute():
            directory = path.parent / directory
        directories.append(directory.resolve())
    return directories


def _read_dirs(directories: list[Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    for directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            if path.name == "manifest.json":
                continue
            try:
                entry = json.loads(path.read_text())
            except Exception:
                continue
            entry_id = str(entry.get("id") or path.stem)
            identity = entry_identity(entry)
            if entry_id in seen_ids or (identity is not None and identity in seen_sources):
                continue
            seen_ids.add(entry_id)
            if identity is not None:
                seen_sources.add(identity)
            out.append(entry)
    return out


def write_lit_entry(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist one literature entry to the shared lit forum. uuid-named so many
    agents writing concurrently never collide."""
    d = _lit_dir()
    if d is None:
        return {"_saved_path": None, "error": "LIT_FORUM_DIR unset"}
    d.mkdir(parents=True, exist_ok=True)
    e = {k: payload.get(k) for k in _FIELDS}
    e["schema_version"] = e.get("schema_version") or int(
        os.getenv("LITREVIEW_SCHEMA_VERSION", "1")
    )
    e["track"] = e.get("track") or os.getenv("LITREVIEW_TRACK") or None
    e["scope"] = e.get("scope") or os.getenv("LITREVIEW_SCOPE_CURRENT") or None
    if not e.get("dimensions"):
        dimensions = os.getenv("LITREVIEW_DIMENSIONS_CURRENT") or os.getenv(
            "AAR_DIMENSIONS", ""
        )
        e["dimensions"] = [item.strip() for item in dimensions.split(",") if item.strip()]

    expected_scope = os.getenv("LITREVIEW_SCOPE_CURRENT")
    expected_dimensions = [
        item.strip()
        for item in os.getenv("LITREVIEW_DIMENSIONS_CURRENT", "").split(",")
        if item.strip()
    ]
    v2_contract_matches = (
        (not expected_scope or e.get("scope") == expected_scope)
        and (
            not expected_dimensions
            or (
                isinstance(e.get("dimensions"), list)
                and len(e["dimensions"]) == len(expected_dimensions)
                and set(map(str, e["dimensions"])) == set(expected_dimensions)
            )
        )
    )
    if e["schema_version"] >= 2 and (
        not v2_contract_matches
        or not valid_manifest_entry(
            e, e["schema_version"], str(e.get("track") or "")
        )
    ):
        return {
            "_saved_path": None,
            "error": (
                "schema-v2 literature entries require track, supported scope, "
                "dimensions, relevance_by_dimension for every listed dimension, "
                "interaction_evidence, method, and source; scope and dimensions "
                "must match the assigned track"
            ),
        }

    identity = entry_identity(e)
    if identity is not None:
        for existing in read_lit_entries():
            if entry_identity(existing) == identity:
                return {
                    **existing,
                    "_saved_path": f"existing:{existing.get('id', identity)}",
                    "_duplicate": True,
                }
    eid = uuid.uuid4().hex
    e["id"] = eid
    e["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(e.get("method") or "entry"))[:48]
    p = d / f"{eid}_{safe}.json"
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(e, f, indent=2, default=str)
    tmp.rename(p)
    e["_saved_path"] = str(p)
    return e


def read_lit_entries() -> list[dict[str, Any]]:
    """Load the legacy or manifested baseline plus this team's own additions."""
    directories = _baseline_lit_dirs()
    team_dir = _lit_dir()
    axis_dir = _axis_lit_dir()
    if team_dir is not None and not (
        _manifest() is not None and axis_dir is not None
        and team_dir.resolve() == axis_dir.resolve()
    ):
        directories.append(team_dir)
    return _read_dirs(directories)


def count() -> int:
    """Count entries with the same validation and ID de-duplication as reads."""
    return len(read_lit_entries())


def baseline_ready(min_entries: int) -> bool:
    """Validate total legacy coverage or every track in a composed manifest."""
    manifest = _manifest()
    if manifest is None:
        configured_dimensions = [
            item.strip()
            for item in os.getenv("LITREVIEW_DIMENSIONS", "").split(",")
            if item.strip()
        ]
        if len(configured_dimensions) > 1:
            return False
        return len(_read_dirs(_baseline_lit_dirs())) >= min_entries

    path, payload = manifest
    if payload.get("complete") is not True:
        return False
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, int) or schema_version < 2:
        return False
    expected_prompt = os.getenv(
        "LITREVIEW_PROMPT_VERSION", "multi-dimensional-v1"
    )
    if payload.get("prompt_version") != expected_prompt:
        return False
    tracks = payload.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        return False
    directories: list[Path] = []
    for track in tracks:
        if not isinstance(track, dict) or not track.get("directory"):
            return False
        directory = Path(str(track["directory"]))
        if not directory.is_absolute():
            directory = path.parent / directory
        directory = directory.resolve()
        directories.append(directory)
        entries = _read_dirs([directory])
        entries = [
            entry for entry in entries
            if valid_manifest_entry(entry, schema_version, str(track.get("name")))
        ]
        if len(entries) < int(track.get("min_entries", 1)):
            return False
    return len(_read_dirs(directories)) >= min_entries
