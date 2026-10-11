from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import warnings
from unittest import mock

from aar import transport
from aar.benchmarks.deceptionbench.benchmark import (
    DECEPTIONBENCH_GENERATION_TOKEN_BUDGET,
)
from aar.benchmarks.mask.benchmark import MASK_GENERATION_TOKEN_BUDGET
from aar.benchmarks.base import BenchmarkSpec
from aar.eval_pod.models import (
    HFModel,
    _resolve_context_window,
    split_reasoning_and_answer_text,
)
from aar.eval_pod.run_eval import (
    _health_snapshot,
    _run_override,
    _validate_evaluation_health,
)
from aar.infrastructure.serve_v2 import chat_completion
from replication.preflight_v0 import (
    require_judge_configuration,
    require_positive_budget,
    smoke_model_api_judge,
)


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
            with mock.patch(
                "urllib.request.urlopen", return_value=Response()
            ) as urlopen:
                result = chat_completion(
                    [{"role": "user", "content": "17+19"}], deployment_dir=tmp
                )
        self.assertEqual(result["reasoning"], "math")
        self.assertEqual(result["answer"], "36")
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertNotIn("max_tokens", body)

    def test_serve_client_preserves_explicit_positive_completion_budget(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self):
                return json.dumps({
                    "choices": [{
                        "finish_reason": "stop",
                        "message": {
                            "content": "<|channel>thought\nmath<channel|>36"
                        },
                    }],
                }).encode()

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "proxy_info.json").write_text(json.dumps({
                "url": "http://serve.invalid",
                "api_key": "not-logged",
                "model": "gemma-4-31B-it",
            }))
            with mock.patch(
                "urllib.request.urlopen", return_value=Response()
            ) as urlopen:
                chat_completion(
                    [{"role": "user", "content": "17+19"}],
                    deployment_dir=tmp,
                    max_tokens=8192,
                )
        request = urlopen.call_args.args[0]
        self.assertEqual(json.loads(request.data)["max_tokens"], 8192)

    def test_serve_client_rejects_invalid_explicit_completion_budget(self) -> None:
        for invalid in (0, -1, True, 1.5):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "positive integer or None"
            ):
                chat_completion([], deployment_dir="unused", max_tokens=invalid)

    def test_serve_client_enforces_required_target_thinking(self) -> None:
        with mock.patch.dict(
            os.environ, {"AAR_TARGET_ENABLE_THINKING": "1"}, clear=False
        ):
            with self.assertRaisesRegex(
                ValueError, "requires enable_thinking=True"
            ):
                chat_completion(
                    [], deployment_dir="unused", enable_thinking=False
                )

    def test_serve_client_allows_disabled_thinking_when_not_required(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self):
                return json.dumps({
                    "choices": [{
                        "finish_reason": "stop",
                        "message": {"content": "36"},
                    }],
                }).encode()

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "proxy_info.json").write_text(json.dumps({
                "url": "http://serve.invalid",
                "api_key": "not-logged",
                "model": "gemma-4-31B-it",
            }))
            with (
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch("urllib.request.urlopen", return_value=Response()),
            ):
                result = chat_completion(
                    [], deployment_dir=tmp, enable_thinking=False
                )
        self.assertEqual(result["answer"], "36")

    def test_serve_client_rejects_invalid_required_thinking_env(self) -> None:
        with mock.patch.dict(
            os.environ, {"AAR_TARGET_ENABLE_THINKING": "sometimes"}, clear=False
        ):
            with self.assertRaisesRegex(ValueError, "must be a boolean value"):
                chat_completion([], deployment_dir="unused")

    def test_serve_client_rejects_non_boolean_thinking_flag(self) -> None:
        with self.assertRaisesRegex(ValueError, "enable_thinking must be a bool"):
            chat_completion([], deployment_dir="unused", enable_thinking="yes")

    def test_serve_client_rejects_length_truncated_completion(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self):
                return json.dumps({
                    "choices": [{
                        "finish_reason": "length",
                        "message": {"content": "unfinished"},
                    }],
                }).encode()

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "proxy_info.json").write_text(json.dumps({
                "url": "http://serve.invalid",
                "api_key": "not-logged",
                "model": "gemma-4-31B-it",
            }))
            with (
                mock.patch("urllib.request.urlopen", return_value=Response()),
                self.assertRaisesRegex(RuntimeError, "did not stop cleanly: 'length'"),
            ):
                chat_completion([], deployment_dir=tmp)

    def test_nested_text_config_context_precedes_tokenizer_fallback(self) -> None:
        config = SimpleNamespace(
            max_position_embeddings=None,
            text_config=SimpleNamespace(max_position_embeddings=262144),
        )
        tokenizer = SimpleNamespace(model_max_length=4096)
        self.assertEqual(_resolve_context_window(config, tokenizer), 262144)
        model = object.__new__(HFModel)
        model.max_new_tokens = None
        model._ctx = _resolve_context_window(config, tokenizer)
        model._auto_ceiling = 8192
        self.assertEqual(model._budget(input_len=96), 8192)

    def test_top_level_context_still_takes_priority(self) -> None:
        config = SimpleNamespace(
            max_position_embeddings=131072,
            text_config=SimpleNamespace(max_position_embeddings=262144),
        )
        tokenizer = SimpleNamespace(model_max_length=4096)
        self.assertEqual(_resolve_context_window(config, tokenizer), 131072)


