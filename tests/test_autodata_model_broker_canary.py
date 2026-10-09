from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "autodata_model_broker_canary.py"
RECIPE = REPO / "aar" / "autodata_recipes" / "dishonest_sycophancy_concealing"


def _module():
    spec = importlib.util.spec_from_file_location(
        "autodata_model_broker_canary", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _usage(
    request_id: str,
    role: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: str,
):
    return {
        "request_id": request_id,
        "role": role,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": cost,
        "cost_basis": "operator-configured-token-rates",
    }


class _FakeSpec:
    def __init__(self, value):
        self.value = value

    def to_dict(self):
        return self.value


class _FakeBrokerJobSpec:
    captured = None

    @classmethod
    def from_dict(cls, value):
        cls.captured = value
        return _FakeSpec(value)


class _FakeBrokerClient:
    instances = []
    result = None

    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.requests = []
        self.uploads = []
        self.downloads = []
        self.__class__.instances.append(self)

    def json_request(self, method, path, body=None):
        self.requests.append((method, path, body))
        if method == "POST":
            return {"id": "job_canary", "status": "AWAITING_UPLOAD"}
        return {
            "id": "job_canary",
            "status": "SUCCEEDED",
            "session_id": "session_canary",
        }

    def upload(self, job_id, kind, source):
        self.uploads.append((job_id, kind, source))

    def download_results(self, job_id, destination):
        self.downloads.append((job_id, destination))
        destination.write_bytes(b"fake-results")


def _build_archive(_workspace, destination):
    payload = b"fake-workspace"
    destination.write_bytes(payload)
    return SimpleNamespace(
        size=len(payload), sha256=hashlib.sha256(payload).hexdigest()
    )


def _extract_archive(_archive, destination):
    output = destination / ".autodata" / "task-result.json"
    output.parent.mkdir(parents=True)
    output.write_text(json.dumps(_FakeBrokerClient.result))


class ModelBrokerCanaryTest(unittest.TestCase):
    def setUp(self):
        self.module = _module()
        _FakeBrokerClient.instances.clear()
        _FakeBrokerJobSpec.captured = None
        generator = _usage("kimi-request", "generator", "Kimi-K2.6", 10, 5, "0.00003")
        judge = _usage("luna-request", "judge", "gpt-5-6-luna", 20, 7, "0.000048")
        _FakeBrokerClient.result = {
            "schema": "autodata.task-result/v1",
            "task_id": "run8-model-backed-canary",
            "outcome": "succeeded",
            "generated_items": [
                {
                    "id": "run8-model-backed-canary",
                    "prompt": "SENSITIVE GENERATED PROMPT",
                    "response": "SENSITIVE GENERATED RESPONSE",
                    "metadata": {"judge_accepted": True},
                    "_autodata_usage": [generator, judge],
                }
            ],
            "metrics": {
                "quality": 0.9,
                "valid": 1.0,
                "challenge": 0.0,
                "quality_challenge_utility": 0.0,
            },
            "provider_usage": [generator, judge],
            "reason_code": None,
            "trajectory_artifacts": [],
        }

    def test_one_authenticated_model_backed_job_retains_only_safe_evidence(self):
        runtime = self.module._Runtime(
            _FakeBrokerClient,
            _FakeBrokerJobSpec,
            _build_archive,
            _extract_archive,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            token_file = root / "broker.token"
            token_file.write_text("broker-secret")
            token_file.chmod(0o600)
            output = root / "report.json"
            args = self.module._parser().parse_args(
                [
                    "--broker-url",
                    "https://broker.example",
                    "--broker-auth-token-file",
                    str(token_file),
                    "--recipe-root",
                    str(RECIPE),
                    "--output",
                    str(output),
                    "--environment",
                    "oci-runner-firecracker-medium",
                ]
            )
            report = self.module.run(args, runtime=runtime)
            encoded = output.read_text()
            output_mode = output.stat().st_mode & 0o777

        self.assertEqual(len(_FakeBrokerClient.instances), 1)
        client = _FakeBrokerClient.instances[0]
        self.assertEqual(client.token, "broker-secret")
        self.assertEqual(sum(call[0] == "POST" for call in client.requests), 1)
        self.assertEqual(len(client.uploads), 1)
        job = _FakeBrokerJobSpec.captured
        self.assertTrue(job["model_backed"])
        self.assertEqual(job["environment"], "oci-runner-firecracker-medium")
        self.assertEqual(job["solve"]["network"], "host")
        self.assertEqual(job["solve"]["env"]["AUTODATA_GENERATOR_MODEL"], "Kimi-K2.6")
        self.assertEqual(
            job["solve"]["env"]["AUTODATA_GENERATOR_DEPLOYMENT_ID"],
            "winnieyangwn-kimi26",
        )
        self.assertEqual(job["solve"]["env"]["AUTODATA_JUDGE_MODEL"], "gpt-5-6-luna")
        self.assertEqual(job["solve"]["env"]["AUTODATA_TARGET_ENABLED"], "0")
        self.assertNotIn("MODEL_API_KEY", job["solve"]["env"])
        self.assertNotIn("broker-secret", json.dumps(job))
        self.assertEqual(report["provider_call_count"], 2)
        self.assertEqual(report["environment"], "oci-runner-firecracker-medium")
        self.assertEqual(
            [call["role"] for call in report["provider_usage"]],
            ["generator", "judge"],
        )
        self.assertNotIn("SENSITIVE GENERATED PROMPT", encoded)
        self.assertNotIn("SENSITIVE GENERATED RESPONSE", encoded)
        self.assertNotIn('"prompt"', encoded)
        self.assertNotIn('"response"', encoded)
        self.assertEqual(output_mode, 0o600)

    def test_rejects_extra_or_wrong_provider_provenance(self):
        contract = self.module._read_recipe_contract(RECIPE)
        rates = {
            "generator": (self.module.Decimal("1"), self.module.Decimal("4")),
            "judge": (self.module.Decimal("1"), self.module.Decimal("4")),
        }
        extra = dict(_FakeBrokerClient.result)
        extra["provider_usage"] = [
            *_FakeBrokerClient.result["provider_usage"],
            _FakeBrokerClient.result["provider_usage"][1],
        ]
        with self.assertRaisesRegex(RuntimeError, "exactly two"):
            self.module._validate_task_result(extra, contract.schema, rates=rates)
        wrong = json.loads(json.dumps(_FakeBrokerClient.result))
        wrong["provider_usage"][1]["model"] = "wrong-model"
        wrong["generated_items"][0]["_autodata_usage"] = wrong["provider_usage"]
        with self.assertRaisesRegex(RuntimeError, "provenance"):
            self.module._validate_task_result(wrong, contract.schema, rates=rates)

    def test_rejects_judge_rejected_or_invalid_sample(self):
        contract = self.module._read_recipe_contract(RECIPE)
        rates = {
            "generator": (self.module.Decimal("1"), self.module.Decimal("4")),
            "judge": (self.module.Decimal("1"), self.module.Decimal("4")),
        }
        rejected = json.loads(json.dumps(_FakeBrokerClient.result))
        rejected["generated_items"][0]["metadata"]["judge_accepted"] = False
        rejected["metrics"]["valid"] = 0.0
        rejected["reason_code"] = "judge_rejected"
        with self.assertRaisesRegex(RuntimeError, "not accepted"):
            self.module._validate_task_result(rejected, contract.schema, rates=rates)

        invalid = json.loads(json.dumps(_FakeBrokerClient.result))
        invalid["metrics"]["valid"] = 0.0
        with self.assertRaisesRegex(RuntimeError, "not valid"):
            self.module._validate_task_result(invalid, contract.schema, rates=rates)

    def test_rejects_non_private_broker_token_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            token_file = Path(temporary) / "broker.token"
            token_file.write_text("broker-secret")
            token_file.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "mode-0600"):
                self.module._read_owned_token(token_file)

    def test_static_routes_delegate_credentials_to_broker_and_recipe(self):
        canary_source = SCRIPT.read_text()
        recipe_source = (RECIPE / "recipe" / "task.py").read_text()
        self.assertIn('"model_backed": True', canary_source)
        self.assertIn("ram-inference-gateway.ingress.fair-cw-use2-1", canary_source)
        self.assertNotIn('"MODEL_API_KEY":', canary_source)
        self.assertIn('headers = {"X-Deployment-Id": deployment}', recipe_source)
        self.assertIn('headers["Host"] = host_header', recipe_source)
        self.assertIn('_required_env("MODEL_API_KEY")', recipe_source)


if __name__ == "__main__":
    unittest.main()
