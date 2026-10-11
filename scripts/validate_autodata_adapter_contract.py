#!/usr/bin/env python3
"""Fail closed when pinned native serialization and AAR adapters disagree."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from autodata.models import ExecutionSpec, GroundingSpec

from aar.infrastructure.autodata_execution_contract import (
    canonical_execution_manifest,
    canonical_meta_manifest_from_default,
    canonical_production_manifest_from_meta,
)
from scripts.autodata_lifecycle_supervisor import (
    _materialize_canonical_meta_pipeline,
)


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _settings() -> dict[str, Any]:
    policy = {
        "environment": "oci-runner-firecracker-large",
        "image": "python@sha256:" + "a" * 64,
        "expected_image_id": "b" * 64,
        "max_cpus": 2,
        "max_memory_mb": 2048,
        "required_solve_env": {"AUTODATA_TARGET_ENABLED": "1"},
    }
    return {
        "meta": {
            "maximum_iterations": 3,
            "minimum_iterations": 3,
            "early_stop_patience": 3,
            "tuning_tasks": 64,
            "validation_tasks": 32,
            "test_tasks": 32,
        },
        "production": {
            "initial_tasks": 1250,
            "required_rows": 1000,
            "minimum_successful_task_fraction": 0.95,
        },
        "concurrency": 32,
        "campaign_policy": policy,
        "broker_url": "http://127.0.0.1:12345",
        "meta_wall_seconds": 604800,
        "production_wall_seconds": 604800,
        "meta_evaluation_attempts": 608,
        "meta_finalization_retry_attempts": 96,
        "meta_model_task_attempts": 704,
        "meta_task_attempts": 707,
        "pipeline_checks_per_iteration": 1,
        "production_task_attempts": 2500,
    }


def _executor(settings: dict[str, Any]) -> dict[str, Any]:
    policy = settings["campaign_policy"]
    return {
        "kind": "sandoq-firecracker",
        "environment": policy["environment"],
        "image": policy["image"],
        "expected_image_id": policy["expected_image_id"],
        "broker_url": settings["broker_url"],
        "broker_auth_secret_ref": "AAR_AUTODATA_CAPABILITY",
        "model_backed": True,
        "cpus": policy["max_cpus"],
        "memory_mb": policy["max_memory_mb"],
        "network": "host",
        "workdir": "/workspace",
        "non_secret_env": policy["required_solve_env"],
    }


def validate(scratch_root: Path) -> dict[str, Any]:
    settings = _settings()
    with tempfile.TemporaryDirectory(
        prefix="autodata-adapter-contract.", dir=scratch_root
    ) as temporary:
        root = Path(temporary)
        source = root / "source"
        pipeline_manifest = {
            "schema": "autodata.pipeline/v1",
            "checks": [{"argv": ["python3", "recipe/check.py"]}],
        }
        settings["trusted_pipeline_manifest"] = pipeline_manifest
        pipeline = _write_json(
            source / "autodata.pipeline.json", pipeline_manifest
        )
        all_ids = [f"contract-task-{index:04d}" for index in range(128)]
        grounding = _write_json(
            source / "grounding" / "manifest.json",
            {
                "schema": "autodata.grounding/v1",
                "name": "adapter-contract-grounding",
                "description": "Synthetic adapter compatibility check.",
                "sources": [],
                "coverage_dimensions": [],
                "dry_run_task_ids": all_ids[:3],
                "tasks": [{"id": task_id} for task_id in all_ids],
            },
        )
        native_default = json.loads(
            json.dumps(
                ExecutionSpec.from_dict(
                    {
                        "schema": "autodata.execution/v1",
                        "mode": "meta_optimize",
                        "grounding": {
                            "manifest_path": "grounding/manifest.json",
                            "digest": _digest(grounding),
                        },
                        "split_seed": 0,
                        "executor": _executor(settings),
                        "budget": {
                            "max_iterations": 1,
                            "max_task_attempts": 4096,
                            "max_wall_seconds": 6300,
                        },
                        "concurrency": 32,
                        "secret_references": ["AAR_AUTODATA_CAPABILITY"],
                    }
                ).to_dict()
            )
        )
        artifacts = root / "artifacts"
        artifacts.mkdir()
        canonical_pipeline, materialized_default = (
            _materialize_canonical_meta_pipeline(
                source_pipeline=pipeline,
                default_manifest=native_default,
                artifacts=artifacts,
                settings=settings,
            )
        )
        canonical_meta = canonical_meta_manifest_from_default(
            default_manifest=materialized_default,
            pipeline_manifest=canonical_pipeline,
            settings=settings,
        )
        meta_root = canonical_pipeline.parent
        native_meta_grounding = GroundingSpec.from_dict(
            json.loads(
                (meta_root / canonical_meta["grounding"]["manifest_path"]).read_text(
                    encoding="utf-8"
                )
            )
        )
        native_test_grounding = GroundingSpec.from_dict(
            json.loads(
                (
                    meta_root
                    / canonical_meta["test_grounding"]["manifest_path"]
                ).read_text(encoding="utf-8")
            )
        )
        if len(native_meta_grounding.tasks) != 96 or len(
            native_test_grounding.tasks
        ) != 32:
            raise RuntimeError("native grounding serialization changed partition")
        native_meta = json.loads(
            json.dumps(ExecutionSpec.from_dict(canonical_meta).to_dict())
        )
        expected_budget = {
            "max_iterations": 3,
            "min_iterations": 3,
            "early_stop_patience": 3,
            "max_task_attempts": 707,
            "max_wall_seconds": 604800,
        }
        if native_meta["budget"] != expected_budget:
            raise RuntimeError("native meta serialization changed trusted budget")
        if len(native_meta["tuning_task_ids"]) != 64 or len(
            native_meta["validation_task_ids"]
        ) != 32:
            raise RuntimeError("native meta serialization changed trusted partition")

        production_root = root / "production"
        production_pipeline = _write_json(
            production_root / "autodata.pipeline.json", {}
        )
        production_ids = [f"safety-prod-{index:04d}" for index in range(1250)]
        production_grounding = _write_json(
            production_root / "grounding" / "production-manifest.json",
            {
                "schema": "autodata.grounding/v1",
                "name": "adapter-contract-production",
                "description": "Synthetic production adapter compatibility check.",
                "sources": [],
                "coverage_dimensions": [],
                "dry_run_task_ids": production_ids[:3],
                "tasks": [{"id": task_id} for task_id in production_ids],
            },
        )
        canonical_production = canonical_production_manifest_from_meta(
            meta_manifest=native_meta,
            pipeline_manifest=production_pipeline,
            production_grounding={
                "manifest_path": "grounding/production-manifest.json",
                "digest": _digest(production_grounding),
            },
            settings=settings,
            reserved_task_ids=all_ids,
        )
        native_production = json.loads(
            json.dumps(ExecutionSpec.from_dict(canonical_production).to_dict())
        )
        GroundingSpec.from_dict(
            json.loads(production_grounding.read_text(encoding="utf-8"))
        )
        if native_production["budget"] != {
            "max_iterations": 0,
            "min_iterations": 0,
            "early_stop_patience": None,
            "max_task_attempts": 2500,
            "max_wall_seconds": 604800,
        }:
            raise RuntimeError("native production serialization changed trusted budget")
        if native_production.get("finalization") != {
            "minimum_generated_items": 1000,
            "minimum_successful_task_fraction": 0.95,
        }:
            raise RuntimeError("native production serialization changed finalization")
        native_production_path = _write_json(
            root / "native-production.execution.json", native_production
        )
        replayed_production = canonical_execution_manifest(
            proposed_manifest=native_production_path,
            pipeline_manifest=production_pipeline,
            settings=settings,
            reserved_task_ids=all_ids,
        )
        if replayed_production != canonical_production:
            raise RuntimeError("AAR changed native production persistence on replay")

        deterministic_native_attempts = settings["meta_evaluation_attempts"] + (
            settings["pipeline_checks_per_iteration"]
            * settings["meta"]["maximum_iterations"]
        )
        recovery_attempts = settings["meta_task_attempts"] - deterministic_native_attempts
        if deterministic_native_attempts != 611 or recovery_attempts != 96:
            raise RuntimeError("trusted native meta attempt ledger changed")

    return {
        "schema": "aar.autodata.adapter-contract-check/v1",
        "status": "passed",
        "native_default_fields": sorted(native_default),
        "native_default_budget_fields": sorted(native_default["budget"]),
        "meta_iterations": 3,
        "meta_evaluation_attempts": settings["meta_evaluation_attempts"],
        "meta_deterministic_native_attempts": deterministic_native_attempts,
        "meta_configured_native_attempts": settings["meta_task_attempts"],
        "meta_recovery_attempts": recovery_attempts,
        "partition_counts": [64, 32, 32],
        "production_source_tasks": 1250,
        "production_required_rows": 1000,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch-root", type=Path, required=True)
    args = parser.parse_args()
    scratch_root = args.scratch_root.resolve(strict=True)
    if scratch_root.is_symlink() or not scratch_root.is_dir():
        raise SystemExit("adapter contract scratch root must be a real directory")
    print(json.dumps(validate(scratch_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
