"""Durable Slurm submission intents and fail-closed terminal classification."""

from __future__ import annotations

import argparse
import json
import os
import secrets
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
    "NODE_FAIL",
    "PREEMPTED",
    "REVOKED",
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


def _effective_exit_code(value: str) -> int | None:
    fields = value.strip().split(":", maxsplit=1)
    if len(fields) != 2 or any(not field.isdigit() for field in fields):
        return None
    status, signal = (int(field) for field in fields)
    return status if status else (128 + signal if signal else 0)


def reconcile_session_result(
    path: Path,
    *,
    job_id: str,
    slurm_state: str,
    slurm_exit_code: str,
) -> dict[str, object]:
    """Make authoritative sacct termination override an optimistic EXIT trap."""

    if not job_id.isdigit():
        raise ValueError("research session job ID must be numeric")
    terminal = classify_state(slurm_state)
    if not terminal.terminal:
        raise ValueError("cannot reconcile a nonterminal Slurm state")
    process_result: dict[str, object] | None = None
    if path.is_file() and not path.is_symlink():
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            candidate = None
        if isinstance(candidate, dict):
            if candidate.get("schema") == "aar.research-session-result/v2":
                prior = candidate.get("process_result")
                process_result = prior if isinstance(prior, dict) else None
            else:
                process_result = candidate
    category = (
        "completed"
        if terminal.successful
        else f"slurm_{terminal.state.lower()}"
    )
    result: dict[str, object] = {
        "schema": "aar.research-session-result/v2",
        "status": "completed" if terminal.successful else "failed",
        "job_id": job_id,
        "category": category,
        "retryable": terminal.retryable,
        "slurm_state": terminal.state,
        "slurm_exit_code": slurm_exit_code,
        "exit_code": _effective_exit_code(slurm_exit_code),
        "terminal_source": "sacct",
        "process_result": process_result,
        "reconciled_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(path, result)
    return result


def _atomic_write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = os.open(
        path.parent,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary_name = f".{path.name}.tmp.{secrets.token_hex(16)}"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
        os.fsync(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


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

    reconcile = subparsers.add_parser("reconcile-result")
    reconcile.add_argument("--path", type=Path, required=True)
    reconcile.add_argument("--job-id", required=True)
    reconcile.add_argument("--state", required=True)
    reconcile.add_argument("--exit-code", required=True)

    args = parser.parse_args()
    if args.command == "classify":
        _emit(classify_state(args.state).__dict__)
    elif args.command == "prepare":
        _emit(prepare_intent(args.path, key=args.key, comment=args.comment))
    elif args.command == "transition":
        _emit(transition_intent(args.path, status=args.status, job_id=args.job_id))
    elif args.command == "show":
        _emit(read_intent(args.path))
    elif args.command == "count-registered":
        registered = 0
        if args.directory.is_dir():
            for path in args.directory.glob("*.json"):
                if read_intent(path).get("status") == "registered":
                    registered += 1
        print(registered)
    else:
        _emit(
            reconcile_session_result(
                args.path,
                job_id=args.job_id,
                slurm_state=args.state,
                slurm_exit_code=args.exit_code,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
