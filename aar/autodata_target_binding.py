"""Validate and materialize an iteration-scoped AutoData target binding.

The binding is created by trusted orchestration, never by the AutoData research
agent.  It ties an incumbent PEFT adapter to its fixed base checkpoint, the
atomically merged checkpoint served by vLLM, and the exact gateway deployment
used by target-aware generation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SCHEMA_V1 = "aar.autodata.target-binding/v1"
SCHEMA = "aar.autodata.target-binding/v2"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


@dataclass(frozen=True)
class TargetBinding:
    value: dict[str, Any]

    @property
    def checkpoint_hash(self) -> str:
        return str(self.value["checkpoint_hash"])

    @property
    def endpoint(self) -> dict[str, str]:
        return dict(self.value["endpoint"])

    @property
    def chain_id(self) -> str | None:
        value = self.value.get("chain_id")
        return value if isinstance(value, str) else None

    def solve_environment(self) -> dict[str, str]:
        endpoint = self.endpoint
        environment = {
            "AUTODATA_TARGET_ENABLED": "1",
            "AUTODATA_TARGET_URL": endpoint["url"],
            "AUTODATA_TARGET_MODEL": endpoint["model"],
            "AUTODATA_TARGET_DEPLOYMENT_ID": endpoint["deployment_id"],
            "AUTODATA_TARGET_CHECKPOINT_HASH": self.checkpoint_hash,
        }
        if endpoint.get("host_header"):
            environment["AUTODATA_TARGET_HOST_HEADER"] = endpoint["host_header"]
        return environment


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"{label} is unreadable") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return value


def _real_directory(value: str, label: str) -> Path:
    path = Path(value).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"{label} does not exist") from error
    if not resolved.is_dir():
        raise RuntimeError(f"{label} must be a directory")
    return resolved


def _same_path(left: Any, right: Path, label: str) -> None:
    if not isinstance(left, str):
        raise RuntimeError(f"merge receipt {label} is invalid")
    try:
        resolved = Path(left).expanduser().resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"merge receipt {label} does not exist") from error
    if resolved != right:
        raise RuntimeError(f"merge receipt {label} does not match the binding")


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value.lower()):
        raise RuntimeError(f"{label} must be a SHA-256 digest")
    return value.lower()


def _validate_endpoint(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) - {
        "url",
        "host_header",
        "model",
        "deployment_id",
    }:
        raise RuntimeError("target endpoint is malformed")
    required = ("url", "model", "deployment_id")
    if any(
        not isinstance(value.get(name), str) or not value[name].strip()
        for name in required
    ):
        raise RuntimeError("target endpoint is incomplete")
    parsed = urlsplit(value["url"])
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("target endpoint URL must be absolute HTTP(S)")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError(
            "target endpoint URL must not contain credentials or parameters"
        )
    deployment_id = value["deployment_id"].strip()
    if not _IDENTIFIER.fullmatch(deployment_id):
        raise RuntimeError("target deployment ID is invalid")
    endpoint = {
        "url": value["url"].rstrip("/"),
        "model": value["model"].strip(),
        "deployment_id": deployment_id,
    }
    host_header = value.get("host_header", "")
    if host_header:
        if not isinstance(host_header, str) or any(
            character.isspace() for character in host_header
        ):
            raise RuntimeError("target host header is invalid")
        endpoint["host_header"] = host_header
    return endpoint


def _verified_components(*, base: Path, adapter: Path, merged: Path) -> dict[str, Any]:
    receipt_path = merged / ".merge-complete.json"
    receipt = _json_file(receipt_path, "merge receipt")
    _same_path(receipt.get("base_checkpoint"), base, "base checkpoint")
    _same_path(receipt.get("adapter"), adapter, "adapter")
    _same_path(receipt.get("output"), merged, "output")

    files = {
        "adapter_config_sha256": adapter / "adapter_config.json",
        "adapter_model_sha256": adapter / "adapter_model.safetensors",
        "base_config_sha256": base / "config.json",
        "base_index_sha256": base / "model.safetensors.index.json",
    }
    verified: dict[str, str] = {}
    for field, path in files.items():
        expected = _require_digest(receipt.get(field), f"merge receipt {field}")
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"{field} does not match the merge receipt")
        verified[field] = actual

    adapter_config = _json_file(adapter / "adapter_config.json", "adapter config")
    _same_path(adapter_config.get("base_model_name_or_path"), base, "adapter base")
    if adapter_config.get("peft_type") != "LORA":
        raise RuntimeError("incumbent adapter is not a LoRA adapter")
    if (merged / "config.json").read_bytes() != (base / "config.json").read_bytes():
        raise RuntimeError("merged checkpoint config does not match the fixed base")

    shards = receipt.get("merged_shards")
    if (
        not isinstance(shards, list)
        or not shards
        or any(not isinstance(name, str) or Path(name).name != name for name in shards)
    ):
        raise RuntimeError("merge receipt shard list is invalid")
    actual_bytes = 0
    for name in shards:
        shard = merged / name
        if not shard.is_file():
            raise RuntimeError("merged checkpoint is missing a declared shard")
        actual_bytes += shard.stat().st_size
    if actual_bytes != receipt.get("merged_weight_bytes"):
        raise RuntimeError("merged checkpoint byte count does not match the receipt")
    merged_index = merged / "model.safetensors.index.json"
    if not merged_index.is_file():
        raise RuntimeError("merged checkpoint index is missing")

    return {
        **verified,
        "merge_receipt_sha256": _sha256(receipt_path),
        "merged_index_sha256": _sha256(merged_index),
        "merged_weight_bytes": actual_bytes,
        "merged_shards": list(shards),
        "merge_source_commit": receipt.get("source_commit"),
    }


def _identity_payload(value: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "schema": SCHEMA,
        "iteration": value["iteration"],
        "incumbent_run_id": value["incumbent_run_id"],
        "base_checkpoint": value["base_checkpoint"],
        "adapter_checkpoint": value["adapter_checkpoint"],
        "merged_checkpoint": value["merged_checkpoint"],
        "endpoint": value["endpoint"],
        "verified": value["verified"],
    }
    if value.get("schema") == SCHEMA_V1:
        payload["schema"] = SCHEMA_V1
    else:
        payload["chain_id"] = value["chain_id"]
    return payload


def _checkpoint_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        _identity_payload(value), allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def create_binding(
    *,
    iteration: int,
    incumbent_run_id: str,
    base_checkpoint: str,
    adapter_checkpoint: str,
    merged_checkpoint: str,
    endpoint: dict[str, str],
    chain_id: str | None = None,
) -> TargetBinding:
    if isinstance(iteration, bool) or iteration < 2:
        raise RuntimeError("adapter-backed target binding requires AAR iteration >= 2")
    if not _IDENTIFIER.fullmatch(incumbent_run_id):
        raise RuntimeError("incumbent run ID is invalid")
    if chain_id is not None and not _IDENTIFIER.fullmatch(chain_id):
        raise RuntimeError("chain ID is invalid")
    base = _real_directory(base_checkpoint, "base checkpoint")
    adapter = _real_directory(adapter_checkpoint, "adapter checkpoint")
    merged = _real_directory(merged_checkpoint, "merged checkpoint")
    value: dict[str, Any] = {
        "schema": SCHEMA if chain_id is not None else SCHEMA_V1,
        "iteration": iteration,
        "incumbent_run_id": incumbent_run_id,
        "base_checkpoint": str(base),
        "adapter_checkpoint": str(adapter),
        "merged_checkpoint": str(merged),
        "endpoint": _validate_endpoint(endpoint),
        "verified": _verified_components(base=base, adapter=adapter, merged=merged),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if chain_id is not None:
        value["chain_id"] = chain_id
    value["checkpoint_hash"] = _checkpoint_hash(value)
    return TargetBinding(value)


def validate_binding(value: Any, *, verify_files: bool = True) -> TargetBinding:
    if not isinstance(value, dict) or value.get("schema") not in {SCHEMA_V1, SCHEMA}:
        raise RuntimeError("target binding schema is invalid")
    required = {
        "schema",
        "iteration",
        "incumbent_run_id",
        "base_checkpoint",
        "adapter_checkpoint",
        "merged_checkpoint",
        "endpoint",
        "verified",
        "created_at",
        "checkpoint_hash",
    }
    if value["schema"] == SCHEMA:
        required.add("chain_id")
    if set(value) != required:
        raise RuntimeError("target binding fields are invalid")
    chain_id = value.get("chain_id")
    if chain_id is not None and not _IDENTIFIER.fullmatch(chain_id):
        raise RuntimeError("target binding chain ID is invalid")
    endpoint = _validate_endpoint(value["endpoint"])
    if endpoint != value["endpoint"]:
        raise RuntimeError("target endpoint is not canonical")
    expected = _checkpoint_hash(value)
    if value.get("checkpoint_hash") != expected:
        raise RuntimeError("target binding checkpoint hash is invalid")
    if verify_files:
        recreated = create_binding(
            iteration=value["iteration"],
            incumbent_run_id=value["incumbent_run_id"],
            base_checkpoint=value["base_checkpoint"],
            adapter_checkpoint=value["adapter_checkpoint"],
            merged_checkpoint=value["merged_checkpoint"],
            endpoint=endpoint,
            chain_id=chain_id,
        )
        if recreated.value["verified"] != value["verified"]:
            raise RuntimeError("target binding no longer matches checkpoint files")
        if recreated.checkpoint_hash != value["checkpoint_hash"]:
            raise RuntimeError("target binding identity changed during verification")
    return TargetBinding(dict(value))


def load_binding(path: Path, *, verify_files: bool = True) -> TargetBinding:
    return validate_binding(
        _json_file(path, "target binding"), verify_files=verify_files
    )


def write_binding(path: Path, binding: TargetBinding) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(binding.value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--iteration", required=True, type=int)
    create.add_argument("--incumbent-run-id", required=True)
    create.add_argument("--chain-id")
    create.add_argument("--base-checkpoint", required=True)
    create.add_argument("--adapter-checkpoint", required=True)
    create.add_argument("--merged-checkpoint", required=True)
    create.add_argument("--target-url", required=True)
    create.add_argument("--target-host-header", default="")
    create.add_argument("--target-model", required=True)
    create.add_argument("--target-deployment-id", required=True)
    create.add_argument("--output", required=True, type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("binding", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "create":
        binding = create_binding(
            iteration=args.iteration,
            incumbent_run_id=args.incumbent_run_id,
            base_checkpoint=args.base_checkpoint,
            adapter_checkpoint=args.adapter_checkpoint,
            merged_checkpoint=args.merged_checkpoint,
            chain_id=args.chain_id,
            endpoint={
                "url": args.target_url,
                "host_header": args.target_host_header,
                "model": args.target_model,
                "deployment_id": args.target_deployment_id,
            },
        )
        write_binding(args.output, binding)
    else:
        binding = load_binding(args.binding)
    print(json.dumps({"checkpoint_hash": binding.checkpoint_hash, "valid": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
