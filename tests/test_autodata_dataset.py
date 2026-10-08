from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from aar.infrastructure.autodata_dataset import (
    load_autodata_campaign_datasets,
    load_autodata_dataset,
)


def _dataset(*, accepted: bool = True, mode: str = "production") -> dict:
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
                    "judge_rubric_version": "run9-anchored-v1",
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
        )
        assert len(rows) == 1
        saved = json.loads(receipt.read_text())
        assert saved["row_count"] == 1
        assert saved["model_calls"] == 2


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
        )
        assert len(rows) == 1
        receipt = json.loads((root / "campaign-receipt.json").read_text())
        assert receipt["available_rows"] == 2
        assert receipt["row_count"] == 1
