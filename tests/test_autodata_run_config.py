from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml

from aar.autodata_campaign_policy import (
    atomic_write_json,
    create_base_target_manifest,
)
from aar.autodata_run_config import (
    DEFAULT_TARGET_FEEDBACK_MAX_ATTEMPTS,
    compile_run_config,
    inspect_configs,
    load_run_config,
    load_runtime_profile,
    resolve_runtime_profile_path,
    validate_compiled_config,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "configs/autodata/target_aware_local_v1.yaml"
CANARY2_PROFILE = ROOT / "configs/autodata/target_aware_local_c32_v1.yaml"
RUN = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_12/config/autodata_run.yaml"
)
CANARY2_RUN = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/autodata_run.yaml"
)


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
    assert (
        policy["required_solve_env"]["AUTODATA_TARGET_FEEDBACK_MAX_ATTEMPTS"]
        == "5"
    )
    assert contract["target"]["required"] is True
    assert contract["required_rows"] == 1000
    rubric_path = (
        ROOT
        / "aar/autodata_recipes/dishonest_sycophancy_concealing/recipe/judge_rubric.json"
    )
    assert contract["judge_rubric"] == {
        "version": "run9-axis-conditioned-v3",
        "sha256": "sha256:" + hashlib.sha256(rubric_path.read_bytes()).hexdigest(),
    }
    assert resolved["judge_rubric_source"] == str(rubric_path)
    assert "export AAR_AUTODATA_CONCURRENCY=8\n" in runtime
    assert "export AAR_AUTODATA_META_MAX_ITERATIONS=3\n" in runtime
    assert "export AAR_AUTODATA_TARGET_FEEDBACK_MAX_ATTEMPTS=5\n" in runtime
    assert "export AAR_AUTODATA_AUTHORING_MAX_WALL_SECONDS=1800\n" in runtime
    assert "export AAR_AUTODATA_PRODUCTION_ROWS=1000\n" in runtime
    assert (
        "export AAR_AUTODATA_BOOTSTRAP_CANARY_STOP_AFTER=production\n" in runtime
    )
    assert f"export AAR_RUN_STORAGE_ROOT=/checkpoint/ram/{os.environ['USER']}\n" in runtime
    assert "export AAR_KEEP_CHECKPOINTS=0\n" in runtime
    assert "export AAR_EVAL_MEM=0\n" in runtime
    assert "export EVAL_MAX_TRUNCATION_RATE=0.2\n" in runtime
    assert "export AAR_EXPECTED_MAX_TRUNCATION_RATE=0.2\n" in runtime
    assert "export AAR_AGENT_BACKEND=kimi\n" in runtime
    assert "export AAR_KIMI_TURN_TIMEOUT_SECONDS=1800\n" in runtime
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


def test_canary2_compiles_independent_1000_row_training_smoke_contract(
    tmp_path: Path,
) -> None:
    output = tmp_path / "canary2-compiled"
    compile_run_config(
        profile_path=CANARY2_PROFILE,
        run_path=CANARY2_RUN,
        target_binding_path=_base_binding(tmp_path),
        chain="alpha",
        repo=ROOT,
        output_dir=output,
    )
    contract = json.loads((output / "autodata-training-data-contract.json").read_text())
    runtime = (output / "autodata-runtime.env").read_text()

    assert contract["required_rows"] == 1000
    assert "export AAR_AUTODATA_PROFILE=target-aware-local-c32-v1\n" in runtime
    assert "export AAR_AUTODATA_CONCURRENCY=32\n" in runtime
    assert "export AAR_AUTODATA_PRODUCTION_ROWS=1000\n" in runtime
    assert "export AAR_AUTODATA_PRODUCTION_INITIAL_TASKS=1250\n" in runtime
    assert "AAR_AUTODATA_PRODUCTION_MAX_TASKS" not in runtime
    assert "export AAR_AUTODATA_PRODUCTION_MIN_SUCCESS_FRACTION=0.95\n" in runtime
    assert "export AAR_AUTODATA_AUTHORING_MAX_WALL_SECONDS=604800\n" in runtime
    assert "export AAR_AUTODATA_STAGE_TIMEOUT_POLICY=observe-only\n" in runtime
    assert "export AAR_AUTODATA_NATIVE_SCHEMA_WALL_SECONDS=604800\n" in runtime


