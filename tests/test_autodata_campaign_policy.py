from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aar.autodata_campaign_policy import (
    atomic_write_json,
    build_policy,
    create_base_target_manifest,
    target_environment_from_manifest,
)


class AutoDataCampaignPolicyTest(unittest.TestCase):
    def test_run12_retries_resume_one_approved_outer_iteration(self) -> None:
        root = Path(__file__).resolve().parents[1]
        run12 = root / "experiments/dishonest_sycophancy_concealing/run_12"
        controller = (run12 / "run_12_chain_controller.sbatch").read_text()
        pipeline = (run12 / "run_12_full_pipeline.sbatch").read_text()
        chain = (root / "scripts/slurm_aar_chain.sh").read_text()
        runtime = (root / "scripts/aar_runtime_env.sh").read_text()

        self.assertIn('AAR_IDEA_UID_OVERRIDE="run12-${seed}-iteration-1"', pipeline)
        self.assertIn("AAR_RESUME_APPROVED_PROPOSAL=0", pipeline)
        self.assertIn(
            'AAR_IDEA_UID_OVERRIDE="run12-${SEED}-iteration-${next_iteration}"',
            controller,
        )
        self.assertIn("AAR_RESUME_APPROVED_PROPOSAL=1", controller)
        self.assertIn("AAR_IDEA_UID_OVERRIDE:-", chain)
        self.assertIn("AAR_IDEA_UID_OVERRIDE AAR_RESUME_APPROVED_PROPOSAL", runtime)
        self.assertIn("AAR_AUTODATA_RUNTIME_ENV", pipeline)
        self.assertIn("aar.autodata_run_config compile", controller)
        self.assertNotIn("AAR_RUN12_AUTODATA_CONCURRENCY:-8", pipeline)
        self.assertIn(
            '--generator-deployment-id "${AAR_AUTODATA_GENERATOR_DEPLOYMENT}"',
            controller,
        )

    def test_run13_full_run_uses_claude_and_five_isolated_chains(self) -> None:
        root = Path(__file__).resolve().parents[1]
        run13 = root / "experiments/dishonest_sycophancy_concealing/run_13"
        submitter = (run13 / "submit_run_13_full.sh").read_text()
        pipeline = (run13 / "run_13_full_pipeline.sbatch").read_text()
        controller = (run13 / "run_13_chain_controller.sbatch").read_text()

        self.assertIn("AAR_AGENT_BACKEND=claude", submitter)
        self.assertIn("AAR_AGENT_MODEL=claude-opus-4-8", submitter)
        self.assertIn(
            "AAR_AGENT_BACKEND=claude AAR_AGENT_MODEL=claude-opus-4-8",
            pipeline,
        )
        self.assertIn("for seed in alpha beta gamma delta epsilon", pipeline)
        self.assertIn('AAR_IDEA_UID_OVERRIDE="run13-${seed}-iteration-1"', pipeline)
        self.assertIn("AAR_RESUME_APPROVED_PROPOSAL=0", pipeline)
        self.assertIn(
            'AAR_IDEA_UID_OVERRIDE="run13-${SEED}-iteration-${next_iteration}"',
            controller,
        )
        self.assertIn("AAR_RESUME_APPROVED_PROPOSAL=1", controller)
        self.assertIn("AAR_RUN13_CHECKPOINT_ROOT", pipeline)
        self.assertIn("AAR_RUN13_CHECKPOINT_ROOT", controller)
        self.assertIn("AAR_AUTODATA_PROFILE=target-aware-local-v1", pipeline)
        self.assertNotIn("AAR_RUN13_AUTODATA_CONCURRENCY:-8", pipeline)
        contract = "autodata-training-data-contract.json"
        self.assertIn(contract, submitter)
        self.assertIn("aar.infrastructure.autodata_contract", submitter)
        self.assertIn("AAR_AUTODATA_TRAINING_DATA_CONTRACT", pipeline)
        self.assertIn(contract, controller)
        self.assertIn("aar.infrastructure.autodata_contract", controller)
        self.assertLess(
            controller.index("create-policy"),
            controller.index("aar.infrastructure.autodata_contract"),
        )
        self.assertLess(
            controller.index("aar.infrastructure.autodata_contract"),
            controller.index('job="$(submit_session)"'),
        )

    def test_base_target_round_trip_and_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base"
            base.mkdir()
            (base / "config.json").write_text("{}\n")
            (base / "model.safetensors.index.json").write_text('{"weight_map":{}}\n')
            manifest = create_base_target_manifest(
                iteration=1,
                chain_id="alpha",
                base_checkpoint=base,
                endpoint={
                    "url": "http://gateway/v1",
                    "host_header": "ram-inference-gateway.ingress.",
                    "model": "gemma-4-31B-it",
                    "deployment_id": "chain-alpha-iteration-1",
                },
            )
            path = root / "target.json"
            atomic_write_json(path, manifest)
            environment = target_environment_from_manifest(path)
            policy = build_policy(
                campaign_id="chain-alpha",
                target_environment=environment,
                generator_deployment_id="aar_8-kimi26",
                max_cost_usd="299",
            )

            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(manifest["schema"], "aar.autodata.base-target/v2")
            self.assertEqual(manifest["chain_id"], "alpha")
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_TARGET_DEPLOYMENT_ID"],
                "chain-alpha-iteration-1",
            )
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_GENERATOR_DEPLOYMENT_ID"],
                "aar_8-kimi26",
            )
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_GENERATOR_MAX_INPUT"],
                "196608",
            )
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_GENERATOR_MAX_OUTPUT"],
                "65536",
            )
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_JUDGE_MAX_INPUT"],
                "1000000",
            )
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_JUDGE_MAX_OUTPUT"],
                "65536",
            )
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_TARGET_MAX_INPUT"],
                "196608",
            )
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_TARGET_MAX_OUTPUT"],
                "65536",
            )
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS"],
                "3",
            )

    def test_base_target_rejects_checkpoint_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base"
            base.mkdir()
            (base / "config.json").write_text("{}\n")
            (base / "model.safetensors.index.json").write_text('{"weight_map":{}}\n')
            path = root / "target.json"
            atomic_write_json(
                path,
                create_base_target_manifest(
                    iteration=2,
                    base_checkpoint=base,
                    endpoint={
                        "url": "http://gateway/v1",
                        "host_header": "",
                        "model": "gemma-4-31B-it",
                        "deployment_id": "chain-alpha-iteration-2",
                    },
                ),
            )
            (base / "config.json").write_text('{"changed":true}\n')

            with self.assertRaisesRegex(RuntimeError, "no longer matches"):
                target_environment_from_manifest(path)


if __name__ == "__main__":
    unittest.main()
