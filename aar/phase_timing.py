"""Structured, append-only phase timing for AAR research and evaluation jobs."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from functools import wraps
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import (
    Any,
    Awaitable,
    Callable,
    Iterator,
    Mapping,
    ParamSpec,
    Sequence,
    TypeVar,
)


SCHEMA_VERSION = 1
REQUIRED_METHOD_PHASES = (
    "data_generation",
    "tokenization",
    "model_loading",
    "training",
    "checkpoint_save",
)
_PHASE_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_P = ParamSpec("_P")
_R = TypeVar("_R")


def _utc_iso(timestamp_ns: int) -> str:
    return (
        datetime.fromtimestamp(timestamp_ns / 1_000_000_000, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _resolve_path(path: str | Path | None) -> Path | None:
    value = str(path or os.getenv("AAR_PHASE_TIMINGS_PATH", "")).strip()
    return Path(value) if value else None


def record_phase(
    phase_name: str,
    duration_seconds: float,
    *,
    status: str = "success",
    path: str | Path | None = None,
    started_at_ns: int | None = None,
    ended_at_ns: int | None = None,
    metadata: Mapping[str, Any] | None = None,
    echo: bool = True,
) -> dict[str, Any]:
    """Append one structured timing event and emit a compact log marker."""
    if not _PHASE_RE.fullmatch(phase_name):
        raise ValueError(f"invalid phase name: {phase_name!r}")
    if status not in {"success", "failure"}:
        raise ValueError(f"invalid phase status: {status!r}")
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be nonnegative")

    end_ns = ended_at_ns if ended_at_ns is not None else time.time_ns()
    start_ns = (
        started_at_ns
        if started_at_ns is not None
        else end_ns - round(duration_seconds * 1_000_000_000)
    )
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "phase": phase_name,
        "status": status,
        "started_at": _utc_iso(start_ns),
        "ended_at": _utc_iso(end_ns),
        "duration_seconds": round(float(duration_seconds), 6),
    }
    for key, env_name in (
        ("run_id", "AAR_CURRENT_RUN_ID"),
        ("team_id", "AAR_TEAM_ID"),
        ("session_id", "AAR_CURRENT_SESSION_ID"),
        ("slurm_job_id", "SLURM_JOB_ID"),
    ):
        value = os.getenv(env_name)
        if value:
            event[key] = value
    if metadata:
        event["metadata"] = dict(metadata)

    destination = _resolve_path(path)
    payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    if echo:
        print(f"[timing] {payload}", flush=True)
    return event


@contextmanager
def phase(
    phase_name: str,
    *,
    path: str | Path | None = None,
    metadata: Mapping[str, Any] | None = None,
    echo: bool = True,
) -> Iterator[None]:
    """Time a block and record success or failure without swallowing errors."""
    started_at_ns = time.time_ns()
    started = time.perf_counter()
    try:
        yield
    except BaseException as error:
        record_phase(
            phase_name,
            time.perf_counter() - started,
            status="failure",
            path=path,
            started_at_ns=started_at_ns,
            metadata={**dict(metadata or {}), "error_type": type(error).__name__},
            echo=echo,
        )
        raise
    else:
        record_phase(
            phase_name,
            time.perf_counter() - started,
            path=path,
            started_at_ns=started_at_ns,
            metadata=metadata,
            echo=echo,
        )


def timed_async_phase(
    phase_name: str,
) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    """Decorate an async operation with the same failure-preserving timer."""

    def decorator(
        function: Callable[_P, Awaitable[_R]],
    ) -> Callable[_P, Awaitable[_R]]:
        @wraps(function)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            with phase(phase_name):
                return await function(*args, **kwargs)

        return wrapper

    return decorator


def successful_phases(path: str | Path) -> set[str]:
    result: set[str] = set()
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("status") == "success" and isinstance(event.get("phase"), str):
            result.add(event["phase"])
    return result


def require_successful_phases(
    path: str | Path,
    required: Sequence[str] = REQUIRED_METHOD_PHASES,
) -> None:
    """Fail closed when a generated method omitted required timing boundaries."""
    timing_path = Path(path)
    observed = successful_phases(timing_path) if timing_path.is_file() else set()
    missing = [name for name in required if name not in observed]
    if missing:
        raise RuntimeError(
            "method omitted required successful phase timings: " + ", ".join(missing)
        )


def _main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)

    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--path", required=True)
    record_parser.add_argument("--phase", required=True)
    record_parser.add_argument("--duration-seconds", required=True, type=float)
    record_parser.add_argument(
        "--status", choices=("success", "failure"), default="success"
    )

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--path", required=True)
    run_parser.add_argument("--phase", required=True)
    run_parser.add_argument("command", nargs=argparse.REMAINDER)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--path", required=True)
    validate_parser.add_argument(
        "--required", nargs="+", default=list(REQUIRED_METHOD_PHASES)
    )

    args = parser.parse_args()
    if args.action == "record":
        record_phase(
            args.phase,
            args.duration_seconds,
            status=args.status,
            path=args.path,
        )
        return 0
    if args.action == "validate":
        require_successful_phases(args.path, args.required)
        return 0

    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("run requires a command after --")
    started_at_ns = time.time_ns()
    started = time.perf_counter()
    completed = subprocess.run(command, check=False)
    record_phase(
        args.phase,
        time.perf_counter() - started,
        status="success" if completed.returncode == 0 else "failure",
        path=args.path,
        started_at_ns=started_at_ns,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(_main())
