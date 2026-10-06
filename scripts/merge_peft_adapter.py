#!/usr/bin/env python3
"""Atomically merge a local PEFT LoRA into a serving checkpoint.

This is the local-adapter counterpart of steerability's frozen ``.spipe``
merge helper. It preserves the base checkpoint's serving metadata byte for
byte so newer Transformers normalization cannot make the merged checkpoint
incompatible with the validated vLLM image.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, type=Path)
    parser.add_argument("--base-checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def verify_weight_shards(checkpoint: Path) -> tuple[list[str], int]:
    index_path = checkpoint / "model.safetensors.index.json"
    if not index_path.is_file():
        raise RuntimeError(f"merged checkpoint has no safetensors index: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    shards = sorted(set(index.get("weight_map", {}).values()))
    if not shards:
        raise RuntimeError(f"merged checkpoint has an empty index: {index_path}")
    missing = [shard for shard in shards if not (checkpoint / shard).is_file()]
    if missing:
        raise RuntimeError(f"merged checkpoint is missing shards: {missing}")
    return shards, sum((checkpoint / shard).stat().st_size for shard in shards)


def copy_base_serving_files(base_checkpoint: Path, output: Path) -> None:
    """Copy every non-weight base file, including the exact base config."""
    for source in base_checkpoint.iterdir():
        if source.name == "model.safetensors.index.json" or (
            source.name.startswith("model") and source.suffix == ".safetensors"
        ):
            continue
        destination = output / source.name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)


def main() -> int:
    args = parse_args()
    adapter = args.adapter.expanduser().resolve()
    base_checkpoint = args.base_checkpoint.expanduser().resolve()
    output = args.output.expanduser().resolve()
    temporary_output = output.with_name(f".{output.name}.incomplete")
    complete = output / ".merge-complete.json"

    if complete.is_file():
        print(f"merged checkpoint already complete: {output}", flush=True)
        return 0
    if output.exists():
        raise RuntimeError(f"refusing to overwrite incomplete output: {output}")
    if temporary_output.exists():
        raise RuntimeError(
            f"refusing to overwrite incomplete staging directory: {temporary_output}"
        )
    for required in ("adapter_config.json", "adapter_model.safetensors"):
        if not (adapter / required).is_file():
            raise RuntimeError(f"adapter is missing {required}: {adapter}")
    base_index = base_checkpoint / "model.safetensors.index.json"
    if not base_index.is_file():
        raise RuntimeError(f"base checkpoint has no safetensors index: {base_index}")

    adapter_config = json.loads(
        (adapter / "adapter_config.json").read_text(encoding="utf-8")
    )
    declared_base = adapter_config.get("base_model_name_or_path")
    if declared_base and Path(declared_base).expanduser().resolve() != base_checkpoint:
        raise RuntimeError(
            f"adapter declares base {declared_base!r}, expected {str(base_checkpoint)!r}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    load_kwargs = {
        "dtype": torch.bfloat16,
        "device_map": "cpu",
        "low_cpu_mem_usage": True,
        "trust_remote_code": True,
    }
    try:
        model = AutoModelForCausalLM.from_pretrained(base_checkpoint, **load_kwargs)
    except (KeyError, ValueError):
        from transformers import AutoModelForImageTextToText

        model = AutoModelForImageTextToText.from_pretrained(
            base_checkpoint, **load_kwargs
        )
    loader_class = type(model).__name__
    model = PeftModel.from_pretrained(model, adapter)
    model = model.merge_and_unload(safe_merge=True)
    model.save_pretrained(
        temporary_output,
        safe_serialization=True,
        max_shard_size="5GB",
    )

    copy_base_serving_files(base_checkpoint, temporary_output)
    base_config_hash = sha256_file(base_checkpoint / "config.json")
    if sha256_file(temporary_output / "config.json") != base_config_hash:
        raise RuntimeError("merged config.json differs from known-good base config")
    shards, merged_size = verify_weight_shards(temporary_output)
    metadata = {
        "adapter": str(adapter),
        "adapter_config_sha256": sha256_file(adapter / "adapter_config.json"),
        "adapter_model_sha256": sha256_file(adapter / "adapter_model.safetensors"),
        "base_checkpoint": str(base_checkpoint),
        "base_config_sha256": base_config_hash,
        "base_index_sha256": sha256_file(base_index),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "loader_class": loader_class,
        "merged_shards": shards,
        "merged_weight_bytes": merged_size,
        "output": str(output),
        "source_commit": args.source_commit,
        "tool_versions": {
            "peft": package_version("peft"),
            "torch": package_version("torch"),
            "transformers": package_version("transformers"),
        },
    }
    (temporary_output / ".merge-complete.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_output.rename(output)
    print(
        f"merged checkpoint ready: {output} "
        f"({len(shards)} shards, {merged_size} bytes)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
