"""Build an AutoData broker policy from one trusted target description."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from aar.autodata_target_binding import load_binding


IMAGE = (
    "docker.io/library/python@sha256:"
    "05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f"
)
EXPECTED_IMAGE_ID = (
    "df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def create_base_target_manifest(
    *,
    iteration: int,
    base_checkpoint: Path,
    endpoint: dict[str, str],
) -> dict[str, Any]:
    if isinstance(iteration, bool) or iteration < 1:
        raise RuntimeError("base target iteration must be positive")
    base = base_checkpoint.expanduser().resolve(strict=True)
    verified = {
        "base_config_sha256": _sha256(base / "config.json"),
        "base_index_sha256": _sha256(base / "model.safetensors.index.json"),
    }
    identity = {
        "schema": "aar.autodata.base-target/v1",
        "iteration": iteration,
        "base_checkpoint": str(base),
        "endpoint": endpoint,
        "verified": verified,
    }
    encoded = json.dumps(
        identity, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return {
        **identity,
        "checkpoint_hash": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def target_environment_from_manifest(path: Path) -> dict[str, str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") == "aar.autodata.base-target/v1":
        endpoint = value.get("endpoint")
        checkpoint_hash = value.get("checkpoint_hash")
        if not isinstance(endpoint, dict) or not isinstance(checkpoint_hash, str):
            raise RuntimeError("base target manifest is malformed")
        recreated = create_base_target_manifest(
            iteration=value.get("iteration"),
            base_checkpoint=Path(value.get("base_checkpoint", "")),
            endpoint=endpoint,
        )
        if value != recreated:
            raise RuntimeError("base target manifest no longer matches its checkpoint")
        required = {
            "AUTODATA_TARGET_ENABLED": "1",
            "AUTODATA_TARGET_URL": endpoint["url"],
            "AUTODATA_TARGET_MODEL": endpoint["model"],
            "AUTODATA_TARGET_DEPLOYMENT_ID": endpoint["deployment_id"],
            "AUTODATA_TARGET_CHECKPOINT_HASH": checkpoint_hash,
        }
        if endpoint.get("host_header"):
            required["AUTODATA_TARGET_HOST_HEADER"] = endpoint["host_header"]
        return required
    return load_binding(path).solve_environment()


def build_policy(
    *,
    campaign_id: str,
    target_environment: dict[str, str],
    generator_deployment_id: str,
    max_cost_usd: str,
) -> dict[str, Any]:
    required = {
        "AUTODATA_GENERATOR_URL": (
            "http://fair-cw-use2-1-ingress-slurm-ingress/v1"
        ),
        "AUTODATA_GENERATOR_HOST_HEADER": "ram-inference-gateway.ingress.",
        "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": generator_deployment_id,
        "AUTODATA_GENERATOR_MAX_INPUT": "196608",
        "AUTODATA_GENERATOR_MAX_OUTPUT": "65536",
        "AUTODATA_GENERATOR_TIMEOUT": "90",
        "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_JUDGE_URL": "https://api.meta.ai/v1/responses",
        "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
        "AUTODATA_JUDGE_MAX_INPUT": "1000000",
        "AUTODATA_JUDGE_MAX_OUTPUT": "65536",
        "AUTODATA_JUDGE_TIMEOUT": "90",
        "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_TARGET_MAX_INPUT": "196608",
        "AUTODATA_TARGET_MAX_OUTPUT": "65536",
        "AUTODATA_TARGET_TIMEOUT": "90",
        "AUTODATA_TARGET_INPUT_USD_PER_MILLION": "0",
        "AUTODATA_TARGET_OUTPUT_USD_PER_MILLION": "0",
        "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "1",
        **target_environment,
    }
    return {
        "schema": "autodata.broker-campaign-policy/v1",
        "campaign_id": campaign_id,
        "max_cost_usd": max_cost_usd,
        "runner": "local-bwrap",
        "environment": "oci-runner-firecracker-large",
        "image": IMAGE,
        "expected_image_id": EXPECTED_IMAGE_ID,
        "max_cpus": 2,
        "max_memory_mb": 2048,
        "required_solve_env": required,
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    base = subparsers.add_parser("create-base-target")
    base.add_argument("--iteration", type=int, default=1)
    base.add_argument("--base-checkpoint", required=True, type=Path)
    base.add_argument("--target-url", required=True)
    base.add_argument("--target-host-header", default="")
    base.add_argument("--target-model", required=True)
    base.add_argument("--target-deployment-id", required=True)
    base.add_argument("--output", required=True, type=Path)
    policy_parser = subparsers.add_parser("create-policy")
    policy_parser.add_argument("--campaign-id", required=True)
    policy_parser.add_argument("--target-manifest", required=True, type=Path)
    policy_parser.add_argument("--generator-deployment-id", required=True)
    policy_parser.add_argument("--max-cost-usd", default="299")
    policy_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "create-base-target":
        manifest = create_base_target_manifest(
            iteration=args.iteration,
            base_checkpoint=args.base_checkpoint,
            endpoint={
                "url": args.target_url.rstrip("/"),
                "host_header": args.target_host_header,
                "model": args.target_model,
                "deployment_id": args.target_deployment_id,
            },
        )
        atomic_write_json(args.output, manifest)
        return 0
    policy = build_policy(
        campaign_id=args.campaign_id,
        target_environment=target_environment_from_manifest(args.target_manifest),
        generator_deployment_id=args.generator_deployment_id,
        max_cost_usd=args.max_cost_usd,
    )
    atomic_write_json(args.output, policy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
