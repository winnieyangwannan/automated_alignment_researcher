"""Tests for the fail-closed generated-method contract proof."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.validate_method_contract import (
    _autodata_loader_errors,
    _undefined_name_errors,
    _unsafe_training_api_errors,
)


class ValidateMethodContractTest(unittest.TestCase):
    def test_training_submission_runs_contract_guard_before_sbatch(self) -> None:
        submitter = (
            Path(__file__).resolve().parents[1] / "scripts" / "submit_train_job.sh"
        ).read_text()

        self.assertLess(
            submitter.index('"${REPO}/scripts/validate_method_contract.py"'),
            submitter.index("sbatch --parsable"),
        )

    def test_autodata_loader_gate_matches_native_proposal_contract(self) -> None:
        missing = _autodata_loader_errors(ast.parse("items = json.load(handle)"))
        self.assertIn("load_autodata_campaign_datasets", missing[0])

        valid = _autodata_loader_errors(
            ast.parse(
                """
run_id = os.environ["AAR_CURRENT_RUN_ID"]
team_dir = os.environ["TEAM_DIR"]
handoff_name = "training-handoff.json"
contract_name = "autodata-training-data-contract.json"
dataset_key = "dataset"
execution_key = "production_execution_id"
receipt_name = "training-consumption.json"
production_execution_id = handoff["production_execution_id"]
items = load_autodata_campaign_datasets(
    [production_dataset_path],
    receipt_path=training_consumption_path,
    required_rows=1000,
    expected_execution_ids=[production_execution_id],
    judge_rubric=training_data_contract["judge_rubric"],
    training_objective="sft",
)
"""
            )
        )
        self.assertEqual(valid, [])

        swallowed = _autodata_loader_errors(
            ast.parse(
                """
run_id = os.environ["AAR_CURRENT_RUN_ID"]
team_dir = os.environ["TEAM_DIR"]
names = (
    "training-handoff.json",
    "autodata-training-data-contract.json",
    "dataset",
    "production_execution_id",
    "training-consumption.json",
)
production_execution_id = handoff["production_execution_id"]
try:
    items = load_autodata_campaign_datasets(
        [production_dataset_path],
        receipt_path=training_consumption_path,
        required_rows=1000,
        expected_execution_ids=[production_execution_id],
        judge_rubric=training_data_contract["judge_rubric"],
        training_objective="sft",
    )
except Exception:
    items = fallback_rows
"""
            )
        )
        self.assertIn("may not be swallowed", swallowed[0])

        empty_execution_ids = _autodata_loader_errors(
            ast.parse(
                """
items = load_autodata_campaign_datasets(
    [production_dataset_path],
    receipt_path=training_consumption_path,
    required_rows=1000,
    expected_execution_ids=[],
    judge_rubric=training_data_contract["judge_rubric"],
    training_objective="sft",
)
"""
            )
        )
        self.assertIn("exactly one production execution ID", empty_execution_ids[0])

        placeholder_execution_id = _autodata_loader_errors(
            ast.parse(
                """
names = ("AAR_CURRENT_RUN_ID", "TEAM_DIR", "training-handoff.json",
         "autodata-training-data-contract.json", "dataset",
         "production_execution_id", "training-consumption.json")
production_execution_id = "production_placeholder"
items = load_autodata_campaign_datasets(
    [production_dataset_path],
    receipt_path=training_consumption_path,
    required_rows=1000,
    expected_execution_ids=[production_execution_id],
    judge_rubric=training_data_contract["judge_rubric"],
    training_objective="sft",
)
"""
            )
        )
        self.assertIn("placeholders", placeholder_execution_id[0])

    def test_rejects_observed_target_runtime_failures_before_gpu(self) -> None:
        tree = ast.parse(
            """
from trl import DataCollatorForCompletionOnlyLM

def load_teacher():
    return Model.from_pretrained('teacher')

for item in records:
    load_teacher()

