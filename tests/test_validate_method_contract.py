"""Tests for the fail-closed generated-method contract proof."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ValidateMethodContractTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
