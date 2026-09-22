"""Mocked tests for FAIR Model API judge compatibility."""

from __future__ import annotations

import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest import mock

from aar.benchmarks import _judge_http
from aar.benchmarks.deceptionbench import benchmark as deceptionbench
from aar.benchmarks.mask import benchmark as mask_benchmark
from aar.eval_pod import judges, run_eval
from aar.web_ui.backend import eval_orchestration


class _Response:
    def __init__(self, body):
        self._body = body
        self.status_code = 200
        self.headers = {}

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


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

    def test_explicit_model_api_judge_uses_opus_even_with_openai_key(self):
        response = _Response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "YES"}],
                    }
                ]
            }
        )
        client = _Client(response)
        env = {
            "MODEL_API_KEY": "model-api-test-key",
            "OAI_API": "openai-test-key",
            "JUDGE_BACKEND": "model_api",
            "JUDGE_MODEL": "claude-4-8-opus",
        }

        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("httpx.Client", return_value=client),
        ):
            judge = judges.make_model_api_judge(model="claude-4-8-opus")
            self.assertTrue(judge("grade this"))

        self.assertEqual(client.calls[0][0], "https://api.meta.ai/v1/responses")
        request = client.calls[0][1]
        self.assertEqual(
            request["headers"]["Authorization"], "Bearer model-api-test-key"
        )
        self.assertEqual(request["json"]["model"], "claude-4-8-opus")
        self.assertIn("Respond with ONLY 'YES'", request["json"]["input"])

    def test_model_api_chat_flattens_roles_into_responses_input(self):
        response = _Response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "A"}],
                    }
                ]
            }
        )
        client = _Client(response)
        with (
            mock.patch.dict(
                os.environ, {"MODEL_API_KEY": "model-api-test-key"}, clear=True
            ),
            mock.patch("httpx.Client", return_value=client),
        ):
            output = _judge_http.model_api_chat(
                [
                    {"role": "system", "content": "system text"},
                    {"role": "user", "content": "user text"},
                ],
                model="claude-4-8-opus",
                max_tokens=500,
            )

        self.assertEqual(output, "A")
        payload = client.calls[0][1]["json"]
        self.assertEqual(payload["model"], "claude-4-8-opus")
        self.assertEqual(payload["max_output_tokens"], 500)
        self.assertNotIn("temperature", payload)
        self.assertIn("SYSTEM:\nsystem text", payload["input"])
        self.assertIn("USER:\nuser text", payload["input"])

    def test_mask_routes_model_api_backend_to_opus(self):
        with (
            mock.patch.dict(
                os.environ,
                {
                    "MODEL_API_KEY": "model-api-test-key",
                    "JUDGE_BACKEND": "model_api",
                    "MASK_JUDGE_MODEL": "claude-4-8-opus",
                },
                clear=True,
            ),
            mock.patch.object(
                _judge_http, "model_api_chat", return_value="**Answer: A**"
            ) as call,
        ):
            judge = mask_benchmark.get_mask_judge()
            self.assertEqual(judge("grade this"), "A")
        self.assertEqual(call.call_args.kwargs["model"], "claude-4-8-opus")

    def test_deceptionbench_routes_model_api_backend_to_opus(self):
        with (
            mock.patch.dict(
                os.environ,
                {
                    "MODEL_API_KEY": "model-api-test-key",
                    "JUDGE_MODEL": "claude-4-8-opus",
                },
                clear=True,
            ),
            mock.patch.object(
                _judge_http, "model_api_chat", return_value='{"answer": "ok"}'
            ) as call,
        ):
            self.assertEqual(
                deceptionbench._model_api_generate("grade this"),
                '{"answer": "ok"}',
            )
        self.assertEqual(call.call_args.kwargs["model"], "claude-4-8-opus")

    def test_evaluator_explicit_model_api_backend(self):
        sentinel = object()
        env = {
            "MODEL_API_KEY": "model-api-test-key",
            "OAI_API": "stale-openai-key",
            "JUDGE_BACKEND": "model_api",
            "JUDGE_MODEL": "claude-4-8-opus",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(
                judges, "make_model_api_judge", return_value=sentinel
            ) as make,
        ):
            self.assertIs(run_eval._resolve_judge_fn("gpt-4o"), sentinel)
            make.assert_called_once_with(model="claude-4-8-opus")

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
