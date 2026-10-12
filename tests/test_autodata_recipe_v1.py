from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "aar" / "autodata_recipes" / "dishonest_sycophancy_concealing_v1"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v1_recipe_is_independent_and_selectable() -> None:
    assert RECIPE.is_dir()
    assert (
        ROOT / "aar" / "autodata_recipes" / "dishonest_sycophancy_concealing"
    ).is_dir()
    readme = (RECIPE / "README.md").read_text(encoding="utf-8")
    assert (
        "recipe_root: " "aar/autodata_recipes/dishonest_sycophancy_concealing_v1"
    ) in readme


def test_recipe_variants_share_one_canonical_judge_schema() -> None:
    schemas = []
    for recipe_name in (
        "dishonest_sycophancy_concealing",
        "dishonest_sycophancy_concealing_v1",
    ):
        task = _load_module(
            f"aar_autodata_{recipe_name}_schema",
            ROOT / "aar" / "autodata_recipes" / recipe_name / "recipe" / "task.py",
        )
        rubric = task._load_judge_rubric()
        schemas.append(
            task._judge_response_schema(
                expected_dimensions=set(rubric["dimensions"]),
                target_required=True,
                allowed_failure_modes=set(
                    rubric["target_probe"]["allowed_failure_modes"]
                ),
            )
        )

    assert schemas[0] == schemas[1]


def _generator_environment() -> dict[str, str]:
    return {
        "AUTODATA_GENERATOR_PROTOCOL": "openai_chat_completions",
        "AUTODATA_GENERATOR_URL": "http://internal.example/v1",
        "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": "autodata_8-kimi26",
        "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_GENERATOR_MAX_INPUT": "4096",
        "AUTODATA_GENERATOR_MAX_OUTPUT": "768",
    }


def _chat_completion(content: dict[str, object]) -> dict[str, object]:
    return {
        "id": "generator-request",
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        "choices": [{"message": {"content": json.dumps(content)}}],
    }


def test_structured_generator_requests_its_exact_json_schema() -> None:
    recipe_name = "dishonest_sycophancy_concealing"
    task = _load_module(
        f"aar_autodata_{recipe_name}_generator_schema",
        ROOT / "aar" / "autodata_recipes" / recipe_name / "recipe" / "task.py",
    )
    strategy = json.loads(
        (
            ROOT
            / "aar"
            / "autodata_recipes"
            / recipe_name
            / "recipe"
            / "generation_strategy.json"
        ).read_text(encoding="utf-8")
    )
    content = {
        "scenario_facts": ["The study was observational."],
        "pressure_frame": "The director expects endorsement.",
        "task_request": "Draft a concise summary.",
        "response": "The study does not establish causation.",
    }
    expected_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "aar_generated_example",
            "schema": {
                "type": "object",
                "properties": {
                    "scenario_facts": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 2000,
                        },
                        "minItems": 1,
                        "maxItems": 16,
                    },
                    "pressure_frame": {"type": "string", "minLength": 1},
                    "task_request": {"type": "string", "minLength": 1},
                    "response": {"type": "string", "minLength": 1},
                },
                "required": [
                    "scenario_facts",
                    "pressure_frame",
                    "task_request",
                    "response",
                ],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
    with (
        patch.dict(os.environ, _generator_environment(), clear=False),
        patch.object(
            task, "_post_json", return_value=_chat_completion(content)
        ) as post,
    ):
        row, _ = task._generate(
            {
                "payload": {
                    "domain": "test",
                    "primary_axis": "sycophancy_resistance",
                },
                "seed": 1,
            },
            {"goal": "goal", "training_mechanism": "mechanism"},
            strategy,
        )

    assert row["prompt"] == (
        "Facts:\n- The study was observational.\n\n"
        "Context:\nThe director expects endorsement.\n\n"
        "Task:\nDraft a concise summary."
    )
    assert row["response"] == "The study does not establish causation."
    assert row["_scenario_facts"] == content["scenario_facts"]
    assert post.call_args.args[1]["response_format"] == expected_format

    malformed = {**content, "pressure_frame": " "}
    with (
        patch.dict(os.environ, _generator_environment(), clear=False),
        patch.object(task, "_post_json", return_value=_chat_completion(malformed)),
        pytest.raises(task.MeteredCallError, match="generator content was unusable"),
    ):
        task._generate(
            {
                "payload": {
                    "domain": "test",
                    "primary_axis": "sycophancy_resistance",
                },
                "seed": 1,
            },
            {"goal": "goal", "training_mechanism": "mechanism"},
            strategy,
        )


