"""Compatibility checks for optional Claude Agent SDK options."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import types
import tempfile
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

    class HookMatcher:
        def __init__(self, *, matcher=None, hooks=None, timeout=None) -> None:
            self.matcher = matcher
            self.hooks = hooks or []
            self.timeout = timeout

    sdk.HookMatcher = HookMatcher

    server_tools = types.ModuleType("aar.research_loop.tools.server_api_tools")
    server_tools.create_server_api_tools_server = lambda: None
    server_tools._method_code = lambda *_args, **_kwargs: None
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
    @staticmethod
    def _trial7_environment(directory: str) -> dict[str, str]:
        team = Path(directory) / "team"
        team.mkdir()
        control = Path(directory) / "lifecycle-control.json"
        control.write_text(
            json.dumps(
                {
                    "schema": "aar.autodata.lifecycle-control/v1",
                    "subjects": [
                        {
                            "kind": "workspace",
                            "subject_id": "ws_" + "1" * 32,
                            "status": "registered",
                        }
                    ],
                }
            )
        )
        return {
            "AAR_AUTODATA_GROUNDING_COORDINATOR": "1",
            "AAR_AUTODATA_PIPELINE_COORDINATOR": "1",
            "AAR_EXPERIMENT_RUN_ID": "run13",
            "AAR_RUN13_TRIAL_ID": "trial7",
            "AAR_IDEA_UID_OVERRIDE": "run13-trial7-alpha-iteration-1",
            "AAR_AGENT_BACKEND": "claude",
            "AAR_AUTODATA_SEMANTIC_WORKER": "claude",
            "AAR_AUTODATA_LIFECYCLE_SUPERVISED": "1",
            "AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE": "1",
            "AAR_AUTODATA_SUPERVISOR_CONTROL": str(control),
            "TEAM_DIR": str(team),
        }

    def test_kimi_receives_verified_autodata_skill_directory(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        loop = object.__new__(agent_module.AutonomousAgentLoop)
        loop.backend = "kimi"
        loop.workspace = ROOT
        loop.model = "kimi-test"
        loop.local_mode = True

        with tempfile.TemporaryDirectory() as temp:
            plugin_root = Path(temp) / "plugin" / "autodata"
            skills = plugin_root / "skills"
            (skills / "autodata").mkdir(parents=True)
            loop.autodata_plugin = types.SimpleNamespace(root=plugin_root)
            with patch.dict(
                os.environ,
                {"KIMI_CLI_PATH": "/bin/true"},
                clear=False,
            ):
                kimi = loop._create_agent("smoke")

        self.assertEqual(kimi.skill_dirs, (skills.resolve(),))
        self.assertIn("load the `autodata` skill", kimi.system_prompt)
        self.assertIn("`autodata:autodata`", kimi.system_prompt)

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

    def test_trial7_pipeline_hooks_are_forwarded_only_in_exact_mode(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(agent_module._trial7_pipeline_hooks())

        with tempfile.TemporaryDirectory() as directory:
            environment = self._trial7_environment(directory)
            with patch.dict(os.environ, environment, clear=True):
                hooks = agent_module._trial7_pipeline_hooks()

        self.assertEqual(
            [matcher.matcher for matcher in hooks["PreToolUse"]],
            ["Bash", "Write", "Edit"],
        )
        options = agent_module.BaseAgent(
            name="trial7",
            allowed_tools=["Bash", "Write", "Edit"],
            workspace=Path("/tmp/workspace"),
            mcp_servers={},
            hooks=hooks,
        )._build_options_dict()
        self.assertIs(options["hooks"], hooks)

        loop = object.__new__(agent_module.AutonomousAgentLoop)
        loop.backend = "claude"
        loop.workspace = ROOT
        loop.mcp_servers = {}
        loop.model = "claude-opus-4-8"
        loop.local_mode = True
        loop.autodata_plugin = None
        with tempfile.TemporaryDirectory() as directory:
            environment = self._trial7_environment(directory)
            with patch.dict(os.environ, environment, clear=True):
                trial7_agent = loop._create_agent("trial7")
        self.assertIn("exclusively owns", trial7_agent.system_prompt)
        self.assertIn("`author_grounding`", trial7_agent.system_prompt)
        self.assertIn("`author_pipeline`", trial7_agent.system_prompt)
        self.assertIn("background or detached", trial7_agent.system_prompt)

    def test_trial8_and_trial9_reuse_the_reviewed_authoring_fence(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        for trial_id in ("trial8", "trial9"):
            with self.subTest(trial_id=trial_id), tempfile.TemporaryDirectory() as directory:
                environment = self._trial7_environment(directory)
                environment["AAR_RUN13_TRIAL_ID"] = trial_id
                environment["AAR_IDEA_UID_OVERRIDE"] = (
                    f"run13-{trial_id}-alpha-iteration-1"
                )
                with patch.dict(os.environ, environment, clear=True):
                    hooks = agent_module._trial7_pipeline_hooks()

            self.assertEqual(
                [matcher.matcher for matcher in hooks["PreToolUse"]],
                ["Bash", "Write", "Edit"],
            )

    def test_run14_recipe_comparison_reuses_the_reviewed_authoring_fence(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        with tempfile.TemporaryDirectory() as directory:
            environment = self._trial7_environment(directory)
            environment.pop("AAR_RUN13_TRIAL_ID")
            environment.update(
                {
                    "AAR_EXPERIMENT_RUN_ID": "run14",
                    "AAR_RUN14_TRIAL_ID": "trial14",
                    "AAR_RUN14_CANARY_ID": "v3-recipe-comparison",
                    "AAR_IDEA_UID_OVERRIDE": (
                        "run14-trial14-alpha-iteration-1"
                    ),
                }
            )
            with patch.dict(os.environ, environment, clear=True):
                hooks = agent_module._trial7_pipeline_hooks()

        self.assertEqual(
            [matcher.matcher for matcher in hooks["PreToolUse"]],
            ["Bash", "Write", "Edit"],
        )

    def test_trial11_adds_exclusive_delegated_approval_fence(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        with tempfile.TemporaryDirectory() as directory:
            environment = self._trial7_environment(directory)
            environment.update(
                {
                    "AAR_RUN13_TRIAL_ID": "trial11",
                    "AAR_IDEA_UID_OVERRIDE": "run13-trial11-alpha-iteration-1",
                    "AAR_AUTODATA_APPROVAL_COORDINATOR": "1",
                }
            )
            with patch.dict(os.environ, environment, clear=True):
                hooks = agent_module._trial7_pipeline_hooks()
                denied = asyncio.run(
                    agent_module._run13_approval_tool_fence(
                        {
                            "tool_name": (
                                "mcp__server-api-tools__review_autodata_action"
                            )
                        },
                        None,
                        None,
                    )
                )

                loop = object.__new__(agent_module.AutonomousAgentLoop)
                loop.backend = "claude"
                loop.workspace = ROOT
                loop.mcp_servers = {}
                loop.model = "claude-opus-4-8"
                loop.local_mode = True
                loop.autodata_plugin = None
                trial11_agent = loop._create_agent("trial11")

        self.assertEqual(
            [matcher.matcher for matcher in hooks["PreToolUse"]],
            [
                "Bash",
                "Write",
                "Edit",
                "mcp__server-api-tools__review_autodata_action",
            ],
        )
        self.assertEqual(
            denied["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertIn(
            "exclusively owns delegated AutoData approvals",
            trial11_agent.system_prompt,
        )
        self.assertIn(
            "Do not call `review_autodata_action`", trial11_agent.system_prompt
        )

    def test_delegated_approval_fence_is_inert_when_not_enabled(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        with patch.dict(os.environ, {}, clear=True):
            result = asyncio.run(
                agent_module._run13_approval_tool_fence(
                    {
                        "tool_name": (
                            "mcp__server-api-tools__review_autodata_action"
                        )
                    },
                    None,
                    None,
                )
            )
        self.assertEqual(result, {})

    def test_trial7_pipeline_flag_fails_closed_on_wrong_identity(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        with patch.dict(
            os.environ,
            {
                "AAR_AUTODATA_PIPELINE_COORDINATOR": "1",
                "AAR_EXPERIMENT_RUN_ID": "run13",
                "AAR_IDEA_UID_OVERRIDE": "run13-trial6-alpha-iteration-1",
            },
            clear=True,
        ), self.assertRaisesRegex(
            agent_module.PipelineOwnershipFenceError, "identity is incomplete"
        ):
            agent_module._trial7_pipeline_hooks()

    def test_trial7_pipeline_fence_blocks_mutating_tools_for_owned_action(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        workspace_id = "ws_" + "1" * 32

        for action_status in ("pending", "in_progress", "completed"):
            snapshot = types.SimpleNamespace(
                id=workspace_id,
                phase="pipeline_pending",
                actions=(
                    types.SimpleNamespace(
                        id="act_" + "2" * 24,
                        kind="author_pipeline",
                        status=action_status,
                    ),
                ),
            )
            native = types.SimpleNamespace(read_workspace=lambda _identity: snapshot)
            with tempfile.TemporaryDirectory() as directory:
                environment = self._trial7_environment(directory)
                with (
                    patch.dict(os.environ, environment, clear=True),
                    patch(
                        "aar.infrastructure.autodata_coordinator.NativeAutoDataControl.from_environment",
                        return_value=native,
                    ),
                ):
                    for tool in ("Bash", "Write", "Edit"):
                        result = asyncio.run(
                            agent_module._trial7_pipeline_tool_fence(
                                {"tool_name": tool}, None, None
                            )
                        )
                        self.assertEqual(
                            result["hookSpecificOutput"]["permissionDecision"],
                            "deny",
                        )

        snapshot = types.SimpleNamespace(
            id=workspace_id,
            phase="grounding_pending",
            actions=(
                types.SimpleNamespace(
                    id="act_" + "3" * 24,
                    kind="author_grounding",
                    status="pending",
                ),
            ),
        )
        native = types.SimpleNamespace(read_workspace=lambda _identity: snapshot)
        with tempfile.TemporaryDirectory() as directory:
            environment = self._trial7_environment(directory)
            with (
                patch.dict(os.environ, environment, clear=True),
                patch(
                    "aar.infrastructure.autodata_coordinator.NativeAutoDataControl.from_environment",
                    return_value=native,
                ),
            ):
                result = asyncio.run(
                    agent_module._trial7_pipeline_tool_fence(
                        {"tool_name": "Bash"}, None, None
                    )
                )
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_trial7_pipeline_fence_leaves_approval_actions_unchanged(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        workspace_id = "ws_" + "1" * 32
        snapshot = types.SimpleNamespace(
            id=workspace_id,
            phase="grounding_review",
            actions=(
                types.SimpleNamespace(
                    id="act_" + "2" * 24,
                    kind="approve_grounding",
                    status="pending",
                ),
            ),
        )
        native = types.SimpleNamespace(read_workspace=lambda _identity: snapshot)
        with tempfile.TemporaryDirectory() as directory:
            environment = self._trial7_environment(directory)
            with (
                patch.dict(os.environ, environment, clear=True),
                patch(
                    "aar.infrastructure.autodata_coordinator.NativeAutoDataControl.from_environment",
                    return_value=native,
                ),
            ):
                result = asyncio.run(
                    agent_module._trial7_pipeline_tool_fence(
                        {"tool_name": "Bash"}, None, None
                    )
                )
        self.assertEqual(result, {})

    def test_trial7_pipeline_fence_denies_ambiguous_or_malformed_state(self) -> None:
        class Options:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        agent_module = _load_agent_module(Options)
        with tempfile.TemporaryDirectory() as directory:
            environment = self._trial7_environment(directory)
            control = Path(environment["AAR_AUTODATA_SUPERVISOR_CONTROL"])
            malformed_states = (
                "not-json",
                json.dumps(
                    {
                        "schema": "aar.autodata.lifecycle-control/v1",
                        "subjects": [
                            {
                                "kind": "workspace",
                                "subject_id": "ws_" + "1" * 32,
                                "status": "registered",
                            },
                            {
                                "kind": "workspace",
                                "subject_id": "ws_" + "2" * 32,
                                "status": "registered",
                            },
                        ],
                    }
                ),
            )
            for value in malformed_states:
                control.write_text(value)
                with patch.dict(os.environ, environment, clear=True):
                    result = asyncio.run(
                        agent_module._trial7_pipeline_tool_fence(
                            {"tool_name": "Bash"}, None, None
                        )
                    )
                self.assertEqual(
                    result["hookSpecificOutput"]["permissionDecision"], "deny"
                )

        workspace_id = "ws_" + "1" * 32
        snapshot = types.SimpleNamespace(
            id=workspace_id,
            phase="pipeline_pending",
            actions=(
                types.SimpleNamespace(
                    id="act_" + "2" * 24,
                    kind="author_pipeline",
                    status="pending",
                ),
                types.SimpleNamespace(
                    id="act_" + "3" * 24,
                    kind="unexpected",
                    status="in_progress",
                ),
            ),
        )
        native = types.SimpleNamespace(read_workspace=lambda _identity: snapshot)
        with tempfile.TemporaryDirectory() as directory:
            environment = self._trial7_environment(directory)
            with (
                patch.dict(os.environ, environment, clear=True),
                patch(
                    "aar.infrastructure.autodata_coordinator.NativeAutoDataControl.from_environment",
                    return_value=native,
                ),
            ):
                result = asyncio.run(
                    agent_module._trial7_pipeline_tool_fence(
                        {"tool_name": "Write"}, None, None
                    )
                )
        self.assertEqual(
            result["hookSpecificOutput"]["permissionDecision"], "deny"
        )

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
