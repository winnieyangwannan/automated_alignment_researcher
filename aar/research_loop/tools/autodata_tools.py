"""MCP client for the operator-managed Autodata generation service.

The research agent sees only this narrow HTTP surface. Pipeline checkout,
SandoQ/Firecracker credentials, and model-provider credentials stay in the
service. Callers also cannot choose a Git ref: the operator pins
``AAR_AUTODATA_SHA`` for the complete AAR run.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import stat
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict

from claude_agent_sdk import create_sdk_mcp_server, tool

from aar.infrastructure.autodata import autodata_required, validate_autodata_artifacts

from .http_utils import async_http_get, async_http_post


_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,191}$")
_DIGEST_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_FORBIDDEN_REF_KEYS = {
    "branch",
    "commit",
    "credential",
    "credentials",
    "deployment_id",
    "endpoint",
    "git_ref",
    "image",
    "path",
    "pipeline_sha",
    "ref",
    "secret",
    "sha",
    "token",
    "url",
}
_REQUEST_KEYS = {
    "schema",
    "resource_profile",
    "safety_axis",
    "training_mechanism",
    "training_view",
    "seed",
    "goal",
}
_APPROVAL_RESULT_KEYS = {"approval_attestation", "approved", "user_acknowledged"}
_REQUEST_SCHEMA = "aar.autodata.request/v1"


def autodata_enabled() -> bool:
    return os.getenv("AAR_AUTODATA", "0").lower() in {"1", "true", "yes"}


def _http_timeout() -> int:
    raw = os.getenv("AAR_AUTODATA_HTTP_TIMEOUT", "120")
    try:
        timeout = int(raw)
    except ValueError as error:
        raise ValueError("AAR_AUTODATA_HTTP_TIMEOUT must be a positive integer") from error
    if timeout < 1:
        raise ValueError("AAR_AUTODATA_HTTP_TIMEOUT must be a positive integer")
    return timeout


def _settings() -> tuple[str, str, Dict[str, str]]:
    url = os.getenv("AAR_AUTODATA_URL", "").rstrip("/")
    sha = os.getenv("AAR_AUTODATA_SHA", "").lower()
    if not url.startswith(("http://", "https://")):
        raise ValueError("AAR_AUTODATA_URL must be an http(s) Autodata service URL")
    if not _SHA_RE.fullmatch(sha):
        raise ValueError("AAR_AUTODATA_SHA must be a full lowercase Git SHA or SHA-256")
    headers: Dict[str, str] = {}
    token = os.getenv("AAR_AUTODATA_TOKEN", "")
    token_file = os.getenv("AAR_AUTODATA_TOKEN_FILE", "")
    if token and token_file:
        raise ValueError(
            "configure only one of AAR_AUTODATA_TOKEN or AAR_AUTODATA_TOKEN_FILE"
        )
    if token_file:
        path = Path(token_file).expanduser().absolute()
        try:
            info = path.lstat()
        except OSError as error:
            raise ValueError("AAR_AUTODATA_TOKEN_FILE is not accessible") from error
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_size > 16 << 10
        ):
            raise ValueError(
                "AAR_AUTODATA_TOKEN_FILE must be an owned mode-0600 regular file"
            )
        token = path.read_text(encoding="utf-8").strip()
        if not token or any(character.isspace() for character in token):
            raise ValueError("AAR_AUTODATA_TOKEN_FILE must contain one non-empty token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return url, sha, headers


def _positive_decimal_env(name: str) -> str:
    raw = os.getenv(name, "").strip()
    try:
        value = Decimal(raw)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a positive finite decimal") from error
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a positive finite decimal")
    return format(value, "f")


def _positive_int_env(name: str) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value < 1 or str(value) != raw:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _operator_controls() -> Dict[str, Any]:
    """Return immutable launch controls safe to send to the adapter.

    The stable budget scope is what makes one cap apply across parallel chains;
    a proposal-issued run id must never become an independent money pool.
    """
    if not autodata_required():
        return {}
    profile = _identifier(
        os.getenv("AAR_AUTODATA_RESOURCE_PROFILE"), "AAR_AUTODATA_RESOURCE_PROFILE"
    )
    profile_digest = os.getenv("AAR_AUTODATA_RESOURCE_PROFILE_SHA256", "").lower()
    if not _DIGEST_RE.fullmatch(profile_digest):
        raise ValueError(
            "AAR_AUTODATA_RESOURCE_PROFILE_SHA256 must be a lowercase SHA-256 digest"
        )
    budget_scope = _identifier(
        os.getenv("AAR_AUTODATA_BUDGET_SCOPE_ID"), "AAR_AUTODATA_BUDGET_SCOPE_ID"
    )
    return {
        "resource_profile": profile,
        "resource_profile_sha256": profile_digest.removeprefix("sha256:"),
        "budget_scope_id": budget_scope,
        "max_cost_usd": _positive_decimal_env("AAR_AUTODATA_MAX_COST_USD"),
        "required_retained_rows": _positive_int_env(
            "AAR_AUTODATA_REQUIRED_RETAINED_ROWS"
        ),
    }


def _response(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}]}


def _service_result(result: Any, *, run_id: str) -> Dict[str, Any]:
    if not isinstance(result, dict):
        raise RuntimeError("Autodata service response must be a JSON object")
    if result.get("error"):
        raise RuntimeError(f"Autodata service rejected request: {result['error']}")
    response_run_id = result.get("run_id")
    if response_run_id is not None and response_run_id != run_id:
        raise RuntimeError("Autodata service response is bound to a different run_id")
    if autodata_required() and response_run_id != run_id:
        raise RuntimeError("required Autodata service response omitted its run_id binding")
    return result


def _identifier(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not _ID_RE.fullmatch(result):
        raise ValueError(f"{name} must contain only letters, digits, dot, underscore, or hyphen")
    return result


def _reject_ref_override(value: Any, path: str = "spec") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in _FORBIDDEN_REF_KEYS:
                raise ValueError(
                    f"{path}.{key} is operator-controlled; the tool uses AAR_AUTODATA_SHA"
                )
            _reject_ref_override(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_ref_override(child, f"{path}[{index}]")


def _validate_spec(spec: Dict[str, Any]) -> None:
    _reject_ref_override(spec)
    if not autodata_required():
        return
    unknown = sorted(set(spec) - _REQUEST_KEYS)
    if unknown:
        raise ValueError(
            "AUTODATA_SPEC contains fields outside the v1 scientific request schema: "
            + ", ".join(unknown)
        )
    missing = sorted(_REQUEST_KEYS - set(spec))
    if missing:
        raise ValueError("AUTODATA_SPEC is missing required fields: " + ", ".join(missing))
    if spec.get("schema") != _REQUEST_SCHEMA:
        raise ValueError(f"AUTODATA_SPEC.schema must be {_REQUEST_SCHEMA!r}")
    if spec.get("resource_profile") != os.getenv("AAR_AUTODATA_RESOURCE_PROFILE"):
        raise ValueError("AUTODATA_SPEC.resource_profile does not match the launch profile")
    if spec.get("training_view") not in {"sft", "preference"}:
        raise ValueError("AUTODATA_SPEC.training_view must be 'sft' or 'preference'")
    locked_view = os.getenv("AAR_AUTODATA_TRAINING_VIEW", "").strip()
    if locked_view and spec.get("training_view") != locked_view:
        raise ValueError(
            "AUTODATA_SPEC.training_view does not match the launch profile"
        )
    if isinstance(spec.get("seed"), bool) or not isinstance(spec.get("seed"), int):
        raise ValueError("AUTODATA_SPEC.seed must be an integer")
    limits = {"safety_axis": 128, "training_mechanism": 512, "goal": 2048}
    for key, maximum_bytes in limits.items():
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise ValueError(f"AUTODATA_SPEC.{key} must be a non-empty string")
        if len(spec[key].encode("utf-8")) > maximum_bytes:
            raise ValueError(
                f"AUTODATA_SPEC.{key} exceeds the {maximum_bytes}-byte profile limit"
            )


def _spec_digest(spec: Dict[str, Any]) -> str:
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _artifact_dir(run_id: str) -> Path:
    team_dir_value = os.getenv("TEAM_DIR", "")
    if not team_dir_value:
        raise ValueError("TEAM_DIR is not configured")
    runtime_value = os.getenv("AAR_RUNTIME_ROOT", "")
    if not runtime_value:
        raise ValueError("AAR_RUNTIME_ROOT is not configured")
    runtime_root = Path(runtime_value).absolute()
    team_dir = Path(team_dir_value).absolute()
    try:
        relative = team_dir.relative_to(runtime_root)
    except ValueError as error:
        raise ValueError("TEAM_DIR must stay inside AAR_RUNTIME_ROOT") from error
    current = runtime_root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise ValueError(f"Autodata artifact parent must not be a symlink: {current}")
        if current.exists() and not current.is_dir():
            raise ValueError(f"Autodata artifact parent must be a directory: {current}")
    autodata_root = team_dir / "autodata"
    if autodata_root.is_symlink():
        raise ValueError(
            f"Autodata artifact parent must not be a symlink: {autodata_root}"
        )
    if autodata_root.exists() and not autodata_root.is_dir():
        raise ValueError(f"Autodata artifact parent must be a directory: {autodata_root}")
    return autodata_root / run_id


def validate_autodata_method_code(code: str) -> Dict[str, Any]:
    """Extract and validate the one literal AUTODATA_SPEC from method source."""
    values = []
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == "AUTODATA_SPEC" for target in targets):
            try:
                values.append(ast.literal_eval(node.value))
            except (ValueError, TypeError) as exc:
                raise ValueError("AUTODATA_SPEC must be a literal Python dictionary") from exc
    if len(values) != 1 or not isinstance(values[0], dict) or not values[0]:
        raise ValueError("approved method must define exactly one non-empty literal AUTODATA_SPEC")
    spec = values[0]
    _validate_spec(spec)
    return spec


def _approved_request(run_id: str, idea_name: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Load AUTODATA_SPEC and its exact proposal/code binding."""
    from .server_api_tools import _method_code, _run_proposal_path

    proposal_path = _run_proposal_path(run_id)
    if not proposal_path.is_file():
        raise ValueError("run_id has no frozen approved proposal")
    proposal = json.loads(proposal_path.read_text())
    if proposal.get("run_id") not in (None, run_id):
        raise ValueError("proposal snapshot is bound to a different run_id")
    if proposal.get("idea_name") != idea_name:
        raise ValueError("idea_name does not match the proposal frozen for run_id")
    code, code_hash = _method_code(idea_name)
    if not code or code_hash != proposal.get("code_hash"):
        raise ValueError("approved method code is missing or changed since proposal approval")
    spec = validate_autodata_method_code(code)
    spec_sha256 = _spec_digest(spec)
    frozen_spec_sha256 = proposal.get("autodata_spec_sha256")
    if frozen_spec_sha256 is not None and frozen_spec_sha256 != spec_sha256:
        raise ValueError("AUTODATA_SPEC does not match the digest frozen at proposal approval")
    return spec, {
        "idea_name": idea_name,
        "method_code_sha256": code_hash,
        "autodata_spec_sha256": spec_sha256,
    }


