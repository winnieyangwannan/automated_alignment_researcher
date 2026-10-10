#!/usr/bin/env python3
"""GPU worker: turn one immutable, evaluated PEFT adapter into a verified fat SPipe."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import subprocess
import sys
import zipfile
from dataclasses import fields
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source(adapter_dir: Path, expected_path: Path) -> None:
    expected = read_json(expected_path)
    actual_files = sorted(
        path for path in adapter_dir.rglob("*") if path.is_file() and not path.is_symlink()
    )
    actual_names = {str(path.relative_to(adapter_dir)) for path in actual_files}
    if actual_names != set(expected):
        missing = sorted(set(expected) - actual_names)
        extra = sorted(actual_names - set(expected))
        raise RuntimeError(f"adapter file set changed; missing={missing}, extra={extra}")
    for path in actual_files:
        relative = str(path.relative_to(adapter_dir))
        record = expected[relative]
        if path.stat().st_size != record["size_bytes"] or sha256(path) != record["sha256"]:
            raise RuntimeError(f"adapter changed after selection: {relative}")


def embed_adapter(control: Any) -> None:
    """Freeze a stock LoadLoRA path as an embedded LoRAArtifact."""
    args = {
        field.name: getattr(control.args, field.name)
        for field in fields(control.args)
        if field.init
    }
    control.export_state = lambda: {"artifact": control.export_artifact()}
    control.frozen_form = lambda state: (
        "structural_control/load_lora",
        {**args, "path": state["artifact"]},
    )


def local_resolved_paths(manifest: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and Path(value).is_absolute() and Path(value).exists():
            found.append(value)

    for entry in manifest["controls"]:
        resolved = entry.get("resolved")
        if resolved is None:
            walk(entry.get("args"))
        else:
            for item in resolved if isinstance(resolved, list) else [resolved]:
                walk(item.get("args"))
    return found


def run_checker(output_dir: Path, requested_model: str) -> dict[str, Any]:
    from starterkit import BASE_MODELS

    report_path = output_dir / "check_report.json"
    completed = subprocess.run(
        [sys.executable, "-m", "starterkit.check", str(output_dir), "--out", str(report_path)],
        capture_output=True,
        text=True,
    )
    if not report_path.is_file():
        raise RuntimeError(
            "starter-kit checker wrote no report:\n" + completed.stdout + completed.stderr
        )
    report = read_json(report_path)
    expected = {
        f"no bundle for {model}; a submission covers every base model."
        for model in BASE_MODELS
        if model != requested_model
    }
    report["partial"] = bool(expected)
    report["partial_ok"] = bool(expected) and set(report.get("errors", [])) == expected
    report["requested_models"] = [requested_model]
    write_json(report_path, report)
    if not (report.get("ok") is True or report["partial_ok"]):
        raise RuntimeError(f"starter-kit validation failed: {report.get('errors')}")
    return report


def package(args: argparse.Namespace) -> dict[str, Any]:
    adapter_dir = args.adapter_dir.resolve(strict=True)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    verify_source(adapter_dir, args.source_checksums.resolve(strict=True))

    from starterkit import PIPELINE_KWARGS, model_slug
    from steerability.algorithms.core.steering_pipeline import SteeringPipeline
    from steerability.algorithms.structural_control.load_lora import LoadLoRA
    from steerability.spipe import SPipe
    from transformers import AutoModelForCausalLM
    import torch

    expected_name = f"{model_slug(args.base_model)}.spipe"
    if args.expected_filename != expected_name:
        raise RuntimeError(
            f"expected filename mismatch: {args.expected_filename!r} != {expected_name!r}"
        )
    output = output_dir / expected_name
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing bundle: {output}")

    control = LoadLoRA(path=str(adapter_dir), base_model=args.base_model)
    embed_adapter(control)
    model_kwargs = dict(PIPELINE_KWARGS.get("hf_model_kwargs", {}))
    subject = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        **model_kwargs,
        device_map=None,
    ).to("cuda")
    pipeline = SteeringPipeline(
        args.base_model,
        controls=[control],
        backend="huggingface",
        model=subject,
    )
    try:
        pipeline.steer()
        pipeline.to_spipe(freeze=True).save(str(output), artifacts="fat")
    finally:
        try:
            pipeline.release_backends()
        except Exception:
            pass
        del pipeline
        del subject
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    spipe = SPipe.load(output)
    verification = spipe.verify()
    if not verification.ok:
        raise RuntimeError(verification.render())
    manifest = spipe.manifest
    if manifest.get("lock") is None:
        raise RuntimeError("bundle is not frozen")
    if manifest.get("code_dependent"):
        raise RuntimeError("generated LoadLoRA bundle unexpectedly depends on code")
    local_paths = local_resolved_paths(manifest)
    if local_paths:
        raise RuntimeError(f"bundle resolves container-local path(s): {local_paths}")
    with zipfile.ZipFile(output) as archive:
        artifact_members = [name for name in archive.namelist() if name.startswith("artifacts/")]
        if not artifact_members:
            raise RuntimeError("fat bundle contains no embedded artifacts")

    checker = run_checker(output_dir, args.base_model)
    digest = sha256(output)
    report = {
        "ok": True,
        "bundle": str(output),
        "sha256": digest,
        "size_bytes": output.stat().st_size,
        "format": manifest.get("format"),
        "toolkit_version": manifest.get("toolkit_version"),
        "model": manifest.get("model"),
        "controls": len(manifest.get("controls", [])),
        "frozen": manifest.get("lock") is not None,
        "code_dependent": manifest.get("code_dependent"),
        "embedded_artifact_members": len(artifact_members),
        "verify_warnings": verification.warnings,
        "starterkit_ok": checker.get("ok"),
        "starterkit_partial_ok": checker.get("partial_ok"),
    }
    write_json(output_dir / "bundle_report.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-checksums", required=True, type=Path)
    parser.add_argument("--expected-filename", required=True)
    return parser


def main() -> int:
    report = package(build_parser().parse_args())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
