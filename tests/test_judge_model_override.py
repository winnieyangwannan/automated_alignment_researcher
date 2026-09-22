"""Judge-model precedence tests for evaluator benchmark construction."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from aar.eval_pod import judges, run_eval


class JudgeModelOverrideTest(unittest.TestCase):
    def test_explicit_judge_model_overrides_plugin_default(self):
        for plugin_model in ("gpt-4", "gpt-4o"):
            with self.subTest(plugin_model=plugin_model):
                sentinel = object()
                env = {
                    "OAI_API": "test-key",
                    "JUDGE_BACKEND": "openai",
                    "JUDGE_MODEL": "gpt-5.6-luna",
                }
                with (
                    mock.patch.dict(os.environ, env, clear=True),
                    mock.patch.object(
                        judges, "make_openai_judge", return_value=sentinel
                    ) as make,
                ):
                    self.assertIs(run_eval._resolve_judge_fn(plugin_model), sentinel)
                    make.assert_called_once_with(model="gpt-5.6-luna")

    def test_plugin_judge_model_is_preserved_when_override_unset(self):
        for plugin_model in ("gpt-4", "gpt-4o"):
            with self.subTest(plugin_model=plugin_model):
                sentinel = object()
                env = {"OPENAI_API_KEY": "test-key", "JUDGE_BACKEND": "openai"}
                with (
                    mock.patch.dict(os.environ, env, clear=True),
                    mock.patch.object(
                        judges, "make_openai_judge", return_value=sentinel
                    ) as make,
                ):
                    self.assertIs(run_eval._resolve_judge_fn(plugin_model), sentinel)
                    make.assert_called_once_with(model=plugin_model)

    def test_openai_judge_uses_fallback_when_no_models_are_configured(self):
        env = {"OAI_API": "test-key", "JUDGE_BACKEND": "openai"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(judges, "make_openai_judge") as make,
        ):
            run_eval._resolve_judge_fn()
            make.assert_called_once_with(model="gpt-4o")

    def test_model_api_backend_uses_explicit_opus_model(self):
        sentinel = object()
        env = {
            "MODEL_API_KEY": "test-key",
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