DPOTrainer(model=model)
SFTTrainer(model=model, tokenizer=tokenizer)
trainer.train(max_steps=1)
chosen = torch.tensor(batch['chosen_input_ids'])
"""
        )
        errors = _unsafe_training_api_errors(tree)

        self.assertEqual(len(errors), 6)
        self.assertTrue(
            any("DataCollatorForCompletionOnlyLM" in error for error in errors)
        )
        self.assertTrue(any("DPOTrainer" in error for error in errors))
        self.assertTrue(any("SFTTrainer(tokenizer" in error for error in errors))
        self.assertTrue(any("Trainer.train(max_steps" in error for error in errors))
        self.assertTrue(any("torch.tensor(batch" in error for error in errors))
        self.assertTrue(any("per-item loop" in error for error in errors))

    def test_rejects_removed_tokenizer_keyword_on_sfttrainer_subclass(self) -> None:
        tree = ast.parse(
            """
class CustomTrainer(SFTTrainer):
    pass

trainer = CustomTrainer(model=model, tokenizer=tokenizer)
"""
        )

        errors = _unsafe_training_api_errors(tree)

        self.assertEqual(len(errors), 1)
        self.assertIn("processing_class=tokenizer", errors[0])

    def test_rejects_seq2seq_collator_for_causal_sft(self) -> None:
        sources = [
            """
from transformers import DataCollatorForSeq2Seq

trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer,
    train_dataset=tokenized_dataset,
    data_collator=DataCollatorForSeq2Seq(tokenizer),
)
""",
            """
from transformers import DataCollatorForSeq2Seq as Seq2SeqCollator

collator = Seq2SeqCollator(tokenizer, pad_to_multiple_of=8)
trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer,
    train_dataset=tokenized_dataset,
    data_collator=collator,
)
""",
        ]

        for source in sources:
            with self.subTest(source=source):
                errors = _unsafe_training_api_errors(ast.parse(source))
                self.assertEqual(len(errors), 1)
                self.assertIn("labels=None", errors[0])
                self.assertIn("causal-LM collator", errors[0])

    def test_accepts_default_sft_causal_collator(self) -> None:
        tree = ast.parse(
            """
trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer,
    train_dataset=tokenized_dataset,
)
"""
        )

        self.assertEqual(_unsafe_training_api_errors(tree), [])

    def test_rejects_invalid_shared_chat_template_helper_calls(self) -> None:
        sources = [
            """
from aar.utils.chat_template import normalize_chat_template_ids
ids = normalize_chat_template_ids(ids, tokenizer)
""",
            """
from aar.utils.chat_template import normalize_chat_template_ids as normalize_ids
ids = normalize_ids()
""",
            """
from aar.utils import chat_template as chat_helpers
ids = chat_helpers.normalize_chat_template_ids(ids, tokenizer=tokenizer)
""",
            """
import aar.utils.chat_template
ids = aar.utils.chat_template.normalize_chat_template_ids(ids, tokenizer)
""",
        ]

        for source in sources:
            with self.subTest(source=source):
                errors = _unsafe_training_api_errors(ast.parse(source))
                self.assertEqual(len(errors), 1)
                self.assertIn("accepts exactly one argument (value)", errors[0])

    def test_accepts_valid_shared_chat_template_helper_calls(self) -> None:
        sources = [
            """
from aar.utils.chat_template import normalize_chat_template_ids
ids = normalize_chat_template_ids(ids)
""",
            """
from aar.utils.chat_template import normalize_chat_template_ids as normalize_ids
ids = normalize_ids(value=ids)
""",
            """
from aar.utils import chat_template
ids = chat_template.normalize_chat_template_ids(ids)
""",
        ]

        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(
                    _unsafe_training_api_errors(ast.parse(source)),
                    [],
                )

    def test_undefined_name_gate_reports_ruff_diagnostic(self) -> None:
        completed = subprocess.CompletedProcess(
            ["ruff"],
            1,
            "run.py:9:5: F821 Undefined name `torch`\n",
            "",
        )
        with (
            patch("scripts.validate_method_contract.shutil.which", return_value="ruff"),
            patch(
                "scripts.validate_method_contract.subprocess.run",
                return_value=completed,
            ),
        ):
            errors = _undefined_name_errors(Path("run.py"))
        self.assertEqual(len(errors), 1)
        self.assertIn("F821 Undefined name `torch`", errors[0])

    def test_rejects_trl_021_sfttrainer_constructor_keywords(self) -> None:
        tree = ast.parse(
            """
