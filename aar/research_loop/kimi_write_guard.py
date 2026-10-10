"""Fail-closed Kimi hook that confines direct file editing to AAR outputs."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping


EDIT_TOOLS = {"Write", "Edit"}
ACTION_ID_PATTERN = re.compile(r"act_[0-9a-f]{24}")


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


def _allowed_action_path(
    destination: Path,
    lexical_destination: Path,
    env: Mapping[str, str],
) -> bool:
    """Allow only paths delegated by one live native AutoData action."""
    state_value = env.get("AAR_AUTODATA_STATE", "").strip()
    if not state_value:
        return False
    state = Path(state_value).expanduser()
    if state.is_symlink() or not state.is_file():
        return False
    try:
        with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT id,specJson FROM actions WHERE status='in_progress' "
                "ORDER BY createdAt,id"
            ).fetchall()
    except sqlite3.Error:
        return False

    result_match = re.fullmatch(
        r"aar-autodata-(act_[0-9a-f]{24})-result\.json", destination.name
    )
    if destination.parent == Path("/tmp").resolve() and result_match is not None:
        return any(
            isinstance(action_id, str)
            and ACTION_ID_PATTERN.fullmatch(action_id) is not None
            and action_id == result_match.group(1)
            for action_id, _ in rows
        )

    if destination.is_symlink():
        return False
    for action_id, spec_raw in rows:
        if (
            not isinstance(action_id, str)
            or ACTION_ID_PATTERN.fullmatch(action_id) is None
        ):
            continue
        try:
            spec = json.loads(str(spec_raw))
        except json.JSONDecodeError:
            continue
        if not isinstance(spec, dict):
            continue
        root_raw = spec.get("editable_root")
        allowed_paths = spec.get("allowed_paths")
        if not isinstance(root_raw, str) or not isinstance(allowed_paths, list):
            continue
        root_path = Path(root_raw).expanduser()
        if root_path.is_symlink() or not root_path.is_dir():
            continue
        try:
            root = root_path.resolve(strict=True)
            relative = destination.relative_to(root)
            lexical_relative = lexical_destination.relative_to(root)
        except (OSError, ValueError):
            continue
        if lexical_relative != relative:
            continue
        if not relative.parts or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            continue
        unsafe_component = False
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                unsafe_component = True
                break
        if unsafe_component:
            continue
        relative_text = relative.as_posix()
        for pattern in allowed_paths:
            if not isinstance(pattern, str):
                continue
            if pattern == "**":
                return True
            if pattern.endswith("/**"):
                prefix = Path(pattern[:-3])
                if prefix.is_absolute() or ".." in prefix.parts:
                    continue
                try:
                    nested = relative.relative_to(prefix)
                except ValueError:
                    continue
                if nested.parts:
                    return True
            elif Path(pattern).is_absolute() or ".." in Path(pattern).parts:
                continue
            elif relative_text == Path(pattern).as_posix():
                return True
    return False


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
        lexical_destination = Path(raw_path).expanduser()
        if not lexical_destination.is_absolute():
            lexical_destination = cwd / lexical_destination
        lexical_destination = Path(os.path.abspath(lexical_destination))
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

    if (
        destination == memory_file
        or _is_within(destination, ideas_dir)
        or _allowed_action_path(destination, lexical_destination, env)
    ):
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
