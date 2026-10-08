from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aar.research_loop.autodata_plugin import resolve_autodata_plugin


class AutoDataPluginTest(unittest.TestCase):
    def _checkout(self, root: Path) -> tuple[Path, str]:
        plugin = root / "plugin" / "autodata"
        for relative in (
            ".claude-plugin/plugin.json",
            "skills/autodata/SKILL.md",
            "scripts/autodata.py",
            "scripts/bootstrap.py",
            "wheels/wheels.lock.json",
        ):
            (plugin / relative).parent.mkdir(parents=True, exist_ok=True)
            (plugin / relative).write_text("{}\n")
        (plugin / ".claude-plugin/plugin.json").write_text(
            json.dumps({"name": "autodata", "skills": ["./skills/"]})
        )
        subprocess.run(["git", "init", "-b", "main", str(root)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "fixture"],
            check=True,
            capture_output=True,
        )
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return plugin, sha

    def test_disabled_plugin_resolves_to_none(self) -> None:
        with patch.dict(os.environ, {"AAR_AUTODATA": "0"}, clear=True):
            self.assertIsNone(resolve_autodata_plugin())

    def test_resolves_clean_pinned_main_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plugin, sha = self._checkout(Path(temporary))
            with patch.dict(
                os.environ,
                {
                    "AAR_AUTODATA": "1",
                    "AAR_AUTODATA_PLUGIN_ROOT": str(plugin),
                    "AAR_AUTODATA_SHA": sha,
                },
                clear=True,
            ):
                resolved = resolve_autodata_plugin()

            self.assertIsNotNone(resolved)
            assert resolved is not None
            self.assertEqual(resolved.root, plugin.resolve())
            self.assertEqual(
                resolved.sdk_config(), {"type": "local", "path": str(plugin.resolve())}
            )

    def test_rejects_sha_mismatch_and_dirty_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plugin, sha = self._checkout(Path(temporary))
            base = {
                "AAR_AUTODATA": "1",
                "AAR_AUTODATA_PLUGIN_ROOT": str(plugin),
                "AAR_AUTODATA_SHA": "0" * 40,
            }
            with patch.dict(os.environ, base, clear=True):
                with self.assertRaisesRegex(RuntimeError, "SHA mismatch"):
                    resolve_autodata_plugin()

            (plugin / "skills/autodata/SKILL.md").write_text("changed\n")
            base["AAR_AUTODATA_SHA"] = sha
            with patch.dict(os.environ, base, clear=True):
                with self.assertRaisesRegex(RuntimeError, "uncommitted changes"):
                    resolve_autodata_plugin()


if __name__ == "__main__":
    unittest.main()
