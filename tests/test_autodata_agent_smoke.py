from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from unittest import TestCase


SCRIPT = Path(__file__).parents[1] / "scripts" / "autodata_agent_smoke.py"


def _module():
    spec = importlib.util.spec_from_file_location("autodata_agent_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutoDataAgentSmokeTest(TestCase):
    def test_prompt_uses_skill_bash_and_native_cli_only(self):
        module = _module()
        root = Path("/retained/run")
        prompt = module._agent_prompt(root, root / "fixture/toy", "a" * 64)

        self.assertIn("load the `autodata:autodata` skill", prompt)
        self.assertIn('${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py', prompt)
        self.assertIn("Do not recompute", prompt)
        self.assertIn("workspace", prompt)
        self.assertIn("execution", prompt)
        self.assertIn("action", prompt)
        self.assertIn("export", prompt)
        self.assertIn("never call a tool", prompt)
        for old_name in (
            "autodata_generate",
            "autodata_step",
            "autodata_status",
            "autodata_fetch",
        ):
            self.assertNotIn(old_name, prompt)

    def test_required_tools_are_sdk_skill_and_bash_not_mcp(self):
        module = _module()
        self.assertEqual(module.REQUIRED_AGENT_TOOLS, frozenset({"Skill", "Bash"}))
        self.assertFalse(any(name.startswith("mcp__") for name in module.REQUIRED_AGENT_TOOLS))

        source = SCRIPT.read_text()
        self.assertIn(
            'tools=["Skill", "Bash", "Read", "Write", "Edit", "Glob", "Grep"]',
            source,
        )

    def test_fixed_approvals_are_bound_to_fixture_digest(self):
        module = _module()
        document = module._approval_document("b" * 64)

        self.assertEqual(document["fixture_sha256"], "b" * 64)
        self.assertEqual(
            set(document["decisions"]), {"approve_grounding", "approve_baseline"}
        )
        self.assertTrue(
            all(value["user_acknowledged"] for value in document["decisions"].values())
        )

    def test_verifier_accepts_native_export_and_rejects_autodata_mcp(self):
        module = _module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "export" / "dataset.json"
            export.parent.mkdir()
            export.write_text(json.dumps(
                {
                    "schema": "autodata.dataset/v1",
                    "execution_id": "exec_1",
                    "items": [{"value": 2}],
                }
            ))
            (root / "completion.json").write_text(json.dumps(
                {
                    "workspace_id": "ws_1",
                    "execution_id": "exec_1",
                    "workspace_status": "frozen",
                    "execution_status": "completed",
                    "export_path": str(export),
                }
            ))

            report = module._verify_result(
                root,
                {"successful_sessions": 1},
                ["Skill", "Bash"],
            )
            self.assertEqual(report["dataset_item_count"], 1)
            self.assertEqual(report["autodata_mcp_calls"], [])

            with self.assertRaisesRegex(RuntimeError, "forbidden"):
                module._verify_result(
                    root,
                    {"successful_sessions": 1},
                    ["Skill", "Bash", "mcp__autodata-tools__autodata_step"],
                )
