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
    _undefined_name_errors,
    _unsafe_training_api_errors,
)


class ValidateMethodContractTest(unittest.TestCase):
    def test_rejects_observed_target_runtime_failures_before_gpu(self) -> None:
        tree = ast.parse(
            """
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

        self.assertEqual(len(errors), 5)
        self.assertTrue(any("DPOTrainer" in error for error in errors))
        self.assertTrue(any("SFTTrainer(tokenizer" in error for error in errors))
        self.assertTrue(any("Trainer.train(max_steps" in error for error in errors))
        self.assertTrue(any("torch.tensor(batch" in error for error in errors))
        self.assertTrue(any("per-item loop" in error for error in errors))

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


if __name__ == "__main__":
    unittest.main()
