"""Compatibility checks for optional Claude Agent SDK options."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
AGENT_MODULE = ROOT / "aar" / "research_loop" / "agent.py"


def _load_agent_module(options_class: type) -> types.ModuleType:
    sdk = types.ModuleType("claude_agent_sdk")
    sdk.ClaudeAgentOptions = options_class
    for name in (
        "ClaudeSDKClient",
        "AssistantMessage",
        "ResultMessage",
        "TextBlock",
        "ToolUseBlock",
    ):
        setattr(sdk, name, type(name, (), {}))

    server_tools = types.ModuleType("aar.research_loop.tools.server_api_tools")
    server_tools.create_server_api_tools_server = lambda: None
    prior_tools = types.ModuleType("aar.research_loop.tools.prior_work_tools")
    prior_tools.create_prior_work_tools_server = lambda: None
    findings = types.ModuleType("aar.research_loop.tools.findings_sync")
    findings.FindingsSync = type("FindingsSync", (), {})

    module_name = "aar.research_loop.agent_sdk_compat_under_test"
    spec = importlib.util.spec_from_file_location(module_name, AGENT_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            module_name: module,
            "claude_agent_sdk": sdk,
            "aar.research_loop.tools.server_api_tools": server_tools,
            "aar.research_loop.tools.prior_work_tools": prior_tools,
            "aar.research_loop.tools.findings_sync": findings,
        },
    ):
        spec.loader.exec_module(module)
    return module


class AgentSdkCompatibilityTest(unittest.TestCase):
    def test_research_subprocess_environment_hides_operator_secrets(self) -> None:
        class Options:
            def __init__(self) -> None:
                pass

        agent_module = _load_agent_module(Options)
        operator_env = {
            "SERVICE_STATUS_URL": "http://service.example:8123",
            "SANDOQ_FLEET_AUTH_TOKEN": "sandoq-secret",
            "HARNESS_ENV": "/operator/harness.env",
            "MODEL_API_KEY": "model-secret",
            "AAR_MONITOR_MODEL_API_KEY": "monitor-secret",
            "AAR_RUN8_EXECSIDECAR_TOKEN_FILE": "/operator/execsidecar.token",
            "AAR_RUN8_BROKER_TOKEN_FILE": "/operator/broker.token",
        }
        with patch.dict(os.environ, operator_env, clear=True):
            with agent_module._sanitized_research_subprocess_environment():
                self.assertEqual(
                    os.environ.get("SERVICE_STATUS_URL"),
                    "http://service.example:8123",
                )
                for name in operator_env:
                    if name != "SERVICE_STATUS_URL":
                        self.assertNotIn(name, os.environ)

            # The trusted parent regains its services and integrity-monitor
            # credentials after the research subprocess is spawned.
            self.assertEqual(
                os.environ["SANDOQ_FLEET_AUTH_TOKEN"],
                "sandoq-secret",
            )
            self.assertEqual(
                os.environ["AAR_MONITOR_MODEL_API_KEY"], "monitor-secret"
            )

    def test_secret_name_filter_covers_provider_and_token_path_variants(self) -> None:
        class Options:
            def __init__(self) -> None:
                pass

        agent_module = _load_agent_module(Options)
        for name in (
            "SOME_NEW_PROVIDER_API_KEY",
            "SOME_SERVICE_TOKEN",
            "SOME_SERVICE_TOKEN_FILE",
            "CUSTOM_CREDENTIAL_PATH",
            "SANDOQ_FLEET_AUTH_TOKEN",
        ):
            self.assertTrue(agent_module._is_research_child_secret_name(name), name)
        self.assertFalse(
            agent_module._is_research_child_secret_name("SERVICE_STATUS_URL")
        )

    def test_sdk_client_is_spawned_inside_sanitized_boundary(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        observed: dict[str, str] = {}

        class Client:
            def __init__(self, *, options) -> None:
                self.options = options

            async def __aenter__(self):
                observed.update(os.environ)
                return self

            async def __aexit__(self, *_args) -> None:
                return None

            async def query(self, _task: str) -> None:
                return None

            async def receive_response(self):
                result = agent_module.ResultMessage()
                result.is_error = False
                result.result = "ok"
                yield result

        agent_module.ClaudeSDKClient = Client
        base = agent_module.BaseAgent(
            name="isolated",
            allowed_tools=[],
            workspace=Path("/tmp/workspace"),
            mcp_servers={},
        )
        operator_env = {
            "SERVICE_STATUS_URL": "http://service.example:8123",
            "SANDOQ_FLEET_AUTH_TOKEN": "sandoq-secret",
            "MODEL_API_KEY": "operator-secret",
        }
        with patch.dict(os.environ, operator_env, clear=True):
            result = asyncio.run(base._execute_once("test", 0.0))
            self.assertIn("SANDOQ_FLEET_AUTH_TOKEN", os.environ)

        self.assertTrue(result.success)
        self.assertEqual(
            observed["SERVICE_STATUS_URL"], "http://service.example:8123"
        )
        self.assertNotIn("SANDOQ_FLEET_AUTH_TOKEN", observed)
        self.assertNotIn("MODEL_API_KEY", observed)

    def test_restrictive_options_are_forwarded_only_when_explicit(self) -> None:
        class Options:
            def __init__(self) -> None:
                pass

        agent_module = _load_agent_module(Options)
        base = agent_module.BaseAgent(
            name="restricted",
            allowed_tools=["Bash(/repo/scripts/aar-paper-search *)", "mcp__lit__get"],
            workspace=Path("/tmp/workspace"),
            mcp_servers={"lit": {"type": "sdk"}},
            tools=["Bash"],
            setting_sources=[],
            strict_mcp_config=True,
        )

        options = base._build_options_dict()

        self.assertEqual(options["tools"], ["Bash"])
        self.assertEqual(options["setting_sources"], [])
        self.assertIs(options["strict_mcp_config"], True)
        self.assertEqual(options["mcp_servers"], {"lit": {"type": "sdk"}})
        self.assertIn("mcp__lit__get", options["allowed_tools"])

        ordinary = agent_module.BaseAgent(
            name="ordinary",
            allowed_tools=[],
            workspace=Path("/tmp/workspace"),
            mcp_servers={},
        )._build_options_dict()
        self.assertNotIn("tools", ordinary)
        self.assertNotIn("setting_sources", ordinary)
        self.assertNotIn("strict_mcp_config", ordinary)

    def test_local_plugin_and_skill_are_forwarded_when_supported(self) -> None:
        class Options:
            def __init__(
                self,
                *,
                plugins: list[dict[str, str]] | None = None,
                skills: list[str] | None = None,
            ) -> None:
                self.plugins = plugins
                self.skills = skills

        agent_module = _load_agent_module(Options)
        base = agent_module.BaseAgent(
            name="plugin",
            allowed_tools=["Bash"],
            workspace=Path("/tmp/workspace"),
            mcp_servers={},
            plugins=[{"type": "local", "path": "/pinned/plugin/autodata"}],
            skills=["autodata:autodata"],
        )

        options = base._build_options_dict()

        self.assertEqual(
            options["plugins"],
            [{"type": "local", "path": "/pinned/plugin/autodata"}],
        )
        self.assertEqual(options["skills"], ["autodata:autodata"])

    def test_older_sdk_omits_unsupported_reasoning_options(self) -> None:
        class OldOptions:
            def __init__(self, *, model: str | None = None) -> None:
                self.model = model

        agent = _load_agent_module(OldOptions)
        options: dict[str, object] = {"model": "claude-sonnet-4-6"}

        agent._add_supported_reasoning_options(options)

        self.assertEqual(options, {"model": "claude-sonnet-4-6"})

    def test_newer_sdk_receives_supported_reasoning_options(self) -> None:
        class NewOptions:
            def __init__(
                self,
                *,
                thinking: dict[str, str] | None = None,
                effort: str | None = None,
            ) -> None:
                self.thinking = thinking
                self.effort = effort

        agent = _load_agent_module(NewOptions)
        options: dict[str, object] = {}

        with patch.dict("os.environ", {"AAR_EFFORT": "xhigh"}, clear=False):
            agent._add_supported_reasoning_options(options)

        self.assertEqual(
            options,
            {
                "thinking": {"type": "adaptive", "display": "summarized"},
                "effort": "xhigh",
            },
        )

    def test_session_budget_is_forwarded_and_requires_sdk_support(self) -> None:
        class NewOptions:
            def __init__(self, *, max_budget_usd: float | None = None) -> None:
                self.max_budget_usd = max_budget_usd

        agent = _load_agent_module(NewOptions)
        options: dict[str, object] = {}
        with patch.dict(
            os.environ, {"AAR_CLAUDE_SESSION_BUDGET_USD": "250"}, clear=False
        ):
            agent._add_supported_budget_options(options)
        self.assertEqual(options, {"max_budget_usd": 250.0})

        class OldOptions:
            def __init__(self, *, model: str | None = None) -> None:
                self.model = model

        old_agent = _load_agent_module(OldOptions)
        with patch.dict(
            os.environ, {"AAR_CLAUDE_SESSION_BUDGET_USD": "250"}, clear=False
        ), self.assertRaisesRegex(RuntimeError, "cannot enforce"):
            old_agent._add_supported_budget_options({})

    def test_full_agent_meta_secure_mode_uses_restricted_web_surface(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        loop = object.__new__(agent_module.AutonomousAgentLoop)
        loop.workspace = ROOT
        loop.mcp_servers = {"server-api-tools": {"type": "sdk"}}
        loop.model = "claude-opus-4-8"
        loop.local_mode = True

        with patch.dict(
            os.environ,
            {
                "AAR_WEB_MODE": "meta_secure",
                "CLAUDE_CLI_PATH": "/usr/local/bin/claude",
            },
            clear=False,
        ):
            base = loop._create_agent("smoke")
            options = base._build_options_dict()

        self.assertEqual(options["permission_mode"], "dontAsk")
        self.assertEqual(options["setting_sources"], [])
        self.assertIs(options["strict_mcp_config"], True)
        self.assertNotIn("WebSearch", options["allowed_tools"])
        self.assertNotIn("WebFetch", options["allowed_tools"])
        self.assertTrue(
            any("aar-paper-search" in tool for tool in options["allowed_tools"])
        )
        self.assertEqual(options["cli_path"], "/usr/local/bin/claude")

if __name__ == "__main__":
    unittest.main()