def _approved_spec(run_id: str, idea_name: str) -> Dict[str, Any]:
    """Backward-compatible helper returning only the frozen specification."""
    return _approved_request(run_id, idea_name)[0]


def _approved_binding(run_id: str) -> Dict[str, Any]:
    from .server_api_tools import _run_proposal_path

    proposal_path = _run_proposal_path(run_id)
    if not proposal_path.is_file():
        raise ValueError("run_id has no frozen approved proposal")
    proposal = json.loads(proposal_path.read_text())
    idea_name = _identifier(proposal.get("idea_name"), "approved idea_name")
    _, binding = _approved_request(run_id, idea_name)
    return binding


def _reject_agent_approval(result: Dict[str, Any]) -> None:
    forbidden = sorted(_APPROVAL_RESULT_KEYS & set(result))
    if forbidden:
        raise ValueError(
            "approval evidence is issued by the delegated policy, not the research agent: "
            + ", ".join(forbidden)
        )
    if result.get("decision") in {"approve", "retry"}:
        raise ValueError(
            "the research agent cannot complete user/resource approval actions; "
            "the adapter's delegated policy must issue the attestation"
        )
    encoded = json.dumps(result)
    if len(encoded.encode()) > 256_000:
        raise ValueError("Autodata action result exceeds 256 KiB")


