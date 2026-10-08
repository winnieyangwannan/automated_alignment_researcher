#!/usr/bin/env python3
"""Run one bounded AAR research agent against the native AutoData plugin.

The smoke uses the unmodified upstream plugin, its ``autodata:autodata`` skill,
and its packaged CLI wrapper. It never registers or calls an AutoData MCP tool.
The execution is the deterministic upstream toy recipe, so no model, network,
SandoQ, or production credential is needed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


REQUIRED_AGENT_TOOLS = frozenset({"Skill", "Bash"})
NATIVE_DATASET_SCHEMA = "autodata.dataset/v1"


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _prepare_fixture(plugin_root: Path, output_root: Path) -> tuple[Path, str]:
    checkout = plugin_root.parent.parent
    source = checkout / "recipes" / "toy"
    if not source.is_dir():
        raise RuntimeError(f"canonical AutoData toy recipe is missing: {source}")
    fixture = output_root / "fixture" / "toy"
    shutil.copytree(source, fixture)
    return fixture, _tree_digest(fixture)


def _approval_document(fixture_digest: str) -> dict[str, Any]:
    """Return pre-authorized decisions for this immutable local fixture only."""
    return {
        "schema": "aar.autodata.plugin-smoke-approvals/v1",
        "fixture_sha256": fixture_digest,
        "scope": "local deterministic upstream toy recipe only",
        "decisions": {
            "approve_grounding": {
                "decision": "approve",
                "feedback": "Operator pre-approved the pinned toy grounding.",
                "target": "grounding",
                "user_acknowledged": True,
            },
            "approve_baseline": {
                "decision": "approve",
                "feedback": "Operator pre-approved the tested local toy baseline.",
                "target": "pipeline",
                "user_acknowledged": True,
            },
        },
    }


def _agent_prompt(output_root: Path, fixture: Path, fixture_digest: str) -> str:
    state = output_root / "native" / "state.db"
    artifacts = output_root / "native" / "artifacts"
    workspaces = output_root / "native" / "workspaces"
    draft = output_root / "draft"
    export = output_root / "export" / "dataset.json"
    completion = output_root / "completion.json"
    approvals = output_root / "fixture" / "approvals.json"
    return f"""You are running one bounded AAR AutoData plugin smoke test.

First load the `autodata:autodata` skill. Use only Bash plus the native wrapper
documented by that skill. There is no AutoData MCP interface: never call a tool
whose name starts with `mcp__autodata`.

The immutable upstream toy recipe is at `{fixture}` and has SHA-256 tree digest
`{fixture_digest}`. Its exact pre-authorized local-only approval decisions are at
`{approvals}`. Those decisions apply only while the fixture digest is unchanged.
The trusted launcher already verified this digest. Do not recompute it or inspect
AutoData implementation internals; start the native workspace immediately.

Use these stable native CLI roots on every command:

```bash
python3 "${{AAR_AUTODATA_PLUGIN_ROOT}}/scripts/autodata.py" \\
  --state {state} \\
  --artifacts {artifacts} \\
  --workspaces {workspaces} \\
  <command>
```

Complete this workflow:

1. Create a native workspace from `{fixture / 'autodata.workspace.json'}` with
   writable draft root `{draft}`.
2. Step the workspace. For editable authoring actions, copy only the matching
   files from the immutable toy fixture into the action's `editable_root` and
   `allowed_paths`, then complete the native action lease with a small JSON
   result. For the two approval actions, submit only the matching fixed decision
   from `{approvals}`. Do not invent or broaden an approval.
3. Continue native workspace steps until it freezes and returns its execution ID.
4. Step that native execution and fulfill its visible actions according to the
   loaded skill until it completes. Do not use network services or credentials.
5. Export the completed execution to `{export}` with native `autodata export`.
6. Write `{completion}` as JSON containing `workspace_id`, `execution_id`,
   `workspace_status`, `execution_status`, and `export_path`.
7. Finish with the exact text `AUTODATA_PLUGIN_AGENT_SMOKE_COMPLETE`.