SFTTrainer(
    model=model,
    max_seq_length=2048,
    dataset_text_field="text",
)
"""
        )

        errors = _unsafe_training_api_errors(tree)

        self.assertEqual(len(errors), 1)
        self.assertIn("locked TRL 0.21", errors[0])
        self.assertIn("SFTConfig(max_length=", errors[0])

    def test_rejects_trl_021_sftconfig_and_multi_step_smoke(self) -> None:
        tree = ast.parse(
            """
max_steps = 8 if config.smoke_run else -1
SFTConfig(
    max_seq_length=2048,
    warmup_ratio=0.03,
    max_steps=max_steps,
)
"""
        )

        errors = _unsafe_training_api_errors(tree)

        self.assertEqual(len(errors), 2)
        self.assertTrue(any("use max_length and warmup_steps" in error for error in errors))
        self.assertTrue(any("must set max_steps=1, not 8" in error for error in errors))

    def test_rejects_invalid_serve_v2_call_and_silent_fallback(self) -> None:
        tree = ast.parse(
            """
def generate(model, messages):
    return chat_completion(
        model,
        messages,
        top_p=0.9,
        chat_template_kwargs={"enable_thinking": True},
    )

try:
    rows.extend(generate(model, messages))
except Exception:
    pass
"""
        )

        errors = _unsafe_training_api_errors(tree)

        self.assertEqual(len(errors), 3)
        self.assertTrue(any("exactly one positional argument" in error for error in errors))
        self.assertTrue(any("chat_template_kwargs, top_p" in error for error in errors))
        self.assertTrue(any("fail closed" in error for error in errors))

    def test_rejects_undersized_or_unverifiable_thinking_budget(self) -> None:
        sources = [
            "chat_completion(messages, enable_thinking=True, max_tokens=1024)",
            "chat_completion(messages, max_tokens=budget)",
            (
                "from aar.infrastructure.serve_v2 import chat_completion as generate\n"
                "generate(messages, enable_thinking=True, max_tokens=256)"
            ),
            (
                "from aar.infrastructure import serve_v2 as target\n"
                "target.chat_completion(messages, max_tokens=4096)"
            ),
        ]
        for source in sources:
            with self.subTest(source=source):
                errors = _unsafe_training_api_errors(ast.parse(source))
                self.assertEqual(len(errors), 1)
                self.assertIn("context-aware maximum", errors[0])
                self.assertIn("at least 8192", errors[0])

    def test_accepts_safe_supported_serve_v2_calls(self) -> None:
        sources = [
            "chat_completion(messages, model=model, enable_thinking=True)",
            "chat_completion(messages, enable_thinking=True, max_tokens=None)",
            "chat_completion(messages, enable_thinking=True, max_tokens=8192)",
            "chat_completion(messages, enable_thinking=False, max_tokens=256)",
            (
                "import aar.infrastructure.serve_v2 as target\n"
                "target.chat_completion(messages, max_tokens=32768)"
            ),
        ]
        with patch.dict("os.environ", {}, clear=True):
            for source in sources:
                with self.subTest(source=source):
                    self.assertEqual(
                        _unsafe_training_api_errors(ast.parse(source)),
                        [],
                    )

    def test_rejects_unbounded_sequential_target_generation(self) -> None:
        source = """
from aar.infrastructure.serve_v2 import chat_completion as complete