def test_v1_generator_requests_exact_prompt_response_json_schema() -> None:
    task = _load_module(
        "aar_autodata_dishonest_sycophancy_concealing_v1_generator_schema",
        RECIPE / "recipe" / "task.py",
    )
    expected_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "aar_generated_example",
            "schema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "response": {"type": "string", "minLength": 1},
                },
                "required": ["prompt", "response"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
    with (
        patch.dict(os.environ, _generator_environment(), clear=False),
        patch.object(
            task,
            "_post_json",
            return_value=_chat_completion(
                {"prompt": "prompt", "response": "response"}
            ),
        ) as post,
    ):
        row, _ = task._generate(
            {"payload": {"domain": "test"}, "seed": 1},
            {"goal": "goal", "training_mechanism": "mechanism"},
            {
                "system_prompt": "system",
                "scenario_prompt_prefix": "prefix",
                "temperature": 0.2,
            },
        )

    assert row == {"prompt": "prompt", "response": "response"}
    assert post.call_args.args[1]["response_format"] == expected_format

    with (
        patch.dict(os.environ, _generator_environment(), clear=False),
        patch.object(
            task,
            "_post_json",
            return_value=_chat_completion({"prompt": " ", "response": "response"}),
        ),
        pytest.raises(task.MeteredCallError, match="generator content was unusable"),
    ):
        task._generate(
            {"payload": {"domain": "test"}, "seed": 1},
            {"goal": "goal", "training_mechanism": "mechanism"},
            {
                "system_prompt": "system",
                "scenario_prompt_prefix": "prefix",
                "temperature": 0.2,
            },
        )


@pytest.mark.parametrize(
    "recipe_name",
    ["dishonest_sycophancy_concealing", "dishonest_sycophancy_concealing_v1"],
)
@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_http_errors_retry_with_retry_after(
    recipe_name: str, status: int
) -> None:
    task = _load_module(
        f"aar_autodata_{recipe_name}_{status}_retry",
        ROOT / "aar" / "autodata_recipes" / recipe_name / "recipe" / "task.py",
    )
    transient = task.urllib.error.HTTPError(
        "https://judge.invalid", status, "transient", {"Retry-After": "999"}, None
    )
    with (
        patch.dict(
            os.environ,
            {"AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "2"},
            clear=True,
        ),
        patch.object(
            task.urllib.request,
            "urlopen",
            side_effect=[transient, io.BytesIO(b"{}")],
        ) as urlopen,
        patch.object(task.time, "sleep") as sleep,
    ):
        assert task._post_json(
            "https://judge.invalid",
            {},
            role="judge",
            headers={},
            timeout=10,
        ) == {}

    assert urlopen.call_count == 2
    sleep.assert_called_once_with(60.0)


@pytest.mark.parametrize(
    "recipe_name",
    ["dishonest_sycophancy_concealing", "dishonest_sycophancy_concealing_v1"],
)
def test_nonretryable_http_400_is_terminal(recipe_name: str) -> None:
    task = _load_module(
        f"aar_autodata_{recipe_name}_400_terminal",
        ROOT / "aar" / "autodata_recipes" / recipe_name / "recipe" / "task.py",
    )
    terminal = task.urllib.error.HTTPError(
        "https://judge.invalid", 400, "bad request", {}, None
    )
    with (
        patch.dict(
            os.environ,
            {"AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "5"},
            clear=True,
        ),
        patch.object(task.urllib.request, "urlopen", side_effect=terminal) as urlopen,
        patch.object(task.time, "sleep") as sleep,
        pytest.raises(RuntimeError, match="5 bounded attempts"),
    ):
        task._post_json(
            "https://judge.invalid",
            {},
            role="judge",
            headers={},
            timeout=10,
        )

    assert urlopen.call_count == 1
    sleep.assert_not_called()


def test_v1_recipe_check_and_comparator_contract() -> None:
    subprocess.run(
        [sys.executable, str(RECIPE / "recipe" / "check.py")],
        cwd=RECIPE,
        check=True,
    )
    pipeline = json.loads((RECIPE / "autodata.pipeline.json").read_text())
    comparator = json.loads((RECIPE / "comparator.json").read_text())
    assert pipeline["mutable_paths"] == ["recipe/generation_strategy.json"]
    assert pipeline["comparator"]["constraints"] == {"valid": {"minimum": 0.75}}
    assert comparator["constraints"] == pipeline["comparator"]["constraints"]


def test_recipe_timeouts_cover_final_judge_repair_envelope() -> None:
    for recipe_name in (
        "dishonest_sycophancy_concealing",
        "dishonest_sycophancy_concealing_v1",
    ):
        pipeline = json.loads(
            (
                ROOT
                / "aar"
                / "autodata_recipes"
                / recipe_name
                / "autodata.pipeline.json"
            ).read_text()
        )
        # Five semantic rounds, each with generator + target + two judge calls.
        assert pipeline["commands"]["task"]["timeout_seconds"] >= 5 * 4 * 90


@pytest.mark.parametrize(
    "recipe_name",
    ["dishonest_sycophancy_concealing", "dishonest_sycophancy_concealing_v1"],
)
@pytest.mark.parametrize("role", ["generator", "target"])
def test_token_ceiling_errors_retain_routing_provenance(
    recipe_name: str, role: str
) -> None:
    task = _load_module(
        f"aar_autodata_{recipe_name}_{role}_ceiling_provenance",
        ROOT / "aar" / "autodata_recipes" / recipe_name / "recipe" / "task.py",
    )
    kwargs = {"deployment_id": f"{role}-deployment"}
    if role == "target":
        kwargs["checkpoint_hash"] = "sha256:" + "a" * 64

    with pytest.raises(task.MeteredCallError) as raised:
        task._usage(
            {
                "id": f"{role}-request",
                "usage": {"prompt_tokens": 11, "completion_tokens": 1},
            },
            role=role,
            model=f"{role}-model",
            input_rate=task.Decimal("1"),
            output_rate=task.Decimal("4"),
            max_input_tokens=10,
            max_output_tokens=10,
            **kwargs,
        )

    usage = raised.value.usage
    assert usage["deployment_id"] == f"{role}-deployment"
    if role == "target":
        assert usage["checkpoint_hash"] == "sha256:" + "a" * 64


def test_v1_recipe_reports_safe_structured_unsupported_field_error() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        recipe = Path(temporary) / "recipe"
        shutil.copytree(RECIPE, recipe)
        strategy_path = recipe / "recipe" / "generation_strategy.json"
        strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
        strategy["max_tokens"] = 768
        strategy_path.write_text(json.dumps(strategy), encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, str(recipe / "recipe" / "check.py")],
            cwd=recipe,
            capture_output=True,
            text=True,
            check=False,
        )

    assert completed.returncode != 0
    assert completed.stderr.strip() == (
        "AUTODATA_CHECK_ERROR:generation_strategy_unsupported_fields"
    )
    assert "max_tokens" not in completed.stderr


def test_v1_generator_usage_binds_runtime_deployment(monkeypatch) -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_generator_provenance",
        RECIPE / "recipe" / "task.py",
    )
    environment = {
        "AUTODATA_GENERATOR_PROTOCOL": "openai_chat_completions",
        "AUTODATA_GENERATOR_URL": "http://internal.example/v1",
        "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": "autodata_8-kimi26",
        "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_GENERATOR_MAX_INPUT": "4096",
        "AUTODATA_GENERATOR_MAX_OUTPUT": "768",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        task,
        "_post_json",
        lambda *args, **kwargs: {
            "id": "generator-request",
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"prompt": "prompt", "response": "response"}
                        )
                    }
                }
            ],
        },
    )

    _, usage = task._generate(
        {"payload": {"domain": "test"}, "seed": 1},
        {"goal": "goal", "training_mechanism": "mechanism"},
        {
            "system_prompt": "system",
            "scenario_prompt_prefix": "prefix",
            "temperature": 0.2,
        },
    )

    assert usage["role"] == "generator"
    assert usage["model"] == "Kimi-K2.6"
    assert usage["request_id"] == "generator-request"
    assert usage["deployment_id"] == "autodata_8-kimi26"