class ReplicationConfigurationTests(unittest.TestCase):
    def test_honesty_target_generation_budgets_are_8192(self) -> None:
        self.assertEqual(MASK_GENERATION_TOKEN_BUDGET, 8192)
        self.assertEqual(DECEPTIONBENCH_GENERATION_TOKEN_BUDGET, 8192)

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

    def test_replication_env_pins_model_api_judge_and_batch(self) -> None:
        output = subprocess.check_output(
            [
                "env",
                "-u", "AAR_RUNTIME_ROOT",
                "bash",
                "-c",
                ". replication/env_v0.sh; printf '%s|%s|%s|%s|%s|%s|%s|%s' "
                '"$AAR_EXPECTED_BRANCH" "$JUDGE_BACKEND" "$JUDGE_MODEL" '
                '"$EVAL_RUN_BATCH" "$EVAL_RUN_GEN_CEILING" '
                '"$EVAL_RUN_GEN_CEILING_BENCHMARKS" '
                '"${OAI_API:-}${OPENAI_API_KEY:-}" '
                '"$AAR_RUNTIME_ROOT"',
            ],
            cwd=ROOT,
            text=True,
        )
        self.assertEqual(
            output,
            f"uv|model_api|gpt-5-6-luna|2|8192|"
            f"sycophancy_eval sycon_fp gsm8k ifeval||"
            f"/checkpoint/ram/aar/{os.environ['USER']}/sycophancy-gemma4-31b-single-v0",
        )

    def test_replication_env_preserves_scoped_attempt_root(self) -> None:
        selected = "/checkpoint/ram/aar/test/baseline_attempts/attempt-1"
        output = subprocess.check_output(
            [
                "env", f"AAR_RUNTIME_ROOT={selected}", "bash", "-c",
                ". replication/env_v0.sh; printf '%s|%s|%s' "
                '"$AAR_RUNTIME_ROOT" "$AAR_BASELINE_OVERRIDES" "$HOLDOUT_DIR"',
            ],
            cwd=ROOT,
            text=True,
        )
        self.assertEqual(
            output,
            f"{selected}|{selected}/metadata/gemma4_31b_baseline.json|"
            f"{selected}/eval/holdout/gemma4_31b",
        )

    def test_full_baseline_uses_fresh_retained_attempt_and_pinned_job(self) -> None:
        launcher = (ROOT / "replication" / "submit_baseline_v0.sh").read_text()
        job = (ROOT / "replication" / "baseline_v0.sbatch").read_text()
        self.assertIn('attempt_parent="${AAR_RUNTIME_BASE}/baseline_attempts"', launcher)
        self.assertIn('if ! mkdir "${attempt_dir}"', launcher)
        self.assertIn("/checkpoint/*", launcher)
        self.assertIn('source "${AAR_REPO}/.venv/bin/activate"', launcher)
        self.assertIn('--only sycophancy_eval sycon_fp mmlu gsm8k ifeval', job)
        self.assertIn('printf \'export AAR_RUNTIME_ROOT=%q\\n\'', launcher)
        self.assertIn('--output="${AAR_RUNTIME_ROOT}/logs/baseline-%j.out"', launcher)
        self.assertIn("--judge-smoke-only", job)
        self.assertIn('source "${REPO}/.venv/bin/activate"', job)
        self.assertIn('EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:', job)
        self.assertIn('"${EVAL_RUN_BATCH}" = 2', job)
        self.assertIn('"${EVAL_RUN_GEN_CEILING}" = 8192', job)
        self.assertIn("refusing to reuse baseline attempt", job)

    def test_two_iteration_launcher_is_attempt_bound_and_fail_closed(self) -> None:
        launcher = (ROOT / "replication" / "launch_two_iteration_v0.sh").read_text()
        self.assertIn(': "${AAR_CLAUDE_SPEND_CAP_USD:', launcher)
        self.assertIn(': "${AAR_GPT_JUDGE_SPEND_CAP_USD:', launcher)
        self.assertNotIn("AAR_CLAUDE_SPEND_CAP_USD=100", launcher)
        self.assertNotIn("AAR_GPT_JUDGE_SPEND_CAP_USD=100", launcher)
        self.assertIn('source "${attempt_env}"', launcher)
        self.assertLess(
            launcher.index('source "${attempt_env}"'),
            launcher.index('source "${SCRIPT_DIR}/env_v0.sh"'),
        )
        self.assertIn("manifest-baseline.json", launcher)
        self.assertIn('submit_preflights_v0.sh" --include-web', launcher)
        for marker in ("environment.ok", "gpu.ok", "evaluator_gpu.ok", "web.ok"):
            self.assertIn(marker, launcher)
        self.assertIn(
            "export AAR_TEAM_ID=sycophancy-gemma4_31b-opus48-twoiter-v0",
            launcher,
        )
        self.assertIn('launch_team.sh" "pilot" 2 12', launcher)
        self.assertIn("--phase two-iteration-pilot", launcher)

    def test_gpu_canary_is_small_retained_and_uses_production_preflight(self) -> None:
        job = (ROOT / "replication" / "gpu_canary_v0.sbatch").read_text()
        launcher = (ROOT / "replication" / "submit_gpu_canary_v0.sh").read_text()
        self.assertIn("#SBATCH --gpus=1", job)
        self.assertIn('"${EVAL_RUN_BATCH}" = 2', job)
        self.assertIn('"${EVAL_RUN_GEN_CEILING}" = 8192', job)
        self.assertNotIn("export EVAL_RUN_BATCH=2", job)
        self.assertIn("--judge-smoke-only", job)
        self.assertIn("--only sycophancy_eval", job)
        self.assertIn("--force-n 20", job)
        self.assertIn('benchmarks[0]["subset_size"] == 20', job)
        self.assertIn('benchmark["n"] == 20', job)
        self.assertIn("/checkpoint/*", launcher)
        self.assertIn('if ! mkdir "${attempt_dir}"', launcher)
        self.assertIn("--output=\"${attempt_dir}/slurm-%j.out\"", launcher)

    def test_judge_configuration_rejects_public_openai_route(self) -> None:
        env = {
            "JUDGE_BACKEND": "model_api",
            "JUDGE_MODEL": "gpt-5-6-luna",
            "MODEL_API_KEY": "model-api-key",
            "OAI_API": "stale-public-key",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(SystemExit, "public OpenAI"):
                require_judge_configuration()

    def test_live_judge_smoke_requires_completed_canonical_response(self) -> None:
        calls = []

        def fake_call(url, key, path, body):
            calls.append((url, key, path, body))
            return {
                "status": "completed",
                "model": "gpt-5-6-luna",
                "output": [{
                    "type": "message",
                    "content": [{"type": "output_text", "text": "JUDGE_SMOKE_OK"}],
                }],
            }

        env = {
            "JUDGE_BACKEND": "model_api",
            "JUDGE_MODEL": "gpt-5-6-luna",
            "MODEL_API_KEY": "model-api-key",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            result = smoke_model_api_judge(fake_call)
        self.assertEqual(result["model"], "gpt-5-6-luna")
        self.assertEqual(calls[0][0:3], ("https://api.meta.ai", "model-api-key", "/v1/responses"))
        self.assertEqual(calls[0][3]["model"], "gpt-5-6-luna")

    def test_run_override_wins_over_golden_batch(self) -> None:
        spec = BenchmarkSpec(
            name="sycophancy_eval",
            category="judge",
            id="sycophancy_eval",
        )
        with mock.patch.dict(os.environ, {"EVAL_RUN_BATCH": "2"}, clear=True):
            self.assertEqual(_run_override(spec, {"batch_size": 32})["batch_size"], 2)

    def test_candidate_evaluator_defaults_and_composed_override_are_pinned(self) -> None:
        expected_batches = {
            "sycophancy": 8,
            "honesty": 32,
            "honesty_sycophancy": 4,
            "honesty_sycophancy_concealing_uncertainty": 4,
        }
        for name in ("eval_worker.sh", "eval_job.sh"):
            evaluator = (ROOT / "scripts" / name).read_text()
            for suite, batch in expected_batches.items():
                self.assertRegex(
                    evaluator,
                    rf'{suite}\)\s+export EVAL_BATCH_SIZE='
                    rf'"\$\{{EVAL_BATCH_SIZE:-{batch}\}}"',
                )

        honesty = (ROOT / "scripts" / "baseline_honesty.sh").read_text()
        self.assertIn("export EVAL_BATCH_SIZE=32", honesty)
        composed = (ROOT / "replication" / "env_multidimensional.sh").read_text()
        self.assertIn("export EVAL_RUN_BATCH=2", composed)

    def test_run_override_raises_replication_generation_ceilings(self) -> None:
        freeform = BenchmarkSpec(
            name="sycophancy_eval",
            category="judge",
            id="sycophancy_eval",
        )
        trajectory = BenchmarkSpec(
            name="sycon_fp",
            category="judge",
            id="sycon_fp",
        )
        gsm8k = BenchmarkSpec(name="gsm8k", category="rule", id="gsm8k")
        ifeval = BenchmarkSpec(name="ifeval", category="rule", id="ifeval")
        mmlu = BenchmarkSpec(name="mmlu", category="logprob", id="mmlu")
        env = {
            "EVAL_RUN_GEN_CEILING": "8192",
            "EVAL_RUN_GEN_CEILING_BENCHMARKS": (
                "sycophancy_eval sycon_fp gsm8k ifeval"
            ),
        }
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                _run_override(
                    freeform, {"auto_ceiling": 1024, "max_new_tokens": 1024}
                )["auto_ceiling"],
                8192,
            )
            self.assertIsNone(
                _run_override(
                    freeform, {"auto_ceiling": 1024, "max_new_tokens": 1024}
                )["max_new_tokens"]
            )
            self.assertEqual(
                _run_override(trajectory, {"auto_ceiling": 4096})["auto_ceiling"],
                8192,
            )
            self.assertEqual(
                _run_override(gsm8k, {"auto_ceiling": 4096})["auto_ceiling"],
                8192,
            )
            self.assertEqual(
                _run_override(ifeval, {"auto_ceiling": 4096})["auto_ceiling"],
                8192,
            )
            self.assertEqual(
                _run_override(mmlu, {"auto_ceiling": 4096})["auto_ceiling"],
                4096,
            )

    def test_health_gate_rejects_abnormal_truncation(self) -> None:
        class FakeModel:
            health = {
                "generated": 100,
                "truncated": 10,
                "allocator_warnings": 0,
                "ooms": 0,
            }

            def evaluation_health(self):
                return self.health

        model = FakeModel()
        before = {name: 0 for name in model.health}
        env = {
            "EVAL_MAX_TRUNCATION_RATE": "0.05",
            "EVAL_TRUNCATION_MIN_COMPLETIONS": "20",
            "EVAL_FAIL_ON_ALLOCATOR_WARNING": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "truncation rate"):
                _validate_evaluation_health(model, before, "sycophancy_eval")
        self.assertEqual(_health_snapshot(model)["generated"], 100)

    def test_health_gate_rejects_allocator_warning(self) -> None:
        class FakeModel:
            def evaluation_health(self):
                return {
                    "generated": 4,
                    "truncated": 0,
                    "allocator_warnings": 1,
                    "ooms": 0,
                }

        env = {
            "EVAL_FAIL_ON_ALLOCATOR_WARNING": "1",
            "EVAL_MAX_TRUNCATION_RATE": "0.05",
            "EVAL_TRUNCATION_MIN_COMPLETIONS": "20",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "allocator warning"):
                _validate_evaluation_health(FakeModel(), {}, "ifeval")

    def test_hf_generation_records_allocator_warning(self) -> None:
        class FakeOOM(RuntimeError):
            pass

        class Generator:
            @staticmethod
            def generate(**_kwargs):
                warnings.warn("CUDA allocator could not expand a segment", RuntimeWarning)
                return "generated"

        model = object.__new__(HFModel)
        model.model = Generator()
        model._torch = type("Torch", (), {"cuda": type("Cuda", (), {"OutOfMemoryError": FakeOOM})})
        model._allocator_warning_count = 0
        model._oom_count = 0
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            self.assertEqual(model._tracked_generate(), "generated")
        self.assertEqual(model._allocator_warning_count, 1)

    def test_run_specific_prompt_baselines_hide_heldout_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "baselines.json"
            env = os.environ.copy()
            env.pop("AAR_BASELINE_OVERRIDES", None)
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
                env=env,
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
