"""MCP client for the operator-managed Autodata generation service.

The research agent sees only this narrow HTTP surface. Pipeline checkout,
SandoQ/Firecracker credentials, and model-provider credentials stay in the
service. Callers also cannot choose a Git ref: the operator pins
``AAR_AUTODATA_SHA`` for the complete AAR run.
"""

from __future__ import annotations

import json
import os
import re
import ast
import hashlib
from pathlib import Path
from typing import Any, Dict

from claude_agent_sdk import create_sdk_mcp_server, tool

from .http_utils import async_http_get, async_http_post


_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,191}$")
_FORBIDDEN_REF_KEYS = {"branch", "commit", "git_ref", "pipeline_sha", "ref", "sha"}


def autodata_enabled() -> bool:
    return os.getenv("AAR_AUTODATA", "0").lower() in {"1", "true", "yes"}


def _settings() -> tuple[str, str, Dict[str, str]]:
    url = os.getenv("AAR_AUTODATA_URL", "").rstrip("/")
    sha = os.getenv("AAR_AUTODATA_SHA", "").lower()
    if not url.startswith(("http://", "https://")):
        raise ValueError("AAR_AUTODATA_URL must be an http(s) Autodata service URL")
    if not _SHA_RE.fullmatch(sha):
        raise ValueError("AAR_AUTODATA_SHA must be a full lowercase Git SHA or SHA-256")
    headers: Dict[str, str] = {}
    token = os.getenv("AAR_AUTODATA_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return url, sha, headers


def _response(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}]}


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


def _artifact_dir(run_id: str) -> Path:
    team_dir_value = os.getenv("TEAM_DIR", "")
    if not team_dir_value:
        raise ValueError("TEAM_DIR is not configured")
    return Path(team_dir_value).resolve() / "autodata" / run_id


def _approved_spec(run_id: str, idea_name: str) -> Dict[str, Any]:
    """Load AUTODATA_SPEC from the exact method frozen by proposal approval."""
    from .server_api_tools import _method_code, _run_proposal_path

    proposal_path = _run_proposal_path(run_id)
    if not proposal_path.is_file():
        raise ValueError("run_id has no frozen approved proposal")
    proposal = json.loads(proposal_path.read_text())
    if proposal.get("idea_name") != idea_name:
        raise ValueError("idea_name does not match the proposal frozen for run_id")
    code, code_hash = _method_code(idea_name)
    if not code or code_hash != proposal.get("code_hash"):
        raise ValueError("approved method code is missing or changed since proposal approval")
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
    _reject_ref_override(values[0])
    return values[0]


@tool(
    "autodata_generate",
    "Start a provenance-tracked Autodata job after proposal approval. Strong generators such "
    "as Kimi are allowed. The complete generation spec is read from the monitor-approved "
    "AUTODATA_SPEC literal; this call cannot alter it or the operator-pinned pipeline revision.",
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
        spec = _approved_spec(run_id, idea_name)
        url, sha, headers = _settings()
        result = await async_http_post(
            f"{url}/v1/jobs",
            {"run_id": run_id, "pipeline_sha": sha, "spec": spec},
            timeout=int(os.getenv("AAR_AUTODATA_HTTP_TIMEOUT", "120")),
            headers=headers,
        )
        if not isinstance(result, dict) or not result.get("job_id"):
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
            timeout=int(os.getenv("AAR_AUTODATA_HTTP_TIMEOUT", "120")),
            headers=headers,
        )
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
        output_dir = _artifact_dir(run_id)
        url, sha, headers = _settings()
        result = await async_http_get(
            f"{url}/v1/runs/{run_id}/artifacts",
            timeout=int(os.getenv("AAR_AUTODATA_HTTP_TIMEOUT", "120")),
            headers=headers,
        )
        if not isinstance(result, dict):
            raise RuntimeError("Autodata artifacts response must be a JSON object")
        rows = result.get("rows")
        manifest = result.get("manifest")
        if not isinstance(rows, list) or not isinstance(manifest, dict):
            raise RuntimeError("Autodata artifacts response requires rows[] and manifest{}")
        response_sha = str(manifest.get("pipeline_sha", "")).lower()
        if response_sha != sha:
            raise RuntimeError(
                f"Autodata artifact SHA mismatch: expected {sha}, received {response_sha or '<missing>'}"
            )
        if manifest.get("schema") != "aar.autodata.dataset/v1":
            raise RuntimeError("Autodata artifact manifest has an unsupported schema")
        if manifest.get("run_id") != run_id:
            raise RuntimeError("Autodata artifact manifest is bound to a different run_id")
        rows_payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        if manifest.get("row_count") != len(rows):
            raise RuntimeError("Autodata artifact manifest row_count mismatch")
        if manifest.get("dataset_sha256") != hashlib.sha256(rows_payload.encode()).hexdigest():
            raise RuntimeError("Autodata artifact manifest dataset digest mismatch")
        output_dir.mkdir(parents=True, exist_ok=True)
        rows_path = output_dir / "autodata_rows.jsonl"
        manifest_path = output_dir / "autodata_manifest.json"
        rows_path.write_text(rows_payload)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return _response(
            {
                "success": True,
                "run_id": run_id,
                "pipeline_sha": sha,
                "row_count": len(rows),
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
    return create_sdk_mcp_server(
        name="autodata-tools",
        version="1.0.0",
        tools=[autodata_generate, autodata_status, autodata_fetch],
    )
