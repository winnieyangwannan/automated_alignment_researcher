"""Host-owned, per-chain memory reconstructed from durable public artifacts.

The research model's editable ``AGENT_LOG`` is useful scratch space, but it is
not an authoritative lifecycle record.  This module maintains a separate
journal from the research-visible score, finding, proposal, and method-contract
channels.  One atomic event file is retained per deduplication key; the Markdown
view is derived and can always be rebuilt after an interrupted write.

This module deliberately never accepts an evaluator-private directory.  Score
entries use a small public-field allowlist, and failure entries discard raw
reason text, log paths, judge output, and all unknown fields.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import secrets
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Mapping
from zoneinfo import ZoneInfo

from aar.failure_feedback import (
    failure_guidance,
    safe_failure_feedback_view,
    sanitize_failure_summary,
)


SCHEMA = "aar.chain-memory-event/v1"
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9._-]+\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RUN_ID = re.compile(r"[A-Za-z0-9._-]{1,256}\Z")
_STAGE = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_PT_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}\Z"
)
_PT = ZoneInfo("America/Los_Angeles")
_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
_MAX_EVENT_BYTES = 128 * 1024
_HOST_BLOCK_START = "<!-- AAR HOST MEMORY START; controller-owned, do not edit -->"
_HOST_BLOCK_END = "<!-- AAR HOST MEMORY END -->"
_EVENT_KINDS = {"result", "method_contract", "proposal", "failure"}
_EVENT_SOURCES = {
    "result": "public_score_finding_join",
    "method_contract": "method_contract_validator",
    "proposal": "proposal_decision",
    "failure": "typed_failure",
}
_COMMON_EVENT_KEYS = {
    "schema", "chain_id", "dedupe_key", "recorded_at_pt", "kind", "source",
}
_RESULT_KEYS = {
    "run_id", "title", "method", "public_score", "key_tradeoffs",
    "results_summary", "limitations", "missing_for_reproduction",
}
_CONTRACT_KEYS = {"source_sha256", "method_name", "status", "errors"}
_CONTRACT_KEYS |= {"requirements", "requirements_sha256"}
_PROPOSAL_KEYS = {
    "idea_name", "title", "method", "code_sha256", "approved", "violations",
    "missing_for_reproduction", "error",
}
_FAILURE_KEYS = {
    "status", "stage", "error_code", "retryable", "disposition", "summary",
    "guidance", "exception_type", "exit_code", "count", "run_id",
}


class ChainMemoryIntegrityError(RuntimeError):
    """A path or immutable journal record violated the host-owned contract."""


def _now_pt() -> str:
    return datetime.now(_PT).isoformat(timespec="seconds")


def _bounded(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _is_safe_text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= limit
        and not any(ord(character) < 32 for character in value)
    )


def _is_safe_text_list(value: object, *, items: int, item_limit: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= items
        and all(_is_safe_text(item, item_limit) for item in value)
    )


def _is_safe_run_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and _RUN_ID.fullmatch(value) is not None
        and value not in {".", ".."}
        and Path(value).name == value
    )


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_for_render(value: object) -> object:
    """Recursively neutralize controller delimiters in all rendered event data."""

    if isinstance(value, str):
        return value.replace(_HOST_BLOCK_START, "[reserved host-memory start]").replace(
            _HOST_BLOCK_END, "[reserved host-memory end]"
        )
    if isinstance(value, list):
        return [_safe_for_render(item) for item in value]
    if isinstance(value, dict):
        return {key: _safe_for_render(item) for key, item in value.items()}
    return value


def _agent_scratch_without_host_fragments(content: str) -> str:
    """Remove complete host blocks and reserved delimiter fragments.

    An unmatched delimiter can be left by an interrupted atomic-write recovery or
    by model editing.  Text outside a complete block is conservatively retained as
    scratch because it cannot safely be classified as controller-owned.
    """

    pieces: list[str] = []
    cursor = 0
    while cursor < len(content):
        start = content.find(_HOST_BLOCK_START, cursor)
        end = content.find(_HOST_BLOCK_END, cursor)
        if start < 0 and end < 0:
            pieces.append(content[cursor:])
            break
        if end >= 0 and (start < 0 or end < start):
            pieces.append(content[cursor:end])
            cursor = end + len(_HOST_BLOCK_END)
            continue
        pieces.append(content[cursor:start])
        matching_end = content.find(_HOST_BLOCK_END, start + len(_HOST_BLOCK_START))
        if matching_end < 0:
            cursor = start + len(_HOST_BLOCK_START)
        else:
            cursor = matching_end + len(_HOST_BLOCK_END)
    return "".join(pieces)


def _safe_component(value: str, *, name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not safe or _SAFE_COMPONENT.fullmatch(safe) is None:
        raise ValueError(f"{name} does not contain a safe path component")
    return safe[:160]


def _read_regular_json(path: Path, *, parent: Path) -> dict[str, Any] | None:
    """Read a direct-child regular JSON file without following symlinks."""

    try:
        if path.is_symlink():
            raise ChainMemoryIntegrityError(f"refusing symlink artifact: {path.name}")
        if path.parent.resolve(strict=True) != parent.resolve(strict=True):
            raise ChainMemoryIntegrityError(f"artifact escaped its public directory: {path.name}")
        if not path.is_file():
            return None
        if path.stat().st_size > _MAX_ARTIFACT_BYTES:
            raise ChainMemoryIntegrityError(f"artifact exceeds size limit: {path.name}")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_write(path: Path, content: str, *, mode: int = 0o600) -> None:
    if path.exists() and path.is_symlink():
        raise ChainMemoryIntegrityError(f"refusing symlink journal target: {path.name}")
    directory = path.parent
    directory_fd = os.open(
        directory,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary = f".{path.name}.tmp.{secrets.token_hex(16)}"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


class ChainMemoryJournal:
    """Atomic event journal for one research chain inside one team directory."""

    def __init__(
        self,
        team_dir: str | Path,
        *,
        chain_id: str,
        idea_uid: str | None = None,
        forum_dir: str | Path | None = None,
    ) -> None:
        requested_team = Path(team_dir)
        if requested_team.is_symlink():
            raise ChainMemoryIntegrityError("TEAM_DIR may not be a symlink")
        self.team_dir = requested_team.resolve(strict=True)
        self.chain_id = str(chain_id)
        if _SAFE_COMPONENT.fullmatch(self.chain_id) is None or len(self.chain_id) > 160:
            raise ValueError("chain_id must be a safe, unambiguous component")
        self.chain_tag = _safe_component(self.chain_id, name="chain_id")
        self.method_chain_tag = (
            re.sub(r"[^A-Za-z0-9]+", "_", self.chain_id).strip("_") or "chain"
        )
        self.idea_uid = str(idea_uid or "")
        self.scores_dir = self.team_dir / "scores"
        requested_forum = (
            Path(forum_dir) if forum_dir is not None else self.team_dir / "forum"
        )
        if requested_forum.is_symlink():
            raise ChainMemoryIntegrityError("public forum directory may not be a symlink")
        self.forum_dir = requested_forum.resolve(strict=False)
        self.methods_dir = self.team_dir / "methods"
        self.root = self.team_dir / "host_memory" / self.chain_tag
        self.events_dir = self.root / "events"
        self.rendered_path = self.root / "journal.md"
        configured_agent_log = os.getenv("AAR_AGENT_LOG_PATH", "").strip()
        configured_logs_dir = (
            os.getenv("SESSION_LOGS_DIR", "").strip()
            or os.getenv("LOGS_DIR", "").strip()
        )
        if not configured_agent_log and not configured_logs_dir:
            self._prepare_directory(self.team_dir / "logs")
        self.agent_log_path = (
            Path(configured_agent_log)
            if configured_agent_log
            else Path(configured_logs_dir) / "AGENT_LOG.md"
            if configured_logs_dir
            else self.team_dir / "logs" / "AGENT_LOG.md"
        )
        self._prepare_directory(self.team_dir / "host_memory")
        self._prepare_directory(self.root)
        self._prepare_directory(self.events_dir)

    @classmethod
    def from_environment(
        cls,
        *,
        chain_id: str | None = None,
        idea_uid: str | None = None,
        fallback_team_dir: str | Path | None = None,
    ) -> "ChainMemoryJournal":
        team = os.getenv("TEAM_DIR", "").strip()
        if not team:
            if fallback_team_dir is None:
                raise ValueError("TEAM_DIR is required for host-owned chain memory")
            team = str(fallback_team_dir)
        return cls(
            team,
            chain_id=chain_id or os.getenv("IDEA_NAME", "chain"),
            idea_uid=idea_uid or os.getenv("IDEA_UID"),
            forum_dir=os.getenv("LOCAL_FINDINGS_DIR", "").strip() or None,
        )

    @staticmethod
    def _prepare_directory(path: Path) -> None:
        if path.exists() and path.is_symlink():
            raise ChainMemoryIntegrityError(f"refusing symlink journal directory: {path}")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise ChainMemoryIntegrityError(f"journal path is not a directory: {path}")
        os.chmod(path, 0o700)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        lock_path = self.root / ".lock"
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _belongs_to_chain(self, run_id: str, finding: Mapping[str, Any] | None = None) -> bool:
        if not _is_safe_run_id(run_id):
            return False
        finding_uid = finding.get("idea_uid") if finding else None
        if self.idea_uid and finding is not None and "idea_uid" in finding:
            # An artifact that declares an owner must match exactly.  Never let a
            # conflicting explicit UID fall through to the weaker legacy naming
            # heuristics below.
            return isinstance(finding_uid, str) and finding_uid == self.idea_uid
        prefixes = (f"{self.chain_id}-", f"{self.chain_id}__")
        if run_id.startswith(prefixes):
            return True
        session = finding.get("aar_session_id") if finding else None
        return isinstance(session, str) and f"_{self.method_chain_tag}_" in session

    def _event_path(self, dedupe_key: str) -> Path:
        return self.events_dir / f"{hashlib.sha256(dedupe_key.encode()).hexdigest()}.json"

    def _store_event(
        self,
        dedupe_key: str,
        payload: Mapping[str, Any],
        *,
        immutable: bool = False,
    ) -> bool:
        event = {
            **dict(payload),
            "schema": SCHEMA,
            "chain_id": self.chain_id,
            "dedupe_key": dedupe_key,
            "recorded_at_pt": _now_pt(),
        }
        event["source"] = _EVENT_SOURCES.get(str(event.get("kind")), "invalid")
        self._validate_event(self._event_path(dedupe_key), event)
        path = self._event_path(dedupe_key)
        existing = _read_regular_json(path, parent=self.events_dir)
        if path.exists() and existing is None:
            raise ChainMemoryIntegrityError(
                f"pre-existing chain-memory event is malformed: {path.name}"
            )
        if existing is not None:
            comparable = dict(existing)
            comparable.pop("recorded_at_pt", None)
            candidate = dict(event)
            candidate.pop("recorded_at_pt", None)
            if comparable == candidate:
                return False
            if immutable:
                raise ChainMemoryIntegrityError(
                    f"immutable chain-memory event changed: {dedupe_key}"
                )
        _atomic_write(path, json.dumps(event, indent=2, sort_keys=True) + "\n")
        return True

    def _validate_event(self, path: Path, value: Mapping[str, Any]) -> None:
        """Fail closed if an immutable event cannot be safely rendered."""

        dedupe = value.get("dedupe_key")
        kind = value.get("kind")
        if (
            value.get("schema") != SCHEMA
            or value.get("chain_id") != self.chain_id
            or not _is_safe_text(dedupe, 768)
            or any(ord(character) < 32 for character in dedupe)
            or path.name != f"{hashlib.sha256(dedupe.encode()).hexdigest()}.json"
            or kind not in _EVENT_KINDS
            or value.get("source") != _EVENT_SOURCES.get(kind)
            or not isinstance(value.get("recorded_at_pt"), str)
            or _PT_TIMESTAMP.fullmatch(value["recorded_at_pt"]) is None
        ):
            raise ChainMemoryIntegrityError(
                f"chain-memory event has an invalid envelope: {path.name}"
            )

        allowed = _COMMON_EVENT_KEYS | {
            "result": _RESULT_KEYS,
            "method_contract": _CONTRACT_KEYS,
            "proposal": _PROPOSAL_KEYS,
            "failure": _FAILURE_KEYS,
        }[kind]
        if set(value) - allowed:
            raise ChainMemoryIntegrityError(
                f"chain-memory event has unexpected fields: {path.name}"
            )

        valid = False
        if kind == "result":
            run_id = value.get("run_id")
            score = value.get("public_score")
            valid = (
                _is_safe_run_id(run_id)
                and dedupe == f"result:{run_id}"
                and _is_safe_text(value.get("title"), 300)
                and _is_safe_text(value.get("method"), 4000)
                and _is_safe_text(value.get("results_summary"), 4000)
                and _is_safe_text_list(value.get("key_tradeoffs"), items=3, item_limit=500)
                and _is_safe_text_list(value.get("limitations"), items=3, item_limit=500)
                and _is_safe_text_list(
                    value.get("missing_for_reproduction"), items=8, item_limit=500
                )
                and isinstance(score, dict)
                and set(score) <= {"headline_pct", "passes_filter", "passes_regression", "suite"}
                and isinstance(score.get("headline_pct"), (int, float))
                and not isinstance(score.get("headline_pct"), bool)
                and math.isfinite(score["headline_pct"])
                and all(
                    field not in score or isinstance(score[field], bool)
                    for field in ("passes_filter", "passes_regression")
                )
                and ("suite" not in score or _is_safe_text(score["suite"], 160))
            )
        elif kind == "method_contract":
            source_hash = value.get("source_sha256")
            requirements = value.get("requirements")
            requirements_hash = value.get("requirements_sha256")
            valid = (
                isinstance(source_hash, str)
                and _SHA256.fullmatch(source_hash) is not None
                and isinstance(requirements, dict)
                and set(requirements) == {
                    "run_dry_run",
                    "require_gemma4_targets",
                    "require_smoke_run",
                    "require_autodata_loader",
                }
                and all(isinstance(item, bool) for item in requirements.values())
                and isinstance(requirements_hash, str)
                and _SHA256.fullmatch(requirements_hash) is not None
                and requirements_hash == _digest(requirements)
                and dedupe == (
                    f"contract:{source_hash}:{requirements_hash}:{value.get('status')}"
                )
                and _is_safe_text(value.get("method_name"), 200)
                and value.get("status") in {"running", "passed", "failed"}
                and _is_safe_text_list(value.get("errors"), items=8, item_limit=500)
            )
        elif kind == "proposal":
            code_hash = value.get("code_sha256")
            proposal_verdict = {
                "approved": value.get("approved"),
                "violations": value.get("violations"),
                "missing_for_reproduction": value.get("missing_for_reproduction"),
                "error": value.get("error"),
            }
            proposal_identity = _digest(
                {
                    "idea_name": value.get("idea_name"),
                    "title": value.get("title"),
                    "method": value.get("method"),
                }
            )
            expected_dedupe = (
                f"proposal:{code_hash}:{proposal_identity}:{_digest(proposal_verdict)}"
            )
            valid = (
                dedupe == expected_dedupe
                and (code_hash == "missing" or (
                    isinstance(code_hash, str) and _SHA256.fullmatch(code_hash) is not None
                ))
                and isinstance(value.get("approved"), bool)
                and _is_safe_text(value.get("idea_name"), 200)
                and _is_safe_text(value.get("title"), 300)
                and _is_safe_text(value.get("method"), 2000)
                and _is_safe_text_list(value.get("violations"), items=8, item_limit=500)
                and _is_safe_text_list(
                    value.get("missing_for_reproduction"), items=8, item_limit=500
                )
                and (value.get("error") is None or _is_safe_text(value.get("error"), 500))
            )
        elif kind == "failure":
            run_id = value.get("run_id")
            identity = run_id or dedupe.removeprefix("failure:").split(":", 1)[0]
            valid = (
                value.get("status") == "failed"
                and isinstance(value.get("stage"), str)
                and _STAGE.fullmatch(value["stage"]) is not None
                and isinstance(value.get("error_code"), str)
                and _ERROR_CODE.fullmatch(value["error_code"]) is not None
                and isinstance(value.get("retryable"), bool)
                and value.get("disposition") in {"retry_operation", "advance_session", "halt"}
                and (run_id is None or _is_safe_run_id(run_id))
                and _SAFE_COMPONENT.fullmatch(identity) is not None
                and dedupe == f"failure:{identity}:{value['stage']}:{value['error_code']}"
                and _is_safe_text(value.get("summary"), 1000)
                and _is_safe_text(value.get("guidance"), 1000)
                and ("exception_type" not in value or _is_safe_text(value["exception_type"], 128))
                and all(
                    field not in value
                    or (isinstance(value[field], int) and not isinstance(value[field], bool))
                    for field in ("exit_code", "count")
                )
            )
        if not valid:
            raise ChainMemoryIntegrityError(
                f"chain-memory event failed strict validation: {path.name}"
            )

    @staticmethod
    def _result_sections(results_writeup: str) -> tuple[list[str], list[str]]:
        sentences = [
            _bounded(item, 500)
            for item in re.split(r"(?<=[.!?])\s+|\n+", results_writeup)
            if item.strip()
        ]
        tradeoff_terms = (
            "trade-off", "tradeoff", "improv", "increase", "decrease",
            "regress", "unchanged", "capability", "benchmark", "dimension",
        )
        limitation_terms = (
            "limit", "caveat", "failed", "failure", "did not", "only",
            "uncertain", "future", "unable",
        )
        tradeoffs = [s for s in sentences if any(term in s.lower() for term in tradeoff_terms)][:3]
        limitations = [s for s in sentences if any(term in s.lower() for term in limitation_terms)][:3]
        return tradeoffs, limitations

    def _result_event(
        self,
        run_id: str,
        score: Mapping[str, Any],
        finding: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        headline = score.get("headline_pct")
        if not isinstance(headline, (int, float)) or isinstance(headline, bool):
            return None
        writeup = _bounded(finding.get("results_writeup"), 4000)
        tradeoffs, limitations = self._result_sections(writeup)
        public_score: dict[str, Any] = {"headline_pct": float(headline)}
        for field in ("passes_filter", "passes_regression"):
            value = score.get(field)
            if isinstance(value, bool):
                public_score[field] = value
        suite = score.get("suite")
        if isinstance(suite, str):
            public_score["suite"] = _bounded(suite, 160)
        return {
            "kind": "result",
            "run_id": run_id,
            "title": _bounded(finding.get("title") or finding.get("idea_name"), 300),
            "method": _bounded(finding.get("method"), 4000),
            "public_score": public_score,
            "key_tradeoffs": tradeoffs,
            "results_summary": writeup,
            "limitations": limitations,
            "missing_for_reproduction": [
                _bounded(value, 500)
                for value in (
                    finding.get("missing_for_reproduction")
                    if isinstance(finding.get("missing_for_reproduction"), list)
                    else []
                )[:8]
            ],
        }

    def _reconcile_results(self) -> None:
        if self.scores_dir.is_symlink() or self.forum_dir.is_symlink():
            raise ChainMemoryIntegrityError("public score/forum directory may not be a symlink")
        if not self.scores_dir.is_dir():
            return
        if not self.forum_dir.is_dir():
            return
        findings: dict[str, tuple[Path, dict[str, Any]]] = {}
        for path in sorted(self.forum_dir.glob("*.json")):
            finding = _read_regular_json(path, parent=self.forum_dir)
            if not finding or finding.get("finding_type") != "result":
                continue
            run_id = finding.get("run_id")
            if not isinstance(run_id, str) or not self._belongs_to_chain(run_id, finding):
                continue
            findings.setdefault(run_id, (path, finding))
        for run_id, (finding_path, finding) in findings.items():
            score_path = self.scores_dir / f"{run_id}.json"
            score = _read_regular_json(score_path, parent=self.scores_dir)
            if score is None:
                continue
            event = self._result_event(
                run_id,
                score,
                finding,
            )
            if event is not None:
                self._store_event(f"result:{run_id}", event, immutable=True)

    def _reconcile_contracts(self) -> None:
        if self.methods_dir.is_symlink():
            raise ChainMemoryIntegrityError("public methods directory may not be a symlink")
        if not self.methods_dir.is_dir():
            return
        # Method package tags historically normalized both '-' and '_' to '_'.
        # Bind recovery to this chain's exact proposed code and method name
        # instead of treating that lossy tag as ownership evidence.
        owned_contracts = self._owned_proposal_contracts()
        if not owned_contracts:
            return
        prefix = f"{self.method_chain_tag}__"
        for method_dir in sorted(self.methods_dir.iterdir()):
            if method_dir.is_symlink():
                raise ChainMemoryIntegrityError(
                    f"method package may not be a symlink: {method_dir.name}"
                )
            if not method_dir.is_dir() or not method_dir.name.startswith(prefix):
                continue
            proof_path = method_dir / ".aar-method-contract.json"
            proof = _read_regular_json(proof_path, parent=method_dir)
            if not proof:
                continue
            source_hash = proof.get("source_sha256")
            status = proof.get("status")
            if not isinstance(source_hash, str) or _SHA256.fullmatch(source_hash) is None:
                continue
            if (source_hash, method_dir.name) not in owned_contracts:
                continue
            if status not in {"running", "passed", "failed"}:
                continue
            self._record_contract_unlocked(
                proof,
                expected_method_name=method_dir.name,
            )

    def _record_contract_unlocked(
        self,
        result: Mapping[str, Any],
        *,
        expected_method_name: str | None = None,
    ) -> bool:
        source_hash = result.get("source_sha256")
        status = result.get("status")
        if not isinstance(source_hash, str) or _SHA256.fullmatch(source_hash) is None:
            return False
        if status not in {"running", "passed", "failed"}:
            return False
        method_path = result.get("method_path")
        if not isinstance(method_path, str):
            return False
        resolved_method = Path(method_path).resolve(strict=False)
        try:
            resolved_method.relative_to(self.methods_dir.resolve(strict=True))
        except (OSError, ValueError):
            raise ChainMemoryIntegrityError("method contract path escaped TEAM_DIR/methods")
        method_name = expected_method_name or resolved_method.parent.name
        if not method_name.startswith(f"{self.method_chain_tag}__"):
            return False
        errors = result.get("errors") if isinstance(result.get("errors"), list) else []
        raw_requirements = (
            result.get("requirements")
            if isinstance(result.get("requirements"), Mapping)
            else {}
        )
        requirements = {
            name: raw_requirements.get(name) is True
            for name in (
                "run_dry_run",
                "require_gemma4_targets",
                "require_smoke_run",
                "require_autodata_loader",
            )
        }
        requirements_hash = _digest(requirements)
        return self._store_event(
            f"contract:{source_hash}:{requirements_hash}:{status}",
            {
                "kind": "method_contract",
                "source_sha256": source_hash,
                "requirements": requirements,
                "requirements_sha256": requirements_hash,
                "method_name": _bounded(method_name, 200),
                "status": status,
                "errors": [sanitize_failure_summary(value, limit=500) for value in errors[:8]],
            },
            immutable=True,
        )

    def record_contract(self, result: Mapping[str, Any]) -> bool:
        with self._locked():
            changed = self._record_contract_unlocked(result)
            self._refresh_views_unlocked()
            return changed

    def _owned_proposal_contracts(self) -> set[tuple[str, str]]:
        """Return exact ``(code hash, method name)`` proposal bindings."""

        owned = {
            (str(event["code_sha256"]), str(event["idea_name"]))
            for event in self._events()
            if event.get("kind") == "proposal"
            and isinstance(event.get("code_sha256"), str)
            and _SHA256.fullmatch(str(event["code_sha256"])) is not None
            and isinstance(event.get("idea_name"), str)
            and bool(event.get("idea_name"))
        }
        proposals = self.scores_dir / ".proposals"
        if (
            not self.idea_uid
            or not _is_safe_run_id(self.idea_uid)
            or not proposals.is_dir()
            or proposals.is_symlink()
        ):
            return owned
        marker_path = proposals / f"{self.idea_uid}.json"
        marker = _read_regular_json(marker_path, parent=proposals)
        if marker and marker.get("idea_uid") == self.idea_uid:
            code_hash = marker.get("code_hash")
            idea_name = marker.get("idea_name")
            if (
                isinstance(code_hash, str)
                and _SHA256.fullmatch(code_hash)
                and isinstance(idea_name, str)
                and idea_name
            ):
                owned.add((code_hash, idea_name))
        return owned

    def _reconcile_proposals(self) -> None:
        proposals = self.scores_dir / ".proposals"
        if proposals.is_symlink():
            raise ChainMemoryIntegrityError("proposal directory may not be a symlink")
        if (
            not proposals.is_dir()
            or not self.idea_uid
            or not _is_safe_run_id(self.idea_uid)
        ):
            return
        for path in (proposals / f"{self.idea_uid}.json",):
            marker = _read_regular_json(path, parent=proposals)
            if not marker:
                continue
            idea_uid = marker.get("idea_uid")
            if idea_uid != self.idea_uid:
                continue
            approved = marker.get("approved")
            code_hash = marker.get("code_hash")
            if (
                not isinstance(approved, bool)
                or not isinstance(code_hash, str)
                or _SHA256.fullmatch(code_hash) is None
            ):
                continue
            verdict = marker.get("verdict") if isinstance(marker.get("verdict"), dict) else {}
            self._record_proposal_unlocked(
                idea_name=marker.get("idea_name"),
                title=(marker.get("paper") or {}).get("title") if isinstance(marker.get("paper"), dict) else None,
                method=(marker.get("paper") or {}).get("method") if isinstance(marker.get("paper"), dict) else None,
                code_hash=code_hash,
                approved=approved,
                verdict=verdict,
            )

    def _reconcile_score_failures(self) -> None:
        if self.scores_dir.is_symlink():
            raise ChainMemoryIntegrityError("public scores directory may not be a symlink")
        if not self.scores_dir.is_dir():
            return
        for path in sorted(self.scores_dir.glob("*.failed.json")):
            payload = _read_regular_json(path, parent=self.scores_dir)
            if not payload or payload.get("schema_version") != 2 or payload.get("status") != "failed":
                continue
            run_id = payload.get("run_id")
            stage = payload.get("stage")
            error_code = payload.get("error_code")
            retryable = payload.get("retryable")
            disposition = payload.get("disposition")
            if (
                not _is_safe_run_id(run_id)
                or path.name != f"{run_id}.failed.json"
                or not isinstance(stage, str)
                or _STAGE.fullmatch(stage) is None
                or not isinstance(error_code, str)
                or _ERROR_CODE.fullmatch(error_code) is None
                or not isinstance(retryable, bool)
                or disposition not in {"retry_operation", "advance_session", "halt"}
            ):
                continue
            if not self._belongs_to_chain(run_id):
                continue
            failure: dict[str, Any] = {
                "kind": "failure",
                "status": "failed",
                "run_id": run_id,
                "stage": stage,
                "error_code": error_code,
                "retryable": retryable,
                "disposition": disposition,
                "summary": f"{stage} failed ({error_code})",
                "guidance": failure_guidance(stage, error_code),
            }
            if isinstance(payload.get("exit_code"), int) and not isinstance(payload["exit_code"], bool):
                failure["exit_code"] = payload["exit_code"]
            self._store_event(f"failure:{run_id}:{stage}:{error_code}", failure)

    def _record_proposal_unlocked(
        self,
        *,
        idea_name: object,
        title: object,
        method: object,
        code_hash: object,
        approved: bool,
        verdict: Mapping[str, Any] | None,
    ) -> bool:
        safe_code_hash = code_hash if isinstance(code_hash, str) and _SHA256.fullmatch(code_hash) else "missing"
        verdict = verdict if isinstance(verdict, Mapping) else {}
        violations = verdict.get("violations") if isinstance(verdict.get("violations"), list) else []
        error = verdict.get("error")
        missing = (
            verdict.get("missing_for_reproduction")
            if isinstance(verdict.get("missing_for_reproduction"), list)
            else []
        )
        safe_verdict = {
            "approved": bool(approved),
            "violations": [sanitize_failure_summary(value, limit=500) for value in violations[:8]],
            "missing_for_reproduction": [
                sanitize_failure_summary(value, limit=500) for value in missing[:8]
            ],
            "error": sanitize_failure_summary(error, limit=500) if error else None,
        }
        safe_idea_name = _bounded(idea_name, 200)
        safe_title = _bounded(title, 300)
        safe_method = _bounded(method, 2000)
        if not safe_title or not safe_method:
            for prior in self._events():
                prior_verdict = {
                    name: prior.get(name)
                    for name in (
                        "approved",
                        "violations",
                        "missing_for_reproduction",
                        "error",
                    )
                }
                if (
                    prior.get("kind") == "proposal"
                    and prior.get("idea_name") == safe_idea_name
                    and prior.get("code_sha256") == safe_code_hash
                    and prior_verdict == safe_verdict
                ):
                    safe_title = safe_title or _bounded(prior.get("title"), 300)
                    safe_method = safe_method or _bounded(prior.get("method"), 2000)
                    break
        proposal_identity = _digest(
            {
                "idea_name": safe_idea_name,
                "title": safe_title,
                "method": safe_method,
            }
        )
        key = f"proposal:{safe_code_hash}:{proposal_identity}:{_digest(safe_verdict)}"
        return self._store_event(
            key,
            {
                "kind": "proposal",
                "idea_name": safe_idea_name,
                "title": safe_title,
                "method": safe_method,
                "code_sha256": safe_code_hash,
                **safe_verdict,
            },
        )

    def record_proposal(
        self,
        *,
        idea_name: object,
        title: object,
        method: object,
        code_hash: object,
        approved: bool,
        verdict: Mapping[str, Any] | None,
    ) -> bool:
        with self._locked():
            changed = self._record_proposal_unlocked(
                idea_name=idea_name,
                title=title,
                method=method,
                code_hash=code_hash,
                approved=approved,
                verdict=verdict,
            )
            self._refresh_views_unlocked()
            return changed

    def _record_failure_unlocked(
        self,
        value: object,
        *,
        session_id: str | None = None,
    ) -> bool:
        safe = safe_failure_feedback_view(value)
        if safe is None:
            return False
        run_id = safe.get("run_id")
        if isinstance(run_id, str) and not self._belongs_to_chain(run_id):
            return False
        identity = run_id if isinstance(run_id, str) else _safe_component(
            session_id or "session", name="session_id"
        )
        payload = {
            "kind": "failure",
            **safe,
        }
        return self._store_event(
            f"failure:{identity}:{safe['stage']}:{safe['error_code']}",
            payload,
        )

    def record_failure(self, value: object, *, session_id: str | None = None) -> bool:
        with self._locked():
            changed = self._record_failure_unlocked(value, session_id=session_id)
            self._refresh_views_unlocked()
            return changed

    def record_proposal_transaction(
        self,
        *,
        idea_name: object,
        title: object,
        method: object,
        code_hash: object,
        approved: bool,
        verdict: Mapping[str, Any] | None,
        nested_failure: object = None,
        session_id: str | None = None,
    ) -> tuple[bool, bool]:
        """Atomically record one proposal decision and its typed tool failure."""

        with self._locked():
            proposal_changed = self._record_proposal_unlocked(
                idea_name=idea_name,
                title=title,
                method=method,
                code_hash=code_hash,
                approved=approved,
                verdict=verdict,
            )
            failure_changed = self._record_failure_unlocked(
                nested_failure,
                session_id=session_id,
            )
            self._refresh_views_unlocked()
            return proposal_changed, failure_changed

    def _events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for path in sorted(self.events_dir.glob("*.json")):
            if path.is_symlink() or path.stat().st_size > _MAX_EVENT_BYTES:
                raise ChainMemoryIntegrityError(
                    f"chain-memory event is unsafe or oversized: {path.name}"
                )
            os.chmod(path, 0o600)
            value = _read_regular_json(path, parent=self.events_dir)
            if value is None:
                raise ChainMemoryIntegrityError(
                    f"chain-memory event is malformed: {path.name}"
                )
            if value.get("schema") != SCHEMA or value.get("chain_id") != self.chain_id:
                raise ChainMemoryIntegrityError(
                    f"chain-memory event has an invalid identity: {path.name}"
                )
            self._validate_event(path, value)
            events.append(value)
        return sorted(events, key=lambda item: (str(item.get("recorded_at_pt")), str(item.get("dedupe_key"))))

    def _render(self) -> str:
        events = [_safe_for_render(event) for event in self._events()]
        results = [event for event in events if event.get("kind") == "result"]
        contracts = [event for event in events if event.get("kind") == "method_contract"]
        proposals = [event for event in events if event.get("kind") == "proposal"]
        failures = [event for event in events if event.get("kind") == "failure"]
        lines = [
            f"# Host-owned chain memory — {self.chain_id}",
            "",
            "Generated from durable research-visible artifacts. Do not edit this file; "
            "the controller rebuilds it atomically. Evaluator-private examples, judge "
            "output, raw errors, and hidden scores are never included.",
            "",
            "## Durable public score/finding joins",
            "",
        ]
        if not results:
            lines.append("No durable public score/finding joins yet.")
        for event in results:
            score = event.get("public_score") or {}
            lines.extend(
                [
                    f"### {event.get('title') or event.get('run_id')}",
                    "",
                    f"- Run ID: `{event.get('run_id')}`",
                    f"- Public headline: {score.get('headline_pct')}",
                    f"- Capability filter: {score.get('passes_filter', 'not reported')}",
                    f"- Regression gate: {score.get('passes_regression', 'not reported')}",
                    f"- Method: {event.get('method') or 'not reported'}",
                    f"- Key tradeoffs: {' '.join(event.get('key_tradeoffs') or []) or 'not reported'}",
                    f"- Results and limitations: {event.get('results_summary') or 'not reported'}",
                    f"- Missing for reproduction: {'; '.join(event.get('missing_for_reproduction') or []) or 'none reported'}",
                    "",
                ]
            )
        lines.extend(["## Method contracts and proposal decisions", ""])
        if not contracts and not proposals:
            lines.append("No durable method-contract or proposal decision yet.")
        for event in contracts[-20:]:
            enabled = [
                name for name, required in (event.get("requirements") or {}).items()
                if required
            ]
            lines.append(
                f"- Contract `{event.get('source_sha256')}` "
                f"({', '.join(enabled) or 'base checks'}): {event.get('status')}"
                + (f" — {'; '.join(event.get('errors') or [])}" if event.get("errors") else "")
            )
        for event in proposals[-20:]:
            lines.append(
                f"- Proposal `{event.get('idea_name') or 'unknown'}` "
                f"(code `{event.get('code_sha256')}`): "
                f"{'approved' if event.get('approved') else 'rejected'}"
                + (f" — {'; '.join(event.get('violations') or [])}" if event.get("violations") else "")
                + (f" — missing for reproduction: {'; '.join(event.get('missing_for_reproduction') or [])}" if event.get("missing_for_reproduction") else "")
                + (f" — {event.get('error')}" if event.get("error") else "")
            )
        lines.extend(["", "## Sanitized lifecycle failures", ""])
        if not failures:
            lines.append("No sanitized lifecycle failure recorded.")
        for event in failures[-20:]:
            lines.append(
                f"- `{event.get('run_id') or event.get('dedupe_key')}`: "
                f"{event.get('stage')}/{event.get('error_code')} — "
                f"{event.get('summary')} Guidance: {event.get('guidance', 'repair before retrying.')}"
            )
        return "\n".join(lines).rstrip() + "\n"

    def _materialize_agent_log_unlocked(self, rendered: str) -> None:
        """Replace one delimited controller block while preserving model scratch."""

        path = self.agent_log_path
        if path is None:
            return
        if path.is_symlink():
            raise ChainMemoryIntegrityError("AAR_AGENT_LOG_PATH may not be a symlink")
        try:
            parent = path.parent.resolve(strict=True)
            parent.relative_to(self.team_dir)
        except (OSError, ValueError) as error:
            raise ChainMemoryIntegrityError(
                "AAR_AGENT_LOG_PATH must be inside TEAM_DIR"
            ) from error
        if not parent.is_dir():
            raise ChainMemoryIntegrityError("AAR_AGENT_LOG_PATH parent is not a directory")
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(self.team_dir)
        except ValueError as error:
            raise ChainMemoryIntegrityError(
                "AAR_AGENT_LOG_PATH escaped TEAM_DIR"
            ) from error
        existing = ""
        if path.exists():
            if not path.is_file() or path.stat().st_size > _MAX_ARTIFACT_BYTES:
                raise ChainMemoryIntegrityError("AAR_AGENT_LOG_PATH is unsafe or oversized")
            try:
                existing = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                raise ChainMemoryIntegrityError("AAR_AGENT_LOG_PATH is unreadable") from error
        block = f"{_HOST_BLOCK_START}\n\n{rendered.rstrip()}\n\n{_HOST_BLOCK_END}"
        scratch = _agent_scratch_without_host_fragments(existing)
        separator = "" if not scratch else ("\n" if scratch.endswith("\n") else "\n\n")
        content = scratch + separator + block + "\n"
        _atomic_write(path, content)

    def _refresh_views_unlocked(self) -> None:
        rendered = self._render()
        _atomic_write(self.rendered_path, rendered)
        self._materialize_agent_log_unlocked(rendered)

    def reconcile(self) -> int:
        """Rebuild missing events from durable artifacts and refresh Markdown."""

        with self._locked():
            before = len(self._events())
            self._reconcile_contracts()
            self._reconcile_proposals()
            self._reconcile_score_failures()
            self._reconcile_results()
            self._refresh_views_unlocked()
            return len(self._events()) - before

    def prompt_snapshot(self) -> str:
        if not self.rendered_path.is_file() or self.rendered_path.is_symlink():
            raise ChainMemoryIntegrityError("host-owned chain-memory view is unavailable")
        return self.rendered_path.read_text(encoding="utf-8")


def record_proposal_from_environment(
    args: Mapping[str, Any],
    verdict: Mapping[str, Any],
    *,
    code_hash: object = None,
) -> None:
    """Backend-neutral proposal-event hook used by the shared MCP tool."""

    team = os.getenv("TEAM_DIR", "").strip()
    if not team:
        return
    journal = ChainMemoryJournal.from_environment()
    journal.record_proposal_transaction(
        idea_name=args.get("idea_name"),
        title=args.get("title"),
        method=args.get("method"),
        code_hash=code_hash,
        approved=bool(verdict.get("approved")),
        verdict=verdict,
        nested_failure=verdict.get("failure"),
        session_id=os.getenv("AAR_CURRENT_SESSION_ID") or "proposal-session",
    )
    journal.reconcile()


def record_contract_from_environment(result: Mapping[str, Any]) -> None:
    """Persist a validator result before its mutable proof path is overwritten."""

    team = os.getenv("TEAM_DIR", "").strip()
    if not team:
        return
    journal = ChainMemoryJournal.from_environment()
    journal.record_contract(result)