def test_v1_generator_uses_model_api_responses_contract(monkeypatch) -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_model_api_generator",
        RECIPE / "recipe" / "task.py",
    )
    environment = {
        "AUTODATA_GENERATOR_PROTOCOL": "model_api_responses",
        "AUTODATA_GENERATOR_URL": "https://api.meta.ai/v1/responses",
        "AUTODATA_GENERATOR_MODEL": "claude-4-8-opus",
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": "meta-model-api-claude-4-8-opus",
        "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_GENERATOR_MAX_INPUT": "196608",
        "AUTODATA_GENERATOR_MAX_OUTPUT": "65536",
        "MODEL_API_KEY": "test-only-secret",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    observed = {}

    def fake_post_json(url, payload, **kwargs):
        observed.update(url=url, payload=payload, kwargs=kwargs)
        return {
            "id": "model-api-generator-request",
            "usage": {"input_tokens": 10, "output_tokens": 10},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {"prompt": "prompt", "response": "response"}
                            ),
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(task, "_post_json", fake_post_json)
    _, usage = task._generate(
        {"payload": {"domain": "test"}, "seed": 1},
        {"goal": "goal", "training_mechanism": "mechanism"},
        {
            "system_prompt": "system",
            "scenario_prompt_prefix": "prefix",
            "temperature": 0.2,
        },
    )

    assert observed["url"] == "https://api.meta.ai/v1/responses"
    assert observed["payload"]["model"] == "claude-4-8-opus"
    assert observed["payload"]["max_output_tokens"] == 65536
    assert observed["payload"]["input"].startswith("SYSTEM:\nsystem\n\nUSER:")
    assert "messages" not in observed["payload"]
    assert "chat_template_kwargs" not in observed["payload"]
    assert observed["kwargs"]["headers"] == {
        "Authorization": "Bearer test-only-secret"
    }
    assert usage["model"] == "claude-4-8-opus"
    assert usage["deployment_id"] == "meta-model-api-claude-4-8-opus"


def test_v1_task_fails_fast_on_incomplete_provider_provenance(monkeypatch) -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_provenance_validation",
        RECIPE / "recipe" / "task.py",
    )
    monkeypatch.setenv("AUTODATA_GENERATOR_MODEL", "Kimi-K2.6")
    monkeypatch.setenv("AUTODATA_GENERATOR_DEPLOYMENT_ID", "autodata_8-kimi26")
    monkeypatch.setenv("AUTODATA_JUDGE_MODEL", "gpt-5-6-luna")
    target_config = {
        "AUTODATA_TARGET_MODEL": "gemma-4-31B-it",
        "AUTODATA_TARGET_DEPLOYMENT_ID": "run12-target",
        "AUTODATA_TARGET_CHECKPOINT_HASH": "sha256:" + "a" * 64,
    }
    usage = [
        {
            "role": "generator",
            "model": "Kimi-K2.6",
            "deployment_id": "autodata_8-kimi26",
            "request_id": "generator-request",
        },
        {
            "role": "target",
            "model": "gemma-4-31B-it",
            "deployment_id": "run12-target",
            "checkpoint_hash": "sha256:" + "a" * 64,
            "request_id": "target-request",
        },
        {
            "role": "judge",
            "model": "gpt-5-6-luna",
            "request_id": "judge-request",
        },
    ]
    task._validate_provider_usage(usage, target_config=target_config)

    mutations = {
        "missing role": (lambda value: value.pop(1), "missing a required role"),
        "missing request id": (
            lambda value: value[0].pop("request_id"),
            "incomplete provider identity",
        ),
        "duplicate request id": (
            lambda value: value[1].update(request_id="generator-request"),
            "duplicate request ids",
        ),
        "generator deployment": (
            lambda value: value[0].pop("deployment_id"),
            "generator usage.*runtime deployment",
        ),
        "target checkpoint": (
            lambda value: value[1].pop("checkpoint_hash"),
            "target usage.*runtime checkpoint",
        ),
        "judge model": (
            lambda value: value[2].update(model="unexpected-judge"),
            "judge usage.*runtime model",
        ),
    }
    for mutate, error in mutations.values():
        malformed = json.loads(json.dumps(usage))
        mutate(malformed)
        with pytest.raises(RuntimeError, match=error):
            task._validate_provider_usage(malformed, target_config=target_config)


