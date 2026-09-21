"""Compatibility checks for optional Claude Agent SDK options."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
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

    def test_explicit_cli_gets_longer_default_initialize_timeout(self) -> None:
        class Options:
            def __init__(self) -> None:
                pass

        agent = _load_agent_module(Options)
        with patch.dict("os.environ", {}, clear=True):
            agent._configure_cli_initialize_timeout("/usr/local/bin/claude")
            self.assertEqual(
                agent.os.environ["CLAUDE_CODE_STREAM_CLOSE_TIMEOUT"], "300000"
            )

    def test_explicit_timeout_override_is_preserved(self) -> None:
        class Options:
            def __init__(self) -> None:
                pass

        agent = _load_agent_module(Options)
        with patch.dict(
            "os.environ", {"CLAUDE_CODE_STREAM_CLOSE_TIMEOUT": "420000"}, clear=True
        ):
            agent._configure_cli_initialize_timeout("/usr/local/bin/claude")
            self.assertEqual(
                agent.os.environ["CLAUDE_CODE_STREAM_CLOSE_TIMEOUT"], "420000"
            )


if __name__ == "__main__":
    unittest.main()