@tool(
    "autodata_generate",
    "Create the approved run's idempotent Autodata workspace/job and return its first state. "
    "This initiates native workspace authoring; it does not silently approve grounding or the "
    "pipeline. The complete scientific request is read from monitor-approved AUTODATA_SPEC, "
    "while models, spend, concurrency, credentials, and pipeline revision remain operator-pinned.",
    {
        "type": "object",
        "properties": {
            "run_id": {"type": "string", "description": "run_id returned by submit_idea_proposal"},
            "idea_name": {"type": "string", "description": "approved method package name"},
        },
        "required": ["run_id", "idea_name"],
    },
)
async def autodata_generate(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        run_id = _identifier(args.get("run_id"), "run_id")
        idea_name = _identifier(args.get("idea_name"), "idea_name")
        spec, binding = _approved_request(run_id, idea_name)
        url, sha, headers = _settings()
        result = await async_http_post(
            f"{url}/v1/jobs",
            {
                "run_id": run_id,
                "pipeline_sha": sha,
                "spec": spec,
                "binding": binding,
                "controls": _operator_controls(),
            },
            timeout=_http_timeout(),
            headers=headers,
        )
        result = _service_result(result, run_id=run_id)
        if not result.get("job_id"):
            raise RuntimeError("Autodata service response did not contain job_id")
        return _response({"success": True, **result, "run_id": run_id, "pipeline_sha": sha})
    except Exception as exc:
        return _response({"success": False, "error": str(exc)})


@tool(
    "autodata_status",
    "Get state, progress, counts, and provenance summary for the Autodata job bound to an AAR run.",
    {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
    },
)
async def autodata_status(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        run_id = _identifier(args.get("run_id"), "run_id")
        url, sha, headers = _settings()
        result = await async_http_get(
            f"{url}/v1/runs/{run_id}",
            timeout=_http_timeout(),
            headers=headers,
        )
        result = _service_result(result, run_id=run_id)
        return _response({"success": True, **result, "run_id": run_id, "pipeline_sha": sha})
    except Exception as exc:
        return _response({"success": False, "error": str(exc)})


@tool(
    "autodata_step",
    "Advance one deterministic native Autodata workspace or execution step for this approved "
    "run. Returns either safe state or the next visible host action. Repeat after completing "
    "the returned action. Approval attestations are completed by delegated policy, not this agent.",
    {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
    },
)
async def autodata_step(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        run_id = _identifier(args.get("run_id"), "run_id")
        _approved_binding(run_id)
        url, sha, headers = _settings()
        result = await async_http_post(
            f"{url}/v1/runs/{run_id}/step",
            {},
            timeout=_http_timeout(),
            headers=headers,
        )
        result = _service_result(result, run_id=run_id)
        return _response({"success": True, **result, "run_id": run_id, "pipeline_sha": sha})
    except Exception as exc:
        return _response({"success": False, "error": str(exc)})


@tool(
    "autodata_action_begin",
    "Lease a visible semantic authoring action returned by autodata_step. The action remains "
    "bound to this approved AAR run and its current workspace revision.",
    {
        "type": "object",
        "properties": {"run_id": {"type": "string"}, "action_id": {"type": "string"}},
        "required": ["run_id", "action_id"],
    },
)
async def autodata_action_begin(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        run_id = _identifier(args.get("run_id"), "run_id")
        action_id = _identifier(args.get("action_id"), "action_id")
        _approved_binding(run_id)
        url, sha, headers = _settings()
        result = await async_http_post(
            f"{url}/v1/runs/{run_id}/actions/{action_id}/begin",
            {},
            timeout=_http_timeout(),
            headers=headers,
        )
        result = _service_result(result, run_id=run_id)
        if not isinstance(result.get("lease_token"), str) or not result["lease_token"]:
            raise RuntimeError("Autodata action begin response omitted lease_token")
        return _response({"success": True, **result, "run_id": run_id, "pipeline_sha": sha})
    except Exception as exc:
        return _response({"success": False, "error": str(exc)})


@tool(
    "autodata_action_complete",
    "Complete one leased semantic authoring action. This tool rejects attempts to manufacture "
    "user/resource approvals; those are independently attested by the adapter's delegated policy.",
    {
        "type": "object",
        "properties": {
            "run_id": {"type": "string"},
            "action_id": {"type": "string"},
            "lease_token": {"type": "string"},
            "result": {"type": "object"},
        },
        "required": ["run_id", "action_id", "lease_token", "result"],
    },
)
async def autodata_action_complete(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        run_id = _identifier(args.get("run_id"), "run_id")
        action_id = _identifier(args.get("action_id"), "action_id")
        lease_token = str(args.get("lease_token") or "")
        if not lease_token or len(lease_token) > 1024:
            raise ValueError("lease_token must be a non-empty string of at most 1024 characters")
        result_payload = args.get("result")
        if not isinstance(result_payload, dict):
            raise ValueError("result must be a JSON object")
        _reject_agent_approval(result_payload)
        _approved_binding(run_id)
        url, sha, headers = _settings()
        result = await async_http_post(
            f"{url}/v1/runs/{run_id}/actions/{action_id}/complete",
            {"lease_token": lease_token, "result": result_payload},
            timeout=_http_timeout(),
            headers=headers,
        )
        result = _service_result(result, run_id=run_id)
        return _response({"success": True, **result, "run_id": run_id, "pipeline_sha": sha})
    except Exception as exc:
        return _response({"success": False, "error": str(exc)})


@tool(
    "autodata_action_fail",
    "Fail one leased semantic authoring action with a concise reason so Autodata can retain "
    "audit history and deterministically retry or end the run.",
    {
        "type": "object",
        "properties": {
            "run_id": {"type": "string"},
            "action_id": {"type": "string"},
            "lease_token": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["run_id", "action_id", "lease_token", "reason"],
    },
)
async def autodata_action_fail(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        run_id = _identifier(args.get("run_id"), "run_id")
        action_id = _identifier(args.get("action_id"), "action_id")
        lease_token = str(args.get("lease_token") or "")
        reason = str(args.get("reason") or "").strip()
        if not lease_token or len(lease_token) > 1024:
            raise ValueError("lease_token must be a non-empty string of at most 1024 characters")
        if not reason or len(reason) > 4000:
            raise ValueError("reason must contain 1 to 4000 characters")
        _approved_binding(run_id)
        url, sha, headers = _settings()
        result = await async_http_post(
            f"{url}/v1/runs/{run_id}/actions/{action_id}/fail",
            {"lease_token": lease_token, "reason": reason},
            timeout=_http_timeout(),
            headers=headers,
        )
        result = _service_result(result, run_id=run_id)
        return _response({"success": True, **result, "run_id": run_id, "pipeline_sha": sha})
    except Exception as exc:
        return _response({"success": False, "error": str(exc)})


@tool(
    "autodata_fetch",
    "Fetch a completed Autodata dataset and provenance manifest into the immutable directory "
    "$TEAM_DIR/autodata/<run_id>. The training job can read it through AAR_CURRENT_RUN_ID.",
    {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
    },
)
async def autodata_fetch(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        run_id = _identifier(args.get("run_id"), "run_id")
        binding = _approved_binding(run_id)
        output_dir = _artifact_dir(run_id)
        url, sha, headers = _settings()
        result = await async_http_get(
            f"{url}/v1/runs/{run_id}/artifacts",
            timeout=_http_timeout(),
            headers=headers,
        )
        result = _service_result(result, run_id=run_id)
        rows = result.get("rows")
        manifest = result.get("manifest")
        rows_payload = validate_autodata_artifacts(
            rows,
            manifest,
            run_id=run_id,
            expected_pipeline_sha=sha,
            expected_binding=binding,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        rows_path = output_dir / "autodata_rows.jsonl"
        manifest_path = output_dir / "autodata_manifest.json"
        manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        for path, payload in ((rows_path, rows_payload), (manifest_path, manifest_payload)):
            if path.is_symlink():
                raise RuntimeError(f"refusing to write Autodata artifact through symlink: {path}")
            if path.exists():
                if path.read_bytes() != payload:
                    raise RuntimeError(
                        "immutable Autodata artifact already exists with different content"
                    )
                continue
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
        return _response(
            {
                "success": True,
                "run_id": run_id,
                "pipeline_sha": sha,
                "row_count": len(rows),
                "dataset_sha256": manifest["dataset_sha256"],
                "data_dir": str(output_dir),
                "rows_path": str(rows_path),
                "manifest_path": str(manifest_path),
            }
        )
    except Exception as exc:
        return _response({"success": False, "error": str(exc)})


def create_autodata_tools_server():
    """Validate configuration and create the optional SDK MCP server."""
    _settings()
    _operator_controls()
    return create_sdk_mcp_server(
        name="autodata-tools",
        version="2.0.0",
        tools=[
            autodata_generate,
            autodata_status,
            autodata_step,
            autodata_action_begin,
            autodata_action_complete,
            autodata_action_fail,
            autodata_fetch,
        ],
    )
