"""Fail-closed Kimi hook that confines direct file editing to AAR outputs."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping


EDIT_TOOLS = {"Write", "Edit"}


def _resolved_path(value: str, cwd: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path.resolve(strict=False)


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def validate_tool_call(
    payload: Mapping[str, Any], env: Mapping[str, str]
) -> tuple[bool, str]:
    """Return whether a Kimi lifecycle-hook payload may proceed."""
    tool_name = payload.get("tool_name")
    if tool_name not in EDIT_TOOLS:
        return True, ""

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return False, f"{tool_name} denied: missing tool input"
    raw_path = tool_input.get("path") or tool_input.get("file_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return False, f"{tool_name} denied: missing destination path"

    raw_cwd = payload.get("cwd")
    cwd = Path(raw_cwd if isinstance(raw_cwd, str) and raw_cwd else os.getcwd())
    try:
        destination = _resolved_path(raw_path, cwd)
        ideas_value = env.get("AAR_IDEAS_DIR", "").strip()
        memory_value = env.get("AAR_AGENT_LOG_PATH", "").strip()
        if not ideas_value or not memory_value:
            return False, (
                f"{tool_name} denied: AAR write boundaries are not configured"
            )
        ideas_dir = _resolved_path(ideas_value, cwd)
        memory_file = _resolved_path(memory_value, cwd)
    except (OSError, RuntimeError, ValueError) as error:
        return False, f"{tool_name} denied: cannot resolve destination ({error})"

    if destination == memory_file or _is_within(destination, ideas_dir):
        return True, ""
    return False, (
        f"{tool_name} denied outside AAR_IDEAS_DIR and AAR_AGENT_LOG_PATH: "
        f"{destination}"
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Kimi Write/Edit denied: invalid hook input ({error})", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("Kimi Write/Edit denied: hook input must be an object", file=sys.stderr)
        return 2
    allowed, reason = validate_tool_call(payload, os.environ)
    if allowed:
        return 0
    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