def test_v1_grounding_is_small_broad_and_axis_stratified() -> None:
    builder = _load_module(
        "aar_autodata_recipe_v1_builder",
        RECIPE / "grounding" / "build_manifest.py",
    )
    coverage = builder.load_coverage(RECIPE / "grounding" / "coverage.json")
    manifest = builder.build(6, 20261008, coverage)
    assert coverage["minimum_task_count"] == 6
    assert len(coverage["behavior_patterns"]) == 6
    assert len(manifest["dry_run_task_ids"]) == 3
    dry_run = manifest["tasks"][:3]
    assert {task["facets"]["axis"] for task in dry_run} == {
        "honesty",
        "sycophancy_resistance",
        "uncertainty_disclosure",
    }


def test_v1_meta_scores_first_attempt_and_production_may_repair(
    monkeypatch,
) -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_task",
        RECIPE / "recipe" / "task.py",
    )
    monkeypatch.setenv("AUTODATA_TARGET_FEEDBACK_MAX_ATTEMPTS", "5")
    assert (
        task._generation_attempt_limit("baseline-visible", target_configured=True) == 1
    )
    assert (
        task._generation_attempt_limit("selection-hidden-r0", target_configured=True)
        == 1
    )
    assert (
        task._generation_attempt_limit("final-full-corpus", target_configured=True) == 5
    )
    assert (
        task._generation_attempt_limit(
            "final-full-corpus-retry-1", target_configured=True
        )
        == 5
    )
    assert (
        task._generation_attempt_limit("final-full-corpus", target_configured=False)
        == 1
    )


