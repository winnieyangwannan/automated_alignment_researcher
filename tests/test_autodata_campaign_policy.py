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
    def test_base_target_round_trip_and_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base"
            base.mkdir()
            (base / "config.json").write_text("{}\n")
            (base / "model.safetensors.index.json").write_text(
                '{"weight_map":{}}\n'
            )
            manifest = create_base_target_manifest(
                iteration=1,
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
            self.assertEqual(
                policy["required_solve_env"]["AUTODATA_TARGET_DEPLOYMENT_ID"],
                "chain-alpha-iteration-1",
            )
            self.assertEqual(
                policy["required_solve_env"][
                    "AUTODATA_GENERATOR_DEPLOYMENT_ID"
                ],
                "aar_8-kimi26",
            )

    def test_base_target_rejects_checkpoint_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base"
            base.mkdir()
            (base / "config.json").write_text("{}\n")
            (base / "model.safetensors.index.json").write_text(
                '{"weight_map":{}}\n'
            )
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