Do not train or evaluate a model, browse the web, access benchmarks, change the
plugin, or write outside `{output_root}`.
"""


def _configure_environment(
    *,
    output_root: Path,
    plugin_root: Path,
    pipeline_sha: str,
    repo: Path,
    real_claude_cli: Path,
) -> None:
    os.environ.update(
        {
            "AAR_AUTODATA": "1",
            "AAR_AUTODATA_PLUGIN_ROOT": str(plugin_root),
            "AAR_AUTODATA_SHA": pipeline_sha,
            "AAR_REPO": str(repo),
            "AAR_RUNTIME_ROOT": str(output_root),
            "AAR_RESEARCH_ENV_ISOLATION": "1",
            "AAR_CLAUDE_REAL_CLI_PATH": str(real_claude_cli),
            # Use Meta's native Claude sandbox for this credential-free plugin
            # smoke. Nesting that sandbox inside AAR's production Bubblewrap
            # wrapper is not portable on devservers because the outer user
            # namespace does not map UID 0, which the native launcher needs
            # while constructing its own sandbox.
            "CLAUDE_CLI_PATH": str(real_claude_cli),
            "AUTODATA_CACHE_DIR": str(output_root / "autodata" / "plugin-cache"),
            "TEAM_DIR": str(output_root / "team"),
        }
    )


async def _run_agent(
    *, output_root: Path, prompt: str, plugin_root: Path, model: str
) -> tuple[dict[str, Any], list[str]]:
    from claude_agent_sdk import AssistantMessage, ToolUseBlock

    from aar.research_loop.agent import AutonomousAgentLoop, BaseAgent

    observed_tools: list[str] = []

    class AutoDataPluginSmokeLoop(AutonomousAgentLoop):
        def _get_prompt(self) -> str:
            return prompt

        def _create_agent(self, session_id: str, message_callback=None) -> BaseAgent:
            def observe(message: Any) -> None:
                if message_callback is not None:
                    message_callback(message)
                if isinstance(message, AssistantMessage):
                    observed_tools.extend(
                        content.name
                        for content in message.content
                        if isinstance(content, ToolUseBlock)
                    )

            return BaseAgent(
                name=f"autodata-plugin-smoke-{session_id}",
                allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
                workspace=output_root,
                mcp_servers={},
                model=model,
                cli_path=os.getenv("CLAUDE_CLI_PATH") or shutil.which("claude"),
                message_callback=observe,
                permission_mode="bypassPermissions",
                system_prompt=(
                    "Load autodata:autodata, then use the unmodified plugin's native "
                    "CLI. Never use an AutoData MCP tool or any network service."
                ),
                # An explicit base-tool list suppresses every omitted built-in,
                # including Skill. Keep Skill here while the SDK's `skills`
                # option adds the narrower Skill(autodata:autodata) allow rule.
                tools=["Skill", "Bash", "Read", "Write", "Edit", "Glob", "Grep"],
                setting_sources=[],
                strict_mcp_config=True,
                plugins=[{"type": "local", "path": str(plugin_root)}],
                skills=["autodata:autodata"],
            )

    loop = AutoDataPluginSmokeLoop(
        idea_uid="autodata-plugin-agent-smoke",
        idea_name="autodata_plugin_agent_smoke",
        workspace=output_root,
        logs_dir=output_root / "logs",
        max_runtime_seconds=900,
        max_iterations=1,
        model=model,
        local_mode=True,
    )
    return await loop.run(), observed_tools


def _verify_result(
    output_root: Path,
    loop_result: dict[str, Any],
    observed_tools: list[str],
) -> dict[str, Any]:
    missing = sorted(REQUIRED_AGENT_TOOLS - set(observed_tools))
    forbidden = [name for name in observed_tools if name.startswith("mcp__autodata")]
    if loop_result.get("successful_sessions") != 1 or missing or forbidden:
        raise RuntimeError(
            "live AAR agent did not complete the native plugin tool path; "
            f"missing={missing}, forbidden={forbidden}, loop={loop_result}"
        )

    completion_path = output_root / "completion.json"
    if not completion_path.is_file() or completion_path.is_symlink():
        raise RuntimeError("agent did not write a safe completion record")
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    if not isinstance(completion, dict):
        raise RuntimeError("completion record is not an object")
    if completion.get("workspace_status") != "frozen":
        raise RuntimeError(f"workspace did not freeze: {completion}")
    if completion.get("execution_status") != "completed":
        raise RuntimeError(f"execution did not complete: {completion}")

    export_path = (output_root / "export" / "dataset.json").resolve()
    if Path(str(completion.get("export_path", ""))).resolve() != export_path:
        raise RuntimeError("completion record names an unexpected export path")
    if not export_path.is_file() or export_path.is_symlink():
        raise RuntimeError("native AutoData dataset export is missing or unsafe")
    dataset_bytes = export_path.read_bytes()
    dataset = json.loads(dataset_bytes)
    if not isinstance(dataset, dict) or dataset.get("schema") != NATIVE_DATASET_SCHEMA:
        raise RuntimeError("native AutoData export has an unsupported schema")
    items = dataset.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("native AutoData export contains no generated items")

    return {
        "schema": "aar.autodata.plugin-agent-smoke/v1",
        "workspace_id": completion.get("workspace_id"),
        "execution_id": completion.get("execution_id"),
        "observed_tools": observed_tools,
        "autodata_mcp_calls": forbidden,
        "dataset_schema": dataset["schema"],
        "dataset_item_count": len(items),
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "export_path": str(export_path),
        "training_or_evaluation_performed": False,
    }


async def _main(args: argparse.Namespace) -> None:
    repo = Path(__file__).resolve().parents[1]
    output_root = Path(args.output_root).resolve()
    try:
        output_root.relative_to(repo)
    except ValueError:
        pass
    else:
        raise RuntimeError("smoke output root must not be inside the source checkout")
    output_root.mkdir(parents=True, exist_ok=False)
    plugin_root = Path(args.plugin_root).expanduser().resolve(strict=True)
    real_claude_cli = Path(args.claude_cli).expanduser().resolve(strict=True)
    if not real_claude_cli.is_file() or not os.access(real_claude_cli, os.X_OK):
        raise RuntimeError("Claude CLI is not executable")
    _configure_environment(
        output_root=output_root,
        plugin_root=plugin_root,
        pipeline_sha=args.pipeline_sha,
        repo=repo,
        real_claude_cli=real_claude_cli,
    )

    from aar.research_loop.autodata_plugin import resolve_autodata_plugin

    plugin = resolve_autodata_plugin()
    if plugin is None:
        raise RuntimeError("AutoData plugin unexpectedly disabled")
    fixture, fixture_digest = _prepare_fixture(plugin.root, output_root)
    approvals_path = output_root / "fixture" / "approvals.json"
    approvals_path.write_text(
        json.dumps(_approval_document(fixture_digest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prompt = _agent_prompt(output_root, fixture, fixture_digest)
    (output_root / "agent_prompt.md").write_text(prompt, encoding="utf-8")

    loop_result, observed_tools = await _run_agent(
        output_root=output_root,
        prompt=prompt,
        plugin_root=plugin.root,
        model=args.model,
    )
    report = {
        **_verify_result(output_root, loop_result, observed_tools),
        "plugin_root": str(plugin.root),
        "autodata_git_sha": plugin.git_sha,
        "agent_model": args.model,
        "loop": loop_result,
        "fixture_sha256": fixture_digest,
    }
    report_path = output_root / "agent_smoke_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"AUTODATA_PLUGIN_AGENT_SMOKE_PASS report={report_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plugin-root",
        default=os.getenv("AAR_AUTODATA_PLUGIN_ROOT", ""),
        required=not bool(os.getenv("AAR_AUTODATA_PLUGIN_ROOT")),
    )
    parser.add_argument("--pipeline-sha", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--claude-cli",
        default=os.getenv("AAR_CLAUDE_REAL_CLI_PATH") or shutil.which("claude") or "",
        required=not bool(
            os.getenv("AAR_CLAUDE_REAL_CLI_PATH") or shutil.which("claude")
        ),
    )
    parser.add_argument(
        "--model", default=os.getenv("AAR_AGENT_MODEL", "claude-opus-4-8")
    )
    args = parser.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
