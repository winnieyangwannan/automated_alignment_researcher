from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from aar import config
from aar.infrastructure.autodata import load_autodata_dataset
from aar.research_loop.tools import autodata_tools
from aar.research_loop.tools.server_api_tools import _method_code


SHA = "a" * 40


def _payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


class AutodataToolsTest(TestCase):
    def _approved_method(self, root: Path, *, with_ref: bool = False) -> tuple[str, str]:
        idea_name = "chain_method"
        method_dir = root / "methods" / idea_name
        method_dir.mkdir(parents=True)
        extra = ", 'git_ref': 'main'" if with_ref else ""
        (method_dir / "run.py").write_text(
            "AUTODATA_SPEC = {'task_set': 'sycophancy-v1', "
            "'generator': 'Kimi-K2.6', 'acceptance_rule': 'verified_accept'"
            f"{extra}}}\n"
        )
        with patch.object(config, "IDEAS_DIR", str(root / "methods")):
            _, code_hash = _method_code(idea_name)
        return idea_name, code_hash

    def test_generate_uses_only_spec_frozen_in_approved_code(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            idea_name, code_hash = self._approved_method(root)
            run_id = "approved-run-1"
            proposal = root / "scores" / ".proposals" / "runs" / f"{run_id}.json"
            proposal.parent.mkdir(parents=True)
            proposal.write_text(json.dumps({"idea_name": idea_name, "code_hash": code_hash}))
            post = AsyncMock(return_value={"job_id": "job-1", "state": "queued"})
            env = {
                "SCORES_DIR": str(root / "scores"),
                "AAR_AUTODATA_URL": "https://autodata.test",
                "AAR_AUTODATA_SHA": SHA,
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch.object(config, "IDEAS_DIR", str(root / "methods")),
                patch.object(autodata_tools, "async_http_post", post),
            ):
                result = asyncio.run(
                    autodata_tools.autodata_generate.handler(
                        {"idea_name": idea_name, "run_id": run_id}
                    )
                )
            self.assertTrue(_payload(result)["success"])
            sent = post.await_args.args[1]
            self.assertEqual(sent["pipeline_sha"], SHA)
            self.assertEqual(sent["spec"]["generator"], "Kimi-K2.6")

    def test_generate_rejects_unapproved_ref_override(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            idea_name, code_hash = self._approved_method(root, with_ref=True)
            run_id = "approved-run-2"
            proposal = root / "scores" / ".proposals" / "runs" / f"{run_id}.json"
            proposal.parent.mkdir(parents=True)
            proposal.write_text(json.dumps({"idea_name": idea_name, "code_hash": code_hash}))
            with (
                patch.dict(
                    os.environ,
                    {
                        "SCORES_DIR": str(root / "scores"),
                        "AAR_AUTODATA_URL": "https://autodata.test",
                        "AAR_AUTODATA_SHA": SHA,
                    },
                    clear=False,
                ),
                patch.object(config, "IDEAS_DIR", str(root / "methods")),
            ):
                result = asyncio.run(
                    autodata_tools.autodata_generate.handler(
                        {"idea_name": idea_name, "run_id": run_id}
                    )
                )
            self.assertFalse(_payload(result)["success"])
            self.assertIn("operator-controlled", _payload(result)["error"])

    def test_fetch_and_loader_fail_closed_on_manifest_and_digest(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            run_id = "run-fetch"
            rows = [{"prompt": "p", "response": "r"}]
            payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
            manifest = {
                "schema": "aar.autodata.dataset/v1",
                "run_id": run_id,
                "pipeline_sha": SHA,
                "row_count": 1,
                "dataset_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            }
            get = AsyncMock(return_value={"rows": rows, "manifest": manifest})
            env = {
                "TEAM_DIR": str(root / "team"),
                "AAR_AUTODATA_URL": "https://autodata.test",
                "AAR_AUTODATA_SHA": SHA,
                "AAR_CURRENT_RUN_ID": run_id,
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch.object(autodata_tools, "async_http_get", get),
            ):
                result = asyncio.run(autodata_tools.autodata_fetch.handler({"run_id": run_id}))
                self.assertTrue(_payload(result)["success"])
                self.assertEqual(load_autodata_dataset(), rows)
                rows_path = Path(_payload(result)["rows_path"])
                rows_path.write_text(rows_path.read_text() + "{}\n")
                with self.assertRaisesRegex(ValueError, "digest"):
                    load_autodata_dataset()

    def test_agent_wiring_is_opt_in(self):
        source = (Path(__file__).parents[1] / "aar" / "research_loop" / "agent.py").read_text()
        self.assertIn('self.mcp_servers["autodata-tools"]', source)
        self.assertIn("mcp__autodata-tools__autodata_generate", source)
        self.assertIn("mcp__autodata-tools__autodata_status", source)
        self.assertIn("mcp__autodata-tools__autodata_fetch", source)
