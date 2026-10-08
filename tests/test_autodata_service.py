from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aar" / "infrastructure" / "autodata_service.py"
MODULE_SPEC = importlib.util.spec_from_file_location("aar_autodata_service", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)
AutoDataJobService = MODULE.AutoDataJobService
LifecycleBackend = MODULE.LifecycleBackend

SHA = "b" * 40


class FakeBackend(LifecycleBackend):
    @property
    def models(self):
        return {
            "generator": {"identity": "deterministic"},
            "judge": {"identity": "deterministic"},
        }

    def run(self, job_root, request):
        time.sleep(0.01)
        return {
            "rows": [{"id": "one", "prompt": "p", "response": "r"}],
            "manifest_fields": {
                "study_id": "study-1",
                "execution_id": "exec-production",
                "recipe_digest": "1" * 64,
                "pipeline_digest": "2" * 64,
                "approval_principal": "aar-integrity-monitor",
            },
            "status_fields": {
                "workspace_id": "ws-1",
                "meta_execution_id": "exec-meta",
                "production_execution_id": "exec-production",
            },
        }


class CostBackend(FakeBackend):
    def __init__(self, spent: str) -> None:
        self.spent = spent

    def run(self, job_root, request):
        result = super().run(job_root, request)
        result["manifest_fields"]["budget"] = {
            "max_cost_usd": request["controls"]["max_cost_usd"],
            "spent_cost_usd": self.spent,
            "model_calls": 2,
            "input_tokens": 10,
            "output_tokens": 5,
        }
        return result


class InteractiveBackend(FakeBackend):
    def __init__(self):
        self.stage = 0
        self.completions = []
        self.begun_actions = []

    @property
    def interactive(self):
        return True

    def create_workspace(self, job_root, request, ledger):
        return {
            "state": "active",
            "phase": "grounding",
            "workspace_id": "ws-live",
            "native_status": {"workspace": {"id": "ws-live", "phase": "clarification"}},
        }

    def step_interactive(self, job_root, request, ledger):
        if self.stage == 0:
            return {
                "state": "waiting_action",
                "phase": "grounding",
                "action": {"id": "author-1", "kind": "author_grounding"},
            }
        if self.stage == 1:
            return {
                "state": "waiting_action",
                "phase": "grounding-review",
                "action": {
                    "id": "approve-1",
                    "kind": "approve_grounding",
                    "evidence": {
                        "schema": "aar.autodata.approval-evidence/v1",
                        "artifact_digest": "sha256:" + "a" * 64,
                        "task_count": 3,
                        "checks": [
                            {"name": "coverage_present", "passed": True},
                            {"name": "provenance_valid", "passed": True},
                        ],
                    },
                },
            }
        return {
            "state": "complete",
            "rows": [{"id": "one", "prompt": "p", "response": "r"}],
            "manifest_fields": {
                "study_id": "study-live",
                "execution_id": "production-live",
                "recipe_digest": "1" * 64,
                "pipeline_digest": "2" * 64,
                "approval_principal": "aar-integrity-monitor",
            },
            "status_fields": {
                "workspace_id": "ws-live",
                "meta_execution_id": "meta-live",
                "production_execution_id": "production-live",
            },
        }

    def action_interactive(
        self, operation, job_root, request, action_id, payload, ledger
    ):
        if operation == "begin":
            self.begun_actions.append(action_id)
            return {"lease_token": f"native-{action_id}"}
        self.completions.append((operation, action_id, payload))
        self.stage += 1
        return {"state": "active", "phase": "advance"}


def request(run_id="run-1"):
    spec = {
        "schema": "aar.autodata.request/v1",
        "resource_profile": "integration-v1",
        "safety_axis": "test",
        "training_mechanism": "sft",
        "training_view": "sft",
        "seed": 1,
        "goal": "integration test",
    }
    return {
        "run_id": run_id,
        "pipeline_sha": SHA,
        "spec": spec,
        "binding": {
            "idea_name": "idea",
            "method_code_sha256": "3" * 64,
            "autodata_spec_sha256": MODULE.hashlib.sha256(
                MODULE._canonical_json(spec)
            ).hexdigest(),
        },
        "controls": {
            "resource_profile": "integration-v1",
            "resource_profile_sha256": "4" * 64,
            "budget_scope_id": "campaign-1",
            "required_retained_rows": 1,
            "max_cost_usd": "10.00",
        },
    }


