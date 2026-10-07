from __future__ import annotations

import ast
import importlib.util
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
    def test_fixture_contains_one_literal_strict_spec_and_loader(self):
        module = _module()
        tree = ast.parse(module._method_source())
        assignments = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "AUTODATA_SPEC"
                    for target in node.targets)
        ]
        self.assertEqual(len(assignments), 1)
        self.assertEqual(ast.literal_eval(assignments[0].value), module.AUTODATA_SPEC)
        self.assertIn("load_autodata_dataset()", module._method_source())

    def test_prompt_is_bounded_and_requires_full_agent_tool_path(self):
        module = _module()
        prompt = module._agent_prompt("run-1", "method-1")
        self.assertIn("autodata_generate exactly once", prompt)
        self.assertIn("autodata_step", prompt)
        self.assertIn("autodata_status", prompt)
        self.assertIn("autodata_fetch", prompt)
        self.assertIn("Do not train or evaluate", prompt)
        self.assertNotIn("evaluate_model", prompt)

    def test_live_agent_has_no_training_or_evaluation_tools(self):
        module = _module()
        self.assertEqual(
            module.REQUIRED_AGENT_TOOLS,
            {
                "mcp__autodata-tools__autodata_generate",
                "mcp__autodata-tools__autodata_step",
                "mcp__autodata-tools__autodata_fetch",
            },
        )
