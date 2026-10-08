"""Resolve the operator-pinned native AutoData Claude plugin.

This module deliberately does not wrap AutoData operations.  The research
agent loads the upstream plugin and invokes its bundled ``autodata`` CLI
directly through Bash.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_TRUE = frozenset({"1", "true", "yes", "on"})
_REQUIRED_PLUGIN_FILES = (
    Path(".claude-plugin/plugin.json"),
    Path("skills/autodata/SKILL.md"),
    Path("scripts/autodata.py"),
    Path("scripts/bootstrap.py"),
    Path("wheels/wheels.lock.json"),
)


def autodata_plugin_enabled() -> bool:
    """Return whether the native AutoData plugin is enabled for this run."""
    return os.getenv("AAR_AUTODATA", "0").strip().lower() in _TRUE


def _git(checkout: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(checkout), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@dataclass(frozen=True)
class AutoDataPlugin:
    """Validated native plugin selected by the trusted launcher."""

    root: Path
    checkout: Path
    git_sha: str

    def sdk_config(self) -> dict[str, str]:
        return {"type": "local", "path": str(self.root)}


def resolve_autodata_plugin() -> AutoDataPlugin | None:
    """Validate and return the configured native plugin.

    AutoData remains the implementation and source of workflow instructions.
    AAR verifies only which immutable checkout is loaded into the SDK.
    """
    if not autodata_plugin_enabled():
        return None

    configured = os.getenv("AAR_AUTODATA_PLUGIN_ROOT", "").strip()
    if not configured:
        raise RuntimeError(
            "AAR_AUTODATA=1 requires AAR_AUTODATA_PLUGIN_ROOT"
        )
    raw_root = Path(configured).expanduser()
    if raw_root.is_symlink():
        raise RuntimeError("AAR_AUTODATA_PLUGIN_ROOT must not be a symlink")
    try:
        root = raw_root.resolve(strict=True)
    except FileNotFoundError as error:
        raise RuntimeError("AAR_AUTODATA_PLUGIN_ROOT does not exist") from error
    if not root.is_dir():
        raise RuntimeError("AAR_AUTODATA_PLUGIN_ROOT must be a directory")

    checkout = root.parent.parent
    try:
        relative = root.relative_to(checkout)
    except ValueError as error:
        raise RuntimeError("AutoData plugin is outside its checkout") from error
    if relative != Path("plugin/autodata"):
        raise RuntimeError(
            "AAR_AUTODATA_PLUGIN_ROOT must be <checkout>/plugin/autodata"
        )

    for relative_path in _REQUIRED_PLUGIN_FILES:
        path = root / relative_path
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(
                f"AutoData plugin file is missing or unsafe: {relative_path}"
            )
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(
                f"AutoData plugin contains a symlink: {path.relative_to(root)}"
            )

    try:
        manifest: Any = json.loads(
            (root / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("AutoData plugin manifest is unreadable") from error
    if not isinstance(manifest, dict) or manifest.get("name") != "autodata":
        raise RuntimeError("AutoData plugin manifest must declare name=autodata")
    if "./skills/" not in manifest.get("skills", []):
        raise RuntimeError("AutoData plugin manifest does not publish its skills")

    try:
        branch = _git(checkout, "branch", "--show-current")
        git_sha = _git(checkout, "rev-parse", "HEAD").lower()
        dirty = _git(checkout, "status", "--porcelain", "--", "plugin/autodata")
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("AutoData plugin checkout is not a readable Git checkout") from error
    if branch != "main":
        raise RuntimeError(f"AutoData plugin checkout must be on main, found {branch!r}")
    if dirty:
        raise RuntimeError("AutoData plugin directory has uncommitted changes")

    expected_sha = os.getenv("AAR_AUTODATA_SHA", "").strip().lower()
    if len(expected_sha) != 40 or any(c not in "0123456789abcdef" for c in expected_sha):
        raise RuntimeError("AAR_AUTODATA_SHA must be a full Git SHA")
    if git_sha != expected_sha:
        raise RuntimeError(
            f"AutoData plugin SHA mismatch: expected {expected_sha}, found {git_sha}"
        )

    return AutoDataPlugin(root=root, checkout=checkout, git_sha=git_sha)
