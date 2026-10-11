"""Durable Slurm submission intents and fail-closed terminal classification."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA = "aar.slurm.submission-intent/v1"

_TERMINAL_STATES = {
    "BOOT_FAIL",
    "CANCELLED",
    "COMPLETED",
    "DEADLINE",
    "FAILED",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "REVOKED",
    "TIMEOUT",
}
_RETRYABLE_INFRASTRUCTURE_STATES = {
    "BOOT_FAIL",
    "DEADLINE",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "REVOKED",
    "TIMEOUT",
}


@dataclass(frozen=True)
class TerminalResult:
    state: str
    terminal: bool
    successful: bool
    retryable: bool
    category: str


def normalize_state(value: str) -> str:
    """Normalize sacct's decorated states without guessing an empty state."""

    fields = value.strip().split(maxsplit=1)
    if not fields:
        return ""
    state = fields[0].rstrip("+")
    if state.startswith("CANCELLED"):
        return "CANCELLED"
    return state


def classify_state(value: str) -> TerminalResult:
    state = normalize_state(value)
    if not state or state not in _TERMINAL_STATES:
        return TerminalResult(
            state=state or "UNKNOWN",
            terminal=False,
            successful=False,
            retryable=False,
            category="nonterminal_or_unknown",
        )
    if state == "COMPLETED":
        return TerminalResult(state, True, True, False, "completed")
    if state in _RETRYABLE_INFRASTRUCTURE_STATES:
        return TerminalResult(state, True, False, True, "infrastructure")
    return TerminalResult(state, True, False, False, "permanent")


def scheduler_comment_matches(comment: str, outputs: Iterable[str]) -> list[str]:
    """Return unique job IDs whose pipe-delimited scheduler comment is exact."""

    matches: set[str] = set()
    for output in outputs:
        for line in output.splitlines():
            fields = line.strip().split("|", maxsplit=2)
            if len(fields) >= 2 and fields[1] == comment and fields[0].isdigit():
                matches.add(fields[0])
    return sorted(matches, key=int)


def _atomic_write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.chmod(0o600)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def read_intent(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise RuntimeError(f"invalid Slurm submission intent: {path}")
    return value


def prepare_intent(path: Path, *, key: str, comment: str) -> dict[str, object]:
    if path.exists():
        value = read_intent(path)
        if value.get("key") != key or value.get("comment") != comment:
            raise RuntimeError(
                "submission intent identity changed across controller restart"
            )
        return value
    now = datetime.now(timezone.utc).isoformat()
    value: dict[str, object] = {
        "schema": SCHEMA,
        "key": key,
        "comment": comment,
        "status": "prepared",
        "created_at": now,
        "updated_at": now,
    }
    _atomic_write(path, value)
    return value


def transition_intent(
    path: Path, *, status: str, job_id: str | None = None
) -> dict[str, object]:
    if status not in {"submitting", "registered"}:
        raise ValueError(f"unsupported submission intent status: {status}")
    value = read_intent(path)
    current = value.get("status")
    if current == "registered" and status == "registered":
        if value.get("job_id") != job_id:
            raise RuntimeError("submission intent is already bound to another job")
        return value
    allowed = {
        "prepared": {"submitting"},
        "submitting": {"submitting", "registered"},
        "registered": {"registered"},
    }
    if status not in allowed.get(str(current), set()):
        raise RuntimeError(
            f"invalid submission intent transition: {current} -> {status}"
        )
    if status == "registered":
        if not job_id or not job_id.isdigit():
            raise ValueError("registered submission intent requires a numeric job ID")
        value["job_id"] = job_id
    value["status"] = status
    value["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(path, value)
    return value


def _emit(value: object) -> None:
    print(json.dumps(value, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify = subparsers.add_parser("classify")
    classify.add_argument("--state", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--path", type=Path, required=True)
    prepare.add_argument("--key", required=True)
    prepare.add_argument("--comment", required=True)

    transition = subparsers.add_parser("transition")
    transition.add_argument("--path", type=Path, required=True)
    transition.add_argument("--status", required=True)
    transition.add_argument("--job-id")

    show = subparsers.add_parser("show")
    show.add_argument("--path", type=Path, required=True)

    count = subparsers.add_parser("count-registered")
    count.add_argument("--directory", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "classify":
        _emit(classify_state(args.state).__dict__)
    elif args.command == "prepare":
        _emit(prepare_intent(args.path, key=args.key, comment=args.comment))
    elif args.command == "transition":
        _emit(transition_intent(args.path, status=args.status, job_id=args.job_id))
    elif args.command == "show":
        _emit(read_intent(args.path))
    else:
        registered = 0
        if args.directory.is_dir():
            for path in args.directory.glob("*.json"):
                if read_intent(path).get("status") == "registered":
                    registered += 1
        print(registered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
