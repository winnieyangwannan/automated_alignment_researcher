"""Checks for architecture-specific binary dependencies and their lock entries."""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
FLASH_MARKER = "platform_machine == 'x86_64' and sys_platform == 'linux'"
LOCK_FLASH_MARKER = f"python_full_version < '3.13' and {FLASH_MARKER}"


class DependencyMarkerTest(unittest.TestCase):
    def test_flash_attention_is_x86_64_linux_only(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)

        flash_dependencies = [
            requirement
            for requirement in project["project"]["dependencies"]
            if requirement.startswith("flash-attn")
        ]
        self.assertEqual(flash_dependencies, [f"flash-attn; {FLASH_MARKER}"])

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
        self.assertEqual(metadata_dependency["marker"], FLASH_MARKER)
        self.assertTrue(metadata_dependency["url"].endswith("linux_x86_64.whl"))


if __name__ == "__main__":
    unittest.main()
