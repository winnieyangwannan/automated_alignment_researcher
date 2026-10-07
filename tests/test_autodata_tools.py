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
from aar.infrastructure.autodata import (
    autodata_training_link,
    load_autodata_dataset,
    record_autodata_training_link,
    validate_autodata_artifacts,
    verify_autodata_consumption,
)
from aar.research_loop.tools import autodata_tools
from aar.research_loop.tools.server_api_tools import _method_code


SHA = "a" * 40


def _payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


class AutodataToolsTest(TestCase):
    def test_settings_loads_service_token_from_owned_private_file(self):
        with TemporaryDirectory() as td:
            token_file = Path(td) / "adapter.token"
            token_file.write_text("private-adapter-token\n")
            token_file.chmod(0o600)
            with patch.dict(
                os.environ,
                {
                    "AAR_AUTODATA_URL": "https://autodata.test",
                    "AAR_AUTODATA_SHA": SHA,
                    "AAR_AUTODATA_TOKEN": "",
                    "AAR_AUTODATA_TOKEN_FILE": str(token_file),
                },
                clear=False,
            ):
                _, _, headers = autodata_tools._settings()
            self.assertEqual(headers, {"Authorization": "Bearer private-adapter-token"})

    def test_settings_rejects_world_readable_service_token_file(self):
        with TemporaryDirectory() as td:
            token_file = Path(td) / "adapter.token"
            token_file.write_text("private-adapter-token\n")
            token_file.chmod(0o644)
            with (
                patch.dict(
                    os.environ,
                    {
                        "AAR_AUTODATA_URL": "https://autodata.test",
                        "AAR_AUTODATA_SHA": SHA,
                        "AAR_AUTODATA_TOKEN": "",
                        "AAR_AUTODATA_TOKEN_FILE": str(token_file),
                    },
                    clear=False,
                ),
                self.assertRaisesRegex(ValueError, "mode-0600"),
            ):
                autodata_tools._settings()

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
            idea_name, code_hash = self._approved_method(root)
            run_id = "run-fetch"
            proposal = root / "scores" / ".proposals" / "runs" / f"{run_id}.json"
            proposal.parent.mkdir(parents=True)
            proposal.write_text(json.dumps({"idea_name": idea_name, "code_hash": code_hash}))
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
                "AAR_RUNTIME_ROOT": str(root),
                "AAR_AUTODATA_URL": "https://autodata.test",
                "AAR_AUTODATA_SHA": SHA,
                "AAR_CURRENT_RUN_ID": run_id,
                "SCORES_DIR": str(root / "scores"),
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch.object(config, "IDEAS_DIR", str(root / "methods")),
                patch.object(autodata_tools, "async_http_get", get),
            ):
                result = asyncio.run(autodata_tools.autodata_fetch.handler({"run_id": run_id}))
                self.assertTrue(_payload(result)["success"])
                self.assertEqual(load_autodata_dataset(), rows)
                self.assertEqual(verify_autodata_consumption()["row_count"], 1)
                link = autodata_training_link()
                self.assertEqual(link["dataset_sha256"], manifest["dataset_sha256"])
                recorded = record_autodata_training_link(
                    link, model_submission_ref="submissions/run-fetch/model"
                )
                self.assertEqual(recorded["run_id"], run_id)
                self.assertEqual(
                    record_autodata_training_link(
                        link, model_submission_ref="submissions/run-fetch/model"
                    ),
                    recorded,
                )
                rows_path = Path(_payload(result)["rows_path"])
                rows_path.write_text(
                    rows_path.read_text()
                    + json.dumps({"prompt": "tampered", "response": "row"})
                    + "\n"
                )
                with self.assertRaisesRegex(ValueError, "row_count|digest"):
                    load_autodata_dataset()

    def test_artifact_dir_rejects_parent_symlink_escape(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            runtime = root / "runtime"
            team = runtime / "team"
            escape = root / "escape"
            team.mkdir(parents=True)
            escape.mkdir()
            (team / "autodata").symlink_to(escape, target_is_directory=True)
            with (
                patch.dict(
                    os.environ,
                    {
                        "AAR_RUNTIME_ROOT": str(runtime),
                        "TEAM_DIR": str(team),
                    },
                    clear=False,
                ),
                self.assertRaisesRegex(ValueError, "must not be a symlink"),
            ):
                autodata_tools._artifact_dir("run-fetch")

    def test_agent_wiring_is_opt_in(self):
        source = (Path(__file__).parents[1] / "aar" / "research_loop" / "agent.py").read_text()
        chain = (Path(__file__).parents[1] / "scripts" / "slurm_aar_chain.sh").read_text()
        submit = (Path(__file__).parents[1] / "scripts" / "submit_train_job.sh").read_text()
        train = (Path(__file__).parents[1] / "scripts" / "slurm_train_submit.sh").read_text()
        prompt = (
            Path(__file__).parents[1]
            / "aar"
            / "research_loop"
            / "prompt_safety.jinja2"
        ).read_text()
        self.assertIn('self.mcp_servers["autodata-tools"]', source)
        self.assertIn("mcp__autodata-tools__autodata_generate", source)
        self.assertIn("mcp__autodata-tools__autodata_status", source)
        self.assertIn("mcp__autodata-tools__autodata_step", source)
        self.assertIn("mcp__autodata-tools__autodata_action_begin", source)
        self.assertIn("mcp__autodata-tools__autodata_action_complete", source)
        self.assertIn("mcp__autodata-tools__autodata_action_fail", source)
        self.assertIn("mcp__autodata-tools__autodata_fetch", source)
        self.assertIn("autodata_contract_smoke_server.py", chain)
        self.assertIn('AAR_FUNCTIONAL_SMOKE:-0', chain)
        self.assertIn("verify_autodata_dataset", submit)
        self.assertIn("autodata_training_link", train)
        self.assertIn("record_autodata_training_link", train)
        self.assertIn("must** import and call", prompt)
        self.assertIn("load_autodata_dataset()", prompt)

    def test_required_generate_sends_campaign_budget_and_frozen_binding(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            idea_name = "chain_required"
            method_dir = root / "methods" / idea_name
            method_dir.mkdir(parents=True)
            spec = {
                "schema": "aar.autodata.request/v1",
                "resource_profile": "run8",
                "safety_axis": "dishonest_sycophancy_concealing",
                "training_mechanism": "contrastive correction SFT",
                "training_view": "sft",
                "seed": 7,
                "goal": "Generate diverse corrections for concealed uncertainty.",
            }
            (method_dir / "run.py").write_text(f"AUTODATA_SPEC = {spec!r}\n")
            with patch.object(config, "IDEAS_DIR", str(root / "methods")):
                _, code_hash = _method_code(idea_name)
            run_id = "required-run"
            proposal = root / "scores" / ".proposals" / "runs" / f"{run_id}.json"
            proposal.parent.mkdir(parents=True)
            proposal.write_text(
                json.dumps({"run_id": run_id, "idea_name": idea_name, "code_hash": code_hash})
            )
            post = AsyncMock(
                return_value={"run_id": run_id, "job_id": "job-1", "state": "workspace"}
            )
            env = {
                "SCORES_DIR": str(root / "scores"),
                "AAR_AUTODATA": "1",
                "AAR_AUTODATA_REQUIRED": "1",
                "AAR_AUTODATA_URL": "https://autodata.test",
                "AAR_AUTODATA_SHA": SHA,
                "AAR_AUTODATA_RESOURCE_PROFILE": "run8",
                "AAR_AUTODATA_RESOURCE_PROFILE_SHA256": "b" * 64,
                "AAR_AUTODATA_BUDGET_SCOPE_ID": "campaign-1",
                "AAR_AUTODATA_MAX_COST_USD": "25.00",
                "AAR_AUTODATA_REQUIRED_RETAINED_ROWS": "256",
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
            request = post.await_args.args[1]
            self.assertEqual(request["binding"]["method_code_sha256"], code_hash)
            self.assertEqual(request["controls"]["budget_scope_id"], "campaign-1")
            self.assertEqual(request["controls"]["max_cost_usd"], "25.00")
            self.assertEqual(request["controls"]["required_retained_rows"], 256)

    def test_action_complete_cannot_manufacture_user_approval(self):
        result = asyncio.run(
            autodata_tools.autodata_action_complete.handler(
                {
                    "run_id": "run-1",
                    "action_id": "action-1",
                    "lease_token": "lease",
                    "result": {"decision": "approve", "user_acknowledged": True},
                }
            )
        )
        self.assertFalse(_payload(result)["success"])
        self.assertIn("delegated policy", _payload(result)["error"])

    def test_step_and_action_begin_use_run_bound_adapter_routes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            idea_name, code_hash = self._approved_method(root)
            run_id = "action-run"
            proposal = root / "scores" / ".proposals" / "runs" / f"{run_id}.json"
            proposal.parent.mkdir(parents=True)
            proposal.write_text(json.dumps({"idea_name": idea_name, "code_hash": code_hash}))
            post = AsyncMock(
                side_effect=[
                    {"run_id": run_id, "state": "authoring"},
                    {"run_id": run_id, "lease_token": "lease-1", "action": {}},
                ]
            )
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
                patch.object(autodata_tools, "async_http_post", post),
            ):
                step = asyncio.run(autodata_tools.autodata_step.handler({"run_id": run_id}))
                begin = asyncio.run(
                    autodata_tools.autodata_action_begin.handler(
                        {"run_id": run_id, "action_id": "action-1"}
                    )
                )
            self.assertTrue(_payload(step)["success"])
            self.assertTrue(_payload(begin)["success"])
            self.assertTrue(post.await_args_list[0].args[0].endswith(f"/{run_id}/step"))
            self.assertTrue(
                post.await_args_list[1].args[0].endswith(
                    f"/{run_id}/actions/action-1/begin"
                )
            )

    def test_required_spec_rejects_unknown_recipe_override(self):
        code = (
            "AUTODATA_SPEC = {"
            "'schema': 'aar.autodata.request/v1', "
            "'resource_profile': 'run8', "
            "'safety_axis': 'honesty', "
            "'training_mechanism': 'SFT', "
            "'training_view': 'sft', "
            "'seed': 1, "
            "'goal': 'Generate grounded corrections.', "
            "'recipe_path': '/tmp/agent-owned'}\n"
        )
        with patch.dict(
            os.environ,
            {
                "AAR_AUTODATA_REQUIRED": "1",
                "AAR_AUTODATA_RESOURCE_PROFILE": "run8",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "outside the v1"):
                autodata_tools.validate_autodata_method_code(code)

    def test_required_spec_respects_operator_locked_training_view(self):
        code = (
            "AUTODATA_SPEC = {"
            "'schema': 'aar.autodata.request/v1', "
            "'resource_profile': 'run8', "
            "'safety_axis': 'honesty', "
            "'training_mechanism': 'preference optimization', "
            "'training_view': 'preference', "
            "'seed': 1, "
            "'goal': 'Generate grounded corrections.'}\n"
        )
        with patch.dict(
            os.environ,
            {
                "AAR_AUTODATA_REQUIRED": "1",
                "AAR_AUTODATA_RESOURCE_PROFILE": "run8",
                "AAR_AUTODATA_TRAINING_VIEW": "sft",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "launch profile"):
                autodata_tools.validate_autodata_method_code(code)

    def test_required_spec_bounds_model_prompt_fields(self):
        code = (
            "AUTODATA_SPEC = {"
            "'schema': 'aar.autodata.request/v1', "
            "'resource_profile': 'run8', "
            "'safety_axis': 'honesty', "
            "'training_mechanism': 'SFT', "
            "'training_view': 'sft', "
            "'seed': 1, "
            f"'goal': {'x' * 2049!r}}}\n"
        )
        with patch.dict(
            os.environ,
            {
                "AAR_AUTODATA_REQUIRED": "1",
                "AAR_AUTODATA_RESOURCE_PROFILE": "run8",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "2048-byte"):
                autodata_tools.validate_autodata_method_code(code)

    def test_required_manifest_enforces_retained_rows_and_provenance(self):
        rows = [{"id": "one", "prompt": "p", "response": "r"}]
        payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        manifest = {
            "schema": "aar.autodata.dataset/v1",
            "run_id": "run-1",
            "pipeline_sha": SHA,
            "row_count": 1,
            "dataset_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "idea_name": "idea",
            "method_code_sha256": "b" * 64,
            "autodata_spec_sha256": "c" * 64,
            "resource_profile": "run8",
            "resource_profile_sha256": "f" * 64,
            "budget_scope_id": "campaign-1",
            "study_id": "study-1",
            "execution_id": "execution-1",
            "recipe_digest": "d" * 64,
            "pipeline_digest": "e" * 64,
            "training_view": "sft",
            "required_retained_rows": 2,
            "counts": {"generated": 1, "rejected": 0, "retained": 1},
            "models": {
                "generator": {"identity": "Kimi-K2.6"},
                "judge": {"identity": "gpt-5.6-luna"},
            },
            "budget": {
                "max_cost_usd": "25.00",
                "spent_cost_usd": "0",
                "model_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            },
        }
        with self.assertRaisesRegex(ValueError, "required_retained_rows"):
            validate_autodata_artifacts(
                rows,
                manifest,
                run_id="run-1",
                expected_pipeline_sha=SHA,
                required=True,
            )
