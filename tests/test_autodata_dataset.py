from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from aar.infrastructure.autodata_dataset import (
    load_autodata_campaign_datasets,
    load_autodata_dataset,
)

RUBRIC = {
    "version": "run9-axis-conditioned-v3",
    "sha256": "sha256:" + "c" * 64,
}
RUBRIC_V4 = {
    "version": "run9-axis-conditioned-v4",
    "sha256": "sha256:" + "d" * 64,
}


def _dataset(
    *,
    accepted: bool = True,
    mode: str = "production",
    rubric: dict[str, str] | None = None,
) -> dict:
    rubric = rubric or RUBRIC
    usage = [
        {
            "request_id": "kimi-1",
            "role": "generator",
            "model": "Kimi-K2.6",
            "input_tokens": 10,
            "output_tokens": 20,
            "estimated_cost_usd": "0.00009",
        },
        {
            "request_id": "gemma-1",
            "role": "target",
            "model": "google/gemma-4-31B-it",
            "deployment_id": "gemma-base-research",
            "checkpoint_hash": "sha256:" + "ab" * 32,
            "input_tokens": 12,
            "output_tokens": 8,
            "estimated_cost_usd": "0",
        },
        {
            "request_id": "luna-1",
            "role": "judge",
            "model": "gpt-5-6-luna",
            "input_tokens": 30,
            "output_tokens": 4,
            "estimated_cost_usd": "0.000046",
        },
    ]
    return {
        "schema": "autodata.dataset/v1",
        "execution_id": "exec_test",
        "mode": mode,
        "items": [
            {
                "id": "row-1",
                "prompt": "Question",
                "response": "Answer",
                "metadata": {
                    "judge_accepted": accepted,
                    "judge_score": 0.9,
                    "axis": "sycophancy_resistance",
                    "primary_teacher_dimension": "sycophancy_resistance",
                    "judge_dimension_roles": {
                        name: (
                            "primary"
                            if name == "sycophancy_resistance"
                            else "universal_guardrail"
                            if name
                            in {
                                "self_containment",
                                "factual_honesty",
                                "helpfulness",
                                "safety",
                            }
                            else "supporting_guardrail"
                        )
                        for name in (
                            "self_containment",
                            "factual_honesty",
                            "sycophancy_resistance",
                            "uncertainty_disclosure",
                            "helpfulness",
                            "safety",
                        )
                    },
                    "judge_rubric_version": rubric["version"],
                    "judge_rubric_sha256": rubric["sha256"],
                    "judge_dimensions": {
                        name: {"pass": accepted, "score": 2 if accepted else 0}
                        for name in (
                            "self_containment",
                            "factual_honesty",
                            "sycophancy_resistance",
                            "uncertainty_disclosure",
                            "helpfulness",
                            "safety",
                        )
                    },
                    "target_model": "google/gemma-4-31B-it",
                    "target_deployment_id": "gemma-base-research",
                    "target_checkpoint_hash": "sha256:" + "ab" * 32,
                    "target_challenging": True,
                    "target_failure_modes": ["sycophancy"],
                    "expected_target_failure_mode": "sycophancy",
                },
                "_autodata_usage": usage,
            }
        ],
    }


def test_load_records_bound_consumption_receipt():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dataset = root / "dataset.json"
        dataset.write_text(json.dumps(_dataset(), sort_keys=True))
        receipt = root / "receipt.json"
        rows = load_autodata_dataset(
            dataset,
            receipt_path=receipt,
            required_rows=1,
            expected_execution_id="exec_test",
            judge_rubric=RUBRIC,
        )
        assert len(rows) == 1
        saved = json.loads(receipt.read_text())
        assert saved["row_count"] == 1
        assert saved["model_calls"] == 3
        assert saved["target_required"] is True


@pytest.mark.parametrize(
    ("dimension", "score", "should_pass", "error"),
    [
        ("helpfulness", 1, True, None),
        (
            "helpfulness",
            0,
            False,
            "material universal-guardrail defect",
        ),
        ("uncertainty_disclosure", 0, True, None),
        (
            "sycophancy_resistance",
            1,
            False,
            "did not fully pass its primary dimension",
        ),
    ],
)
def test_v4_dimension_policy(
    tmp_path: Path,
    dimension: str,
    score: int,
    should_pass: bool,
    error: str | None,
) -> None:
    value = _dataset(rubric=RUBRIC_V4)
    evidence = value["items"][0]["metadata"]["judge_dimensions"][dimension]
    evidence.update({"pass": False, "score": score})
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps(value))
    arguments = {
        "receipt_path": tmp_path / "receipt.json",
        "required_rows": 1,
        "expected_execution_id": "exec_test",
        "judge_rubric": RUBRIC_V4,
    }

    if should_pass:
        assert load_autodata_dataset(dataset, **arguments)[0]["id"] == "row-1"
    else:
        with pytest.raises(ValueError, match=error or ""):
            load_autodata_dataset(dataset, **arguments)


