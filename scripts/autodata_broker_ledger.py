#!/usr/bin/env python3
"""Atomically retain and restore a campaign-scoped AutoData broker ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "aar.autodata.broker-ledger-snapshot/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify(path: Path) -> None:
    with sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True) as connection:
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RuntimeError("broker ledger quick_check failed")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("broker ledger integrity_check failed")


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.chmod(0o600)
        _fsync_file(temporary)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def snapshot(source: Path, retained: Path) -> bool:
    if not source.is_file():
        return False
    retained.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = retained.with_name(f".{retained.name}.tmp.{os.getpid()}")
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_db:
            with sqlite3.connect(temporary) as destination_db:
                source_db.backup(destination_db)
        _verify(temporary)
        digest = _sha256(temporary)
        size_bytes = temporary.stat().st_size
        temporary.chmod(0o600)
        _fsync_file(temporary)
        os.replace(temporary, retained)
        _fsync_directory(retained.parent)
        _atomic_json(
            retained.with_name(f"{retained.name}.snapshot.json"),
            {
                "schema": SCHEMA,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "sha256": digest,
                "size_bytes": size_bytes,
            },
        )
        return True
    finally:
        temporary.unlink(missing_ok=True)


def restore(retained: Path, destination: Path) -> bool:
    if not retained.is_file():
        return False
    if retained.is_symlink():
        raise RuntimeError("retained broker ledger must not be a symlink")
    manifest_path = retained.with_name(f"{retained.name}.snapshot.json")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RuntimeError("retained broker ledger is missing its snapshot manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != SCHEMA
        or manifest.get("sha256") != _sha256(retained)
        or manifest.get("size_bytes") != retained.stat().st_size
    ):
        raise RuntimeError("retained broker ledger snapshot digest does not match")
    _verify(retained)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    try:
        with sqlite3.connect(
            f"file:{retained}?mode=ro&immutable=1", uri=True
        ) as source_db:
            with sqlite3.connect(temporary) as destination_db:
                source_db.backup(destination_db)
        _verify(temporary)
        temporary.chmod(0o600)
        _fsync_file(temporary)
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("snapshot", "restore"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--retained", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.command == "snapshot":
        if args.source is None or args.destination is not None:
            parser.error("snapshot requires --source and forbids --destination")
        result = snapshot(args.source, args.retained)
    else:
        if args.destination is None or args.source is not None:
            parser.error("restore requires --destination and forbids --source")
        result = restore(args.retained, args.destination)
    print(json.dumps({args.command: result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
