"""Trusted, backend-independent bootstrap for an approved AutoData workspace.

The research model owns scientific authoring and meta-optimization actions.  This
module owns only the deterministic transition from an approved AAR proposal to a
native, proposal-scoped workspace registered with the lifecycle supervisor.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


BOOTSTRAP_SCHEMA = "aar.autodata.workspace-bootstrap/v1"
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
_WORKSPACE_ID = re.compile(r"^ws_[0-9a-f]{32}$")


def _required_path(name: str, *, directory: bool = False) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        raise RuntimeError(f"{name} is required for AutoData bootstrap")
    configured = Path(raw).expanduser()
    if configured.is_symlink():
        raise RuntimeError(f"{name} must not be a symlink")
    path = configured.resolve(strict=True)
    wrong_kind = not path.is_dir() if directory else not path.is_file()
    if wrong_kind:
        kind = "directory" if directory else "file"
        raise RuntimeError(f"{name} must be a real {kind}")
    return path


def _configured_path(name: str) -> Path:
    """Resolve a configured output path whose file may not exist yet."""
    raw = os.getenv(name, "").strip()
    if not raw:
        raise RuntimeError(f"{name} is required for AutoData bootstrap")
    configured = Path(raw).expanduser()
    if configured.is_symlink():
        raise RuntimeError(f"{name} must not be a symlink")
    path = configured.resolve()
    if not path.parent.is_dir():
        raise RuntimeError(f"{name} parent directory does not exist")
    return path


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} must be a real JSON file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must contain one JSON object")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(dict(value), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _executor(policy: Mapping[str, Any]) -> dict[str, Any]:
    environment = policy.get("required_solve_env")
    if not isinstance(environment, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in environment.items()
    ):
        raise RuntimeError("AutoData campaign policy has invalid required_solve_env")
    runner = policy.get("runner")
    if runner not in {"local-bwrap", "sandoq-firecracker"}:
        raise RuntimeError("AutoData campaign policy has an unsupported runner")
    # The native SandoQ executor is the broker client.  The campaign-scoped
    # broker then selects either local-bwrap or Firecracker from its pinned
    # operator policy; the workspace never chooses or changes that backend.
    return {
        "kind": "sandoq-firecracker",
        "environment": policy.get("environment"),
        "image": policy.get("image"),
        "expected_image_id": policy.get("expected_image_id"),
        "broker_url": os.environ["AAR_AUTODATA_BROKER_URL"],
        "broker_auth_secret_ref": "AAR_AUTODATA_CAPABILITY",
        "model_backed": True,
        "cpus": policy.get("max_cpus"),
        "memory_mb": policy.get("max_memory_mb"),
        "network": "host",
        "workdir": "/workspace",
        "non_secret_env": dict(environment),
    }


def _run_json(command: list[str], *, timeout: int = 120) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr[-2000:].strip() or completed.stdout[-2000:].strip()
        raise RuntimeError(f"AutoData bootstrap command failed: {detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("AutoData bootstrap command returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("AutoData bootstrap command returned a non-object")
    return value


def _native_command(*arguments: str) -> list[str]:
    plugin = _required_path("AAR_AUTODATA_PLUGIN_ROOT", directory=True)
    wrapper = plugin / "scripts" / "autodata.py"
    if wrapper.is_symlink() or not wrapper.is_file():
        raise RuntimeError("pinned AutoData wrapper is missing")
    return [
        os.environ["AAR_AUTODATA_WRAPPER_PYTHON"],
        str(wrapper),
        "--state",
        str(_configured_path("AAR_AUTODATA_STATE")),
        "--artifacts",
        str(_required_path("AAR_AUTODATA_ARTIFACTS", directory=True)),
        "--workspaces",
        str(_required_path("AAR_AUTODATA_WORKSPACES", directory=True)),
        *arguments,
    ]


def _workspace_status(workspace_id: str) -> str:
    state = _configured_path("AAR_AUTODATA_STATE")
    if not state.is_file():
        raise RuntimeError("live AutoData state is missing an approved workspace")
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT status FROM workspaces WHERE id=?", (workspace_id,)
        ).fetchone()
    if row is None:
        raise RuntimeError("approved AutoData workspace is missing from native state")
    return str(row[0])


def _register_command(workspace_id: str) -> list[str]:
    repository = Path(__file__).resolve().parents[2]
    supervisor = repository / "scripts" / "autodata_lifecycle_supervisor.py"
    return [
        os.environ.get("AAR_HARNESS_PYTHON", sys.executable),
        str(supervisor),
        "register",
        "--state",
        str(_configured_path("AAR_AUTODATA_STATE")),
        "--retained-state",
        str(Path(os.environ["AAR_AUTODATA_RETAINED_STATE"]).expanduser().resolve()),
        "--control-file",
        str(Path(os.environ["AAR_AUTODATA_SUPERVISOR_CONTROL"]).expanduser().resolve()),
        "--subject-kind",
        "workspace",
        "--subject-id",
        workspace_id,
    ]


def _prepare_brief(run_root: Path) -> tuple[Path, str]:
    recipe = _required_path("AAR_AUTODATA_RECIPE_ROOT", directory=True)
    source_brief = recipe / "autodata.workspace.json"
    brief = _json_object(source_brief, "reviewed AutoData workspace brief")
    policy = _json_object(
        _required_path("AAR_AUTODATA_CAMPAIGN_POLICY"),
        "AutoData campaign policy",
    )
    executor = _executor(policy)
    brief["authoring_executor"] = executor
    authoring_budget = brief.get("authoring_budget")
    if not isinstance(authoring_budget, dict):
        raise RuntimeError("reviewed workspace brief has invalid authoring_budget")
    try:
        authoring_max_wall_seconds = int(
            os.environ["AAR_AUTODATA_AUTHORING_MAX_WALL_SECONDS"]
        )
    except (KeyError, ValueError) as error:
        raise RuntimeError(
            "AAR_AUTODATA_AUTHORING_MAX_WALL_SECONDS must be a positive integer"
        ) from error
    if authoring_max_wall_seconds < 1:
        raise RuntimeError(
            "AAR_AUTODATA_AUTHORING_MAX_WALL_SECONDS must be a positive integer"
        )
    authoring_budget["max_wall_seconds"] = authoring_max_wall_seconds
    defaults = brief.get("execution_defaults")
    if not isinstance(defaults, dict):
        raise RuntimeError("reviewed workspace brief has invalid execution_defaults")
    defaults["executor"] = executor
    defaults["concurrency"] = int(os.getenv("AAR_AUTODATA_CONCURRENCY", "1"))
    defaults["secret_references"] = ["AAR_AUTODATA_CAPABILITY"]

    public_key = _required_path("AAR_AUTODATA_APPROVAL_PUBLIC_KEY")
    public_bytes = public_key.read_bytes()
    public_digest = _sha256_bytes(public_bytes)
    expected_digest = os.getenv("AAR_AUTODATA_APPROVAL_PUBLIC_KEY_SHA256", "")
    if public_digest != expected_digest:
        raise RuntimeError("delegated approval public key digest mismatch")
    approval_destination = run_root / "draft" / "approval" / "public.pem"
    approval_destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if approval_destination.exists() and approval_destination.read_bytes() != public_bytes:
        raise RuntimeError("run-scoped delegated approval key changed")
    if not approval_destination.exists():
        shutil.copyfile(public_key, approval_destination)
        approval_destination.chmod(0o600)
    brief["approval_policy"] = {
        "mode": "delegated",
        "public_key_path": "approval/public.pem",
        "public_key_sha256": public_digest,
        "actor": os.getenv("AAR_AUTODATA_APPROVAL_ACTOR", "aar-integrity-monitor"),
        "policy_version": os.environ["AAR_AUTODATA_APPROVAL_POLICY_VERSION"],
    }
    destination = run_root / "input" / "autodata.workspace.json"
    _atomic_json(destination, brief)
    recipe_digest = _sha256_bytes(
        json.dumps(brief, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return destination, recipe_digest


def _stage_reviewed_recipe(run_root: Path) -> None:
    """Seed the writable draft from the operator-reviewed recipe deterministically."""
    recipe = _required_path("AAR_AUTODATA_RECIPE_ROOT", directory=True)
    draft = run_root / "draft"
    for name in (
        "autodata.pipeline.json",
        "framework.lock.json",
        "objective.json",
        "comparator.json",
    ):
        source = recipe / name
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"reviewed AutoData recipe is missing {name}")
        shutil.copy2(source, draft / name)
    for name in ("grounding", "recipe", "schemas"):
        source = recipe / name
        if source.is_symlink() or not source.is_dir():
            raise RuntimeError(f"reviewed AutoData recipe is missing {name}/")
        shutil.copytree(
            source,
            draft / name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    tuning = int(os.environ["AAR_AUTODATA_TUNING_TASKS"])
    validation = int(os.environ["AAR_AUTODATA_VALIDATION_TASKS"])
    test = int(os.environ["AAR_AUTODATA_TEST_TASKS"])
    task_count = tuning + validation + test
    if min(tuning, validation, test) < 1:
        raise RuntimeError("AutoData meta partitions must all be non-empty")
    builder = draft / "grounding" / "build_manifest.py"
    coverage = draft / "grounding" / "coverage.json"
    manifest = draft / "grounding" / "manifest.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(builder),
            "--count",
            str(task_count),
            "--coverage",
            str(coverage),
            "--output",
            str(manifest),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr[-2000:].strip() or completed.stdout[-2000:].strip()
        raise RuntimeError(f"reviewed grounding build failed: {detail}")
    generated = _json_object(manifest, "generated reviewed grounding manifest")
    tasks = generated.get("tasks")
    if generated.get("schema") != "autodata.grounding/v1" or not isinstance(
        tasks, list
    ):
        raise RuntimeError("generated reviewed grounding manifest has invalid schema")
    if len(tasks) != task_count:
        raise RuntimeError(
            "generated reviewed grounding manifest has an unexpected task count"
        )
    contract = _required_path("AAR_AUTODATA_TRAINING_DATA_CONTRACT")
    shutil.copy2(contract, draft / "training-data-contract.json")


def ensure_workspace(
    *, run_id: str, idea_name: str, code_hash: str
) -> dict[str, Any]:
    """Create/resume and register the one workspace bound to an approved proposal."""
    if not _SAFE_RUN_ID.fullmatch(run_id):
        raise RuntimeError("approved run id is unsafe for AutoData bootstrap")
    if not idea_name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", idea_name):
        raise RuntimeError("approved idea name is unsafe for AutoData bootstrap")
    if not re.fullmatch(r"[0-9a-f]{64}", code_hash):
        raise RuntimeError("approved method code hash is invalid")
    team = _required_path("TEAM_DIR", directory=True)
    run_root = team / "autodata" / run_id
    run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if run_root.is_symlink() or run_root.resolve().parent != (team / "autodata").resolve():
        raise RuntimeError("AutoData run root escaped the team directory")
    for name in ("input", "draft"):
        path = run_root / name
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink():
            raise RuntimeError("AutoData bootstrap directory must not be a symlink")

    lock_path = run_root / ".bootstrap.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        manifest_path = run_root / "workspace-bootstrap.json"
        if manifest_path.is_file():
            existing = _json_object(manifest_path, "AutoData workspace bootstrap")
            if any(
                existing.get(key) != value
                for key, value in {
                    "schema": BOOTSTRAP_SCHEMA,
                    "run_id": run_id,
                    "idea_name": idea_name,
                    "code_hash": code_hash,
                }.items()
            ):
                raise RuntimeError("existing AutoData bootstrap binds another proposal")
            workspace_id = str(existing.get("workspace_id") or "")
            if not _WORKSPACE_ID.fullmatch(workspace_id):
                raise RuntimeError("existing AutoData bootstrap has an invalid workspace id")
            status = _workspace_status(workspace_id)
            if status in {"cancelled", "failed"}:
                raise RuntimeError("approved AutoData workspace is terminal")
            if status == "active":
                _run_json(_register_command(workspace_id))
            return {**existing, "idempotent": True}

        brief, brief_digest = _prepare_brief(run_root)
        _stage_reviewed_recipe(run_root)
        key_payload = {
            "schema": BOOTSTRAP_SCHEMA,
            "run_id": run_id,
            "idea_name": idea_name,
            "code_hash": code_hash,
            "brief_digest": brief_digest,
            "root": str((run_root / "draft").resolve()),
        }
        idempotency_key = "aar-approved:" + hashlib.sha256(
            json.dumps(key_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        created = _run_json(
            _native_command(
                "workspace",
                "create",
                "--brief",
                str(brief),
                "--root",
                str(run_root / "draft"),
                "--idempotency-key",
                idempotency_key,
            )
        )
        workspace_id = str(created.get("workspace_id") or "")
        if not _WORKSPACE_ID.fullmatch(workspace_id):
            raise RuntimeError("native AutoData did not return a valid workspace id")
        registration = _run_json(_register_command(workspace_id))
        manifest = {
            "schema": BOOTSTRAP_SCHEMA,
            "run_id": run_id,
            "idea_name": idea_name,
            "code_hash": code_hash,
            "workspace_id": workspace_id,
            "study_id": created.get("study_id"),
            "brief_digest": brief_digest,
            "idempotency_key": idempotency_key,
            "registered": registration.get("registered") is True,
            "run_root": str(run_root),
        }
        if not manifest["registered"]:
            raise RuntimeError("native AutoData workspace registration failed")
        _atomic_json(manifest_path, manifest)
        return {**manifest, "idempotent": False}
