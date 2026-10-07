"""Verified loading of Autodata artifacts for an approved AAR training run."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA = "aar.autodata.dataset/v1"


def load_autodata_dataset(run_id: str | None = None) -> list[dict[str, Any]]:
    """Load rows only after verifying their run binding, pipeline pin, and digest."""
    resolved_run_id = run_id or os.getenv("AAR_CURRENT_RUN_ID", "")
    if not resolved_run_id:
        raise ValueError("run_id or AAR_CURRENT_RUN_ID is required")
    team_dir = os.getenv("TEAM_DIR", "")
    if not team_dir:
        raise ValueError("TEAM_DIR is required")
    artifact_dir = Path(team_dir).resolve() / "autodata" / resolved_run_id
    rows_path = artifact_dir / "autodata_rows.jsonl"
    manifest_path = artifact_dir / "autodata_manifest.json"
    if not rows_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"verified Autodata artifacts are missing for run {resolved_run_id}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unexpected Autodata manifest schema: {manifest.get('schema')!r}")
    if manifest.get("run_id") != resolved_run_id:
        raise ValueError("Autodata manifest run_id does not match the training run")
    expected_sha = os.getenv("AAR_AUTODATA_SHA", "").lower()
    if not expected_sha or str(manifest.get("pipeline_sha", "")).lower() != expected_sha:
        raise ValueError("Autodata manifest pipeline SHA does not match AAR_AUTODATA_SHA")
    payload = rows_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if manifest.get("dataset_sha256") != digest:
        raise ValueError("Autodata dataset digest does not match its manifest")
    rows = [json.loads(line) for line in payload.decode().splitlines() if line.strip()]
    if manifest.get("row_count") != len(rows):
        raise ValueError("Autodata dataset row count does not match its manifest")
    if not rows:
        raise ValueError("Autodata dataset is empty")
    return rows
