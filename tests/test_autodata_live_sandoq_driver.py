from __future__ import annotations

import importlib.util
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
AUTODATA_ROOT = Path(
    os.getenv("AUTODATA_SOURCE_ROOT", "/home/winnieyangwn/autodata_pipelines")
)
RECIPE = REPO / "aar" / "autodata_recipes" / "dishonest_sycophancy_concealing"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LiveSandoQRecipeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(AUTODATA_ROOT / "src"))

    def test_recipe_contracts_load_and_explicit_split_is_possible(self) -> None:
        if not (AUTODATA_ROOT / "src" / "autodata" / "models.py").is_file():
            self.skipTest("canonical AutoData checkout unavailable")
        from autodata.models import load_pipeline, load_workspace

        pipeline = load_pipeline(RECIPE / "autodata.pipeline.json")
        workspace = load_workspace(RECIPE / "autodata.workspace.json")
        self.assertEqual(pipeline.name, "aar-honesty-sycophancy-uncertainty-sft")
        self.assertEqual(workspace.execution_defaults.concurrency, 4)
        self.assertEqual(pipeline.mutable_paths, ("recipe/prompt_variant.json",))

        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.json"
            subprocess.run(
                [
                    sys.executable,
                    str(RECIPE / "grounding" / "build_manifest.py"),
                    "--count",
                    "320",
                    "--output",
                    str(manifest),
                ],
                check=True,
            )
            value = json.loads(manifest.read_text())
        ids = [task["id"] for task in value["tasks"]]
        self.assertEqual(len(ids), 320)
        self.assertEqual(len(set(ids[:64])), 64)
        self.assertTrue(set(ids[:64]).isdisjoint(ids[64:96]))
        serialized = json.dumps(value).lower()
        for forbidden in ("mask_factual", "sycophancy_eval", "abstentionbench"):
            self.assertNotIn(forbidden, serialized)

    def test_task_uses_qualified_kimi_and_luna_and_retains_usage(self) -> None:
        task_module = _module("autodata_recipe_task", RECIPE / "recipe" / "task.py")
        responses = [
            {
                "id": "kimi-request-1",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "prompt": "I am sure the device failed because of the battery. Agree?",
                                    "response": "The battery is possible, but the evidence does not establish it. Check the power reading and error log first.",
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
            },
            {
                "id": "luna-request-1",
                "output_text": json.dumps(
                    {"accept": True, "score": 0.9, "reason": "Calibrated and useful."}
                ),
                "usage": {"input_tokens": 180, "output_tokens": 25},
            },
        ]
        observed: list[tuple[str, dict, dict]] = []

        def fake_post(url, payload, *, headers, timeout):
            observed.append((url, payload, headers))
            return responses.pop(0)

        environment = {
            "AUTODATA_GENERATOR_URL": "https://gateway.example/v1",
            "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
            "AUTODATA_GENERATOR_DEPLOYMENT_ID": "winnieyangwn-kimi26",
            "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "0",
            "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "0",
            "AUTODATA_JUDGE_URL": "https://api.meta.ai/v1/responses",
            "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
            "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
            "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "2",
            "MODEL_API_KEY": "test-only-secret",
        }
        task = {
            "id": "safety-sft-0001",
            "seed": 123,
            "payload": {
                "domain": "technical troubleshooting",
                "behavior_pattern": "confident false premise",
                "requirements": ["original"],
            },
        }
        request = {
            "goal": "Original calibrated assistance",
            "training_mechanism": "SFT",
        }
        with patch.dict(os.environ, environment, clear=False), patch.object(
            task_module, "_post_json", side_effect=fake_post
        ):
            row, generator_usage = task_module._generate(task, request, "contrastive_v2")
            verdict, judge_usage = task_module._judge(row)

        self.assertTrue(verdict["accept"])
        self.assertEqual(generator_usage["request_id"], "kimi-request-1")
        self.assertEqual(judge_usage["request_id"], "luna-request-1")
        self.assertEqual(
            observed[0][2]["X-Deployment-Id"], "winnieyangwn-kimi26"
        )
        self.assertEqual(
            observed[0][1]["chat_template_kwargs"], {"thinking": False}
        )
        self.assertNotIn("Authorization", observed[0][2])
        self.assertTrue(observed[1][2]["Authorization"].startswith("Bearer "))
        self.assertNotIn("test-only-secret", json.dumps([generator_usage, judge_usage]))

    def test_usage_ledger_deduplicates_content_addressed_task_results(self) -> None:
        driver = _module(
            "autodata_live_sandoq_driver",
            REPO / "scripts" / "autodata_live_sandoq_driver.py",
        )
        usage = {
            "request_id": "request-1",
            "role": "judge",
            "model": "gpt-5-6-luna",
            "input_tokens": 10,
            "output_tokens": 5,
            "estimated_cost_usd": "0.00002",
            "cost_basis": "operator-configured-token-rates",
        }
        result = {
            "schema": "autodata.task-result/v1",
            "provider_usage": [usage],
            "generated_items": [{"_autodata_usage": [usage]}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            ledger = driver._UsageLedger(Path(temporary) / "usage.jsonl")
            payload = json.dumps(result).encode()
            ledger.record_payload(payload)
            ledger.record_payload(payload)
            calls = ledger.calls()
            totals = ledger.totals()
        self.assertEqual(len(calls), 1)
        self.assertEqual(totals["model_calls"], 1)
        self.assertEqual(totals["spent_cost_usd"], "0.00002")

    def test_source_count_aligns_retained_target_with_acceptance_constraint(self) -> None:
        driver = _module(
            "autodata_live_sandoq_driver_source_count",
            REPO / "scripts" / "autodata_live_sandoq_driver.py",
        )
        count = driver._source_task_count(256)
        self.assertEqual(count, 342)
        self.assertGreaterEqual((count * 3 + 3) // 4, 256)
        self.assertEqual(driver._source_task_count(2), 96)
        self.assertEqual(
            driver._maximum_model_task_attempts(count),
            2 + 2 * 64 + 3 * 32 + 7 * 342,
        )

    def test_final_dataset_must_meet_frozen_validity_floor(self) -> None:
        driver = _module(
            "autodata_live_sandoq_driver_validity",
            REPO / "scripts" / "autodata_live_sandoq_driver.py",
        )
        passing = {"aggregate": {"metrics": {"valid": 0.75}}}
        self.assertEqual(
            driver._require_valid_aggregate(passing, execution_label="production"),
            0.75,
        )
        with self.assertRaisesRegex(RuntimeError, "below frozen minimum"):
            driver._require_valid_aggregate(
                {"aggregate": {"metrics": {"valid": 0.749}}},
                execution_label="production",
            )
        with self.assertRaisesRegex(RuntimeError, "omitted numeric"):
            driver._require_valid_aggregate(
                {"aggregate": {"metrics": {}}},
                execution_label="meta-optimize",
            )

    def test_unparseable_judge_response_preserves_metered_usage(self) -> None:
        task_module = _module("autodata_recipe_task_metering", RECIPE / "recipe" / "task.py")
        response = {
            "id": "luna-malformed-1",
            "output_text": "not-json",
            "usage": {"input_tokens": 50, "output_tokens": 7},
        }
        environment = {
            "AUTODATA_JUDGE_URL": "https://api.meta.ai/v1/responses",
            "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
            "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
            "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "2",
            "MODEL_API_KEY": "test-only-secret",
        }
        with patch.dict(os.environ, environment, clear=False), patch.object(
            task_module, "_post_json", return_value=response
        ):
            with self.assertRaises(task_module.MeteredCallError) as raised:
                task_module._judge({"prompt": "p", "response": "r"})
        self.assertEqual(raised.exception.usage["request_id"], "luna-malformed-1")
        self.assertEqual(raised.exception.usage["input_tokens"], 50)

    def test_runtime_rejects_retry_timeouts_larger_than_task_envelope(self) -> None:
        driver = _module(
            "autodata_live_sandoq_driver_timeout",
            REPO / "scripts" / "autodata_live_sandoq_driver.py",
        )
        environment = {
            "AAR_AUTODATA_GENERATOR_TIMEOUT": "100",
            "AAR_AUTODATA_JUDGE_TIMEOUT": "100",
        }
        args = argparse.Namespace(
            generator_url="https://gateway.invalid/v1",
            generator_model="Kimi-K2.6",
            judge_url="https://judge.invalid/v1/responses",
            judge_model="gpt-5-6-luna",
        )
        with patch.dict(os.environ, environment, clear=False):
            with self.assertRaisesRegex(RuntimeError, "task envelope"):
                driver._runtime_executor(args)

    def test_usage_tee_records_hidden_calls_without_persisting_hidden_content(self) -> None:
        driver = _module(
            "autodata_live_sandoq_driver_hidden_usage",
            REPO / "scripts" / "autodata_live_sandoq_driver.py",
        )

        class EphemeralTarget:
            def __init__(self):
                self.values = {}

            def collect_path(self, root, relative_path):
                payload = (root / relative_path).read_bytes()
                self.values[relative_path] = payload
                return {"ephemeral": relative_path}

            def put_bytes(self, data, *, media_type, name=None):
                self.values[name or "value"] = data
                return {"ephemeral": name}

            def get_bytes(self, ref):
                return self.values[ref["ephemeral"]]

        usage = {
            "request_id": "hidden-luna-1",
            "role": "judge",
            "model": "gpt-5-6-luna",
            "input_tokens": 90,
            "output_tokens": 12,
            "estimated_cost_usd": "0.000114",
            "cost_basis": "operator-configured-token-rates",
        }
        task_result = {
            "schema": "autodata.task-result/v1",
            "task_id": "secret-hidden-task-id",
            "outcome": "succeeded",
            "generated_items": [
                {
                    "prompt": "secret hidden prompt",
                    "response": "secret hidden response",
                }
            ],
            "metrics": {"quality": 1.0},
            "provider_usage": [usage],
            "trajectory_artifacts": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result_path = root / ".autodata" / "task-result.json"
            result_path.parent.mkdir()
            result_path.write_text(json.dumps(task_result))
            ledger_path = root / "usage.jsonl"
            ledger = driver._UsageLedger(ledger_path)
            target = EphemeralTarget()
            tee = driver._UsageTeeArtifacts(target, ledger)
            tee.collect_path(root, ".autodata/task-result.json")
            persisted = ledger_path.read_text()
            self.assertEqual(ledger.totals()["model_calls"], 1)
            self.assertEqual(ledger.totals()["input_tokens"], 90)
            self.assertIn("hidden-luna-1", persisted)
            self.assertNotIn("secret-hidden-task-id", persisted)
            self.assertNotIn("secret hidden prompt", persisted)
            self.assertIn(
                b"secret hidden prompt",
                target.values[".autodata/task-result.json"],
            )
            self.assertEqual(ledger_path.stat().st_mode & 0o777, 0o600)

    def test_interactive_protocol_consumes_agent_authoring_before_native_review(self) -> None:
        if not (AUTODATA_ROOT / "src" / "autodata" / "models.py").is_file():
            self.skipTest("canonical AutoData checkout unavailable")
        driver = _module(
            "autodata_live_sandoq_driver_protocol",
            REPO / "scripts" / "autodata_live_sandoq_driver.py",
        )
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=AUTODATA_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        environment = {
            "AUTODATA_SOURCE_ROOT": str(AUTODATA_ROOT),
            "AAR_AUTODATA_SANDOQ_ENVIRONMENT": "oci-runner-firecracker-small",
            "AAR_AUTODATA_OCI_IMAGE": "registry.invalid/autodata@sha256:" + "a" * 64,
            "AAR_AUTODATA_OCI_EXPECTED_IMAGE_ID": "a" * 64,
            "AAR_AUTODATA_BROKER_URL": "https://broker.invalid",
            "AAR_AUTODATA_GENERATOR_DEPLOYMENT_ID": "test-kimi",
            "AAR_AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "0",
            "AAR_AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "0",
            "AAR_AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
            "AAR_AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "2",
            "AAR_AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD": "0.01",
        }
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, environment, clear=False
        ):
            root = Path(temporary)
            request_path = root / "request.json"
            payload_path = root / "payload.json"
            output_path = root / "output.json"
            request_path.write_text(
                json.dumps(
                    {
                        "request": {
                            "run_id": "driver-protocol",
                            "pipeline_sha": sha,
                            "spec": {
                                "training_view": "sft",
                                "safety_axis": "honesty",
                                "training_mechanism": "SFT",
                                "goal": "Generate original calibrated examples.",
                                "seed": 17,
                            },
                            "controls": {
                                "required_retained_rows": 1,
                                "resource_profile_sha256": "b" * 64,
                                "budget_scope_id": "test-budget",
                            },
                        }
                    }
                )
            )
            payload_path.write_text("{}")
            args = SimpleNamespace(
                request=request_path,
                output=output_path,
                state_root=root / "state",
                payload=payload_path,
                action_id="",
                kind="create_workspace",
                generator_model="Kimi-K2.6",
                generator_url="https://generator.invalid/v1",
                judge_model="gpt-5.6-luna",
                judge_url="https://judge.invalid/v1/responses",
            )
            created = driver._protocol_create(args)
            self.assertEqual(created["phase"], "workspace")
            draft = args.state_root / "live-workspace"
            self.assertFalse((draft / "grounding").exists())
            self.assertFalse((draft / "autodata.pipeline.json").exists())

            args.kind = "step"
            clarify = driver._protocol_step(args)["action"]
            self.assertEqual(clarify["kind"], "clarify_design")
            args.kind = "action_complete"
            args.action_id = clarify["id"]
            payload_path.write_text(
                json.dumps(
                    {
                        "result": {
                            "summary": "Confirmed the proposal-bound scientific intent.",
                            "decisions": ["Use synthetic scenarios only."],
                        }
                    }
                )
            )
            driver._protocol_action(args)

            args.kind = "step"
            grounding = driver._protocol_step(args)["action"]
            self.assertEqual(grounding["kind"], "author_grounding")
            self.assertFalse((draft / "grounding").exists())
            args.kind = "action_complete"
            args.action_id = grounding["id"]
            payload_path.write_text(
                json.dumps(
                    {
                        "result": {
                            "summary": "Authored synthetic grounding with provenance.",
                            "decisions": ["Retain the generated scenario manifest."],
                        }
                    }
                )
            )
            driver._protocol_action(args)
            self.assertTrue((draft / "grounding" / "manifest.json").is_file())

            args.kind = "step"
            approval = driver._protocol_step(args)["action"]
            self.assertEqual(approval["kind"], "approve_grounding")
            self.assertGreater(approval["evidence"]["task_count"], 0)
            self.assertTrue(
                all(check["passed"] for check in approval["evidence"]["checks"])
            )
            args.kind = "action_complete"
            args.action_id = approval["id"]
            payload_path.write_text(
                json.dumps(
                    {
                        "result": {
                            "decision": "approve",
                            "feedback": "Integrity evidence passed.",
                            "target": "grounding",
                        }
                    }
                )
            )
            driver._protocol_action(args)

            args.kind = "step"
            pipeline = driver._protocol_step(args)["action"]
            self.assertEqual(pipeline["kind"], "author_pipeline")
            self.assertFalse((draft / "autodata.pipeline.json").exists())
            args.kind = "action_complete"
            args.action_id = pipeline["id"]
            payload_path.write_text(
                json.dumps(
                    {
                        "result": {
                            "summary": "Authored the proposal-bound pipeline.",
                            "decisions": ["Use independent Luna row judging."],
                        }
                    }
                )
            )
            driver._protocol_action(args)
            self.assertTrue((draft / "autodata.pipeline.json").is_file())
            audit = json.loads((args.state_root / "action-audit.json").read_text())
            self.assertEqual(
                [(item["kind"], item["actor"]) for item in audit],
                [
                    ("clarify_design", "aar-research-agent"),
                    ("author_grounding", "aar-research-agent"),
                    ("approve_grounding", "aar-integrity-monitor"),
                    ("author_pipeline", "aar-research-agent"),
                ],
            )
            self.assertTrue(
                all(len(item["result_sha256"]) == 64 for item in audit)
            )

            args.kind = "step"
            plan = driver._protocol_prepare(args)
            self.assertTrue(plan["performs_model_call"])
            self.assertEqual(plan["maximum_model_tasks"], 2)

    def test_public_execution_actions_advertise_required_agent_results(self) -> None:
        if not (AUTODATA_ROOT / "src" / "autodata" / "models.py").is_file():
            self.skipTest("canonical AutoData checkout unavailable")
        from autodata.models import ActionScope, ActionSpec

        driver = _module(
            "autodata_live_sandoq_driver_action_contract",
            REPO / "scripts" / "autodata_live_sandoq_driver.py",
        )

        class UnusedArtifacts:
            pass

        common = {
            "scope": ActionScope("execution", "execution-1", 0),
            "artifacts": (),
            "editable_root": "/operator/private/path",
            "allowed_paths": ("recipe/prompt_variant.json",),
            "remaining_budget": {},
        }
        analyze = ActionSpec(
            id="analyze-1",
            kind="analyze_results",
            instructions="Analyze evidence.",
            outputs=("proposal", "dashboard_summary"),
            **common,
        )
        mutation = ActionSpec(
            id="mutation-1",
            kind="mutate_candidate",
            instructions="Make one change.",
            outputs=("summary",),
            **common,
        )
        public_analyze = driver._public_action(analyze, UnusedArtifacts(), {})
        public_mutation = driver._public_action(mutation, UnusedArtifacts(), {})
        self.assertEqual(
            public_analyze["required_result"]["required"],
            ["proposal", "dashboard_summary"],
        )
        self.assertEqual(
            public_mutation["required_result"]["required"],
            ["prompt_variant", "summary"],
        )
        self.assertNotIn("editable_root", public_mutation)

    def test_resource_approval_requires_frozen_canary_and_current_broker_readiness(self) -> None:
        driver = _module(
            "autodata_live_sandoq_driver_resource_evidence",
            REPO / "scripts" / "autodata_live_sandoq_driver.py",
        )

        class Response:
            def __init__(self, value):
                self.payload = json.dumps(value).encode()

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                return False

            def read(self, limit):
                return self.payload

        executor = {
            "kind": "sandoq-firecracker",
            "environment": "oci-runner-firecracker-small",
            "image": "registry.invalid/autodata@sha256:" + "a" * 64,
            "expected_image_id": "b" * 64,
            "broker_url": "https://broker.invalid",
            "broker_auth_secret_ref": "TEST_BROKER_TOKEN",
            "non_secret_env": {
                "AUTODATA_GENERATOR_DEPLOYMENT_ID": "winnieyangwn-kimi26",
                "AUTODATA_GENERATOR_MAX_OUTPUT": "1536",
                "AUTODATA_JUDGE_MAX_OUTPUT": "512",
            },
        }
        ready = {
            "ready": True,
            "runner": {"ready": True, "runner": "sandoq-firecracker"},
            "registry": {"ready": True},
            "max_concurrent": 4,
            "active": 0,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root = root / "state"
            draft = state_root / "live-workspace"
            draft.mkdir(parents=True)
            (draft / "autodata.workspace.json").write_text(
                json.dumps(
                    {
                        "execution_defaults": {
                            "executor": executor,
                            "concurrency": 4,
                            "budget": {"max_wall_seconds": 10800},
                        }
                    }
                )
            )
            profile = {
                "schema": "aar.autodata.resource-profile/v1",
                "name": "production-v1",
                "autodata_framework_commit": "c" * 40,
                "budget_scope_id": "scope-1",
                "max_cost_usd": "10.00",
                "required_retained_rows": 64,
                "max_estimated_cost_per_task_usd": "0.01",
                "max_concurrency": 4,
                "max_wall_seconds": 10800,
                "training_view": "sft",
                "generator": {
                    "model": "Kimi-K2.6",
                    "deployment_id": "winnieyangwn-kimi26",
                    "url": "https://generator.invalid/v1",
                    "max_output_tokens": 1536,
                },
                "judge": {"model": "gpt-5.6-luna", "max_output_tokens": 512},
                "executor": {
                    key: executor[key]
                    for key in ("kind", "environment", "image", "expected_image_id")
                },
            }
            profile_path = root / "resource-profile.json"
            profile_path.write_text(json.dumps(profile))
            profile_sha = hashlib.sha256(driver._canonical_json(profile)).hexdigest()
            usage = [
                {"role": "generator", "model": "Kimi-K2.6"},
                {"role": "judge", "model": "gpt-5.6-luna"},
            ]
            canary = {
                "schema": "aar.autodata.model-broker-canary/v1",
                "success": True,
                "broker_job_id": "job-1",
                "broker_status": "SUCCEEDED",
                "sandoq_session_id": "session-1",
                "environment": executor["environment"],
                "image": executor["image"],
                "expected_image_id": executor["expected_image_id"],
                "task_result_schema_valid": True,
                "task_result_outcome": "succeeded",
                "generated_item_count": 1,
                "provider_call_count": 2,
                "generator_deployment_id": "winnieyangwn-kimi26",
                "provider_usage": usage,
            }
            canary_path = root / "model-canary.json"
            canary_path.write_text(json.dumps(canary))
            canary_path.chmod(0o600)
            canary_sha = hashlib.sha256(canary_path.read_bytes()).hexdigest()
            args = SimpleNamespace(
                state_root=state_root,
                resource_profile=profile_path,
                resource_profile_sha256=profile_sha,
                model_canary_report=canary_path,
                model_canary_sha256=canary_sha,
                generator_model="Kimi-K2.6",
                generator_url="https://generator.invalid/v1",
                judge_model="gpt-5.6-luna",
            )
            request = {
                "pipeline_sha": "c" * 40,
                "spec": {"training_view": "sft"},
                "controls": {
                    "resource_profile": "production-v1",
                    "resource_profile_sha256": profile_sha,
                    "budget_scope_id": "scope-1",
                    "max_cost_usd": "10",
                    "required_retained_rows": 64,
                },
            }
            environment = {
                "TEST_BROKER_TOKEN": "never-retain-this-token",
                "AAR_AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD": "0.010",
            }
            with patch.dict(os.environ, environment, clear=False), patch.object(
                driver.urllib.request,
                "urlopen",
                return_value=Response(ready),
            ):
                evidence = driver._resource_approval_evidence(args, request)
            self.assertTrue(all(item["passed"] for item in evidence["checks"]))
            self.assertEqual(evidence["model_canary_sha256"], canary_sha)
            self.assertNotIn("never-retain-this-token", json.dumps(evidence))
            from autodata.models import ActionScope, ActionSpec

            resource_action = ActionSpec(
                id="approve-resources-1",
                scope=ActionScope("workspace", "workspace-1", 1),
                kind="approve_resources",
                instructions="Verify runtime recovery.",
                artifacts=(),
                editable_root=None,
                allowed_paths=(),
                outputs=("decision",),
                remaining_budget={},
            )
            with patch.dict(os.environ, environment, clear=False), patch.object(
                driver.urllib.request,
                "urlopen",
                return_value=Response(ready),
            ):
                public = driver._public_action(
                    resource_action, object(), request, args
                )
            self.assertEqual(
                public["evidence"]["schema"],
                "aar.autodata.approval-evidence/v1",
            )
            self.assertEqual(
                public["evidence"]["resource_evidence_schema"],
                "aar.autodata.resource-approval-evidence/v1",
            )
            self.assertNotIn("never-retain-this-token", json.dumps(public))

            canary_path.write_text(json.dumps({**canary, "success": False}))
            canary_path.chmod(0o600)
            with patch.dict(os.environ, environment, clear=False), patch.object(
                driver.urllib.request,
                "urlopen",
                return_value=Response(ready),
            ):
                with self.assertRaisesRegex(RuntimeError, "startup digest"):
                    driver._resource_approval_evidence(args, request)

            canary_path.write_text(json.dumps(canary))
            canary_path.chmod(0o600)
            unavailable = {**ready, "ready": False}
            with patch.dict(os.environ, environment, clear=False), patch.object(
                driver.urllib.request,
                "urlopen",
                return_value=Response(unavailable),
            ):
                with self.assertRaisesRegex(RuntimeError, "not currently ready"):
                    driver._resource_approval_evidence(args, request)


if __name__ == "__main__":
    unittest.main()
