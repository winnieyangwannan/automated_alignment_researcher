#!/usr/bin/env python3
"""Prepare the pinned public inputs used by llm_uncertainty_bench.

The benchmark author's Hugging Face dataset repository mirrors the data from
smartyfh/LLM-Uncertainty-Bench.  Pinning the immutable dataset revision and the
two file digests keeps suite publication independent of a mutable branch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY = "https://github.com/smartyfh/LLM-Uncertainty-Bench"
MIRROR_REPOSITORY = "https://huggingface.co/datasets/ErikYip/LLM-Uncertainty-Bench"
REVISION = "a199e02b65c6696c467501f01beeb8de9c719916"
FILES = {
    "cosmosqa_10k.json": {
        "sha256": "84c2f3f2916e0a523ef71d64927354b35688642712951691541a59a421a4847f",
        "size_bytes": 8_398_607,
        "item_count": 10_000,
    },
    "hellaswag_10k.json": {
        "sha256": "24a31b2cb77a288822adde563e780adacd25fe80c3ef65d6e56c4c19ccbb5e51",
        "size_bytes": 11_119_667,
        "item_count": 10_000,
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate(path: Path, expected: dict[str, Any]) -> None:
    if not path.is_file():
        raise SystemExit(f"required source file is missing: {path}")
    actual_size = path.stat().st_size
    if actual_size != expected["size_bytes"]:
        raise SystemExit(
            f"size mismatch for {path}: {actual_size} != {expected['size_bytes']}"
        )
    actual_sha = _sha256(path)
    if actual_sha != expected["sha256"]:
        raise SystemExit(
            f"sha256 mismatch for {path}: {actual_sha} != {expected['sha256']}"
        )
    try:
        rows = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid JSON source file {path}: {error}") from error
    if not isinstance(rows, list) or len(rows) != expected["item_count"]:
        raise SystemExit(
            f"item-count mismatch for {path}: "
            f"{len(rows) if isinstance(rows, list) else 'not-a-list'} "
            f"!= {expected['item_count']}"
        )


def _download(destination: Path, name: str) -> None:
    url = f"{MIRROR_REPOSITORY}/resolve/{REVISION}/{name}"
    request = urllib.request.Request(url, headers={"User-Agent": "aar-data-preparer/1"})
    with urllib.request.urlopen(request, timeout=300) as response:
        with destination.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_repository": REPOSITORY,
        "distribution_mirror": MIRROR_REPOSITORY,
        "revision": REVISION,
        "files": FILES,
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
    }


def prepare(output_root: Path, *, verify_only: bool) -> None:
    data_dir = output_root / "data"
    manifest_path = output_root / ".aar-source.json"

    if verify_only:
        for name, expected in FILES.items():
            _validate(data_dir / name, expected)
        if not manifest_path.is_file():
            raise SystemExit(f"source manifest is missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("revision") != REVISION or manifest.get("files") != FILES:
            raise SystemExit(f"source manifest does not match the pinned inputs: {manifest_path}")
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return

    output_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        destination = data_dir / name
        if destination.exists():
            _validate(destination, expected)
            continue
        with tempfile.NamedTemporaryFile(
            prefix=f".{name}.", suffix=".tmp", dir=data_dir, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            _download(temporary_path, name)
            _validate(temporary_path, expected)
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)

    for name, expected in FILES.items():
        _validate(data_dir / name, expected)
    manifest = _manifest()
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=".aar-source.",
        suffix=".tmp",
        dir=output_root,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(manifest, temporary, indent=2, sort_keys=True)
        temporary.write("\n")
    try:
        os.replace(temporary_path, manifest_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(json.dumps(manifest, indent=2, sort_keys=True))


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=repository_root / "data" / "LLM-Uncertainty-Bench",
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    prepare(args.output_root.resolve(), verify_only=args.verify_only)


if __name__ == "__main__":
    main()