def test_canary2_run_yaml_selects_and_enforces_its_shared_profile() -> None:
    run = load_run_config(CANARY2_RUN)

    assert run["runtime_profile"] == (
        "configs/autodata/target_aware_local_c32_v1.yaml"
    )
    assert resolve_runtime_profile_path(
        run_path=CANARY2_RUN,
        repo=ROOT,
    ) == CANARY2_PROFILE
    with pytest.raises(ValueError, match="does not match the run config"):
        resolve_runtime_profile_path(
            run_path=CANARY2_RUN,
            repo=ROOT,
            profile_path=PROFILE,
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


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("storage", "root", "relative/path", "absolute path"),
        ("storage", "keep_checkpoints", "yes", "must be boolean"),
        ("evaluation", "memory", "all", "Slurm memory value"),
        ("evaluation", "max_truncation_rate", 1.1, "between zero and one"),
        ("agent", "backend", "autodata", "must be claude or kimi"),
        ("agent", "turn_timeout_seconds", 0, "positive integer"),
        ("authoring", "max_wall_seconds", 0, "positive integer"),
    ],
)
def test_run_config_rejects_invalid_operational_policy(
    tmp_path: Path, section: str, key: str, value: object, message: str
) -> None:
    config = yaml.safe_load(RUN.read_text())
    config[section][key] = value
    path = tmp_path / "invalid-run.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_run_config(path)


def test_inspect_reports_static_yaml_values() -> None:
    inspected = inspect_configs(PROFILE, RUN)
    assert inspected == {
        "profile_name": "target-aware-local-v1",
        "concurrency_per_chain": 8,
        "model_request_max_attempts": 3,
        "target_feedback_max_attempts": 5,
        "authoring_max_wall_seconds": 1800,
        "researcher_kimi_deployment": "aar_8-kimi26",
        "generator_kimi_deployment": "autodata_8-kimi26",
        "chains": ["alpha", "beta", "gamma", "delta", "epsilon"],
        "target_pairs_per_chain": 5,
        "bootstrap_canary_stop_after": "production",
        "target_enabled": True,
        "generator_url": "http://fair-cw-use2-1-ingress-slurm-ingress/v1",
        "generator_host_header": "ram-inference-gateway.ingress.",
        "generator_model": "Kimi-K2.6",
        "target_model": "gemma-4-31B-it",
        "storage_root": f"/checkpoint/ram/{os.environ['USER']}",
        "keep_checkpoints": False,
        "evaluation_memory": "0",
        "max_truncation_rate": 0.2,
        "agent_backend": "kimi",
        "turn_timeout_seconds": 1800,
    }


@pytest.mark.parametrize("generation", [None, {}])
def test_run_config_defaults_target_feedback_attempts_to_five(
    tmp_path: Path, generation: dict[str, object] | None
) -> None:
    config = yaml.safe_load(RUN.read_text())
    if generation is None:
        config.pop("generation")
    else:
        config["generation"] = generation
    path = tmp_path / "default-generation.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")

    loaded = load_run_config(path)

    assert DEFAULT_TARGET_FEEDBACK_MAX_ATTEMPTS == 5
    assert loaded["generation"]["target_feedback_max_attempts"] == 5


def test_run_config_rejects_non_production_bootstrap_stop(tmp_path: Path) -> None:
    config = yaml.safe_load(RUN.read_text())
    config["bootstrap_canary"]["stop_after"] = "evaluation"
    path = tmp_path / "invalid-canary.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(
        ValueError, match="stop_after must be production or training_smoke"
    ):
        load_run_config(path)
