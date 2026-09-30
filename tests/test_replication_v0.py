from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from aar import transport
from aar.eval_pod.models import split_reasoning_and_answer_text
from aar.infrastructure.serve_v2 import chat_completion
from replication.preflight_v0 import require_positive_budget


ROOT = Path(__file__).resolve().parents[1]


class ThinkingParserTests(unittest.TestCase):
    def test_gemma_thought_channel_is_not_returned_as_answer(self) -> None:
        reasoning, answer = split_reasoning_and_answer_text(
            "<|channel>thought\nAdd 17 and 19.<channel|>36<turn|>"
        )
        self.assertEqual(reasoning, "Add 17 and 19.")
        self.assertEqual(answer, "36")

    def test_plain_model_answer_is_unchanged(self) -> None:
        self.assertEqual(split_reasoning_and_answer_text("plain answer"), ("", "plain answer"))

    def test_serve_client_returns_separate_reasoning_and_answer(self) -> None:
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self):
                return json.dumps({
                    "model": "gemma-4-31B-it",
                    "choices": [{
                        "finish_reason": "stop",
                        "message": {"content": "<|channel>thought\nmath<channel|>36"},
                    }],
                }).encode()

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "proxy_info.json").write_text(json.dumps({
                "url": "http://serve.invalid",
                "api_key": "not-logged",
                "model": "gemma-4-31B-it",
            }))
            with mock.patch("urllib.request.urlopen", return_value=Response()):
                result = chat_completion(
                    [{"role": "user", "content": "17+19"}], deployment_dir=tmp
                )
        self.assertEqual(result["reasoning"], "math")
        self.assertEqual(result["answer"], "36")


class ReplicationConfigurationTests(unittest.TestCase):
    def test_paid_preflight_requires_positive_numeric_cap(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, "positive numeric"):
                require_positive_budget("AAR_CLAUDE_SPEND_CAP_USD")
        with mock.patch.dict(
            os.environ, {"AAR_CLAUDE_SPEND_CAP_USD": "250.00"}, clear=True
        ):
            self.assertEqual(
                require_positive_budget("AAR_CLAUDE_SPEND_CAP_USD"), "250.00"
            )

    def test_gemma4_model_alias(self) -> None:
        output = subprocess.check_output(
            ["bash", "-c", ". scripts/models.sh; resolve_model gemma4_31b"],
            cwd=ROOT,
            text=True,
        ).strip()
        self.assertEqual(output, "google/gemma-4-31B-it")

    def test_run_specific_prompt_baselines_hide_heldout_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "baselines.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "publish_suite.py"),
                    "--suite", "sycophancy",
                    "--target-model", "google/gemma-4-31B-it",
                    "--emit-prompt-baselines", str(output),
                    "--only", "sycophancy_eval", "sycon_fp", "mmlu", "gsm8k", "ifeval",
                ],
                cwd=ROOT,
                check=True,
            )
            table = json.loads(output.read_text())
        self.assertEqual(set(table), {"sycophancy_eval", "mmlu", "gsm8k", "ifeval"})

    def test_adapter_only_submission_rejects_full_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "config.json").write_text("{}")
            (path / "model.safetensors").write_bytes(b"weights")
            (path / "tokenizer_config.json").write_text("{}")
            (path / "tokenizer.json").write_text("{}")
            with mock.patch.dict(os.environ, {"AAR_REQUIRE_ADAPTER": "1"}):
                with self.assertRaisesRegex(ValueError, "requires a PEFT adapter"):
                    transport.validate_model_submission(str(path))


if __name__ == "__main__":
    unittest.main()