def generate(prompts, config):
    for prompt in prompts:
        for _ in range(config.n_responses_per_prompt):
            complete([{"role": "user", "content": prompt}], enable_thinking=True)
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "256"},
            clear=True,
        ):
            errors = _unsafe_training_api_errors(ast.parse(source))

        self.assertEqual(len(errors), 1)
        self.assertIn("local static bound", errors[0])
        self.assertIn("dynamic or while-loop generation", errors[0])

    def test_static_nested_target_generation_honors_configured_cap(self) -> None:
        source = """
from aar.infrastructure import serve_v2 as target

def generate(prompts):
    for prompt in prompts[:8]:
        for _ in range(4):
            target.chat_completion(
                [{"role": "user", "content": prompt}],
                enable_thinking=True,
            )
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "32"},
            clear=True,
        ):
            self.assertEqual(_unsafe_training_api_errors(ast.parse(source)), [])

        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "31"},
            clear=True,
        ):
            errors = _unsafe_training_api_errors(ast.parse(source))
        self.assertEqual(len(errors), 1)
        self.assertIn("may execute 32 times sequentially", errors[0])
        self.assertIn("bounded concurrency", errors[0])

    def test_dynamic_target_generation_comprehensions_are_rejected(self) -> None:
        expressions = (
            "[chat_completion(messages) for prompt in prompts]",
            "{chat_completion(messages) for prompt in prompts}",
            "{prompt: chat_completion(messages) for prompt in prompts}",
            "(chat_completion(messages) for prompt in prompts)",
        )
        for expression in expressions:
            with self.subTest(expression=expression), patch.dict(
                "os.environ",
                {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "256"},
                clear=True,
            ):
                errors = _unsafe_training_api_errors(ast.parse(expression))
            self.assertEqual(len(errors), 1)
            self.assertIn("local static bound", errors[0])

    def test_bounded_target_generation_comprehension_is_accepted(self) -> None:
        source = "[chat_completion(messages) for prompt in prompts[:8]]"
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "8"},
            clear=True,
        ):
            self.assertEqual(_unsafe_training_api_errors(ast.parse(source)), [])

    def test_separate_sequential_loops_are_cumulative_within_scope(self) -> None:
        source = """
for _ in range(200):
    chat_completion(messages)
for _ in range(200):
    chat_completion(messages)
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "256"},
            clear=True,
        ):
            errors = _unsafe_training_api_errors(ast.parse(source))
        self.assertEqual(len(errors), 1)
        self.assertIn("may execute 400 times sequentially", errors[0])

    def test_sequential_totals_do_not_cross_function_scopes(self) -> None:
        source = """
def generate_alpha():
    for _ in range(200):
        chat_completion(messages)

def generate_beta():
    for _ in range(200):
        chat_completion(messages)
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "256"},
            clear=True,
        ):
            self.assertEqual(_unsafe_training_api_errors(ast.parse(source)), [])

    def test_single_literal_target_generation_loop_is_accepted(self) -> None:
        source = """
from aar.infrastructure.serve_v2 import chat_completion

for _ in range(8):
    chat_completion(messages, enable_thinking=True)
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "8"},
            clear=True,
        ):
            self.assertEqual(_unsafe_training_api_errors(ast.parse(source)), [])

    def test_one_level_target_wrapper_in_dynamic_loop_is_rejected(self) -> None:
        source = """
from aar.infrastructure.serve_v2 import chat_completion

def complete_one(messages):
    return chat_completion(messages, enable_thinking=True)

for prompt in prompts:
    complete_one([{"role": "user", "content": prompt}])
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "256"},
            clear=True,
        ):
            errors = _unsafe_training_api_errors(ast.parse(source))
        self.assertEqual(len(errors), 1)
        self.assertIn("local static bound", errors[0])

    def test_one_level_target_wrapper_preserves_internal_loop_cost(self) -> None:
        source = """
from aar.infrastructure.serve_v2 import chat_completion

def complete_four(messages):
    for _ in range(4):
        chat_completion(messages, enable_thinking=True)

