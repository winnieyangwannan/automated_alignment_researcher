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


class DependencyMarkerTest(unittest.TestCase):
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
        for package in X86_OPTIMIZATIONS:
            self.assertEqual(metadata[package]["marker"], X86_LINUX_MARKER)

        # These are the portable ARM training and inference foundation.
        for package in ("torch", "peft", "vllm"):
            self.assertNotIn("marker", metadata[package])

    def test_transformers_has_an_arm_qwen_floor_and_x86_compatible_lock(self) -> None:
        with (ROOT / "uv.lock").open("rb") as stream:
            lock = tomllib.load(stream)

        root = next(package for package in lock["package"] if package.get("source") == {"editable": "."})
        requirements = [
            dependency
            for dependency in root["metadata"]["requires-dist"]
            if dependency["name"] == "transformers"
        ]
        self.assertEqual(
            {(item["marker"], item["specifier"]) for item in requirements},
            {(ARM_LINUX_MARKER, ">=4.57.0"), (NON_ARM_LINUX_MARKER, ">=4.51.0")},
        )

        locked = {
            dependency["marker"]: dependency["version"]
            for dependency in root["dependencies"]
            if dependency["name"] == "transformers"
        }
        arm_version = tuple(int(part) for part in locked[ARM_LINUX_MARKER].split("."))
        self.assertGreaterEqual(arm_version, (4, 57, 0))
        # SGLang 0.5.2 pins this version on the preserved non-ARM stack.
        self.assertEqual(locked[NON_ARM_LINUX_MARKER], "4.56.1")


if __name__ == "__main__":
    unittest.main()
