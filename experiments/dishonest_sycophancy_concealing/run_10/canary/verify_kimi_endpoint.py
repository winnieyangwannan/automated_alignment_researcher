#!/usr/bin/env python3
"""Require a complete Kimi -> AAR MCP tool -> Kimi round trip."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from aar.research_loop.kimi_agent import KimiAgent


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _endpoint_identity(workspace: Path) -> dict[str, str]:
    deployment = os.environ.get("AAR_KIMI_SERVE_DEPLOYMENT", "").strip()
    expected_model = os.environ.get("AAR_KIMI_EXPECTED_MODEL", "").strip()
    serve_root = Path(os.environ["AAR_SERVE_API_V2_ROOT"]).resolve(strict=True)
    serve = serve_root / "serve.sh"
    result = subprocess.run(
        [str(serve), "generate-opencode-config", deployment],
        cwd=serve_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    config = json.loads(result.stdout)
    providers = config["provider"]
    if not isinstance(providers, dict) or len(providers) != 1:
        raise RuntimeError("Kimi health check expected exactly one provider")
    provider = next(iter(providers.values()))
    options = provider["options"]
    models = provider["models"]
    if not isinstance(models, dict) or len(models) != 1:
        raise RuntimeError("Kimi health check expected exactly one configured model")
    model = next(iter(models))
    base_url = str(options["baseURL"]).rstrip("/")
    api_key = str(options["apiKey"])
    if model != expected_model or not api_key:
        raise RuntimeError("Kimi health check model or credential mismatch")

    request = Request(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310 - verified serve_api URL
        model_payload = json.loads(response.read())
    if not isinstance(model_payload, dict):
        raise RuntimeError("Kimi health check returned an invalid model list")
    served_models = {
        item.get("id")
        for item in model_payload.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if model not in served_models:
        raise RuntimeError(
            f"Kimi health check expected {model}, served {sorted(served_models)}"
        )

    cli = Path(os.environ["KIMI_CLI_PATH"]).resolve(strict=True)
    node_version = subprocess.run(
        ["node", "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    commit = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    return {
        "git_commit": commit,
        "deployment": deployment,
        "model": model,
        "base_url": base_url,
        "kimi_cli_sha256": _sha256(cli),
        "node_version": node_version,
    }


def _reusable_cache(
    cache: Path,
    identity: dict[str, str],
    ttl_seconds: int,
    *,
    now: datetime | None = None,
) -> dict[str, object] | None:
    if not cache.is_file():
        return None
    try:
        payload: Any = json.loads(cache.read_text())
        verified_at = datetime.fromisoformat(payload["verified_at_utc"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    current = now or datetime.now(UTC)
    age = (current - verified_at.astimezone(UTC)).total_seconds()
    required = (
        "bash_tool_roundtrip",
        "mcp_tool_roundtrip",
        "named_tool_choice_checkpoint",
    )
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 2
        or payload.get("status") != "passed"
        or payload.get("identity") != identity
        or age < 0
        or age > ttl_seconds
        or not all(payload.get(field) is True for field in required)
    ):
        return None
    reused = dict(payload)
    reused["cache_reused"] = True
    reused["reused_at_utc"] = current.isoformat()
    reused["health_check"] = True
    return reused


def _promote_proof(
    source: Path,
    identity: dict[str, str],
    ttl_seconds: int,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    payload: Any = json.loads(source.read_text())
    current = now or datetime.now(UTC)
    age = current.timestamp() - source.stat().st_mtime
    required = (
        "bash_tool_roundtrip",
        "mcp_tool_roundtrip",
        "named_tool_choice_checkpoint",
    )
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "passed"
        or payload.get("deployment") != identity["deployment"]
        or payload.get("model") != identity["model"]
        or age < 0
        or age > ttl_seconds
        or not all(payload.get(field) is True for field in required)
    ):
        raise RuntimeError("prior Kimi MCP proof is stale, mismatched, or incomplete")
    return {
        "schema_version": 2,
        "status": "passed",
        "model": identity["model"],
        "deployment": identity["deployment"],
        "bash_tool_roundtrip": True,
        "mcp_tool_roundtrip": True,
        "sequential_mcp_tool_roundtrips": payload.get(
            "sequential_mcp_tool_roundtrips", 1
        ),
        "named_tool_choice_checkpoint": True,
        "tools": payload.get("tools", []),
        "identity": identity,
        "verified_at_utc": current.isoformat(),
        "cache_reused": False,
        "proof_promoted": True,
        "health_check": True,
        "promoted_from": str(source),
    }


async def verify(workspace: Path, timeout_seconds: int) -> dict[str, object]:
    deployment = os.environ.get("AAR_KIMI_SERVE_DEPLOYMENT", "").strip()
    expected_model = os.environ.get("AAR_KIMI_EXPECTED_MODEL", "").strip()
    if not deployment or not expected_model:
        raise RuntimeError(
            "AAR_KIMI_SERVE_DEPLOYMENT and AAR_KIMI_EXPECTED_MODEL are required"
        )
    turn_timeout = timeout_seconds
    if turn_timeout < 30 or turn_timeout > 600:
        raise RuntimeError("Kimi preflight timeout must be 30..600 seconds")
    max_output_tokens = int(
        os.environ.get("AAR_KIMI_PREFLIGHT_MAX_OUTPUT_TOKENS", "1024")
    )
    if max_output_tokens < 128 or max_output_tokens > 4096:
        raise RuntimeError(
            "AAR_KIMI_PREFLIGHT_MAX_OUTPUT_TOKENS must be 128..4096"
        )
    os.environ["KIMI_MODEL_MAX_OUTPUT_SIZE"] = str(max_output_tokens)
    os.environ["KIMI_MODEL_MAX_COMPLETION_TOKENS"] = str(max_output_tokens)
    result = await KimiAgent(
        "run10-preflight",
        workspace,
        model=None,
        cli_path=os.environ.get("KIMI_CLI_PATH"),
        include_prior_work=True,
        system_prompt=(
            "You are a noninteractive endpoint verifier. Follow the user's exact "
            "tool sequence and do not create or manage a separate goal."
        ),
        disallowed_tools=[
            "CreateGoal",
            "UpdateGoal",
            "SetGoalBudget",
            "TodoList",
            "WaitFor",
            "Agent",
            "AgentSwarm",
        ],
        completion_tool="get_literature",
        max_continuations=2,
        auto_approve=True,
        turn_timeout_seconds=timeout_seconds,
    ).execute(
        "First call the Bash tool exactly once with command `test -w \"$PWD\" && "
        "printf KIMI_AUTO_OK`. Only after receiving that result, call the "
        "get_literature MCP tool exactly once with dimension set to honesty. Only "
        "after receiving that tool result, reply with exactly KIMI_MCP_CANARY_OK."
    )
    tools = [str(item.get("tool", "")) for item in result.output.get("tool_uses", [])]
    texts = [str(item) for item in result.output.get("text_outputs", [])]
    bash_positions = [index for index, name in enumerate(tools) if name == "Bash"]
    literature_positions = [
        index
        for index, name in enumerate(tools)
        if name == "get_literature" or name.endswith("get_literature")
    ]
    tool_ok = (
        len(bash_positions) == 1
        and len(literature_positions) == 1
        and bash_positions[0] < literature_positions[0]
    )
    response_ok = any(text.strip().endswith("KIMI_MCP_CANARY_OK") for text in texts)
    if not result.success or not tool_ok or not response_ok:
        stderr_tail = str(result.output.get("stderr", ""))[-2000:]
        raise RuntimeError(
            f"Kimi MCP round trip failed: success={result.success}, tools={tools}, "
            f"response_ok={response_ok}, error={result.error}, stderr={stderr_tail}"
        )

    try:
        forced_result = await asyncio.wait_for(
            KimiAgent(
                "run10-forced-tool-preflight",
                workspace,
                model=None,
                cli_path=os.environ.get("KIMI_CLI_PATH"),
                include_prior_work=False,
                system_prompt=(
                    "You are a noninteractive endpoint verifier. Follow the user's "
                    "exact two-turn instruction and do not create or manage a separate "
                    "goal."
                ),
                disallowed_tools=[
                    "CreateGoal",
                    "UpdateGoal",
                    "SetGoalBudget",
                    "TodoList",
                    "WaitFor",
                    "Agent",
                    "AgentSwarm",
                ],
                completion_tool="Bash",
                max_continuations=2,
                auto_approve=True,
                force_checkpoint_tools=True,
                turn_timeout_seconds=turn_timeout,
            ).execute(
                "In this first turn, do not call any tool; reply exactly "
                "KIMI_FORCE_READY. On the later turn that requires Bash, call it with "
                "command `printf KIMI_FORCE_OK`."
            ),
            timeout=turn_timeout + 10,
        )
    except TimeoutError as error:
        raise RuntimeError(
            f"Kimi named-tool checkpoint exceeded {turn_timeout} seconds"
        ) from error
    forced_uses = [
        item
        for item in forced_result.output.get("tool_uses", [])
        if str(item.get("tool", "")).rsplit("__", 1)[-1] == "Bash"
    ]
    forced_commands = [
        str((item.get("input") or {}).get("command", ""))
        for item in forced_uses
    ]
    forced_ok = (
        forced_result.success
        and forced_result.output.get("continuations", 0) >= 1
        and bool(forced_commands)
        and all(command == "printf KIMI_FORCE_OK" for command in forced_commands)
    )
    if not forced_ok:
        raise RuntimeError(
            "Kimi named tool-choice checkpoint failed: "
            f"success={forced_result.success}, continuations="
            f"{forced_result.output.get('continuations')}, tools={forced_uses}, "
            f"error={forced_result.error}"
        )
    return {
        "schema_version": 2,
        "status": "passed",
        "model": expected_model,
        "deployment": deployment,
        "bash_tool_roundtrip": True,
        "mcp_tool_roundtrip": True,
        "sequential_mcp_tool_roundtrips": 1,
        "named_tool_choice_checkpoint": True,
        "preflight_max_output_tokens": max_output_tokens,
        "tools": [*tools, "Bash"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--promote-proof", type=Path)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.environ.get("AAR_KIMI_PREFLIGHT_TIMEOUT_SECONDS", "300")),
    )
    parser.add_argument(
        "--cache-ttl-seconds",
        type=int,
        default=int(
            os.environ.get("AAR_KIMI_PREFLIGHT_CACHE_TTL_SECONDS", "21600")
        ),
    )
    args = parser.parse_args()
    if not 30 <= args.timeout_seconds <= 600:
        parser.error("timeout must be between 30 and 600 seconds")
    if args.cache_ttl_seconds < 1:
        parser.error("cache TTL must be positive")

    workspace = args.workspace.resolve(strict=True)
    identity = _endpoint_identity(workspace)
    cache = args.cache.resolve() if args.cache else None
    cached = (
        _reusable_cache(cache, identity, args.cache_ttl_seconds)
        if cache is not None
        else None
    )
    if cached is not None:
        _write_json_atomic(args.output, cached)
        print("Kimi endpoint healthy; reused matching MCP preflight proof")
        return

    if args.promote_proof is not None:
        proof = _promote_proof(
            args.promote_proof.resolve(strict=True),
            identity,
            args.cache_ttl_seconds,
        )
        if cache is not None:
            _write_json_atomic(cache, proof)
        _write_json_atomic(args.output, proof)
        print("Kimi endpoint healthy; promoted recent matching MCP proof")
        return

    try:
        proof = asyncio.run(
            asyncio.wait_for(
                verify(workspace, args.timeout_seconds),
                timeout=args.timeout_seconds,
            )
        )
    except TimeoutError as error:
        raise RuntimeError(
            f"Kimi MCP preflight exceeded {args.timeout_seconds} seconds total"
        ) from error
    proof.update(
        {
            "identity": identity,
            "verified_at_utc": datetime.now(UTC).isoformat(),
            "cache_reused": False,
            "health_check": True,
        }
    )
    if cache is not None:
        _write_json_atomic(cache, proof)
    _write_json_atomic(args.output, proof)
    print("Kimi endpoint and AAR MCP round trip passed with a fresh proof")


if __name__ == "__main__":
    main()
