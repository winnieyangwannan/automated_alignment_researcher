"""Checks for architecture-specific binary dependencies and their lock entries."""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
X86_LINUX_MARKER = "platform_machine == 'x86_64' and sys_platform == 'linux'"
ARM_LINUX_MARKER = "platform_machine == 'aarch64' and sys_platform == 'linux'"
NON_ARM_LINUX_MARKER = "platform_machine != 'aarch64' or sys_platform != 'linux'"
LOCK_FLASH_MARKER = f"python_full_version < '3.13' and {X86_LINUX_MARKER}"
X86_OPTIMIZATIONS = {
    "cut-cross-entropy",
    "liger-kernel",
    "sglang",
    "triton",
    "unsloth",
    "unsloth-zoo",
}
NON_ARM_LEGACY_RUNTIME = {
    "flashinfer-python",
    "sentence-transformers",
    "torch-memory-saver",
    "vllm",
}


class DependencyMarkerTest(unittest.TestCase):
    def test_arm_hpc_instructions_create_header_complete_locked_environment(self) -> None:
        expected = '/usr/local/bin/micromamba create -y -p "$PWD/.venv" python=3.12 pip'
        for path in (ROOT / "README.md", ROOT / "experiments/20260919/plan.md"):
            instructions = path.read_text()
            self.assertIn(expected, instructions)
            self.assertIn(".venv/include/python3.12/Python.h", instructions)
            self.assertIn("uv sync --locked", instructions)

    def test_flash_attention_is_x86_64_linux_only(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)

        flash_dependencies = [
            requirement
            for requirement in project["project"]["dependencies"]
            if requirement.startswith("flash-attn")
        ]
        self.assertEqual(flash_dependencies, [f"flash-attn; {X86_LINUX_MARKER}"])

        source = project["tool"]["uv"]["sources"]["flash-attn"]["url"]
        self.assertTrue(source.endswith("linux_x86_64.whl"))

    def test_lock_preserves_the_architecture_marker(self) -> None:
        with (ROOT / "uv.lock").open("rb") as stream:
            lock = tomllib.load(stream)

        root = next(package for package in lock["package"] if package.get("source") == {"editable": "."})
        locked_dependency = next(
            dependency for dependency in root["dependencies"] if dependency["name"] == "flash-attn"
        )
        metadata_dependency = next(
            dependency for dependency in root["metadata"]["requires-dist"]
            if dependency["name"] == "flash-attn"
        )

        self.assertEqual(locked_dependency["marker"], LOCK_FLASH_MARKER)
        self.assertEqual(metadata_dependency["marker"], X86_LINUX_MARKER)
        self.assertTrue(metadata_dependency["url"].endswith("linux_x86_64.whl"))

    def test_cuda_optimization_stack_is_x86_64_linux_only(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)
        with (ROOT / "uv.lock").open("rb") as stream:
            lock = tomllib.load(stream)

        requirements = project["project"]["dependencies"]
        for package in X86_OPTIMIZATIONS:
            requirement = next(item for item in requirements if item.split("[", 1)[0].startswith(package))
            self.assertEqual(requirement.split("; ", 1)[1], X86_LINUX_MARKER)

        root = next(package for package in lock["package"] if package.get("source") == {"editable": "."})
        metadata = {dependency["name"]: dependency for dependency in root["metadata"]["requires-dist"]}
        locked = {dependency["name"]: dependency for dependency in root["dependencies"]}
        for package in X86_OPTIMIZATIONS:
            self.assertEqual(metadata[package]["marker"], X86_LINUX_MARKER)
            self.assertEqual(locked[package]["marker"], X86_LINUX_MARKER)

        self.assertNotIn("marker", metadata["peft"])

        for package in NON_ARM_LEGACY_RUNTIME:
            self.assertEqual(metadata[package]["marker"], NON_ARM_LINUX_MARKER)
            self.assertEqual(locked[package]["marker"], NON_ARM_LINUX_MARKER)

    def test_arm_core_versions_and_x86_compatible_lock(self) -> None:
        with (ROOT / "uv.lock").open("rb") as stream:
            lock = tomllib.load(stream)

        root = next(package for package in lock["package"] if package.get("source") == {"editable": "."})
        expected_requirements = {
            "torch": {
                (ARM_LINUX_MARKER, "==2.14.0"),
                (NON_ARM_LINUX_MARKER, "==2.8.0"),
            },
            "transformers": {
                (ARM_LINUX_MARKER, "==5.17.0"),
                (NON_ARM_LINUX_MARKER, ">=4.51.0"),
            },
            "tokenizers": {
                (ARM_LINUX_MARKER, ">=0.23.1,<0.24"),
                (NON_ARM_LINUX_MARKER, "==0.22.1"),
            },
            "safetensors": {
                (ARM_LINUX_MARKER, ">=0.8.0"),
                (NON_ARM_LINUX_MARKER, "==0.7.0"),
            },
        }
        for name, expected in expected_requirements.items():
            requirements = [
                dependency
                for dependency in root["metadata"]["requires-dist"]
                if dependency["name"] == name
            ]
            self.assertEqual(
                {(item["marker"], item["specifier"]) for item in requirements},
                expected,
            )

        locked = {
            name: {
                dependency["marker"]: dependency["version"]
                for dependency in root["dependencies"]
                if dependency["name"] == name
            }
            for name in expected_requirements
        }
        self.assertEqual(locked["torch"][ARM_LINUX_MARKER], "2.14.0")
        self.assertEqual(locked["torch"][NON_ARM_LINUX_MARKER], "2.8.0")
        self.assertEqual(locked["transformers"][ARM_LINUX_MARKER], "5.17.0")
        self.assertEqual(locked["transformers"][NON_ARM_LINUX_MARKER], "4.56.1")
        self.assertGreaterEqual(locked["tokenizers"][ARM_LINUX_MARKER], "0.23.1")
        self.assertLess(locked["tokenizers"][ARM_LINUX_MARKER], "0.24")
        self.assertEqual(locked["tokenizers"][NON_ARM_LINUX_MARKER], "0.22.1")
        self.assertGreaterEqual(locked["safetensors"][ARM_LINUX_MARKER], "0.8.0")
        self.assertEqual(locked["safetensors"][NON_ARM_LINUX_MARKER], "0.7.0")

    def test_arm_torch_lock_contains_cuda_runtime_and_aarch64_wheel(self) -> None:
        with (ROOT / "uv.lock").open("rb") as stream:
            lock = tomllib.load(stream)

        torch = next(
            package
            for package in lock["package"]
            if package["name"] == "torch" and package["version"] == "2.14.0"
        )
        dependency_names = {dependency["name"] for dependency in torch["dependencies"]}
        self.assertIn("cuda-toolkit", dependency_names)
        self.assertIn("nvidia-cudnn-cu13", dependency_names)
        self.assertIn("nvidia-nccl-cu13", dependency_names)
        self.assertTrue(torch["wheels"])
        self.assertTrue(all("aarch64.whl" in wheel["url"] for wheel in torch["wheels"]))


if __name__ == "__main__":
    unittest.main()
