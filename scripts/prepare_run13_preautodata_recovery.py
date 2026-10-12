#!/usr/bin/env python3
"""Import one reviewed pre-AutoData proposal into a fresh Run 13 team.

The source manifest is operator-owned and never belongs in the research source
snapshot.  This helper runs in the trusted launcher before any research child
is submitted.  It deliberately imports no AutoData, training, or evaluation
state.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Mapping
from zoneinfo import ZoneInfo


SCHEMA = "aar.run13-preautodata-recovery-manifest/v1"
RECEIPT_SCHEMA = "aar.run13-preautodata-import-receipt/v1"
PAPER_FIELDS = (
    "title",
    "abstract",
    "motivation",
    "related_work",
    "method",
    "data",
    "experimental_setup",
)
ARTIFACT_ROLES = {
    "method_source",
    "literature_research_and_proposal_stamp",
    "approved_proposal_event",
    "method_contract_and_approval_evidence",
}
_SHA256 = re.compile(r"sha256:([0-9a-f]{64})\Z")
_BARE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9._-]+\Z")
_PT = ZoneInfo("America/Los_Angeles")
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_METHOD_BYTES = 2 * 1024 * 1024


class RecoveryImportError(RuntimeError):
    """The reviewed recovery contract could not be established safely."""


@dataclass(frozen=True)
class VerifiedSource:
    manifest: dict[str, Any]
    manifest_sha256: str
    method_bytes: bytes
    method_file_sha256: str
    method_code_hash: str
    paper: dict[str, str]
    verdict: dict[str, Any]
    artifact_hashes: dict[str, str]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_private_directory(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise RecoveryImportError(f"refusing symlink directory: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise RecoveryImportError(f"recovery directory is not regular: {path}")
    os.chmod(path, 0o700)


def _atomic_bytes(path: Path, value: bytes, *, mode: int) -> None:
    _ensure_private_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
        _fsync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def _atomic_json(path: Path, value: Mapping[str, Any], *, mode: int = 0o600) -> None:
    encoded = (
        json.dumps(dict(value), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    _atomic_bytes(path, encoded, mode=mode)


def _read_regular_bytes(path: Path, *, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RecoveryImportError(f"recovery artifact is not a regular file: {path}")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise RecoveryImportError(f"recovery artifact has an unsafe size: {path}")
    return path.read_bytes()


def _read_json(path: Path, *, maximum: int = _MAX_JSON_BYTES) -> dict[str, Any]:
    try:
        value = json.loads(_read_regular_bytes(path, maximum=maximum))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecoveryImportError(f"recovery JSON is malformed: {path}") from error
    if not isinstance(value, dict):
        raise RecoveryImportError(f"recovery JSON must contain one object: {path}")
    return value


def _require_private_manifest(path: Path, *, snapshot: bool) -> Path:
    if path.is_symlink() or not path.is_file():
        raise RecoveryImportError("recovery manifest must be a regular file")
    metadata = path.stat()
    if metadata.st_uid != os.getuid():
        raise RecoveryImportError("recovery manifest must be owned by the launcher user")
    allowed = {0o400, 0o600} if snapshot else {0o600}
    if stat.S_IMODE(metadata.st_mode) not in allowed:
        expected = "0400 or 0600" if snapshot else "0600"
        raise RecoveryImportError(f"recovery manifest mode must be {expected}")
    return path.resolve(strict=True)


def _safe_component(value: object, label: str) -> str:
    if not isinstance(value, str) or _SAFE_COMPONENT.fullmatch(value) is None:
        raise RecoveryImportError(f"{label} is not a safe identifier")
    return value


def _required_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise RecoveryImportError(f"{label} keys differ from the reviewed schema")


def _lookup(value: Mapping[str, Any], dotted: str) -> Any:
    current: Any = value
    for component in dotted.split("."):
        if not isinstance(current, Mapping) or component not in current:
            raise RecoveryImportError(f"required receipt field is missing: {dotted}")
        current = current[component]
    return current


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def verify_manifest(
    path: Path, *, snapshot: bool = False, target_trial_id: str = "trial4"
) -> VerifiedSource:
    path = _require_private_manifest(path, snapshot=snapshot)
    raw = _read_regular_bytes(path, maximum=_MAX_JSON_BYTES)
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RecoveryImportError("recovery manifest is malformed") from error
    if not isinstance(manifest, dict):
        raise RecoveryImportError("recovery manifest must contain one object")
    _required_keys(
        manifest,
        {"schema", "source", "target", "artifacts", "method_contract", "fresh_autodata_contract"},
        "manifest",
    )
    if manifest.get("schema") != SCHEMA:
        raise RecoveryImportError("unsupported recovery manifest schema")

    source = manifest.get("source")
    target = manifest.get("target")
    artifacts = manifest.get("artifacts")
    fresh = manifest.get("fresh_autodata_contract")
    if not all(isinstance(value, dict) for value in (source, target, fresh)):
        raise RecoveryImportError("recovery manifest mappings are malformed")
    if not isinstance(artifacts, list):
        raise RecoveryImportError("recovery manifest artifacts must be an array")
    if source.get("experiment_run_id") != "run13" or source.get("trial_id") != "trial3":
        raise RecoveryImportError("recovery source must be Run 13 Trial 3")
    if re.fullmatch(r"trial[4-9][0-9]*", target_trial_id) is None:
        raise RecoveryImportError("recovery target trial identity is invalid")
    if (
        target.get("experiment_run_id") != "run13"
        or target.get("trial_id") != target_trial_id
    ):
        raise RecoveryImportError(
            f"recovery target must be Run 13 {target_trial_id}"
        )
    if source.get("chain") != "alpha" or target.get("chain") != "alpha":
        raise RecoveryImportError("recovery is restricted to the alpha chain")
    if target.get("entry_boundary") != "fresh_autodata_workspace_before_clarify_design":
        raise RecoveryImportError("recovery entry boundary drifted")
    for key in ("require_fresh_attempt", "require_fresh_team", "require_fresh_autodata_state"):
        if target.get(key) is not True:
            raise RecoveryImportError(f"recovery target must set {key}")

    source_attempt = Path(str(source.get("attempt_root", ""))).resolve(strict=True)
    source_team = Path(str(source.get("team_root", ""))).resolve(strict=True)
    if not source_attempt.is_absolute() or not source_team.is_absolute():
        raise RecoveryImportError("source roots must be absolute")
    if not _under(source_team, source_attempt / "aar_teams"):
        raise RecoveryImportError("source team is outside the source attempt")
    snapshots = _read_json(source_attempt / "metadata" / "source-snapshots.json")
    if (
        _lookup(snapshots, "aar.commit") != source.get("aar_commit")
        or _lookup(snapshots, "autodata.commit") != source.get("autodata_commit")
    ):
        raise RecoveryImportError("source attempt commits disagree with the manifest")
    source_run_id = _safe_component(source.get("source_run_id"), "source run ID")
    source_idea_uid = _safe_component(source.get("source_idea_uid"), "source idea UID")
    idea_name = _safe_component(source.get("idea_name"), "idea name")
    target_uid = _safe_component(target.get("idea_uid"), "target idea UID")
    if target_trial_id not in target_uid or target_uid == source_idea_uid:
        raise RecoveryImportError(
            f"target idea UID is not fresh for {target_trial_id}"
        )
    code_hash = source.get("method_code_hash")
    if not isinstance(code_hash, str) or _BARE_SHA256.fullmatch(code_hash) is None:
        raise RecoveryImportError("source method code hash is invalid")

    forbidden_prefixes = fresh.get("forbidden_source_prefixes")
    forbidden_reuse = fresh.get("forbidden_reuse")
    forbidden_ids = fresh.get("forbidden_native_ids")
    if (
        not isinstance(forbidden_prefixes, list)
        or not forbidden_prefixes
        or not isinstance(forbidden_reuse, list)
        or not forbidden_reuse
        or not isinstance(forbidden_ids, dict)
        or not forbidden_ids
        or fresh.get("required_first_native_action") != "clarify_design"
    ):
        raise RecoveryImportError("fresh AutoData exclusions are incomplete")
    forbidden_roots = [Path(str(value)).resolve(strict=True) for value in forbidden_prefixes]
    for root in forbidden_roots:
        if not _under(root, source_team):
            raise RecoveryImportError("forbidden source root escaped the source team")
    for value in forbidden_ids.values():
        _safe_component(value, "forbidden native ID")

    by_role: dict[str, dict[str, Any]] = {}
    artifact_hashes: dict[str, str] = {}
    artifact_bytes: dict[str, bytes] = {}
    for entry in artifacts:
        if not isinstance(entry, dict):
            raise RecoveryImportError("artifact entry must be an object")
        role = entry.get("role")
        if role not in ARTIFACT_ROLES or role in by_role:
            raise RecoveryImportError("artifact roles are missing, duplicated, or unknown")
        artifact = Path(str(entry.get("path", ""))).resolve(strict=True)
        if not _under(artifact, source_team):
            raise RecoveryImportError("source artifact escaped the source team")
        if any(_under(artifact, root) for root in forbidden_roots):
            raise RecoveryImportError("source artifact belongs to forbidden lifecycle state")
        maximum = _MAX_METHOD_BYTES if role == "method_source" else _MAX_JSON_BYTES
        content = _read_regular_bytes(artifact, maximum=maximum)
        digest = _sha256_bytes(content)
        expected = entry.get("sha256")
        match = _SHA256.fullmatch(expected) if isinstance(expected, str) else None
        if match is None or digest != match.group(1):
            raise RecoveryImportError(f"source artifact hash mismatch for {role}")
        by_role[role] = entry
        artifact_hashes[role] = f"sha256:{digest}"
        artifact_bytes[role] = content
    if set(by_role) != ARTIFACT_ROLES:
        raise RecoveryImportError("recovery manifest does not contain the exact artifact set")

    method_path = Path(by_role["method_source"]["path"]).resolve(strict=True)
    if method_path.name != "run.py" or method_path.parent.name != idea_name:
        raise RecoveryImportError("source method path disagrees with the proposal")
    python_files = sorted(
        item for item in method_path.parent.rglob("*.py") if item.is_file()
    )
    if python_files != [method_path]:
        raise RecoveryImportError("source method package is not the reviewed one-file package")
    try:
        method_text = artifact_bytes["method_source"].decode("utf-8")
    except UnicodeDecodeError as error:
        raise RecoveryImportError("source method is not UTF-8") from error
    calculated_code_hash = _sha256_bytes(
        f"# ===== run.py =====\n{method_text}".encode("utf-8")
    )
    if calculated_code_hash != code_hash:
        raise RecoveryImportError("source method package hash disagrees with the manifest")

    def artifact_json(role: str) -> dict[str, Any]:
        try:
            value = json.loads(artifact_bytes[role])
        except json.JSONDecodeError as error:
            raise RecoveryImportError(f"source {role} is malformed") from error
        if not isinstance(value, dict):
            raise RecoveryImportError(f"source {role} must contain one object")
        return value

    stamp = artifact_json("literature_research_and_proposal_stamp")
    evidence = artifact_json("method_contract_and_approval_evidence")
    event = artifact_json("approved_proposal_event")
    paper = stamp.get("paper")
    if (
        stamp.get("run_id") != source_run_id
        or stamp.get("idea_name") != idea_name
        or stamp.get("code_hash") != code_hash
        or not isinstance(paper, dict)
        or set(paper) != set(PAPER_FIELDS)
        or not all(isinstance(paper.get(field), str) and paper[field] for field in PAPER_FIELDS)
    ):
        raise RecoveryImportError("source proposal stamp is not bound to the reviewed method")
    required_fields = by_role["method_contract_and_approval_evidence"].get("required_fields")
    if not isinstance(required_fields, dict) or not required_fields:
        raise RecoveryImportError("approval evidence has no required-field contract")
    for dotted, expected in required_fields.items():
        if _lookup(evidence, str(dotted)) != expected:
            raise RecoveryImportError(f"approval evidence field drifted: {dotted}")
    if (
        evidence.get("idea_name") != idea_name
        or evidence.get("code_hash") != code_hash
        or evidence.get("paper") != paper
        or evidence.get("run_id") != source_run_id
    ):
        raise RecoveryImportError("approval evidence is not bound to the proposal stamp")
    if (
        event.get("schema") != "aar.chain-memory-event/v1"
        or event.get("kind") != "proposal"
        or event.get("source") != "proposal_decision"
        or event.get("approved") is not True
        or event.get("idea_name") != idea_name
        or event.get("code_sha256") != code_hash
    ):
        raise RecoveryImportError("source proposal event is not an approved native event")
    verdict_source = evidence.get("verdict")
    if not isinstance(verdict_source, dict) or verdict_source.get("approved") is not True:
        raise RecoveryImportError("source approval verdict is missing")
    verdict = {
        "approved": True,
        "violations": list(verdict_source.get("violations") or []),
        "missing_for_reproduction": list(
            verdict_source.get("missing_for_reproduction") or []
        ),
        "error": verdict_source.get("error"),
    }
    if verdict != {
        "approved": True,
        "violations": [],
        "missing_for_reproduction": [],
        "error": None,
    }:
        raise RecoveryImportError("only a clean source approval may be imported")

    return VerifiedSource(
        manifest=manifest,
        manifest_sha256=_sha256_bytes(raw),
        method_bytes=artifact_bytes["method_source"],
        method_file_sha256=artifact_hashes["method_source"],
        method_code_hash=code_hash,
        paper={field: paper[field] for field in PAPER_FIELDS},
        verdict=verdict,
        artifact_hashes=artifact_hashes,
    )


@contextmanager
def _temporary_environment(values: Mapping[str, str]) -> Iterator[None]:
    prior = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _assert_no_forbidden_target_data(
    paths: list[Path], source: VerifiedSource
) -> None:
    manifest = source.manifest
    tokens = {
        str(manifest["source"]["attempt_root"]),
        str(manifest["source"]["team_root"]),
        str(manifest["source"]["source_run_id"]),
        str(manifest["source"]["source_idea_uid"]),
        *[str(value) for value in manifest["fresh_autodata_contract"]["forbidden_native_ids"].values()],
    }
    for path in paths:
        content = _read_regular_bytes(path, maximum=_MAX_JSON_BYTES).decode(
            "utf-8", errors="replace"
        )
        if any(token and token in content for token in tokens):
            raise RecoveryImportError(
                f"target artifact retained forbidden source identity: {path}"
            )


def _validate_method_proof(proof: Path, method: Path) -> dict[str, Any]:
    value = _read_json(proof)
    expected_requirements = {
        "run_dry_run": True,
        "require_gemma4_targets": True,
        "require_smoke_run": True,
        "require_autodata_loader": True,
    }
    if (
        value.get("schema_version") != 1
        or value.get("status") != "passed"
        or value.get("method_path") != str(method.resolve())
        or value.get("source_sha256") != _sha256_file(method)
        or value.get("requirements") != expected_requirements
        or value.get("errors") != []
    ):
        raise RecoveryImportError("fresh method-contract proof is invalid")
    return value


def _target_paths(team: Path, chain_id: str, idea_uid: str, idea_name: str) -> dict[str, Path]:
    return {
        "method": team / "methods" / idea_name / "run.py",
        "proof": team / "methods" / idea_name / ".aar-method-contract.json",
        "marker": team / "scores" / ".proposals" / f"{idea_uid}.json",
        "events": team / "host_memory" / chain_id / "events",
        "journal": team / "host_memory" / chain_id / "journal.md",
    }


def _validate_existing_import(
    *,
    receipt_path: Path,
    source: VerifiedSource,
    team: Path,
    chain_id: str,
    idea_uid: str,
    idea_name: str,
) -> dict[str, Any]:
    receipt = _read_json(receipt_path)
    if (
        receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("manifest_sha256") != f"sha256:{source.manifest_sha256}"
        or receipt.get("source_artifact_sha256") != source.artifact_hashes
    ):
        raise RecoveryImportError("existing import receipt disagrees with the manifest")
    target = receipt.get("target")
    if not isinstance(target, dict) or any(
        target.get(key) != value
        for key, value in {
            "idea_uid": idea_uid,
            "idea_name": idea_name,
            "chain_id": chain_id,
            "method_code_hash": source.method_code_hash,
            "method_file_sha256": source.method_file_sha256,
        }.items()
    ):
        raise RecoveryImportError("existing import receipt has the wrong target")
    paths = _target_paths(team, chain_id, idea_uid, idea_name)
    if f"sha256:{_sha256_file(paths['method'])}" != source.method_file_sha256:
        raise RecoveryImportError("existing imported method drifted")
    _validate_method_proof(paths["proof"], paths["method"])
    if target.get("method_proof_sha256") != f"sha256:{_sha256_file(paths['proof'])}":
        raise RecoveryImportError("existing method-contract proof hash drifted")
    marker = _read_json(paths["marker"])
    run_id = target.get("run_id")
    if (
        marker.get("approved") is not True
        or marker.get("journaled") is not True
        or marker.get("execution_ready") is not True
        or marker.get("idea_uid") != idea_uid
        or marker.get("idea_name") != idea_name
        or marker.get("code_hash") != source.method_code_hash
        or marker.get("run_id") != run_id
        or "autodata_bootstrap" in marker
    ):
        raise RecoveryImportError("existing imported proposal marker drifted")
    stamp = team / "scores" / ".proposals" / "runs" / f"{run_id}.json"
    if target.get("proposal_marker_sha256") != f"sha256:{_sha256_file(paths['marker'])}":
        raise RecoveryImportError("existing proposal marker hash drifted")
    if target.get("proposal_stamp_sha256") != f"sha256:{_sha256_file(stamp)}":
        raise RecoveryImportError("existing proposal stamp hash drifted")
    active = [paths["method"], paths["proof"], paths["marker"], stamp, paths["journal"]]
    active.extend(sorted(paths["events"].glob("*.json")))
    _assert_no_forbidden_target_data(active, source)
    if (team / "autodata").exists():
        raise RecoveryImportError("AutoData state exists before the fresh bootstrap")
    return receipt


def prepare_import(
    *,
    manifest_path: Path,
    team_dir: Path,
    attempt_dir: Path,
    receipt_path: Path,
    repo: Path,
    python: Path,
    chain_id: str,
    idea_uid: str,
    target_trial_id: str = "trial4",
) -> dict[str, Any]:
    source = verify_manifest(
        manifest_path,
        snapshot=True,
        target_trial_id=target_trial_id,
    )
    idea_name = str(source.manifest["source"]["idea_name"])
    expected_uid = str(source.manifest["target"]["idea_uid"])
    if idea_uid != expected_uid:
        raise RecoveryImportError("launcher idea UID disagrees with the manifest")
    chain_id = _safe_component(chain_id, "target chain ID")
    idea_uid = _safe_component(idea_uid, "target idea UID")
    repo = repo.resolve(strict=True)
    python = python.resolve(strict=True)
    team = team_dir.resolve(strict=True)
    attempt = attempt_dir.resolve(strict=True)
    receipt_path = receipt_path.resolve(strict=False)
    if not _under(team, attempt / "aar_teams"):
        raise RecoveryImportError("target team escaped the fresh attempt")
    if receipt_path.parent.resolve(strict=True) != (attempt / "metadata").resolve(strict=True):
        raise RecoveryImportError("import receipt must remain in host-owned attempt metadata")
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RecoveryImportError("trusted validator Python is unavailable")
    if (team / "autodata").exists():
        raise RecoveryImportError("target team already contains AutoData state")

    _ensure_private_directory(receipt_path.parent)
    lock_path = receipt_path.with_suffix(receipt_path.suffix + ".lock")
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if receipt_path.exists():
            return _validate_existing_import(
                receipt_path=receipt_path,
                source=source,
                team=team,
                chain_id=chain_id,
                idea_uid=idea_uid,
                idea_name=idea_name,
            )

        paths = _target_paths(team, chain_id, idea_uid, idea_name)
        partial = [paths["method"].parent, paths["marker"], team / "host_memory"]
        runs = team / "scores" / ".proposals" / "runs"
        if any(path.exists() for path in partial) or (
            runs.exists() and any(runs.iterdir())
        ):
            raise RecoveryImportError("partial pre-AutoData import exists without a receipt")
        for forbidden_dir in (team / "_train", team / "submissions", team / "forum"):
            if forbidden_dir.exists() and any(forbidden_dir.iterdir()):
                raise RecoveryImportError("fresh team contains downstream state")

        _ensure_private_directory(paths["method"].parent)
        _atomic_bytes(paths["method"], source.method_bytes, mode=0o600)
        env = {
            "TEAM_DIR": str(team),
            "LOCAL_FINDINGS_DIR": str(team / "forum"),
            "SCORES_DIR": str(team / "scores"),
            "AAR_IDEAS_DIR": str(team / "methods"),
            "SESSION_LOGS_DIR": str(team / "logs"),
            "IDEA_NAME": chain_id,
            "IDEA_UID": idea_uid,
            "AAR_IDEA_UID_OVERRIDE": idea_uid,
            "AAR_AUTODATA": "1",
            "AAR_NO_LOCAL_GPU": "1",
            "PYTHONPATH": str(repo),
        }
        marker = {
            "approved": True,
            "execution_ready": False,
            "journaled": False,
            "idea_name": idea_name,
            "code_hash": source.method_code_hash,
            "ts": time.time(),
            "idea_uid": idea_uid,
            "verdict": source.verdict,
            "paper": source.paper,
        }
        with _temporary_environment(env):
            from aar.research_loop.tools.server_api_tools import (
                _atomic_json_write,
                _approved_proposal_run_id_candidate,
                _ensure_approved_proposal_run_id,
                _method_code,
                ensure_proposal_journal_receipt,
            )

            _atomic_json_write(paths["marker"], marker)
            os.chmod(paths["marker"], 0o600)
            if not ensure_proposal_journal_receipt(
                paths["marker"],
                team_dir=team,
                chain_id=chain_id,
                idea_uid=idea_uid,
                allow_backfill=True,
                mark_journaled=True,
            ):
                raise RecoveryImportError("fresh proposal journal event was not created")
            _, imported_code_hash = _method_code(idea_name)
            if imported_code_hash != source.method_code_hash:
                raise RecoveryImportError("imported method package hash drifted")

            command = [
                str(python),
                str(repo / "scripts" / "validate_method_contract.py"),
                str(paths["method"]),
                "--proof",
                str(paths["proof"]),
                "--run-dry-run",
                "--require-gemma4-targets",
                "--require-smoke-run",
                "--require-autodata-loader",
            ]
            completed = subprocess.run(
                command,
                env={**os.environ, **env},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
                check=False,
            )
            if completed.returncode != 0:
                raise RecoveryImportError("fresh method-contract validation failed")
            proof = _validate_method_proof(paths["proof"], paths["method"])
            _atomic_json(paths["proof"], proof)
            run_id = _ensure_approved_proposal_run_id()
            if _approved_proposal_run_id_candidate() != run_id:
                raise RecoveryImportError("fresh proposal run ID did not reconcile")

        if not run_id.startswith(f"{idea_uid}-"):
            raise RecoveryImportError("fresh proposal run ID has the wrong identity")
        marker = _read_json(paths["marker"])
        if (
            marker.get("run_id") != run_id
            or marker.get("execution_ready") is not True
            or marker.get("journaled") is not True
            or "autodata_bootstrap" in marker
        ):
            raise RecoveryImportError("fresh proposal marker is not resumable")
        stamp = team / "scores" / ".proposals" / "runs" / f"{run_id}.json"
        active = [paths["method"], paths["proof"], paths["marker"], stamp, paths["journal"]]
        active.extend(sorted(paths["events"].glob("*.json")))
        _assert_no_forbidden_target_data(active, source)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "created_at_pt": datetime.now(_PT).isoformat(timespec="seconds"),
            "manifest_sha256": f"sha256:{source.manifest_sha256}",
            "source_artifact_sha256": source.artifact_hashes,
            "target": {
                "chain_id": chain_id,
                "idea_uid": idea_uid,
                "idea_name": idea_name,
                "run_id": run_id,
                "method_code_hash": source.method_code_hash,
                "method_file_sha256": source.method_file_sha256,
                "method_proof_sha256": f"sha256:{_sha256_file(paths['proof'])}",
                "proposal_marker_sha256": f"sha256:{_sha256_file(paths['marker'])}",
                "proposal_stamp_sha256": f"sha256:{_sha256_file(stamp)}",
                "first_native_action": "clarify_design",
                "fresh_autodata_state": True,
            },
        }
        _atomic_json(receipt_path, receipt)
        return receipt
    finally:
        os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--snapshot", action="store_true")
    verify.add_argument("--target-trial-id", default="trial4")

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--team-dir", type=Path, required=True)
    prepare.add_argument("--attempt-dir", type=Path, required=True)
    prepare.add_argument("--receipt", type=Path, required=True)
    prepare.add_argument("--repo", type=Path, required=True)
    prepare.add_argument("--python", type=Path, required=True)
    prepare.add_argument("--chain-id", required=True)
    prepare.add_argument("--idea-uid", required=True)
    prepare.add_argument("--target-trial-id", default="trial4")
    return parser


def main() -> None:
    os.umask(0o077)
    args = _parser().parse_args()
    try:
        if args.command == "verify":
            source = verify_manifest(
                args.manifest,
                snapshot=args.snapshot,
                target_trial_id=args.target_trial_id,
            )
            result = {
                "schema": SCHEMA,
                "status": "verified",
                "manifest_sha256": f"sha256:{source.manifest_sha256}",
                "source_artifact_sha256": source.artifact_hashes,
            }
        else:
            result = prepare_import(
                manifest_path=args.manifest,
                team_dir=args.team_dir,
                attempt_dir=args.attempt_dir,
                receipt_path=args.receipt,
                repo=args.repo,
                python=args.python,
                chain_id=args.chain_id,
                idea_uid=args.idea_uid,
                target_trial_id=args.target_trial_id,
            )
    except (OSError, RecoveryImportError, subprocess.SubprocessError) as error:
        print(f"pre-AutoData recovery rejected: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
