#!/usr/bin/env python3
"""Verify Trial 14 parity and offline recipe compatibility before submission."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from aar.autodata_campaign_policy import atomic_write_json, create_base_target_manifest
from aar.autodata_run_config import (
    _judge_rubric_identity,
    compile_run_config,
    load_run_config,
    load_runtime_profile,
    resolve_runtime_profile_path,
    validate_compiled_config,
)
from aar.research_loop.autodata_bootstrap import _stage_reviewed_recipe


def main() -> None:
    gate = Path(__file__).resolve().parent.parent
    repo = gate.parents[4]
    reference_path = (
        repo
        / "experiments/dishonest_sycophancy_concealing/run_13/canary/trial_14/autodata_run.yaml"
    )
    candidate_path = gate / "config/run.yaml"
    reference = load_run_config(reference_path)
    candidate = load_run_config(candidate_path)
    expected = dict(reference)
    expected.update(
        run_id="run14-canary-v3-recipe-comparison",
        recipe_root="aar/autodata_recipes/dishonest_sycophancy_concealing",
    )
    if candidate != expected:
        raise ValueError("Run 14 must change only run_id and the requested recipe_root")
    profile_path = resolve_runtime_profile_path(run_path=candidate_path, repo=repo)
    profile = load_runtime_profile(profile_path)
    _, rubric_identity = _judge_rubric_identity(repo, candidate)
    os.environ.update(
        AAR_AUTODATA_RECIPE_ROOT=str(repo / candidate["recipe_root"]),
        AAR_AUTODATA_TUNING_TASKS=str(candidate["meta_optimization"]["tuning_tasks"]),
        AAR_AUTODATA_VALIDATION_TASKS=str(
            candidate["meta_optimization"]["validation_tasks"]
        ),
        AAR_AUTODATA_TEST_TASKS=str(candidate["meta_optimization"]["test_tasks"]),
    )
    with tempfile.TemporaryDirectory(prefix="aar-run14-config-") as temporary:
        run_root = Path(temporary)
        base = run_root / "offline-base"
        base.mkdir()
        (base / "config.json").write_text("{}\n")
        (base / "model.safetensors.index.json").write_text('{"weight_map":{}}\n')
        binding = run_root / "offline-target-binding.json"
        atomic_write_json(
            binding,
            create_base_target_manifest(
                iteration=1,
                chain_id="alpha",
                base_checkpoint=base,
                endpoint={
                    "url": "http://offline.invalid/v1",
                    "host_header": "ram-inference-gateway.ingress.",
                    "model": "gemma-4-31B-it",
                    "deployment_id": "run14-offline-config-check",
                },
            ),
        )
        resolved = compile_run_config(
            profile_path=profile_path,
            run_path=candidate_path,
            target_binding_path=binding,
            chain="alpha",
            repo=repo,
            output_dir=run_root / "compiled",
        )
        artifacts = resolved["artifacts"]
        validate_compiled_config(
            run_root / "compiled/resolved-config.yaml",
            Path(artifacts["campaign_policy"]),
            Path(artifacts["training_data_contract"]),
        )
        os.environ["AAR_AUTODATA_TRAINING_DATA_CONTRACT"] = artifacts[
            "training_data_contract"
        ]
        (run_root / "draft").mkdir()
        _stage_reviewed_recipe(run_root)
    print(
        json.dumps(
            {
                "status": "pass",
                "changed_fields": ["run_id", "recipe_root"],
                "recipe_root": candidate["recipe_root"],
                "generator_model": profile["providers"]["generator"]["model"],
                "judge_rubric": rubric_identity,
                "host_recipe_staging": "pass",
                "model_calls": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
