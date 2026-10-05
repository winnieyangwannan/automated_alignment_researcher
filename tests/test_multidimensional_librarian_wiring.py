"""Focused checks for multi-dimensional librarian and researcher wiring."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MultidimensionalLibrarianWiringTest(unittest.TestCase):
    def test_shell_scripts_parse(self) -> None:
        for name in ("litreview.sh", "launch_team.sh"):
            subprocess.run(["bash", "-n", str(ROOT / "scripts" / name)], check=True)

    def test_librarian_defaults_are_scoped_to_composed_suite(self) -> None:
        source = (ROOT / "scripts" / "litreview.sh").read_text()
        self.assertIn('[ "${SUITE}" = "honesty_sycophancy" ]', source)
        self.assertIn("LITREVIEW_DIMENSIONS:-honesty,sycophancy", source)
        self.assertIn(
            '[ "${SUITE}" = "honesty_sycophancy_concealing_uncertainty" ]',
            source,
        )
        self.assertIn(
            "LITREVIEW_DIMENSIONS:-honesty,sycophancy,concealing_uncertainty",
            source,
        )
        self.assertIn("LITREVIEW_TARGET_MODEL:-google/gemma-4-31B-it", source)

    def test_launcher_checks_manifest_aware_readiness(self) -> None:
        source = (ROOT / "scripts" / "launch_team.sh").read_text()
        self.assertIn("baseline_ready", source)
        self.assertIn('[ "${_lit_ready}" = "1" ]', source)
        self.assertIn('[ "${lit_ready}" != "1" ]', source)
        self.assertIn("AAR_DIMENSIONS:-honesty,sycophancy", source)
        self.assertIn(
            "AAR_DIMENSIONS:-honesty,sycophancy,concealing_uncertainty",
            source,
        )

    def test_research_prompt_requires_joint_checkpoint_and_filtered_literature(self) -> None:
        source = (ROOT / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()
        self.assertIn(
            'suite_name == "honesty_sycophancy_concealing_uncertainty"', source
        )
        self.assertIn("one jointly trained target-model checkpoint", source)
        self.assertIn('`dimension="honesty"`', source)
        self.assertIn('`dimension="sycophancy"`', source)
        self.assertIn('`dimension="concealing_uncertainty"`', source)
        self.assertIn('`scope="cross-dimensional"`', source)
        self.assertIn("never seek, infer, or expose held-out benchmark", source)


if __name__ == "__main__":
    unittest.main()