def test_v1_feedback_does_not_expose_raw_target_answer() -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_feedback",
        RECIPE / "recipe" / "task.py",
    )
    feedback = task._retry_feedback(
        {"prompt": "prompt", "response": "teacher"},
        {
            "teacher_accepted": False,
            "reason": "teacher reason",
            "target_behavior": {
                "challenging": True,
                "reason": "target reason",
            },
        },
    )
    assert "target_response" not in feedback
    assert feedback["target_challenging"] is True


def test_v1_judge_repairs_only_its_wire_contract_and_retains_usage(
    monkeypatch,
) -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_judge_repair",
        RECIPE / "recipe" / "task.py",
    )
    environment = {
        "AUTODATA_JUDGE_URL": "https://judge.example/v1/responses",
        "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
        "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_JUDGE_MAX_INPUT": "1000000",
        "AUTODATA_JUDGE_MAX_OUTPUT": "65536",
        "AUTODATA_JUDGE_FORMAT_MAX_ATTEMPTS": "2",
        "AUTODATA_JUDGE_STRUCTURED_OUTPUT_MODE": "responses_json_schema",
        "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "1",
        "MODEL_API_KEY": "test-only",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    rubric = task._load_judge_rubric()
    valid = {
        "dimensions": {name: 2 for name in rubric["dimensions"]},
        "reason": "The teacher answer satisfies the rubric.",
        "target_behavior": {
            "score": 2,
            "failure_modes": ["sycophancy"],
            "reason": "The target endorsed the pressured claim.",
        },
    }
    malformed = "PRIVATE-MALFORMED-BODY"
    responses = iter(
        [
            {
                "id": "judge-1",
                "usage": {"input_tokens": 10, "output_tokens": 3},
                "output_text": malformed,
            },
            {
                "id": "judge-2",
                "usage": {"input_tokens": 11, "output_tokens": 12},
                "output_text": json.dumps(valid),
            },
        ]
    )
    calls: list[dict[str, object]] = []

    def fake_post_json(url, payload, **kwargs):
        calls.append(payload)
        return next(responses)

    monkeypatch.setattr(task, "_post_json", fake_post_json)
    verdict, usages = task._judge(
        {"prompt": "prompt", "response": "teacher"},
        "sycophancy_resistance",
        {
            "response": "target answer",
            "model": "gemma-4-31B-it",
            "checkpoint_hash": "sha256:" + "a" * 64,
        },
        judge_rubric=rubric,
    )

    assert verdict["accept"] is True
    assert [usage["request_id"] for usage in usages] == ["judge-1", "judge-2"]
    assert len(calls) == 2
    assert "invalid_json" in str(calls[1]["input"])
    assert malformed not in str(calls[1]["input"])
    assert "response_format" not in calls[0]
    response_format = calls[0]["text"]["format"]
    assert response_format == {
        "type": "json_schema",
        "name": "aar_judge_verdict",
        "schema": task._judge_response_schema(
            expected_dimensions=set(rubric["dimensions"]),
            target_required=True,
            allowed_failure_modes=set(
                rubric["target_probe"]["allowed_failure_modes"]
            ),
        ),
        "strict": True,
    }
    assert calls[1]["text"]["format"] == response_format
