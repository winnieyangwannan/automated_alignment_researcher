from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aar.autodata_target_binding import (
    create_binding,
    load_binding,
    write_binding,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_checkpoint_fixture(root: Path) -> tuple[Path, Path, Path]:
    base = root / "base"
    adapter = root / "adapter"
    merged = root / "merged"
    base.mkdir()
    adapter.mkdir()
    merged.mkdir()
    (base / "config.json").write_text('{"model_type":"gemma4"}\n')
    (base / "model.safetensors.index.json").write_text('{"weight_map":{}}\n')
    (adapter / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": str(base.resolve()),
                "peft_type": "LORA",
            }
        )
        + "\n"
    )
    (adapter / "adapter_model.safetensors").write_bytes(b"adapter-weights")
    (merged / "config.json").write_bytes((base / "config.json").read_bytes())
    (merged / "model.safetensors.index.json").write_text('{"weight_map":{}}\n')
    shard = merged / "model-00001-of-00001.safetensors"
    shard.write_bytes(b"merged-weights")
    receipt = {
        "adapter": str(adapter.resolve()),
        "adapter_config_sha256": _sha256(adapter / "adapter_config.json"),
        "adapter_model_sha256": _sha256(adapter / "adapter_model.safetensors"),
        "base_checkpoint": str(base.resolve()),
        "base_config_sha256": _sha256(base / "config.json"),
        "base_index_sha256": _sha256(base / "model.safetensors.index.json"),
        "merged_shards": [shard.name],
        "merged_weight_bytes": shard.stat().st_size,
        "output": str(merged.resolve()),
        "source_commit": "deadbeef",
    }
    (merged / ".merge-complete.json").write_text(
        json.dumps(receipt, sort_keys=True) + "\n"
    )
    return base, adapter, merged


class TargetBindingTest(unittest.TestCase):
    def test_round_trip_binds_adapter_base_merge_and_endpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, adapter, merged = make_checkpoint_fixture(root)
            binding = create_binding(
                iteration=2,
                incumbent_run_id="candidate-1",
                base_checkpoint=str(base),
                adapter_checkpoint=str(adapter),
                merged_checkpoint=str(merged),
                endpoint={
                    "url": "http://gateway.example/v1/",
                    "host_header": "ram-inference-gateway.ingress.",
                    "model": "gemma-4-31B-it",
                    "deployment_id": "run12-target",
                },
            )
            path = root / "binding.json"
            write_binding(path, binding)
            loaded = load_binding(path)

            self.assertEqual(loaded.checkpoint_hash, binding.checkpoint_hash)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                loaded.solve_environment()["AUTODATA_TARGET_DEPLOYMENT_ID"],
                "run12-target",
            )

    def test_rejects_changed_adapter_after_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, adapter, merged = make_checkpoint_fixture(root)
            binding = create_binding(
                iteration=2,
                incumbent_run_id="candidate-1",
                base_checkpoint=str(base),
                adapter_checkpoint=str(adapter),
                merged_checkpoint=str(merged),
                endpoint={
                    "url": "https://gateway.example/v1",
                    "model": "gemma-4-31B-it",
                    "deployment_id": "run12-target",
                },
            )
            path = root / "binding.json"
            write_binding(path, binding)
            (adapter / "adapter_model.safetensors").write_bytes(b"changed")

            with self.assertRaisesRegex(RuntimeError, "merge receipt"):
                load_binding(path)


if __name__ == "__main__":
    unittest.main()