for prompt in prompts[:8]:
    complete_four([{"role": "user", "content": prompt}])
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "32"},
            clear=True,
        ):
            self.assertEqual(_unsafe_training_api_errors(ast.parse(source)), [])

        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "31"},
            clear=True,
        ):
            errors = _unsafe_training_api_errors(ast.parse(source))
        self.assertEqual(len(errors), 1)
        self.assertIn("may execute 32 times sequentially", errors[0])

    def test_one_level_wrapper_sums_multiple_target_call_sites(self) -> None:
        source = """
from aar.infrastructure.serve_v2 import chat_completion

def complete_pair(messages, retry):
    chat_completion(messages, enable_thinking=True)
    if retry:
        chat_completion(messages, enable_thinking=True)

for prompt in prompts[:4]:
    complete_pair([{"role": "user", "content": prompt}], retry=True)
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "7"},
            clear=True,
        ):
            errors = _unsafe_training_api_errors(ast.parse(source))
        self.assertEqual(len(errors), 1)
        self.assertIn("may execute 8 times sequentially", errors[0])

    def test_target_worker_submitted_concurrently_is_not_marked_sequential(self) -> None:
        source = """
from concurrent.futures import ThreadPoolExecutor
from aar.infrastructure.serve_v2 import chat_completion

def complete_one(messages):
    return chat_completion(messages, enable_thinking=True)

