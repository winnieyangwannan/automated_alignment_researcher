from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from aar.autodata_campaign_policy import (
    atomic_write_json,
    create_base_target_manifest,
)
from aar.autodata_run_config import (
    compile_run_config,
    inspect_configs,
    load_runtime_profile,
    validate_compiled_config,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "configs/autodata/target_aware_local_v1.yaml"
RUN = ROOT / "experiments/dishonest_sycophancy_concealing/run_12" / "autodata_run.yaml"


def _base_binding(tmp_path: Path, *, chain: str = "alpha") -> Path:
    base = tmp_path / "base"
    base.mkdir()
    (base / "config.json").write_text("{}\n", encoding="utf-8")
    (base / "model.safetensors.index.json").write_text(
        '{"weight_map":{}}\n', encoding="utf-8"
    )
    binding = tmp_path / "target-binding.json"
    atomic_write_json(
        binding,
        create_base_target_manifest(
            iteration=1,
            chain_id=chain,
            base_checkpoint=base,
            endpoint={
                "url": "http://gateway/v1",
                "host_header": "ram-inference-gateway.ingress.",
                "model": "gemma-4-31B-it",
                "deployment_id": "alpha-target-i1",
            },
        ),
    )
    return binding


def test_run12_yaml_compiles_every_runtime_artifact(tmp_path: Path) -> None:
    output = tmp_path / "compiled"
    resolved = compile_run_config(
        profile_path=PROFILE,
        run_path=RUN,
        target_binding_path=_base_binding(tmp_path),
        chain="alpha",
        repo=ROOT,
        output_dir=output,
    )
    policy = json.loads((output / "campaign-policy.json").read_text())
    contract = json.loads((output / "autodata-training-data-contract.json").read_text())
    runtime = (output / "autodata-runtime.env").read_text()

    assert resolved["target"]["challenge_provenance_required"] is True
    assert resolved["target"]["provider_order"] == ["generator", "target", "judge"]
    assert policy["runner"] == "local-bwrap"
    assert policy["required_solve_env"]["AUTODATA_TARGET_ENABLED"] == "1"
    assert (
        policy["required_solve_env"]["AUTODATA_GENERATOR_DEPLOYMENT_ID"]
        == "autodata_8-kimi26"
    )
    assert policy["required_solve_env"]["AUTODATA_GENERATOR_MAX_OUTPUT"] == "65536"
    assert policy["required_solve_env"]["AUTODATA_JUDGE_MAX_INPUT"] == "1000000"
    assert policy["required_solve_env"]["AUTODATA_TARGET_MAX_OUTPUT"] == "65536"
    assert contract["target"]["required"] is True
    assert contract["required_rows"] == 1000
    assert "export AAR_AUTODATA_CONCURRENCY=32\n" in runtime
    assert "export AAR_AUTODATA_META_MAX_ITERATIONS=3\n" in runtime
    assert "export AAR_AUTODATA_PRODUCTION_ROWS=1000\n" in runtime
    validated = validate_compiled_config(
        output / "resolved-config.yaml",
        output / "campaign-policy.json",
        output / "autodata-training-data-contract.json",
    )
    assert validated["chain"] == "alpha"


def test_compiled_config_rejects_artifact_tamper(tmp_path: Path) -> None:
    output = tmp_path / "compiled"
    compile_run_config(
        profile_path=PROFILE,
        run_path=RUN,
        target_binding_path=_base_binding(tmp_path),
        chain="alpha",
        repo=ROOT,
        output_dir=output,
    )
    policy_path = output / "campaign-policy.json"
    policy = json.loads(policy_path.read_text())
    policy["required_solve_env"]["AUTODATA_TARGET_ENABLED"] = "0"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match="artifact changed"):
        validate_compiled_config(
            output / "resolved-config.yaml",
            policy_path,
            output / "autodata-training-data-contract.json",
        )


def test_compiler_rejects_cross_chain_target_binding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="binding chain"):
        compile_run_config(
            profile_path=PROFILE,
            run_path=RUN,
            target_binding_path=_base_binding(tmp_path, chain="beta"),
            chain="alpha",
            repo=ROOT,
            output_dir=tmp_path / "compiled",
        )


def test_profile_requires_all_target_aware_gates(tmp_path: Path) -> None:
    value = yaml.safe_load(PROFILE.read_text())
    value["target"]["require_challenge_provenance"] = False
    path = tmp_path / "unsafe-profile.yaml"
    path.write_text(yaml.safe_dump(value), encoding="utf-8")

    with pytest.raises(ValueError, match="every fail-closed target gate"):
        load_runtime_profile(path)


def test_inspect_reports_static_yaml_values() -> None:
    inspected = inspect_configs(PROFILE, RUN)
    assert inspected == {
        "profile_name": "target-aware-local-v1",
        "concurrency_per_chain": 32,
        "model_request_max_attempts": 3,
        "researcher_kimi_deployment": "aar_8-kimi26",
        "generator_kimi_deployment": "autodata_8-kimi26",
        "chains": ["alpha", "beta", "gamma", "delta", "epsilon"],
        "target_pairs_per_chain": 5,
        "target_enabled": True,
        "generator_url": "http://fair-cw-use2-1-ingress-slurm-ingress/v1",
        "generator_host_header": "ram-inference-gateway.ingress.",
        "generator_model": "Kimi-K2.6",
        "target_model": "gemma-4-31B-it",
    }
