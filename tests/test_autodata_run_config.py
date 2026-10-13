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
from aar.infrastructure.autodata_execution_contract import operator_execution_settings


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "configs/autodata/target_aware_local_v1.yaml"
CANARY2_PROFILE = ROOT / "configs/autodata/target_aware_local_c32_v1.yaml"
RUN17_PROFILE = (
    ROOT / "configs/autodata/target_aware_model_api_claude_opus_4_8_c32_v1.yaml"
)
RUN = (
    ROOT / "experiments/dishonest_sycophancy_concealing/run_12/config/autodata_run.yaml"
)
CANARY2_RUN = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_2/autodata_run.yaml"
)
TRIAL16_RUN = (
    ROOT
    / "experiments"
    / "dishonest_sycophancy_concealing"
    / "run_12"
    / "canary"
    / "canary_2"
    / "trial_16"
    / "autodata_run.yaml"
)
TRIAL17_RUN = TRIAL16_RUN.parent.parent / "trial_17" / "autodata_run.yaml"
TRIAL18_RUN = TRIAL16_RUN.parent.parent / "trial_18" / "autodata_run.yaml"
TRIAL19_RUN = TRIAL16_RUN.parent.parent / "trial_19" / "autodata_run.yaml"
TRIAL20_RUN = TRIAL16_RUN.parent.parent / "trial_20" / "autodata_run.yaml"
TRIAL21_RUN = TRIAL16_RUN.parent.parent / "trial_21" / "autodata_run.yaml"
TRIAL22_RUN = TRIAL16_RUN.parent.parent / "trial_22" / "autodata_run.yaml"
TRIAL26_RUN = TRIAL16_RUN.parent.parent / "trial_26" / "autodata_run.yaml"
TRIAL27_RUN = TRIAL16_RUN.parent.parent / "trial_27" / "autodata_run.yaml"
RUN17 = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_17/config/run.yaml"
)
RUN13_TRIAL13 = (
    ROOT
    / "experiments/dishonest_sycophancy_concealing/run_13/canary/trial_13/autodata_run.yaml"
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
        policy["required_solve_env"]["AUTODATA_GENERATOR_PROTOCOL"]
        == "openai_chat_completions"
    )
    assert (
        policy["required_solve_env"]["AUTODATA_GENERATOR_DEPLOYMENT_ID"]
        == "autodata_8-kimi26"
    )
    assert policy["required_solve_env"]["AUTODATA_GENERATOR_MAX_OUTPUT"] == "65536"
    assert policy["required_solve_env"]["AUTODATA_JUDGE_MAX_INPUT"] == "1000000"
    assert policy["required_solve_env"]["AUTODATA_TARGET_MAX_OUTPUT"] == "65536"
    assert policy["required_solve_env"]["AUTODATA_TARGET_FEEDBACK_MAX_ATTEMPTS"] == "5"
    assert policy["required_solve_env"]["AUTODATA_JUDGE_FORMAT_MAX_ATTEMPTS"] == "2"
    assert (
        policy["required_solve_env"]["AUTODATA_JUDGE_STRUCTURED_OUTPUT_MODE"]
        == "responses_json_schema"
    )
    assert contract["target"]["required"] is True
    assert contract["required_rows"] == 1000
    rubric_path = (
        ROOT
        / "aar/autodata_recipes/dishonest_sycophancy_concealing/recipe/judge_rubric.json"
    )
    assert contract["judge_rubric"] == {
        "version": "run9-axis-conditioned-v4",
        "sha256": "sha256:" + hashlib.sha256(rubric_path.read_bytes()).hexdigest(),
    }
    assert resolved["judge_rubric_source"] == str(rubric_path)
    assert "export AAR_AUTODATA_CONCURRENCY=8\n" in runtime
    assert "export AAR_AUTODATA_META_MAX_ITERATIONS=3\n" in runtime
    assert "export AAR_AUTODATA_TARGET_FEEDBACK_MAX_ATTEMPTS=5\n" in runtime
    assert "export AAR_AUTODATA_JUDGE_FORMAT_MAX_ATTEMPTS=2\n" in runtime
    assert (
        "export AAR_AUTODATA_JUDGE_STRUCTURED_OUTPUT_MODE=responses_json_schema\n"
        in runtime
    )
    assert "export AAR_AUTODATA_AUTHORING_MAX_WALL_SECONDS=1800\n" in runtime
    assert "export AAR_AUTODATA_PRODUCTION_ROWS=1000\n" in runtime
    assert "export AAR_AUTODATA_BOOTSTRAP_CANARY_STOP_AFTER=production\n" in runtime
    assert (
        f"export AAR_RUN_STORAGE_ROOT=/checkpoint/ram/{os.environ['USER']}\n" in runtime
    )
    assert "export AAR_KEEP_CHECKPOINTS=0\n" in runtime
    assert "export AAR_ADAPTER_RETENTION=all\n" in runtime
    assert "export AAR_EVAL_MEM=0\n" in runtime
    assert "export EVAL_MAX_TRUNCATION_RATE=0.2\n" in runtime
    assert "export AAR_EXPECTED_MAX_TRUNCATION_RATE=0.2\n" in runtime
    assert "export AAR_AGENT_BACKEND=kimi\n" in runtime
    assert "export AAR_AGENT_TURN_TIMEOUT_SECONDS=1800\n" in runtime
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
    resolved = compile_run_config(
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
    recipe_root = ROOT / "aar/autodata_recipes/dishonest_sycophancy_concealing_v1"
    assert resolved["run"]["recipe_root"] == (
        "aar/autodata_recipes/dishonest_sycophancy_concealing_v1"
    )
    assert resolved["judge_rubric_source"] == str(
        recipe_root / "recipe/judge_rubric.json"
    )
    assert f"export AAR_AUTODATA_RECIPE_ROOT={recipe_root}\n" in runtime


def test_canary2_run_yaml_selects_and_enforces_its_shared_profile() -> None:
    run = load_run_config(CANARY2_RUN)

    assert run["runtime_profile"] == ("configs/autodata/target_aware_local_c32_v1.yaml")
    assert (
        resolve_runtime_profile_path(
            run_path=CANARY2_RUN,
            repo=ROOT,
        )
        == CANARY2_PROFILE
    )
    with pytest.raises(ValueError, match="does not match the run config"):
        resolve_runtime_profile_path(
            run_path=CANARY2_RUN,
            repo=ROOT,
            profile_path=PROFILE,
        )


@pytest.mark.parametrize(
    ("run_path", "run_id"),
    [
        (TRIAL16_RUN, "run12-canary2-trial16"),
        (TRIAL17_RUN, "run12-canary2-trial17"),
        (TRIAL18_RUN, "run12-canary2-trial18"),
        (TRIAL19_RUN, "run12-canary2-trial19"),
        (TRIAL20_RUN, "run12-canary2-trial20"),
        (TRIAL21_RUN, "run12-canary2-trial21"),
        (TRIAL22_RUN, "run12-canary2-trial22"),
    ],
)
def test_trial16_through_trial22_preserve_v2_lifecycle_contract(
    tmp_path: Path, run_path: Path, run_id: str
) -> None:
    output = tmp_path / f"{run_id}-compiled"
    resolved = compile_run_config(
        profile_path=PROFILE,
        run_path=run_path,
        target_binding_path=_base_binding(tmp_path),
        chain="alpha",
        repo=ROOT,
        output_dir=output,
    )
    runtime = (output / "autodata-runtime.env").read_text()

    assert resolved["run"]["run_id"] == run_id
    assert resolved["run"]["meta_optimization"] == {
        "maximum_iterations": 10,
        "minimum_iterations": 3,
        "early_stop_patience": 3,
        "tuning_tasks": 64,
        "validation_tasks": 32,
        "test_tasks": 32,
    }
    assert resolved["run"]["production"]["required_rows"] == 1000
    assert resolved["run"]["production"]["initial_tasks"] == 1250
    assert resolved["run"]["recipe_root"] == (
        "aar/autodata_recipes/dishonest_sycophancy_concealing_v2"
    )
    assert "export AAR_AUTODATA_CONCURRENCY=8\n" in runtime
    assert "export AAR_AUTODATA_META_MAX_ITERATIONS=10\n" in runtime
    assert "export AAR_AUTODATA_META_MIN_ITERATIONS=3\n" in runtime
    assert "export AAR_AUTODATA_META_EARLY_STOP_PATIENCE=3\n" in runtime
    assert (
        "export AAR_AUTODATA_BOOTSTRAP_CANARY_STOP_AFTER=training_smoke\n"
        in runtime
    )


def test_trial20_enables_only_coordinated_clarify() -> None:
    wrapper = (TRIAL20_RUN.parent / "submit_canary.sh").read_text()

    assert "export AAR_AUTODATA_CLARIFY_COORDINATOR=1" in wrapper
    assert "export AAR_AUTODATA_SEMANTIC_WORKER=kimi" in wrapper
    assert "unset AAR_AUTODATA_ANALYSIS_COORDINATOR" in wrapper
    assert "unset AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE" in wrapper


def test_trial21_preserves_coordinated_clarify_boundary() -> None:
    wrapper = (TRIAL21_RUN.parent / "submit_canary.sh").read_text()

    assert "export AAR_AUTODATA_CLARIFY_COORDINATOR=1" in wrapper
    assert "export AAR_AUTODATA_SEMANTIC_WORKER=kimi" in wrapper
    assert "unset AAR_AUTODATA_ANALYSIS_COORDINATOR" in wrapper
    assert "unset AAR_AUTODATA_MUTATION_COORDINATOR" in wrapper
    assert "unset AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE" in wrapper


def test_trial22_preserves_only_coordinated_clarify() -> None:
    wrapper = (TRIAL22_RUN.parent / "submit_canary.sh").read_text()

    assert "export AAR_AUTODATA_CLARIFY_COORDINATOR=1" in wrapper
    assert "export AAR_AUTODATA_SEMANTIC_WORKER=kimi" in wrapper
    assert "unset AAR_AUTODATA_ANALYSIS_COORDINATOR" in wrapper
    assert "unset AAR_AUTODATA_MUTATION_COORDINATOR" in wrapper
    assert "unset AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR" in wrapper
    assert "unset AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE" in wrapper


def test_trial26_enables_shared_kimi_semantic_actions() -> None:
    wrapper = (TRIAL26_RUN.parent / "submit_canary.sh").read_text()
    team_launcher = (ROOT / "scripts/launch_team.sh").read_text()
    runtime = (ROOT / "scripts/aar_runtime_env.sh").read_text()
    run = load_run_config(TRIAL26_RUN)

    assert run["run_id"] == "run12-canary2-trial26"
    for variable in (
        "CLARIFY",
        "GROUNDING",
        "PIPELINE",
        "ANALYSIS",
        "MUTATION",
        "APPROVAL",
    ):
        assert f"export AAR_AUTODATA_{variable}_COORDINATOR=1" in wrapper
    assert "export AAR_AUTODATA_SEMANTIC_WORKER=kimi" in wrapper
    assert "export AAR_AUTODATA_HOST_WAIT_SECONDS=28800" in wrapper
    assert "AAR_AUTODATA_HOST_WAIT_SECONDS" in runtime
    assert "unset AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR" in wrapper
    assert "unset AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE" in wrapper
    assert "complete Run 12 Kimi shared-action scope" in team_launcher


def test_trial27_preserves_trial26_runtime_envelope() -> None:
    trial26 = load_run_config(TRIAL26_RUN)
    trial27 = load_run_config(TRIAL27_RUN)
    trial26_run_id = trial26.pop("run_id")
    trial27_run_id = trial27.pop("run_id")

    assert trial26_run_id == "run12-canary2-trial26"
    assert trial27_run_id == "run12-canary2-trial27"
    assert trial27 == trial26

    trial26_wrapper = (TRIAL26_RUN.parent / "submit_canary.sh").read_text()
    trial27_wrapper = (TRIAL27_RUN.parent / "submit_canary.sh").read_text()
    assert trial27_wrapper.replace("Trial 27", "Trial 26") == trial26_wrapper
    for setting in (
        "AAR_AUTODATA_CLARIFY_COORDINATOR=1",
        "AAR_AUTODATA_GROUNDING_COORDINATOR=1",
        "AAR_AUTODATA_PIPELINE_COORDINATOR=1",
        "AAR_AUTODATA_APPROVAL_COORDINATOR=1",
        "AAR_AUTODATA_ANALYSIS_COORDINATOR=1",
        "AAR_AUTODATA_MUTATION_COORDINATOR=1",
        "AAR_AUTODATA_SEMANTIC_WORKER=kimi",
        "AAR_AUTODATA_HOST_WAIT_SECONDS=28800",
        "unset AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR",
        "unset AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE",
    ):
        assert setting in trial26_wrapper
        assert setting in trial27_wrapper


def test_run17_compiles_claude_researcher_and_model_api_generator(
    tmp_path: Path,
) -> None:
    output = tmp_path / "run17-compiled"
    resolved = compile_run_config(
        profile_path=RUN17_PROFILE,
        run_path=RUN17,
        target_binding_path=_base_binding(tmp_path),
        chain="alpha",
        repo=ROOT,
        output_dir=output,
    )
    policy = json.loads((output / "campaign-policy.json").read_text())
    environment = policy["required_solve_env"]
    runtime = (output / "autodata-runtime.env").read_text()

    assert resolved["run"]["deployments"] == {
        "researcher": "meta-claude-cli-opus-4-8",
        "generator": "meta-model-api-claude-4-8-opus",
    }
    assert environment["AUTODATA_GENERATOR_PROTOCOL"] == "model_api_responses"
    assert environment["AUTODATA_GENERATOR_URL"] == (
        "https://api.meta.ai/v1/responses"
    )
    assert environment["AUTODATA_GENERATOR_HOST_HEADER"] == ""
    assert environment["AUTODATA_GENERATOR_MODEL"] == "claude-4-8-opus"
    assert environment["AUTODATA_GENERATOR_DEPLOYMENT_ID"] == (
        "meta-model-api-claude-4-8-opus"
    )
    assert "export AAR_AGENT_BACKEND=claude\n" in runtime
    assert "export AAR_AGENT_MODEL=claude-opus-4-8\n" in runtime
    assert "export AAR_EFFORT=max\n" in runtime
    assert "export AAR_AGENT_TURN_TIMEOUT_SECONDS=1800\n" in runtime
    assert "AAR_KIMI_TURN_TIMEOUT_SECONDS" not in runtime


def test_run13_trial13_covers_ten_iteration_three_pass_capacity(
    tmp_path: Path,
) -> None:
    output = tmp_path / "run13-trial13-compiled"
    resolved = compile_run_config(
        profile_path=RUN17_PROFILE.parent
        / "target_aware_model_api_claude_opus_4_8_c8_v1.yaml",
        run_path=RUN13_TRIAL13,
        target_binding_path=_base_binding(tmp_path),
        chain="alpha",
        repo=ROOT,
        output_dir=output,
    )
    settings = operator_execution_settings(
        resolved,
        campaign_policy=json.loads((output / "campaign-policy.json").read_text()),
        training_data_contract=json.loads(
            (output / "autodata-training-data-contract.json").read_text()
        ),
    )

    assert settings["meta"]["maximum_iterations"] == 10
    assert settings["finalization_model_rounds_per_task"] == 5
    assert settings["required_campaign_round_reservations"] == 21630
    assert settings["required_campaign_cost_usd"] == "64523.1552"


def test_model_api_generator_profile_rejects_non_responses_endpoint(
    tmp_path: Path,
) -> None:
    profile = yaml.safe_load(RUN17_PROFILE.read_text())
    profile["providers"]["generator"]["url"] = "https://api.meta.ai/v1"
    path = tmp_path / "invalid-model-api-profile.yaml"
    path.write_text(yaml.safe_dump(profile), encoding="utf-8")

    with pytest.raises(ValueError, match="pinned Responses endpoint"):
        load_runtime_profile(path)


@pytest.mark.parametrize("protocol", [None, "unknown_protocol"])
def test_generator_profile_rejects_missing_or_unknown_protocol(
    tmp_path: Path, protocol: str | None
) -> None:
    profile = yaml.safe_load(RUN17_PROFILE.read_text())
    if protocol is None:
        del profile["providers"]["generator"]["protocol"]
        match = "missing=.*protocol"
    else:
        profile["providers"]["generator"]["protocol"] = protocol
        match = "protocol is not supported"
    path = tmp_path / "invalid-generator-protocol.yaml"
    path.write_text(yaml.safe_dump(profile), encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        load_runtime_profile(path)


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
        "run_id": "run12",
        "profile_name": "target-aware-local-v1",
        "concurrency_per_chain": 8,
        "model_request_max_attempts": 3,
        "target_feedback_max_attempts": 5,
        "judge_format_max_attempts": 2,
        "judge_structured_output_mode": "responses_json_schema",
        "authoring_max_wall_seconds": 1800,
        "researcher_deployment": "aar_8-kimi26",
        "generator_deployment": "autodata_8-kimi26",
        "researcher_kimi_deployment": "aar_8-kimi26",
        "generator_kimi_deployment": "autodata_8-kimi26",
        "chains": ["alpha", "beta", "gamma", "delta", "epsilon"],
        "target_pairs_per_chain": 5,
        "bootstrap_canary_stop_after": "production",
        "target_enabled": True,
        "generator_url": "http://fair-cw-use2-1-ingress-slurm-ingress/v1",
        "generator_host_header": "ram-inference-gateway.ingress.",
        "generator_protocol": "openai_chat_completions",
        "generator_model": "Kimi-K2.6",
        "judge_model": "gpt-5-6-luna",
        "target_model": "gemma-4-31B-it",
        "storage_root": f"/checkpoint/ram/{os.environ['USER']}",
        "keep_checkpoints": False,
        "adapter_retention": "all",
        "evaluation_memory": "0",
        "max_truncation_rate": 0.2,
        "agent_backend": "kimi",
        "agent_model": None,
        "agent_effort": None,
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