with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(complete_one, requests))
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "8"},
            clear=True,
        ):
            self.assertEqual(_unsafe_training_api_errors(ast.parse(source)), [])

    def test_while_loop_target_generation_is_rejected(self) -> None:
        source = """
from aar.infrastructure.serve_v2 import chat_completion

while pending:
    chat_completion(messages, enable_thinking=True)
"""
        with patch.dict(
            "os.environ",
            {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": "256"},
            clear=True,
        ):
            errors = _unsafe_training_api_errors(ast.parse(source))
        self.assertEqual(len(errors), 1)
        self.assertIn("while-loop generation", errors[0])

    def test_invalid_sequential_target_generation_limit_fails_closed(self) -> None:
        for value in ("", "0", "3.5", "100001"):
            with self.subTest(value=value), patch.dict(
                "os.environ",
                {"AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS": value},
                clear=True,
            ):
                errors = _unsafe_training_api_errors(ast.parse("value = 1"))
            self.assertEqual(len(errors), 1)
            self.assertIn("must be an integer between 1 and 100000", errors[0])

    def test_required_target_thinking_rejects_disabled_or_dynamic_calls(self) -> None:
        sources = [
            "chat_completion(messages, enable_thinking=False)",
            "chat_completion(messages, enable_thinking=should_think)",
        ]
        with patch.dict(
            "os.environ", {"AAR_TARGET_ENABLE_THINKING": "1"}, clear=False
        ):
            for source in sources:
                with self.subTest(source=source):
                    errors = _unsafe_training_api_errors(ast.parse(source))
                    self.assertEqual(len(errors), 1)
                    self.assertIn("literal enable_thinking=True", errors[0])

    def test_required_target_thinking_accepts_default_or_literal_true(self) -> None:
        sources = [
            "chat_completion(messages)",
            "chat_completion(messages, enable_thinking=True)",
        ]
        with patch.dict(
            "os.environ", {"AAR_TARGET_ENABLE_THINKING": "1"}, clear=False
        ):
            for source in sources:
                with self.subTest(source=source):
                    self.assertEqual(
                        _unsafe_training_api_errors(ast.parse(source)),
                        [],
                    )

    def test_invalid_required_target_thinking_env_fails_closed(self) -> None:
        with patch.dict(
            "os.environ",
            {"AAR_TARGET_ENABLE_THINKING": "sometimes"},
            clear=False,
        ):
            errors = _unsafe_training_api_errors(ast.parse("value = 1"))
        self.assertEqual(
            errors,
            ["AAR_TARGET_ENABLE_THINKING must be a boolean value when set"],
        )

    def _run(self, source: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            method = root / "run.py"
            proof = root / "proof.json"
            method.write_text(source)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_method_contract.py",
                    str(method),
                    "--proof",
                    str(proof),
                    "--run-dry-run",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            return result, json.loads(proof.read_text())

    def _run_with_gemma_targets(
        self, source: str
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            method = root / "run.py"
            proof = root / "proof.json"
            method.write_text(source)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_method_contract.py",
                    str(method),
                    "--proof",
                    str(proof),
                    "--run-dry-run",
                    "--require-gemma4-targets",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            return result, json.loads(proof.read_text())

    def _run_with_smoke_required(
        self, source: str
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            method = root / "run.py"
            proof = root / "proof.json"
            method.write_text(source)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_method_contract.py",
                    str(method),
                    "--proof",
                    str(proof),
                    "--run-dry-run",
                    "--require-smoke-run",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            return result, json.loads(proof.read_text())

    def test_accepts_complete_training_contract(self) -> None:
        phases = "\n".join(
            f'    with phase("{name}"):\n        pass'
            for name in (
                "data_generation",
                "tokenization",
                "model_loading",
                "training",
                "checkpoint_save",
            )
        )
        result, proof = self._run(
            "from __future__ import annotations\n"
            "from contextlib import contextmanager\n"
            "from dataclasses import dataclass\n"
            "@contextmanager\n"
            "def phase(_name):\n"
            "    yield\n"
            "@dataclass\n"
            "class MethodConfig:\n"
            "    output_dir: str = 'out'\n"
            "    dry_run: bool = False\n"
            "def run_experiment(config):\n"
            f"{phases}\n"
            "    return {'model_path': config.output_dir, 'method': 'test'}\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(proof["status"], "passed")
        self.assertEqual(proof["errors"], [])
        self.assertEqual(len(proof["source_sha256"]), 64)
        self.assertEqual(
            proof["requirements"],
            {
                "run_dry_run": True,
                "require_gemma4_targets": False,
                "require_smoke_run": False,
                "require_autodata_loader": False,
            },
        )

    def test_rejects_missing_method_config_and_phases(self) -> None:
        result, proof = self._run(
            "def run_experiment(config):\n"
            "    return {'model_path': 'out', 'method': 'bad'}\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(proof["status"], "failed")
        self.assertTrue(
            any("missing required phase contexts" in error for error in proof["errors"])
        )
        self.assertIn("MethodConfig class is missing", proof["errors"])

    def test_rejects_broad_gemma_targets_and_missing_bitsandbytes(self) -> None:
        source = (
            "from transformers import BitsAndBytesConfig\n"
            "target_modules = ['q_proj', 'v_proj']\n"
            "class MethodConfig:\n"
            "    def __init__(self, output_dir='out', dry_run=False):\n"
            "        self.output_dir = output_dir\n"
            "        self.dry_run = dry_run\n"
            "def run_experiment(config):\n"
            + "\n".join(
                f'    with phase("{name}"):\n        pass'
                for name in (
                    "data_generation",
                    "tokenization",
                    "model_loading",
                    "training",
                    "checkpoint_save",
                )
            )
            + "\n    return {'model_path': config.output_dir, 'method': 'test'}\n"
        )
        result, proof = self._run_with_gemma_targets(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            any("bitsandbytes" in error.lower() for error in proof["errors"])
        )
        self.assertTrue(
            any("Gemma-4 PEFT" in error for error in proof["errors"])
        )

    def test_rejects_gemma_regex_wrapped_in_collection(self) -> None:
        phases = "\n".join(
            f'    with phase("{name}"):\n        pass'
            for name in (
                "data_generation",
                "tokenization",
                "model_loading",
                "training",
                "checkpoint_save",
            )
        )
        result, proof = self._run_with_gemma_targets(
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def phase(_name):\n"
            "    yield\n"
            "target_modules = "
            "[r'model\\.language_model\\.layers\\.\\d+\\.self_attn\\.(q_proj|v_proj)']\n"
            "class MethodConfig:\n"
            "    def __init__(self, output_dir='out', dry_run=False):\n"
            "        self.output_dir = output_dir\n"
            "        self.dry_run = dry_run\n"
            "def run_experiment(config):\n"
            f"{phases}\n"
            "    LoraConfig(target_modules=target_modules)\n"
            "    return {'model_path': config.output_dir, 'method': 'test'}\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            any("must be passed as a string" in error for error in proof["errors"])
        )

    def test_requires_real_gpu_smoke_interface(self) -> None:
        phases = "\n".join(
            f'    with phase("{name}"):\n        pass'
            for name in (
                "data_generation",
                "tokenization",
                "model_loading",
                "training",
                "checkpoint_save",
            )
        )
        common = (
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def phase(_name):\n"
            "    yield\n"
        )
        missing_result, missing_proof = self._run_with_smoke_required(
            common
            + "class MethodConfig:\n"
            "    def __init__(self, output_dir='out', dry_run=False):\n"
            "        self.output_dir = output_dir\n"
            "        self.dry_run = dry_run\n"
            "def run_experiment(config):\n"
            f"{phases}\n"
            "    return {'model_path': config.output_dir, 'method': 'test'}\n"
        )
        self.assertNotEqual(missing_result.returncode, 0)
        self.assertTrue(
            any("config.smoke_run" in error for error in missing_proof["errors"])
        )

        passing_result, passing_proof = self._run_with_smoke_required(
            common
            + "class MethodConfig:\n"
            "    def __init__(self, output_dir='out', dry_run=False, smoke_run=False):\n"
            "        self.output_dir = output_dir\n"
            "        self.dry_run = dry_run\n"
            "        self.smoke_run = smoke_run\n"
            "def run_experiment(config):\n"
            "    if config.dry_run:\n"
            "        return {'model_path': config.output_dir, 'method': 'test'}\n"
            "    max_steps = 1 if config.smoke_run else 10\n"
            f"{phases}\n"
            "    return {'model_path': config.output_dir, 'method': str(max_steps)}\n"
        )
        self.assertEqual(passing_result.returncode, 0, passing_proof)

    def test_rejects_training_arguments_unsupported_by_environment(self) -> None:
        phases = "\n".join(
            f'    with phase("{name}"):\n        pass'
            for name in (
                "data_generation",
                "tokenization",
                "model_loading",
                "training",
                "checkpoint_save",
            )
        )
        result, proof = self._run_with_smoke_required(
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def phase(_name):\n"
            "    yield\n"
            "class MethodConfig:\n"
            "    def __init__(self, output_dir='out', dry_run=False, smoke_run=False):\n"
            "        self.output_dir = output_dir\n"
            "        self.dry_run = dry_run\n"
            "        self.smoke_run = smoke_run\n"
            "def run_experiment(config):\n"
            "    if config.dry_run:\n"
            "        return {'model_path': config.output_dir, 'method': 'test'}\n"
            "    TrainingArguments(overwrite_output_dir=True)\n"
            f"{phases}\n"
            "    return {'model_path': config.output_dir, 'method': 'test'}\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            any(
                "overwrite_output_dir" in error
                for error in proof["errors"]
            )
        )

    def test_contract_rejects_chat_template_helper_arity_before_smoke(self) -> None:
        phases = "\n".join(
            f'    with phase("{name}"):\n        pass'
            for name in (
                "data_generation",
                "tokenization",
                "model_loading",
                "training",
                "checkpoint_save",
            )
        )
        result, proof = self._run_with_smoke_required(
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def phase(_name):\n"
            "    yield\n"
            "class MethodConfig:\n"
            "    def __init__(self, output_dir='out', dry_run=False, smoke_run=False):\n"
            "        self.output_dir = output_dir\n"
            "        self.dry_run = dry_run\n"
            "        self.smoke_run = smoke_run\n"
            "def run_experiment(config):\n"
            "    if config.dry_run:\n"
            "        return {'model_path': config.output_dir, 'method': 'test'}\n"
            "    from aar.utils.chat_template import normalize_chat_template_ids\n"
            "    ids = normalize_chat_template_ids([], object())\n"
            f"{phases}\n"
            "    return {'model_path': config.output_dir, 'method': str(ids)}\n"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(proof["status"], "failed")
        self.assertTrue(
            any(
                "accepts exactly one argument (value)" in error
                for error in proof["errors"]
            )
        )


if __name__ == "__main__":
    unittest.main()