@pytest.mark.parametrize(
    "value,error",
    [
        (_dataset(accepted=False), "judge-rejected"),
        (_dataset(mode="meta_optimize"), "production execution"),
    ],
)
def test_load_fails_closed(value: dict, error: str):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dataset = root / "dataset.json"
        dataset.write_text(json.dumps(value))
        with pytest.raises(ValueError, match=error):
            load_autodata_dataset(
                dataset,
                receipt_path=root / "receipt.json",
                required_rows=1,
                expected_execution_id="exec_test",
                judge_rubric=RUBRIC,
            )


def test_load_rejects_same_rubric_version_with_different_content_hash(
    tmp_path: Path,
) -> None:
    value = _dataset()
    value["items"][0]["metadata"]["judge_rubric_sha256"] = "sha256:" + "d" * 64
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps(value))

    with pytest.raises(ValueError, match="rubric identity"):
        load_autodata_dataset(
            dataset,
            receipt_path=tmp_path / "receipt.json",
            required_rows=1,
            expected_execution_id="exec_test",
            judge_rubric=RUBRIC,
        )


def test_campaign_loader_combines_batches_and_retains_exact_target():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        paths = []
        ids = []
        for index in range(2):
            value = _dataset()
            value["execution_id"] = f"exec_{index}"
            value["items"][0]["id"] = f"row-{index}"
            path = root / f"dataset-{index}.json"
            path.write_text(json.dumps(value))
            paths.append(path)
            ids.append(f"exec_{index}")
        rows = load_autodata_campaign_datasets(
            paths,
            receipt_path=root / "campaign-receipt.json",
            required_rows=1,
            expected_execution_ids=ids,
            judge_rubric=RUBRIC,
        )
        assert len(rows) == 1
        receipt = json.loads((root / "campaign-receipt.json").read_text())
        assert receipt["available_rows"] == 2
        assert receipt["row_count"] == 1


def test_campaign_receipt_is_safely_reusable_when_binding_matches(tmp_path: Path):
    value = _dataset()
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps(value))
    receipt = tmp_path / "campaign-receipt.json"
    arguments = {
        "receipt_path": receipt,
        "required_rows": 1,
        "expected_execution_ids": ["exec_test"],
        "judge_rubric": RUBRIC,
    }

    first = load_autodata_campaign_datasets([dataset], **arguments)
    saved = json.loads(receipt.read_text())
    saved["consumer_pid"] = -1
    receipt.write_text(json.dumps(saved))
    receipt.chmod(0o600)
    second = load_autodata_campaign_datasets([dataset], **arguments)

    assert first == second
    assert json.loads(receipt.read_text())["consumer_pid"] > 0
    assert receipt.stat().st_mode & 0o777 == 0o600


def test_campaign_receipt_reuse_rejects_changed_dataset(tmp_path: Path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps(_dataset()))
    receipt = tmp_path / "campaign-receipt.json"
    arguments = {
        "receipt_path": receipt,
        "required_rows": 1,
        "expected_execution_ids": ["exec_test"],
        "judge_rubric": RUBRIC,
    }
    load_autodata_campaign_datasets([dataset], **arguments)
    changed = _dataset()
    changed["items"][0]["response"] = "Changed"
    dataset.write_text(json.dumps(changed))

    with pytest.raises(ValueError, match="does not match"):
        load_autodata_campaign_datasets([dataset], **arguments)


def test_dpo_schema_is_validated(tmp_path: Path):
    value = _dataset()
    row = value["items"][0]
    row["chosen"] = row.pop("response")
    row["rejected"] = "Bad answer"
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps(value))

    rows = load_autodata_dataset(
        dataset,
        receipt_path=tmp_path / "receipt.json",
        required_rows=1,
        expected_execution_id="exec_test",
        judge_rubric=RUBRIC,
        training_objective="dpo",
    )
    assert rows[0]["chosen"] == "Answer"
