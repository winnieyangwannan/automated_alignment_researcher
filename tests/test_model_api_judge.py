"""Mocked tests for FAIR Model API judge compatibility."""

from __future__ import annotations

import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest import mock

from aar.eval_pod import judges, run_eval
from aar.web_ui.backend import eval_orchestration


class _Response:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


class _Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class ModelApiJudgeTest(unittest.TestCase):
    @staticmethod
    def _fake_runpod(response):
        module = ModuleType("aar.infrastructure.runpod")
        module.deploy_pod = mock.Mock(return_value=response)
        package = ModuleType("aar.infrastructure")
        package.runpod = module
        modules = {
            "aar.infrastructure": package,
            "aar.infrastructure.runpod": module,
        }
        return module, mock.patch.dict(sys.modules, modules)

    def test_model_api_uses_responses_shape_and_normalizes_luna_name(self):
        response = _Response(
            {
                "output": [
                    {"type": "reasoning", "summary": []},
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "YES"}],
                    },
                ]
            }
        )
        client = _Client(response)
        env = {"MODEL_API_KEY": "model-api-test-key"}

        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("httpx.Client", return_value=client),
        ):
            judge = judges.make_openai_judge(model="gpt-5.6-luna")
            self.assertTrue(judge("grade this"))

        self.assertEqual(client.calls[0][0], "https://api.meta.ai/v1/responses")
        request = client.calls[0][1]
        self.assertEqual(
            request["headers"]["Authorization"], "Bearer model-api-test-key"
        )
        self.assertEqual(request["json"]["model"], "gpt-5-6-luna")
        self.assertIn("Respond with ONLY 'YES'", request["json"]["input"])
        self.assertEqual(request["json"]["max_output_tokens"], 256)
        self.assertNotIn("messages", request["json"])

    def test_public_openai_behavior_wins_when_both_keys_exist(self):
        response = _Response({"choices": [{"message": {"content": "NO"}}]})
        client = _Client(response)
        env = {
            "OAI_API": "openai-test-key",
            "MODEL_API_KEY": "model-api-test-key",
        }

        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("httpx.Client", return_value=client),
        ):
            judge = judges.make_openai_judge(model="gpt-5.6-luna")
            self.assertFalse(judge("grade this"))

        self.assertEqual(
            client.calls[0][0], "https://api.openai.com/v1/chat/completions"
        )
        request = client.calls[0][1]
        self.assertEqual(request["headers"]["Authorization"], "Bearer openai-test-key")
        self.assertEqual(request["json"]["model"], "gpt-5.6-luna")
        self.assertIn("messages", request["json"])
        self.assertNotIn("input", request["json"])

    def test_evaluator_detects_model_api_key(self):
        sentinel = object()
        env = {
            "MODEL_API_KEY": "model-api-test-key",
            "JUDGE_MODEL": "gpt-5.6-luna",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(
                judges, "make_openai_judge", return_value=sentinel
            ) as make,
        ):
            self.assertIs(run_eval._resolve_judge_fn("gpt-4"), sentinel)
            make.assert_called_once_with(model="gpt-5.6-luna")

    def test_slurm_submission_explicitly_exports_caller_environment(self):
        completed = SimpleNamespace(stdout="12345\n")
        with mock.patch.object(
            eval_orchestration.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(
                eval_orchestration._spawn_fs("smoke", "sycophancy"),
                "slurm:12345",
            )

        command = run.call_args.args[0]
        self.assertIn("--export=ALL", command)

    def test_s3_pod_receives_model_api_configuration(self):
        response = {"id": "pod-1"}
        runpod, runpod_modules = self._fake_runpod(response)
        overrides = {
            "MODEL_API_KEY": "model-api-test-key",
            "OAI_API_KEY": "",
            "JUDGE_MODEL_OVERRIDE": "gpt-5.6-luna",
        }
        with (
            runpod_modules,
            mock.patch.multiple(eval_orchestration.config, **overrides),
        ):
            self.assertEqual(
                eval_orchestration._spawn_s3("smoke", "sycophancy"),
                "pod:pod-1",
            )

        env = runpod.deploy_pod.call_args.kwargs["env_vars"]
        self.assertEqual(env["MODEL_API_KEY"], "model-api-test-key")
        self.assertEqual(env["JUDGE_MODEL"], "gpt-5.6-luna")
        self.assertNotIn("OAI_API", env)

    def test_s3_pod_does_not_export_default_judge_model_as_override(self):
        runpod, runpod_modules = self._fake_runpod({"id": "pod-1"})
        overrides = {
            "MODEL_API_KEY": "model-api-test-key",
            "OAI_API_KEY": "",
            "JUDGE_MODEL": "gpt-4o",
            "JUDGE_MODEL_OVERRIDE": "",
        }
        with (
            runpod_modules,
            mock.patch.multiple(eval_orchestration.config, **overrides),
        ):
            eval_orchestration._spawn_s3("smoke", "sycophancy")

        env = runpod.deploy_pod.call_args.kwargs["env_vars"]
        self.assertEqual(env["MODEL_API_KEY"], "model-api-test-key")
        self.assertNotIn("JUDGE_MODEL", env)