def live_evidence(root: Path):
    canary = root / "model-canary.json"
    canary.write_text(json.dumps({"schema": "aar.autodata.model-broker-canary/v1"}))
    canary.chmod(0o600)
    profile = root / "resource-profile.json"
    profile.write_text(json.dumps({"schema": "aar.autodata.resource-profile/v1"}))
    return canary, profile


class AutoDataJobServiceTest(TestCase):
    def make_service(self, root):
        return AutoDataJobService(Path(root) / "state", SHA, backend=FakeBackend())

    def wait(self, service, run_id):
        for _ in range(100):
            status = service.status(run_id)
            if status["state"] in {"complete", "failed"}:
                return status
            time.sleep(0.01)
        self.fail("job did not finish")

    def test_submit_requires_step_then_completes_with_provenance(self):
        with TemporaryDirectory() as td:
            service = self.make_service(td)
            created = service.submit(request())
            self.assertEqual(created["state"], "created")
            started = service.step("run-1")
            self.assertEqual(started["state"], "queued")
            status = self.wait(service, "run-1")
            self.assertEqual(status["state"], "complete")
            manifest = service.artifacts("run-1")["manifest"]
            self.assertEqual(manifest["row_count"], 1)
            self.assertEqual(manifest["approval_principal"], "aar-integrity-monitor")
            self.assertEqual(manifest["models"]["generator"]["identity"], "deterministic")

    def test_submit_and_step_are_idempotent(self):
        with TemporaryDirectory() as td:
            service = self.make_service(td)
            first = service.submit(request())
            second = service.submit(request())
            self.assertEqual(first["job_id"], second["job_id"])
            service.step("run-1")
            self.assertIn(
                service.step("run-1")["state"], {"queued", "running", "complete"}
            )
            self.wait(service, "run-1")

    def test_same_run_rejects_different_request(self):
        with TemporaryDirectory() as td:
            service = self.make_service(td)
            service.submit(request("run-2"))
            changed = request("run-2")
            changed["spec"]["goal"] = "different"
            with self.assertRaisesRegex(ValueError, "different request"):
                service.submit(changed)

    def test_rejects_sha_mismatch_and_unsupported_run_id(self):
        with TemporaryDirectory() as td:
            service = self.make_service(td)
            bad_sha = request("bad-sha")
            bad_sha["pipeline_sha"] = "c" * 40
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                service.submit(bad_sha)
            with self.assertRaisesRegex(ValueError, "unsupported"):
                service.submit(request("../run"))

    def test_action_lease_complete_and_integrity_monitor_reservation(self):
        with TemporaryDirectory() as td:
            service = self.make_service(td)
            service.submit(request("actions"))
            root = Path(td) / "state" / "runs" / "actions"
            status = service.status("actions")
            status["pending_action"] = {"id": "a1", "kind": "author_pipeline"}
            MODULE._write_json(root / "status.json", status)
            lease = service.lease_action("actions", "a1")
            completed = service.complete_action(
                "actions", "a1", lease["lease_token"], {"summary": "done"}
            )
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["run_id"], "actions")
            status = service.status("actions")
            status["pending_action"] = {"id": "a2", "kind": "approve_grounding"}
            MODULE._write_json(root / "status.json", status)
            with self.assertRaisesRegex(RuntimeError, "integrity monitor"):
                service.lease_action("actions", "a2")

    def test_parallel_runs_share_one_budget_scope_cap(self):
        with TemporaryDirectory() as td:
            service = AutoDataJobService(
                Path(td) / "state", SHA, backend=CostBackend("0.6")
            )
            first = request("cost-1")
            first["controls"]["max_cost_usd"] = "1.0"
            service.submit(first)
            service.step("cost-1")
            self.assertEqual(self.wait(service, "cost-1")["state"], "complete")

            second = request("cost-2")
            second["controls"]["max_cost_usd"] = "1.0"
            service.submit(second)
            service.step("cost-2")
            failed = self.wait(service, "cost-2")
            self.assertEqual(failed["state"], "failed")
            self.assertIn("reservation", failed["error"])

            budget = json.loads(
                (
                    Path(td)
                    / "state"
                    / "budget-scopes"
                    / "campaign-1.json"
                ).read_text()
            )
            # The violating backend spent 0.6 against only 0.4 remaining. The
            # run fails, but actual provider spend is still retained in scope.
            self.assertEqual(budget["spent_cost_usd"], "1.2")

    def test_budget_scope_profile_and_cap_are_immutable_across_runs(self):
        with TemporaryDirectory() as td:
            service = self.make_service(td)
            service.submit(request("scope-1"))
            service.submit(request("scope-2"))
            changed_cap = request("scope-cap")
            changed_cap["controls"]["max_cost_usd"] = "11.00"
            with self.assertRaisesRegex(ValueError, "different cap or profile"):
                service.submit(changed_cap)
            changed_profile = request("scope-profile")
            changed_profile["controls"]["resource_profile_sha256"] = "5" * 64
            with self.assertRaisesRegex(ValueError, "different cap or profile"):
                service.submit(changed_profile)

    def test_failed_provider_spend_is_conservatively_charged(self):
        with TemporaryDirectory() as td:
            ledger = MODULE.CampaignBudgetLedger(Path(td))
            controls = request()["controls"]
            ledger.register(controls)
            reservation = ledger.reserve("campaign-1", "0.40")
            state = ledger.settle(
                "campaign-1",
                reservation,
                actual_cost=None,
                model_calls=1,
                input_tokens=10,
                output_tokens=0,
            )
            self.assertEqual(state["spent_cost_usd"], "0.40")
            self.assertEqual(state["model_calls"], 1)

    def test_interactive_agent_action_and_evidence_based_delegated_approval(self):
        with TemporaryDirectory() as td:
            backend = InteractiveBackend()
            service = AutoDataJobService(Path(td) / "state", SHA, backend=backend)
            created = service.submit(request("interactive"))
            self.assertEqual(created["workspace_id"], "ws-live")
            self.assertEqual(created["native_status"]["workspace"]["id"], "ws-live")
            service.step("interactive")
            for _ in range(100):
                action_state = service.status("interactive")
                if action_state.get("pending_action"):
                    break
                time.sleep(0.01)
            self.assertEqual(action_state["pending_action"]["kind"], "author_grounding")
            lease = service.lease_action("interactive", "author-1")
            self.assertEqual(lease["lease_token"], "native-author-1")
            retried_lease = service.lease_action("interactive", "author-1")
            self.assertEqual(retried_lease["lease_token"], lease["lease_token"])
            self.assertEqual(backend.begun_actions.count("author-1"), 1)
            service.complete_action(
                "interactive",
                "author-1",
                lease["lease_token"],
                {"summary": "authored by AAR agent"},
            )
            service.step("interactive")
            for _ in range(100):
                completed = service.status("interactive")
                if completed["state"] in {"complete", "failed"}:
                    break
                if not completed.get("operation_running") and not completed.get("pending_action"):
                    service.step("interactive")
                time.sleep(0.01)
            self.assertEqual(completed["state"], "complete")
            approvals = [item for item in backend.completions if item[1] == "approve-1"]
            self.assertEqual(len(approvals), 1)
            self.assertEqual(
                approvals[0][2]["lease_token"], "native-approve-1"
            )
            attestation = approvals[0][2]["result"]["approval_attestation"]
            self.assertEqual(attestation["principal"], "aar-integrity-monitor")
            self.assertLess(
                attestation["evidence_recorded_sequence"],
                attestation["approval_sequence"],
            )
            root = Path(td) / "state" / "runs" / "interactive"
            self.assertTrue((root / "approval-evidence" / "approve-1.json").is_file())
            self.assertTrue(
                (root / "approval-attestations" / "approve-1.json").is_file()
            )

    def test_duplicate_interactive_step_returns_busy_without_second_operation(self):
        class SlowInteractive(InteractiveBackend):
            def __init__(self):
                super().__init__()
                self.step_calls = 0

            def step_interactive(self, job_root, request, ledger):
                self.step_calls += 1
                time.sleep(0.05)
                return super().step_interactive(job_root, request, ledger)

        with TemporaryDirectory() as td:
            backend = SlowInteractive()
            service = AutoDataJobService(Path(td) / "state", SHA, backend=backend)
            service.submit(request("busy-step"))
            first = service.step("busy-step")
            second = service.step("busy-step")
            self.assertTrue(first["operation_running"])
            self.assertTrue(second["operation_running"])
            self.assertEqual(backend.step_calls, 1)
            for _ in range(100):
                if not service.status("busy-step").get("operation_running"):
                    break
                time.sleep(0.01)
            else:
                self.fail("interactive step worker did not finish")

    def test_integrity_monitor_rejects_incomplete_approval_evidence(self):
        with TemporaryDirectory() as td:
            service = AutoDataJobService(
                Path(td) / "state", SHA, backend=InteractiveBackend()
            )
            service.submit(request("weak-evidence"))
            root = Path(td) / "state" / "runs" / "weak-evidence"
            action = {
                "id": "approve-weak",
                "kind": "approve_grounding",
                "created_sequence": 2,
                "evidence": {
                    "schema": "aar.autodata.approval-evidence/v1",
                    "artifact_digest": "sha256:" + "a" * 64,
                    "recorded_sequence": 1,
                    "task_count": 1,
                    "checks": [{"name": "coverage_present", "passed": True}],
                },
            }
            with self.assertRaisesRegex(RuntimeError, "required checks"):
                service._approval_result(root, action)

    def test_resource_approval_is_bound_to_frozen_canary_and_profile(self):
        class ResourceBackend(FakeBackend):
            @property
            def resource_evidence_binding(self):
                return {
                    "model_canary_sha256": "5" * 64,
                    "resource_profile_sha256": "4" * 64,
                }

        with TemporaryDirectory() as td:
            service = AutoDataJobService(
                Path(td) / "state", SHA, backend=ResourceBackend()
            )
            service.submit(request("resource-evidence"))
            root = Path(td) / "state" / "runs" / "resource-evidence"
            action = {
                "id": "approve-resources",
                "kind": "approve_resources",
                "created_sequence": 2,
                "evidence": {
                    "schema": "aar.autodata.approval-evidence/v1",
                    "resource_evidence_schema": "aar.autodata.resource-approval-evidence/v1",
                    "artifact_digest": "sha256:" + "a" * 64,
                    "recorded_sequence": 1,
                    "resource_profile_sha256": "4" * 64,
                    "budget_scope_id": "campaign-1",
                    "model_canary_sha256": "5" * 64,
                    "broker_ready_snapshot_sha256": "6" * 64,
                    "executor_sha256": "7" * 64,
                    "checks": [
                        {"name": name, "passed": True}
                        for name in (
                            "resource_profile_verified",
                            "budget_scope_verified",
                            "startup_model_canary_verified",
                            "broker_ready_verified",
                            "executor_pins_verified",
                        )
                    ],
                },
            }
            result = service._approval_result(root, action)
            self.assertEqual(result["decision"], "retry")
            self.assertNotIn("target", result)
            action["evidence"]["model_canary_sha256"] = "8" * 64
            with self.assertRaisesRegex(RuntimeError, "operator controls"):
                service._approval_result(root, action)

    def test_direct_client_cannot_expand_operator_controls(self):
        with TemporaryDirectory() as td:
            expected = dict(request()["controls"])
            service = AutoDataJobService(
                Path(td) / "state",
                SHA,
                backend=FakeBackend(),
                required_controls=expected,
            )
            changed = request("bypass")
            changed["controls"]["max_cost_usd"] = "1000000"
            with self.assertRaisesRegex(ValueError, "operator policy"):
                service.submit(changed)

            changed = request("bypass-rows")
            changed["controls"]["required_retained_rows"] = 0
            with self.assertRaisesRegex(ValueError, "operator policy"):
                service.submit(changed)

    def test_direct_client_cannot_replace_operator_scientific_profile(self):
        with TemporaryDirectory() as td:
            service = AutoDataJobService(
                Path(td) / "state",
                SHA,
                backend=FakeBackend(),
                required_spec={
                    "resource_profile": "integration-v1",
                    "safety_axis": "test",
                    "training_view": "sft",
                },
            )
            changed = request("bypass-axis")
            changed["spec"]["safety_axis"] = "unapproved-axis"
            changed["binding"]["autodata_spec_sha256"] = MODULE.hashlib.sha256(
                MODULE._canonical_json(changed["spec"])
            ).hexdigest()
            with self.assertRaisesRegex(ValueError, "operator policy"):
                service.submit(changed)

    def test_live_backend_fails_closed_when_route_credentials_are_missing(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            driver = root / "driver.py"
            driver.write_text("pass\n")
            canary, profile = live_evidence(root)
            os.environ.pop("MISSING_GENERATOR_TOKEN", None)
            os.environ.pop("MISSING_JUDGE_TOKEN", None)
            with self.assertRaisesRegex(ValueError, "credential environment variable"):
                MODULE.LiveModelLifecycleBackend(
                    driver_script=driver,
                    generator_model="Kimi-K2.6",
                    judge_model="gpt-5.6-luna",
                    generator_url="https://generator.invalid",
                    judge_url="https://judge.invalid",
                    generator_token_env="MISSING_GENERATOR_TOKEN",
                    judge_token_env="MISSING_JUDGE_TOKEN",
                    model_canary_report=canary,
                    resource_profile_path=profile,
                )

    def test_live_backend_records_qualified_generator_deployment(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            driver = root / "driver.py"
            driver.write_text("pass\n")
            canary, profile = live_evidence(root)
            previous_generator = os.environ.get("TEST_GENERATOR_TOKEN")
            previous_judge = os.environ.get("TEST_JUDGE_TOKEN")
            os.environ["TEST_GENERATOR_TOKEN"] = "generator-secret"
            os.environ["TEST_JUDGE_TOKEN"] = "judge-secret"
            try:
                backend = MODULE.LiveModelLifecycleBackend(
                    driver_script=driver,
                    generator_model="Kimi-K2.6",
                    judge_model="gpt-5.6-luna",
                    generator_url="https://generator.invalid/v1",
                    judge_url="https://judge.invalid/v1/responses",
                    generator_token_env="TEST_GENERATOR_TOKEN",
                    judge_token_env="TEST_JUDGE_TOKEN",
                    model_canary_report=canary,
                    resource_profile_path=profile,
                    generator_deployment_id="winnieyangwn-kimi26",
                    max_wall_seconds=7200,
                )
            finally:
                if previous_generator is None:
                    os.environ.pop("TEST_GENERATOR_TOKEN", None)
                else:
                    os.environ["TEST_GENERATOR_TOKEN"] = previous_generator
                if previous_judge is None:
                    os.environ.pop("TEST_JUDGE_TOKEN", None)
                else:
                    os.environ["TEST_JUDGE_TOKEN"] = previous_judge
            self.assertEqual(
                backend.models["generator"],
                {
                    "identity": "Kimi-K2.6",
                    "route": "https://generator.invalid/v1",
                    "deployment_id": "winnieyangwn-kimi26",
                },
            )
            self.assertEqual(backend.max_wall_seconds, 7200)

    def test_live_backend_passes_operator_credential_names_to_driver(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            driver = root / "driver.py"
            driver.write_text("pass\n")
            canary, profile = live_evidence(root)
            os.environ["TEST_GENERATOR_TOKEN"] = "generator-secret"
            os.environ["TEST_JUDGE_TOKEN"] = "judge-secret"
            try:
                backend = MODULE.LiveModelLifecycleBackend(
                    driver_script=driver,
                    generator_model="Kimi-K2.6",
                    judge_model="gpt-5.6-luna",
                    generator_url="https://generator.invalid/v1",
                    judge_url="https://judge.invalid/v1/responses",
                    generator_token_env="TEST_GENERATOR_TOKEN",
                    judge_token_env="TEST_JUDGE_TOKEN",
                    model_canary_report=canary,
                    resource_profile_path=profile,
                )
                observed = []

                def fake_run(command, **kwargs):
                    observed.append(list(command))
                    output = Path(command[command.index("--output") + 1])
                    if command[command.index("--operation") + 1] == "prepare":
                        output.write_text(
                            json.dumps(
                                {
                                    "maximum_cost_usd": "0",
                                    "performs_model_call": False,
                                }
                            )
                        )
                    else:
                        output.write_text(
                            json.dumps(
                                {
                                    "state": "active",
                                    "phase": "workspace",
                                    "usage": {
                                        "spent_cost_usd": "0",
                                        "model_calls": 0,
                                        "input_tokens": 0,
                                        "output_tokens": 0,
                                    },
                                }
                            )
                        )
                    return SimpleNamespace(returncode=0, stderr="")

                job_root = root / "job"
                job_root.mkdir()
                (job_root / "request.json").write_text("{}")
                with patch.object(MODULE.subprocess, "run", side_effect=fake_run):
                    backend.create_workspace(job_root, request(), object())
            finally:
                os.environ.pop("TEST_GENERATOR_TOKEN", None)
                os.environ.pop("TEST_JUDGE_TOKEN", None)
            execute = observed[1]
            self.assertEqual(
                execute[execute.index("--generator-token-env") + 1],
                "TEST_GENERATOR_TOKEN",
            )
            self.assertEqual(
                execute[execute.index("--judge-token-env") + 1],
                "TEST_JUDGE_TOKEN",
            )
            self.assertEqual(
                execute[execute.index("--model-canary-sha256") + 1],
                backend.model_canary_sha256,
            )
            self.assertEqual(
                execute[execute.index("--resource-profile-sha256") + 1],
                backend.resource_profile_sha256,
            )

    def test_live_backend_charges_full_reservation_when_usage_is_incomplete(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            driver = root / "driver.py"
            driver.write_text("pass\n")
            canary, profile = live_evidence(root)
            os.environ["TEST_GENERATOR_TOKEN"] = "generator-secret"
            os.environ["TEST_JUDGE_TOKEN"] = "judge-secret"
            try:
                backend = MODULE.LiveModelLifecycleBackend(
                    driver_script=driver,
                    generator_model="Kimi-K2.6",
                    judge_model="gpt-5.6-luna",
                    generator_url="https://generator.invalid/v1",
                    judge_url="https://judge.invalid/v1/responses",
                    generator_token_env="TEST_GENERATOR_TOKEN",
                    judge_token_env="TEST_JUDGE_TOKEN",
                    model_canary_report=canary,
                    resource_profile_path=profile,
                )
                ledger = MODULE.CampaignBudgetLedger(root / "ledger")
                ledger.register(request()["controls"])

                def fake_run(command, **kwargs):
                    output = Path(command[command.index("--output") + 1])
                    if command[command.index("--operation") + 1] == "prepare":
                        output.write_text(
                            json.dumps(
                                {
                                    "maximum_cost_usd": "0.40",
                                    "performs_model_call": True,
                                }
                            )
                        )
                        return SimpleNamespace(returncode=0, stderr="")
                    output.write_text(
                        json.dumps(
                            {
                                "state": "failed",
                                "usage_complete": False,
                                "usage": {
                                    "spent_cost_usd": "0.01",
                                    "model_calls": 1,
                                    "input_tokens": 10,
                                    "output_tokens": 1,
                                },
                            }
                        )
                    )
                    return SimpleNamespace(returncode=1, stderr="usage collection failed")

                job_root = root / "job"
                job_root.mkdir()
                (job_root / "request.json").write_text("{}")
                with patch.object(MODULE.subprocess, "run", side_effect=fake_run):
                    with self.assertRaisesRegex(RuntimeError, "usage collection failed"):
                        backend.create_workspace(job_root, request(), ledger)
                self.assertEqual(
                    ledger.snapshot("campaign-1")["spent_cost_usd"], "0.40"
                )
            finally:
                os.environ.pop("TEST_GENERATOR_TOKEN", None)
                os.environ.pop("TEST_JUDGE_TOKEN", None)

    def test_live_backend_rejects_mutable_canary_evidence(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            driver = root / "driver.py"
            driver.write_text("pass\n")
            canary, profile = live_evidence(root)
            canary.chmod(0o644)
            os.environ["TEST_GENERATOR_TOKEN"] = "generator-secret"
            os.environ["TEST_JUDGE_TOKEN"] = "judge-secret"
            try:
                with self.assertRaisesRegex(ValueError, "unsafe ownership or mode"):
                    MODULE.LiveModelLifecycleBackend(
                        driver_script=driver,
                        generator_model="Kimi-K2.6",
                        judge_model="gpt-5.6-luna",
                        generator_url="https://generator.invalid/v1",
                        judge_url="https://judge.invalid/v1/responses",
                        generator_token_env="TEST_GENERATOR_TOKEN",
                        judge_token_env="TEST_JUDGE_TOKEN",
                        model_canary_report=canary,
                        resource_profile_path=profile,
                    )
                canary.chmod(0o600)
                canary_link = root / "model-canary-link.json"
                canary_link.symlink_to(canary)
                with self.assertRaisesRegex(ValueError, "regular file"):
                    MODULE.LiveModelLifecycleBackend(
                        driver_script=driver,
                        generator_model="Kimi-K2.6",
                        judge_model="gpt-5.6-luna",
                        generator_url="https://generator.invalid/v1",
                        judge_url="https://judge.invalid/v1/responses",
                        generator_token_env="TEST_GENERATOR_TOKEN",
                        judge_token_env="TEST_JUDGE_TOKEN",
                        model_canary_report=canary_link,
                        resource_profile_path=profile,
                    )
            finally:
                os.environ.pop("TEST_GENERATOR_TOKEN", None)
                os.environ.pop("TEST_JUDGE_TOKEN", None)

    def test_live_backend_rejects_invalid_operator_wall_timeout(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            driver = root / "driver.py"
            driver.write_text("pass\n")
            canary, profile = live_evidence(root)
            previous_generator = os.environ.get("TEST_GENERATOR_TOKEN")
            previous_judge = os.environ.get("TEST_JUDGE_TOKEN")
            os.environ["TEST_GENERATOR_TOKEN"] = "generator-secret"
            os.environ["TEST_JUDGE_TOKEN"] = "judge-secret"
            try:
                with self.assertRaisesRegex(ValueError, "max_wall_seconds"):
                    MODULE.LiveModelLifecycleBackend(
                        driver_script=driver,
                        generator_model="Kimi-K2.6",
                        judge_model="gpt-5.6-luna",
                        generator_url="https://generator.invalid/v1",
                        judge_url="https://judge.invalid/v1/responses",
                        generator_token_env="TEST_GENERATOR_TOKEN",
                        judge_token_env="TEST_JUDGE_TOKEN",
                        model_canary_report=canary,
                        resource_profile_path=profile,
                        max_wall_seconds=0,
                    )
            finally:
                if previous_generator is None:
                    os.environ.pop("TEST_GENERATOR_TOKEN", None)
                else:
                    os.environ["TEST_GENERATOR_TOKEN"] = previous_generator
                if previous_judge is None:
                    os.environ.pop("TEST_JUDGE_TOKEN", None)
                else:
                    os.environ["TEST_JUDGE_TOKEN"] = previous_judge
