from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "autodata_unattended_e2e.py"
AUTODATA_ROOT = Path(
    os.getenv("AUTODATA_SOURCE_ROOT", "/home/winnieyangwn/autodata_pipelines")
)


class AutodataUnattendedE2ETest(TestCase):
    def test_workspace_meta_then_production_without_human_pause(self) -> None:
        if not (AUTODATA_ROOT / "src" / "autodata" / "engine.py").is_file():
            self.skipTest(f"canonical AutoData checkout unavailable: {AUTODATA_ROOT}")
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--autodata-root",
                    str(AUTODATA_ROOT),
                    "--output-root",
                    str(output),
                    "--run-id",
                    "unit-e2e",
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads((output / "e2e_report.json").read_text())
            self.assertTrue(report["success"])
            self.assertEqual(report["workspace_created"]["actor"], "aar-research-agent")
            self.assertEqual(report["meta_optimize"]["status"], "completed")
            self.assertEqual(report["meta_optimize"]["fitness"], 1.0)
            self.assertGreater(report["meta_optimize"]["hidden_task_attempt_count"], 0)
            self.assertEqual(report["production"]["status"], "completed")
            self.assertEqual(report["production"]["fitness"], 1.0)
            self.assertEqual(report["production"]["hidden_task_attempt_count"], 0)
            self.assertEqual(report["production"]["retained_rows"], 10)
            self.assertEqual(
                report["manifest"]["modes_completed_in_order"],
                ["meta_optimize", "production"],
            )
            approvals = [
                action
                for action in report["action_audit"]
                if action["kind"] in {"approve_grounding", "approve_baseline"}
            ]
            self.assertEqual(len(approvals), 2)
            self.assertEqual(
                {approval["actor"] for approval in approvals},
                {"aar-integrity-monitor"},
            )
            rows = (output / "autodata_rows.jsonl").read_text().splitlines()
            self.assertEqual(len(rows), 10)
            self.assertTrue(
                all(
                    json.loads(row)["prediction"] == json.loads(row)["target"]
                    for row in rows
                )
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
